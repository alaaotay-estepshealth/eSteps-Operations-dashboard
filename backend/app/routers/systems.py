from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.dependencies import get_system
from app.models.system import System
from app.models.user import User
from app.models.workflow_execution import WorkflowExecution
from app.services.system_service import SystemService

router = APIRouter(prefix="/admin/systems", tags=["systems"])


# ─── List systems ─────────────────────────────────────────────────────────────

@router.get("", summary="List all active automation systems")
def list_systems(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    svc = SystemService(db)
    systems = svc.list_active()
    return [
        {
            "slug": s.slug,
            "name": s.name,
            "description": s.description,
            "n8n_project_id": s.n8n_project_id,
            "is_active": s.is_active,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in systems
    ]


# ─── Cross-system overview ────────────────────────────────────────────────────

@router.get("/overview", summary="Cross-system KPIs and per-system summary")
def get_cross_system_overview(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    svc = SystemService(db)
    return svc.get_cross_system_overview()


# ─── Per-system stats ─────────────────────────────────────────────────────────

@router.get("/{system_slug}", summary="Stats for a single automation system")
def get_system_stats(
    days: int = Query(7, ge=1, le=30),
    system: System = Depends(get_system),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    svc = SystemService(db)
    stats = svc.get_system_stats(system.id, days=days)
    return {
        "slug": system.slug,
        "name": system.name,
        "description": system.description,
        **stats,
    }


# ─── Per-system activity feed ─────────────────────────────────────────────────

@router.get("/{system_slug}/activity", summary="Recent activity feed for a single system")
def get_system_activity(
    system: System = Depends(get_system),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return SystemService(db).get_activity(system.id)


# ─── Per-system execution history ─────────────────────────────────────────────

@router.get("/{system_slug}/executions", summary="Paginated execution history for a system")
def get_system_executions(
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    system: System = Depends(get_system),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = db.query(WorkflowExecution).filter(
        WorkflowExecution.system_id == system.id
    )
    if status:
        query = query.filter(WorkflowExecution.status == status)

    total = query.count()
    executions = (
        query.order_by(WorkflowExecution.started_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "executions": [
            {
                "id": str(e.id),
                "workflow_id": e.workflow_id,
                "workflow_name": e.workflow_name,
                "execution_id": e.execution_id,
                "status": e.status,
                "started_at": e.started_at.isoformat() if e.started_at else None,
                "finished_at": e.finished_at.isoformat() if e.finished_at else None,
                "duration_seconds": e.duration_seconds,
                "error_message": e.error_message,
                "error_type": e.error_type,
                "retry_count": e.retry_count,
            }
            for e in executions
        ],
    }
