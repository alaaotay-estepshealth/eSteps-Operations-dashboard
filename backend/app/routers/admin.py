from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from sqlalchemy import text

from app.auth import get_current_user, require_admin, require_operator
from app.database import get_db, get_leads_db
from app.config import settings
from app.models.ai_request import AIRequest
from app.models.audit_log import AuditLog
from app.models.workflow_execution import WorkflowExecution
from app.models.user import User
from app.schemas.responses import (
    ActivityEvent, AIDecision, AIStats, AlertItem, ConfidenceBucket, AITypeBreakdown,
    DashboardMetrics, DailyExecutionPoint, LeadRow, LogEntry, LogStats,
    PipelineFunnelStep, PriorityCount, ResearchAreaStats, ReviewItem,
    ReviewResolution, SystemHealthDot, WorkflowStatusDetail, WorkflowSummary,
)

router = APIRouter(prefix="/admin", tags=["admin"])

PRIORITY_COLORS = {
    "Priority_A": "#2ECC71",
    "Priority_B": "#f59e0b",
    "Priority_C": "#6b7280",
    "Below_ICP": "#ef4444",
}


# ─── Dashboard Overview Metrics ──────────────────────────────────────────────

@router.get("/dashboard/metrics", response_model=DashboardMetrics)
def get_dashboard_metrics(
    db: Session = Depends(get_db),
    leads_db: Session = Depends(get_leads_db),
    _: User = Depends(get_current_user),
):
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # ── Leads (from leads source DB) ─────────────────────────────────────
    _lq = lambda sql, params=None: leads_db.execute(text(sql), params or {}).scalar() or 0

    leads_this_week = _lq("SELECT COUNT(*) FROM leads WHERE created_at >= :d", {"d": week_ago})
    leads_prev_week = _lq(
        "SELECT COUNT(*) FROM leads WHERE created_at >= :a AND created_at < :b",
        {"a": two_weeks_ago, "b": week_ago},
    )

    # ── Avg processing time ──────────────────────────────────────────────
    avg_time_raw = leads_db.execute(text(
        "SELECT AVG(EXTRACT(EPOCH FROM (updated_at - created_at)) / 60) "
        "FROM leads WHERE updated_at IS NOT NULL AND touch_number > 0 AND created_at >= :d"
    ), {"d": week_ago}).scalar()
    avg_time = round(float(avg_time_raw), 1) if avg_time_raw else 3.8

    # ── Hours saved (baseline 8 min per lead) ────────────────────────────
    leads_processed = _lq(
        "SELECT COUNT(*) FROM leads WHERE touch_number > 0 AND created_at >= :d",
        {"d": week_ago},
    )
    hours_saved = round(leads_processed * (8.0 - avg_time) / 60, 1) if avg_time < 8 else 0.0

    leads_processed_prev = _lq(
        "SELECT COUNT(*) FROM leads WHERE touch_number > 0 AND created_at >= :a AND created_at < :b",
        {"a": two_weeks_ago, "b": week_ago},
    )
    avg_time_prev_raw = leads_db.execute(text(
        "SELECT AVG(EXTRACT(EPOCH FROM (updated_at - created_at)) / 60) "
        "FROM leads WHERE updated_at IS NOT NULL AND touch_number > 0 "
        "AND created_at >= :a AND created_at < :b"
    ), {"a": two_weeks_ago, "b": week_ago}).scalar()
    avg_time_prev = float(avg_time_prev_raw) if avg_time_prev_raw else 3.8
    hours_saved_prev = round(leads_processed_prev * (8.0 - avg_time_prev) / 60, 1)

    # ── Automation rate (leads with email sent = automated) ──────────────
    total_leads = _lq("SELECT COUNT(*) FROM leads")
    auto_leads = _lq("SELECT COUNT(*) FROM leads WHERE email1_sent_at IS NOT NULL")
    automation_rate = round(auto_leads / total_leads * 100, 1) if total_leads > 0 else 0.0
    auto_leads_prev = _lq(
        "SELECT COUNT(*) FROM leads WHERE email1_sent_at IS NOT NULL AND created_at < :d",
        {"d": week_ago},
    )
    total_prev = _lq("SELECT COUNT(*) FROM leads WHERE created_at < :d", {"d": week_ago})
    auto_rate_prev = round(auto_leads_prev / total_prev * 100, 1) if total_prev > 0 else 0.0

    # ── AI accuracy (from ops DB) ────────────────────────────────────────
    verified = db.query(AIRequest).filter(AIRequest.human_verified == True).count()
    correct = db.query(AIRequest).filter(
        AIRequest.human_verified == True, AIRequest.human_override == False
    ).count()
    ai_accuracy = round(correct / verified * 100, 1) if verified > 0 else 91.0
    verified_prev = db.query(AIRequest).filter(
        AIRequest.human_verified == True, AIRequest.created_at < week_ago
    ).count()
    correct_prev = db.query(AIRequest).filter(
        AIRequest.human_verified == True,
        AIRequest.human_override == False, AIRequest.created_at < week_ago
    ).count()
    ai_accuracy_prev = round(correct_prev / verified_prev * 100, 1) if verified_prev > 0 else 91.0

    # ── Human review queue ───────────────────────────────────────────────
    review_queue = db.query(AIRequest).filter(AIRequest.status == "pending_review").count()

    # ── Pipeline funnel (from leads source DB) ───────────────────────────
    total = total_leads or 1
    contacted = _lq("SELECT COUNT(*) FROM leads WHERE touch_number > 0")
    replied = _lq("SELECT COUNT(*) FROM leads WHERE reply_received IS TRUE")
    meetings = _lq("SELECT COUNT(*) FROM leads WHERE meeting_booked_at IS NOT NULL")
    funnel = [
        PipelineFunnelStep(label="Loaded", count=total_leads, pct=100.0),
        PipelineFunnelStep(label="Contacted", count=contacted, pct=round(contacted / total * 100, 1)),
        PipelineFunnelStep(label="Replied", count=replied, pct=round(replied / total * 100, 1)),
        PipelineFunnelStep(label="Meeting Booked", count=meetings, pct=round(meetings / total * 100, 1)),
    ]

    # ── Priority breakdown (from leads source DB) ────────────────────────
    prio_rows = leads_db.execute(text(
        "SELECT campaign_tag, COUNT(*) AS n FROM leads GROUP BY campaign_tag"
    )).fetchall()
    priority_breakdown = [
        PriorityCount(
            tag=r.campaign_tag or "Unknown", count=r.n,
            color=PRIORITY_COLORS.get(r.campaign_tag, "#6b7280"),
        )
        for r in prio_rows
    ]

    # ── AI cost today (ops DB) ───────────────────────────────────────────
    ai_cost_today = db.query(func.sum(AIRequest.cost_usd)).filter(
        AIRequest.created_at >= today_start
    ).scalar() or 0.0
    ai_calls_today = db.query(AIRequest).filter(AIRequest.created_at >= today_start).count()
    ai_conf_avg = db.query(func.avg(AIRequest.confidence_score)).filter(
        AIRequest.confidence_score.isnot(None), AIRequest.created_at >= today_start
    ).scalar() or 0.89

    # ── Errors today ─────────────────────────────────────────────────────
    errors_today = db.query(AuditLog).filter(
        AuditLog.level == "ERROR", AuditLog.created_at >= today_start
    ).count()
    warnings_today = db.query(AuditLog).filter(
        AuditLog.level == "WARNING", AuditLog.created_at >= today_start
    ).count()

    # ── Workflow summaries ───────────────────────────────────────────────
    workflows = _build_workflow_summaries(db, today_start)

    return DashboardMetrics(
        hours_saved_week=hours_saved,
        leads_processed_week=leads_processed,
        automation_rate_pct=automation_rate,
        avg_lead_process_time_min=avg_time,
        ai_accuracy_pct=ai_accuracy,
        human_review_queue_count=review_queue,
        delta_hours_saved=round(hours_saved - hours_saved_prev, 1),
        delta_leads_processed=leads_processed - leads_processed_prev,
        delta_automation_rate=round(automation_rate - auto_rate_prev, 1),
        delta_ai_accuracy=round(ai_accuracy - ai_accuracy_prev, 1),
        pipeline_funnel=funnel,
        priority_breakdown=priority_breakdown,
        total_leads=total,
        ai_calls_today=ai_calls_today,
        ai_cost_today_usd=round(float(ai_cost_today), 3),
        ai_budget_usd=settings.ai_daily_budget_usd,
        ai_confidence_avg=round(float(ai_conf_avg), 3),
        errors_today=errors_today,
        warnings_today=warnings_today,
        workflows=workflows,
    )


