from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.models.ai_request import AIRequest
from app.models.audit_log import AuditLog
from app.models.system import System
from app.models.workflow_execution import WorkflowExecution


def compute_weighted_success_rate(systems) -> float | None:
    """
    Weighted mean of per-system success_rate_pct, weighted by total_executions.
    Systems with total_executions == 0 are excluded from both numerator and
    denominator so idle systems can't drag the rate to zero.
    Returns None when no system has executed anything.
    """
    weighted_num = sum(
        s.success_rate_pct * s.total_executions
        for s in systems
        if s.total_executions > 0
    )
    weighted_den = sum(
        s.total_executions
        for s in systems
        if s.total_executions > 0
    )
    if not weighted_den:
        return None
    return round(weighted_num / weighted_den, 1)


class SystemService:
    def __init__(self, db: Session):
        self.db = db

    def get_by_slug(self, slug: str) -> Optional[System]:
        return self.db.query(System).filter(System.slug == slug).first()

    def list_active(self) -> List[System]:
        return self.db.query(System).filter(System.is_active == True).order_by(System.name).all()

    def get_system_stats(self, system_id: UUID, days: int = 7) -> dict:
        # `days` retained for signature compatibility but success rate is all-time
        # so idle systems don't mis-report 0% when the recent window happens to be empty.
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        total = self.db.query(WorkflowExecution).filter(
            WorkflowExecution.system_id == system_id
        ).count()
        success = self.db.query(WorkflowExecution).filter(
            WorkflowExecution.system_id == system_id,
            WorkflowExecution.status == "success",
        ).count()
        failed = self.db.query(WorkflowExecution).filter(
            WorkflowExecution.system_id == system_id,
            WorkflowExecution.status == "failed",
        ).count()
        period_total = success + failed

        avg_dur = self.db.query(func.avg(WorkflowExecution.duration_seconds)).filter(
            WorkflowExecution.system_id == system_id,
        ).scalar() or 0.0

        errors_today = self.db.query(AuditLog).filter(
            AuditLog.system_id == system_id,
            AuditLog.level == "ERROR",
            AuditLog.created_at >= today_start,
        ).count()

        ai_cost = self.db.query(func.sum(AIRequest.cost_usd)).filter(
            AIRequest.system_id == system_id,
            AIRequest.created_at >= today_start,
        ).scalar() or 0.0

        last_exec = self.db.query(WorkflowExecution.started_at).filter(
            WorkflowExecution.system_id == system_id
        ).order_by(WorkflowExecution.started_at.desc()).first()

        last_error = self.db.query(WorkflowExecution.error_message).filter(
            WorkflowExecution.system_id == system_id,
            WorkflowExecution.status == "failed",
            WorkflowExecution.resolved.is_(False),
        ).order_by(WorkflowExecution.started_at.desc()).first()

        return {
            "total_executions": total,
            "success_count": success,
            "failure_count": failed,
            "success_rate_pct": round(success / period_total * 100, 1) if period_total > 0 else 0.0,
            "avg_duration_seconds": round(float(avg_dur), 1),
            "errors_today": errors_today,
            "ai_cost_today_usd": round(float(ai_cost), 4),
            "last_run_at": last_exec[0].isoformat() if last_exec and last_exec[0] else None,
            "last_error": last_error[0] if last_error else None,
        }

    def get_activity(self, system_id: UUID, limit: int = 12) -> List[dict]:
        since = datetime.utcnow() - timedelta(days=3)
        events: List[dict] = []

        execs = self.db.query(WorkflowExecution).filter(
            WorkflowExecution.system_id == system_id,
            WorkflowExecution.started_at >= since,
        ).order_by(WorkflowExecution.started_at.desc()).limit(15).all()
        for ex in execs:
            status = ex.status or "unknown"
            if status == "failed" and ex.error_message:
                detail = ex.error_message[:120]
            elif ex.duration_seconds:
                detail = f"Completed in {ex.duration_seconds:.1f}s"
            else:
                detail = None
            events.append({
                "type": "workflow",
                "title": ex.workflow_name or ex.workflow_id or "Workflow",
                "detail": detail,
                "timestamp": ex.started_at,
                "status": status,
            })

        ai_items = self.db.query(AIRequest).filter(
            AIRequest.system_id == system_id,
            AIRequest.created_at >= since,
        ).order_by(AIRequest.created_at.desc()).limit(8).all()
        for ai in ai_items:
            conf = f"{ai.confidence_score * 100:.0f}%" if ai.confidence_score else ""
            events.append({
                "type": "ai",
                "title": f"AI {(ai.request_type or 'decision').replace('_', ' ')}",
                "detail": f"Confidence {conf}" if conf else None,
                "timestamp": ai.created_at,
                "status": ai.status,
            })

        logs = self.db.query(AuditLog).filter(
            AuditLog.system_id == system_id,
            AuditLog.created_at >= since,
            AuditLog.level.in_(["WARNING", "ERROR"]),
        ).order_by(AuditLog.created_at.desc()).limit(5).all()
        for log in logs:
            events.append({
                "type": "event",
                "title": log.message[:80] if log.message else "System event",
                "detail": log.source,
                "timestamp": log.created_at,
                "status": "error" if log.level == "ERROR" else "warning",
            })

        events.sort(key=lambda e: e["timestamp"] or datetime.min, reverse=True)
        return [
            {**e, "timestamp": e["timestamp"].isoformat() if e["timestamp"] else None}
            for e in events[:limit]
        ]

    def get_cross_system_overview(self) -> dict:
        systems = self.list_active()
        since = datetime.utcnow() - timedelta(days=7)
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        total_executions = self.db.query(WorkflowExecution).filter(
            WorkflowExecution.started_at >= since
        ).count()
        total_failures = self.db.query(WorkflowExecution).filter(
            WorkflowExecution.status == "failed",
            WorkflowExecution.started_at >= since,
        ).count()
        errors_today = self.db.query(AuditLog).filter(
            AuditLog.level == "ERROR",
            AuditLog.created_at >= today_start,
        ).count()
        ai_cost_today = self.db.query(func.sum(AIRequest.cost_usd)).filter(
            AIRequest.created_at >= today_start
        ).scalar() or 0.0

        per_system = []
        for sys in systems:
            stats = self.get_system_stats(sys.id)
            per_system.append({
                "slug": sys.slug,
                "name": sys.name,
                "is_active": sys.is_active,
                **stats,
            })

        # Build lightweight proxies so compute_weighted_success_rate can read
        # .success_rate_pct and .total_executions from the same per_system dicts
        # that the frontend receives — single source of truth for the aggregate.
        class _DictProxy:
            __slots__ = ("success_rate_pct", "total_executions")

            def __init__(self, d):
                self.success_rate_pct = d["success_rate_pct"]
                self.total_executions = d["total_executions"]

        proxies = [_DictProxy(s) for s in per_system]

        return {
            "system_count": len(systems),
            "total_executions_7d": total_executions,
            "total_failures_7d": total_failures,
            "global_success_rate_pct": compute_weighted_success_rate(proxies),
            "errors_today": errors_today,
            "ai_cost_today_usd": round(float(ai_cost_today), 4),
            "systems": per_system,
        }