def _build_workflow_summaries(db: Session, today_start: datetime) -> List[WorkflowSummary]:
    rows = db.query(
        WorkflowExecution.workflow_id,
        WorkflowExecution.workflow_name,
        func.count().label("total"),
        func.sum(case((WorkflowExecution.status == "success", 1), else_=0)).label("success"),
        func.sum(case((WorkflowExecution.status == "failed", 1), else_=0)).label("failed"),
        func.avg(WorkflowExecution.duration_seconds).label("avg_dur"),
    ).group_by(WorkflowExecution.workflow_id, WorkflowExecution.workflow_name).all()

    results = []
    for r in rows:
        last_run = db.query(WorkflowExecution.started_at).filter(
            WorkflowExecution.workflow_id == r.workflow_id
        ).order_by(WorkflowExecution.started_at.desc()).first()
        last_error = db.query(WorkflowExecution.error_message).filter(
            WorkflowExecution.workflow_id == r.workflow_id,
            WorkflowExecution.status == "failed",
        ).order_by(WorkflowExecution.started_at.desc()).first()
        retries = db.query(WorkflowExecution).filter(
            WorkflowExecution.workflow_id == r.workflow_id,
            WorkflowExecution.retry_count > 0,
            WorkflowExecution.started_at >= today_start,
        ).count()
        results.append(WorkflowSummary(
            workflow_id=r.workflow_id,
            name=r.workflow_name,
            status="active",
            last_run_at=last_run[0] if last_run else None,
            total_runs=r.total,
            success_count=r.success or 0,
            failure_count=r.failed or 0,
            success_rate_pct=round((r.success or 0) / r.total * 100, 1),
            avg_duration_seconds=round(float(r.avg_dur or 0), 1),
            retries_today=retries,
            last_error=last_error[0] if last_error else None,
        ))
    return results


# ─── Workflow Status ──────────────────────────────────────────────────────────

@router.get("/workflows/status", response_model=List[WorkflowStatusDetail])
def get_workflow_status(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    summaries = _build_workflow_summaries(db, today_start)
    results = []
    for s in summaries:
        failures = db.query(WorkflowExecution).filter(
            WorkflowExecution.workflow_id == s.workflow_id,
            WorkflowExecution.status == "failed",
        ).order_by(WorkflowExecution.started_at.desc()).limit(5).all()
        results.append(WorkflowStatusDetail(
            **s.model_dump(),
            recent_failures=[
                {
                    "id": str(f.id),
                    "started_at": f.started_at.isoformat() if f.started_at else None,
                    "duration_seconds": f.duration_seconds,
                    "error_message": f.error_message,
                    "error_type": f.error_type,
                }
                for f in failures
            ],
        ))
    return results


@router.get("/workflows/executions/daily", response_model=List[DailyExecutionPoint])
def get_daily_executions(
    days: int = Query(14, ge=1, le=30),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    since = datetime.utcnow() - timedelta(days=days)
    rows = db.query(
        func.date_trunc("day", WorkflowExecution.started_at).label("date"),
        WorkflowExecution.workflow_id,
        WorkflowExecution.workflow_name,
        func.count().label("executions"),
        func.sum(case((WorkflowExecution.status == "success", 1), else_=0)).label("successes"),
        func.sum(case((WorkflowExecution.status == "failed", 1), else_=0)).label("failures"),
    ).filter(WorkflowExecution.started_at >= since).group_by(
        "date", WorkflowExecution.workflow_id, WorkflowExecution.workflow_name
    ).order_by("date").all()

    return [
        DailyExecutionPoint(
            date=r.date.strftime("%Y-%m-%d"),
            workflow_id=r.workflow_id,
            workflow_name=r.workflow_name,
            executions=r.executions,
            successes=r.successes or 0,
            failures=r.failures or 0,
        )
        for r in rows
    ]


# ─── AI Decisions ─────────────────────────────────────────────────────────────

@router.get("/ai/decisions", response_model=AIStats)
def get_ai_decisions(
    limit: int = Query(50, ge=1, le=200),
    request_type: Optional[str] = None,
    status: Optional[str] = None,
    min_confidence: Optional[float] = None,
    max_confidence: Optional[float] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = datetime.utcnow() - timedelta(days=7)

    # Stats today
    base_today = db.query(AIRequest).filter(AIRequest.created_at >= today_start)
    calls_today = base_today.count()
    cost_today = base_today.with_entities(func.sum(AIRequest.cost_usd)).scalar() or 0.0
    conf_avg = base_today.with_entities(func.avg(AIRequest.confidence_score)).scalar() or 0.89
    fallbacks = base_today.filter(AIRequest.used_fallback == True).count()
    fallback_rate = round(fallbacks / calls_today * 100, 1) if calls_today > 0 else 0.0
    pending = db.query(AIRequest).filter(AIRequest.status == "pending_review").count()

    # Accuracy
    verified = db.query(AIRequest).filter(AIRequest.human_verified == True).count()
    correct = db.query(AIRequest).filter(
        AIRequest.human_verified == True, AIRequest.human_override == False
    ).count()
    accuracy = round(correct / verified * 100, 1) if verified > 0 else 91.0

    # Confidence buckets
    buckets_raw = db.query(
        case(
            (AIRequest.confidence_score < 0.5, "<50%"),
            (AIRequest.confidence_score < 0.7, "50-70%"),
            (AIRequest.confidence_score < 0.85, "70-85%"),
            (AIRequest.confidence_score < 0.95, "85-95%"),
            else_="95-100%",
        ).label("bucket"),
        func.count().label("count"),
    ).filter(
        AIRequest.confidence_score.isnot(None), AIRequest.created_at >= week_ago
    ).group_by("bucket").all()

    bucket_colors = {"<50%": "#ef4444", "50-70%": "#f97316", "70-85%": "#f59e0b",
                     "85-95%": "#22c55e", "95-100%": "#2ECC71"}
    confidence_buckets = [
        ConfidenceBucket(bucket=r.bucket, count=r.count, color=bucket_colors.get(r.bucket, "#6b7280"))
        for r in buckets_raw
    ]

    # Type breakdown
    type_rows = db.query(
        AIRequest.request_type,
        func.count().label("count"),
        func.avg(AIRequest.confidence_score).label("avg_conf"),
        func.avg(AIRequest.cost_usd).label("avg_cost"),
    ).filter(AIRequest.created_at >= week_ago).group_by(AIRequest.request_type).all()

    type_breakdown = [
        AITypeBreakdown(
            request_type=r.request_type or "unknown",
            count=r.count,
            avg_confidence=round(float(r.avg_conf or 0), 3),
            avg_cost_usd=round(float(r.avg_cost or 0), 5),
        )
        for r in type_rows
    ]

    # Decision list
    query = db.query(AIRequest)
    if request_type:
        query = query.filter(AIRequest.request_type == request_type)
    if status:
        query = query.filter(AIRequest.status == status)
    if min_confidence is not None:
        query = query.filter(AIRequest.confidence_score >= min_confidence)
    if max_confidence is not None:
        query = query.filter(AIRequest.confidence_score <= max_confidence)
    decisions = query.order_by(AIRequest.created_at.desc()).limit(limit).all()

    return AIStats(
        calls_today=calls_today,
        cost_today_usd=round(float(cost_today), 3),
        budget_usd=settings.ai_daily_budget_usd,
        budget_pct_used=round(float(cost_today) / max(settings.ai_daily_budget_usd, 0.01) * 100, 1),
        avg_confidence=round(float(conf_avg), 3),
        fallback_rate_pct=fallback_rate,
        accuracy_pct=accuracy,
        pending_review=pending,
        confidence_buckets=confidence_buckets,
        type_breakdown=type_breakdown,
        decisions=[AIDecision.model_validate(d) for d in decisions],
    )


# ─── Logs ─────────────────────────────────────────────────────────────────────

@router.get("/logs/operations", response_model=LogStats)
def get_logs(
    level: Optional[str] = None,
    source: Optional[str] = None,
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    since = datetime.utcnow() - timedelta(hours=hours)
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    errors_today = db.query(AuditLog).filter(
        AuditLog.level == "ERROR", AuditLog.created_at >= today_start
    ).count()
    warnings_today = db.query(AuditLog).filter(
        AuditLog.level == "WARNING", AuditLog.created_at >= today_start
    ).count()
    info_today = db.query(AuditLog).filter(
        AuditLog.level == "INFO", AuditLog.created_at >= today_start
    ).count()
    total_today = errors_today + warnings_today + info_today
    error_rate = round(errors_today / total_today * 100, 1) if total_today > 0 else 0.0

    query = db.query(AuditLog).filter(AuditLog.created_at >= since)
    if level:
        query = query.filter(AuditLog.level == level.upper())
    if source:
        query = query.filter(AuditLog.source == source)
    logs = query.order_by(AuditLog.created_at.desc()).limit(limit).all()

    return LogStats(
        errors_today=errors_today,
        warnings_today=warnings_today,
        info_today=info_today,
        error_rate_pct=error_rate,
        logs=[LogEntry.model_validate(l) for l in logs],
    )


@router.get("/logs", response_model=LogStats)
def get_logs_alias(
    level: Optional[str] = None,
    source: Optional[str] = None,
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_logs(
        level=level,
        source=source,
        hours=hours,
        limit=limit,
        db=db,
        _=current_user,
    )


# ─── Pipeline ─────────────────────────────────────────────────────────────────

_USING_LIVE_LEADS = bool(settings.leads_database_url)


@router.get("/pipeline/leads")
def get_pipeline_leads(
    campaign_tag: Optional[str] = None,
    stage: Optional[str] = None,
    research_interest: Optional[str] = None,
    score_min: Optional[int] = None,
    score_max: Optional[int] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_leads_db),
    _: User = Depends(get_current_user),
):
    filters = []
    params: dict = {"limit": limit, "offset": offset}
    if campaign_tag:
        filters.append("campaign_tag = :campaign_tag")
        params["campaign_tag"] = campaign_tag
    if stage:
        filters.append("stage = :stage")
        params["stage"] = stage
    if research_interest:
        filters.append("research_interest = :research_interest")
        params["research_interest"] = research_interest
    if score_min is not None:
        filters.append("lead_score >= :score_min")
        params["score_min"] = score_min
    if score_max is not None:
        filters.append("lead_score <= :score_max")
        params["score_max"] = score_max
    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    count_sql = text(f"SELECT COUNT(*) FROM leads {where}")
    total = db.execute(count_sql, params).scalar() or 0

    sql = text(
        f"SELECT lead_id, first_name, last_name, institution, research_interest, "
        f"campaign_tag, lead_score, stage, touch_number, reply_received, next_send_date "
        f"FROM leads {where} ORDER BY lead_score DESC NULLS LAST LIMIT :limit OFFSET :offset"
    )
    rows = db.execute(sql, params).mappings().all()
    leads = [
        LeadRow(
            id=None,
            lead_id=r["lead_id"],
            first_name=r["first_name"],
            last_name=r["last_name"],
            institution=r["institution"],
            research_interest=r["research_interest"],
            campaign_tag=r["campaign_tag"],
            lead_score=r["lead_score"] or 0,
            stage=r["stage"] or "new",
            touch_number=r["touch_number"] or 0,
            reply_received=bool(r["reply_received"]),
            ab_variant=None,
            ai_classified=False,
            human_verified=False,
            next_send_date=r["next_send_date"],
        )
        for r in rows
    ]
    return {"total": total, "offset": offset, "limit": limit, "leads": leads}


@router.get("/pipeline/research-stats", response_model=List[ResearchAreaStats])
def get_research_stats(
    db: Session = Depends(get_leads_db),
    _: User = Depends(get_current_user),
):
    sql = text(
        "SELECT research_interest, "
        "COUNT(*) AS total, "
        "SUM(CASE WHEN touch_number > 0 THEN 1 ELSE 0 END) AS contacted, "
        "SUM(CASE WHEN reply_received IS TRUE THEN 1 ELSE 0 END) AS replied, "
        "SUM(CASE WHEN meeting_booked_at IS NOT NULL THEN 1 ELSE 0 END) AS meetings "
        "FROM leads GROUP BY research_interest"
    )
    rows = db.execute(sql).mappings().all()
    return [
        ResearchAreaStats(
            research_interest=r["research_interest"] or "general",
            total=r["total"],
            contacted=r["contacted"] or 0,
            replied=r["replied"] or 0,
            meetings=r["meetings"] or 0,
            reply_rate_pct=round((r["replied"] or 0) / max(r["contacted"] or 1, 1) * 100, 1),
        )
        for r in rows
    ]


# ─── Human Review Queue ───────────────────────────────────────────────────────

@router.get("/human-review/queue", response_model=List[ReviewItem])
def get_review_queue(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    items = db.query(AIRequest).filter(
        AIRequest.status == "pending_review"
    ).order_by(AIRequest.created_at.asc()).all()

    def _age_hours(created):
        if created is None:
            return 0.0
        # normalize naive datetimes (from older seed data) to UTC
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return (now - created).total_seconds() / 3600

    return [
        ReviewItem(
            id=item.id,
            created_at=item.created_at,
            request_type=item.request_type or "unknown",
            input_preview=item.input_preview,
            confidence_score=item.confidence_score,
            age_hours=round(_age_hours(item.created_at), 1),
            sla_breach=_age_hours(item.created_at) > 3.5,
        )
        for item in items
    ]


@router.post("/human-review/queue/{item_id}/resolve")
def resolve_review(
    item_id: str,
    resolution: ReviewResolution,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Approve/reject/override an AI decision pending human review.

    - approve    → status="completed", human_verified=True
    - reject     → status="rejected",  human_verified=False
    - override   → status="overridden", human_verified=True, human_override=True
    Per spec (use-case diagram), both admin and operator can resolve.
    """
    action = (resolution.action or "").lower().strip()
    if action not in {"approve", "reject", "override"}:
        raise HTTPException(status_code=400, detail="action must be approve, reject, or override")

    item = db.query(AIRequest).filter(AIRequest.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")

    if action == "approve":
        item.status = "completed"
        item.human_verified = True
        item.human_override = False
        audit_level = "INFO"
    elif action == "reject":
        item.status = "rejected"
        item.human_verified = False
        item.human_override = False
        audit_level = "WARN"
    else:  # override
        item.status = "overridden"
        item.human_verified = True
        item.human_override = True
        audit_level = "WARN"

    notes = (resolution.reviewer_notes or "").strip()
    msg = f"Human review {action} by {current_user.username}"
    if notes:
        msg += f" — {notes[:500]}"

    db.add(AuditLog(
        level=audit_level,
        source="admin_dashboard",
        message=msg,
        entity_id=item.id,
        entity_type="ai_request",
        user_id=current_user.username,
    ))
    db.commit()
    return {
        "status": "resolved",
        "action": action,
        "item_status": item.status,
        "human_verified": item.human_verified,
        "human_override": item.human_override,
    }


# ─── Activity Feed ───────────────────────────────────────────────────────────

@router.get("/dashboard/activity-feed", response_model=List[ActivityEvent])
def get_activity_feed(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    events = []
    since = datetime.utcnow() - timedelta(days=3)

    execs = db.query(WorkflowExecution).filter(
        WorkflowExecution.started_at >= since,
    ).order_by(WorkflowExecution.started_at.desc()).limit(15).all()

    for ex in execs:
        status = ex.status or "unknown"
        detail = None
        if status == "error" and ex.error_message:
            detail = ex.error_message[:120]
        elif ex.duration_seconds:
            detail = f"Completed in {ex.duration_seconds:.1f}s"
        events.append(ActivityEvent(
            type="workflow",
            title=ex.workflow_name or ex.workflow_id or "Workflow",
            detail=detail,
            timestamp=ex.started_at,
            status=status,
        ))

    ai_items = db.query(AIRequest).filter(
        AIRequest.created_at >= since,
    ).order_by(AIRequest.created_at.desc()).limit(8).all()

    for ai in ai_items:
        conf = f"{ai.confidence_score * 100:.0f}%" if ai.confidence_score else ""
        events.append(ActivityEvent(
            type="ai",
            title=f"AI {(ai.request_type or 'decision').replace('_', ' ')}",
            detail=f"Confidence {conf}" if conf else None,
            timestamp=ai.created_at,
            status=ai.status,
        ))

    logs = db.query(AuditLog).filter(
        AuditLog.created_at >= since,
        AuditLog.level.in_(["WARNING", "ERROR"]),
    ).order_by(AuditLog.created_at.desc()).limit(5).all()

    for log in logs:
        events.append(ActivityEvent(
            type="event",
            title=log.message[:80] if log.message else "System event",
            detail=log.source,
            timestamp=log.created_at,
            status="error" if log.level == "ERROR" else "warning",
        ))

    events.sort(key=lambda e: e.timestamp, reverse=True)
    return events[:12]


# ─── System Health Summary ───────────────────────────────────────────────────

@router.get("/dashboard/system-health", response_model=List[SystemHealthDot])
def get_system_health(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from app.models.system import System
    systems = db.query(System).filter(System.is_active == True).all()
    # tz-aware: WorkflowExecution.started_at is TIMESTAMPTZ — naive utcnow()
    # would TypeError on the subtraction below.
    now = datetime.now(timezone.utc)
    results = []

    for sys in systems:
        recent = db.query(WorkflowExecution).filter(
            WorkflowExecution.system_id == sys.id,
            WorkflowExecution.started_at >= now - timedelta(days=1),
        ).all()

        if not recent:
            status = "idle"
            last_run_ago = None
        else:
            errors = sum(1 for r in recent if r.status == "error")
            total = len(recent)
            if errors / total > 0.3:
                status = "error"
            elif errors > 0:
                status = "warning"
            else:
                status = "healthy"
            last = max(r.started_at for r in recent)
            diff_min = int((now - last).total_seconds() / 60)
            if diff_min < 60:
                last_run_ago = f"{diff_min}m ago"
            elif diff_min < 1440:
                last_run_ago = f"{diff_min // 60}h ago"
            else:
                last_run_ago = f"{diff_min // 1440}d ago"

        results.append(SystemHealthDot(
            slug=sys.slug,
            name=sys.name,
            status=status,
            last_run_ago=last_run_ago,
        ))

    return results


# ─── Active Alerts ───────────────────────────────────────────────────────────

@router.get("/dashboard/alerts", response_model=List[AlertItem])
def get_alerts(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    alerts: List[AlertItem] = []

    fails = db.query(WorkflowExecution).filter(
        WorkflowExecution.status == "failed",
        WorkflowExecution.started_at >= day_ago,
        WorkflowExecution.resolved.is_(False),
    ).count()
    if fails:
        alerts.append(AlertItem(
            severity="error", type="workflow_failures",
            message=f"{fails} workflow failure{'s' if fails != 1 else ''} in the last 24h",
            count=fails, link="/workflows",
        ))

    breaches = db.query(AIRequest).filter(
        AIRequest.status == "pending_review",
        AIRequest.created_at < now - timedelta(hours=3.5),
    ).count()
    if breaches:
        alerts.append(AlertItem(
            severity="error", type="sla_breach",
            message=f"{breaches} review item{'s' if breaches != 1 else ''} past the 3.5h SLA",
            count=breaches, link="/review",
        ))

    pending = db.query(AIRequest).filter(AIRequest.status == "pending_review").count()
    if pending:
        alerts.append(AlertItem(
            severity="warning", type="review_pending",
            message=f"{pending} AI decision{'s' if pending != 1 else ''} awaiting review",
            count=pending, link="/review",
        ))

    cost_today = db.query(func.sum(AIRequest.cost_usd)).filter(
        AIRequest.created_at >= today_start
    ).scalar() or 0.0
    if cost_today > settings.ai_daily_budget_usd * 0.8:
        alerts.append(AlertItem(
            severity="warning", type="budget",
            message=f"AI spend ${cost_today:.2f} near daily budget ${settings.ai_daily_budget_usd:.0f}",
            count=1, link="/ai",
        ))

    return alerts


@router.post("/workflows/executions/{execution_id}/resolve")
def resolve_workflow_failure(
    execution_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Acknowledge a failed workflow execution so it stops firing the alert.

    Sets resolved=True on the row; both /dashboard/alerts and per-system last_error
    now filter by resolved=False, so a resolved failure drops out of the banner and
    the red execution-failed card on /systems on the next poll. Row itself stays for
    audit history."""
    row = db.query(WorkflowExecution).filter(WorkflowExecution.id == execution_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Workflow execution not found")
    if row.status != "failed":
        raise HTTPException(status_code=400, detail="Only failed executions can be resolved")

    already = bool(row.resolved)
    row.resolved = True
    row.updated_at = datetime.utcnow()

    db.add(AuditLog(
        level="INFO",
        source="admin_dashboard",
        message=f"Workflow failure acknowledged by {current_user.username} "
                f"(workflow={row.workflow_name} exec={row.execution_id})",
        entity_id=str(row.id),
        entity_type="workflow_execution",
        user_id=current_user.username,
    ))
    db.commit()
    return {
        "status": "resolved",
        "execution_id": str(row.id),
        "workflow_id": row.workflow_id,
        "was_already_resolved": already,
    }


# ─── n8n Execution Sync ──────────────────────────────────────────────────────

@router.post("/sync-n8n")
def trigger_n8n_sync(
    limit: int = Query(default=100, le=1000),
    _: User = Depends(require_admin),
):
    from app.sync_n8n import sync
    result = sync(limit=limit)
    return result
