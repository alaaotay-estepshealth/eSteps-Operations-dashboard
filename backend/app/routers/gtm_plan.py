"""GTM plan + tasks endpoints.

Surfaces the latest Claude Opus 4.7 GTM ingest, lets operators apply/reject
extracted KPIs, and serves per-user task lists with RBAC filtering.
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_user, require_admin, require_operator
from app.config import settings
from app.database import get_db
from app.models.ai_request import AIRequest
from app.models.audit_log import AuditLog
from app.models.gtm_initiative import GtmInitiative
from app.models.user import User
from app.schemas.gtm_plan import (
    AssignRequest,
    CalendarItem,
    GenerateAccepted,
    GenerateRequest,
    GtmPlanResponse,
    InitiativeRow,
)
from app.services.gtm_extractor import (
    GtmExtractorError,
    generate_gtm_plan,
    gtm_today_spend_usd,
)

router = APIRouter(prefix="/admin", tags=["gtm-plan"])


def _is_admin(user: User) -> bool:
    return (user.role or "").lower() == "admin"


def _display(user: Optional[User]) -> Optional[str]:
    if not user:
        return None
    return user.display_name or user.username


def _run_background(db_factory, ai_request_id: UUID):
    """Re-open a session because BackgroundTasks runs after the request closes."""
    db = db_factory()
    try:
        ai_req = db.query(AIRequest).filter(AIRequest.id == ai_request_id).first()
        if not ai_req:
            return
        try:
            generate_gtm_plan(db, ai_req=ai_req)
        except GtmExtractorError as e:
            ai_req.status = "rejected"
            ai_req.ai_output = {"error": str(e)}
            db.commit()
    finally:
        db.close()


@router.post(
    "/insights/gtm-plan/generate",
    response_model=GenerateAccepted,
    status_code=202,
)
def generate_endpoint(
    body: GenerateRequest = GenerateRequest(),
    background: BackgroundTasks = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_operator),
) -> GenerateAccepted:
    """Trigger a new GTM plan generation. Returns 202 + execution_id."""
    # Budget guard
    spent = gtm_today_spend_usd(db)
    if spent >= settings.gtm_ai_budget_usd:
        raise HTTPException(
            status_code=503,
            detail=f"GTM AI budget exhausted (${spent:.4f} / ${settings.gtm_ai_budget_usd:.2f} today)",
        )

    # Concurrency check
    in_flight = (
        db.query(AIRequest)
        .filter(
            AIRequest.request_type == "gtm_retrospective",
            AIRequest.status == "pending_review",
        )
        .order_by(AIRequest.created_at.desc())
        .first()
    )
    if in_flight and not body.force:
        return GenerateAccepted(execution_id=str(in_flight.id), status="in_flight")

    # Pre-create the AIRequest row so we can return its id immediately.
    ai_req = AIRequest(
        request_type="gtm_retrospective",
        provider="anthropic",
        model=settings.gtm_model,
        status="pending_review",
        input_preview="manual" if background is None else "background",
    )
    db.add(ai_req)
    db.commit()
    db.refresh(ai_req)

    db.add(AuditLog(
        level="INFO",
        source="gtm_plan",
        message=f"GTM plan generation queued by {user.username}",
        entity_id=ai_req.id,
        entity_type="ai_request",
        user_id=user.username,
    ))
    db.commit()

    if background is not None:
        from app.database import SessionLocal
        background.add_task(_run_background, SessionLocal, ai_req.id)

    return GenerateAccepted(execution_id=str(ai_req.id), status="queued")


# ---------------------------------------------------------------------------
# Task 10: GET /admin/insights/gtm-plan
# ---------------------------------------------------------------------------

@router.get("/insights/gtm-plan", response_model=GtmPlanResponse)
def get_plan(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GtmPlanResponse:
    latest = (
        db.query(AIRequest)
        .filter(AIRequest.request_type == "gtm_retrospective")
        .order_by(AIRequest.created_at.desc())
        .first()
    )
    if not latest:
        return GtmPlanResponse(status="none")
    age_seconds = int((datetime.now(timezone.utc) - latest.created_at).total_seconds()) if latest.created_at else None
    return GtmPlanResponse(
        ai_request_id=latest.id,
        generated_at=latest.created_at,
        age_seconds=age_seconds,
        status=latest.status if latest.status in ("completed", "rejected") else "running",
        output=latest.ai_output if latest.status == "completed" else None,
        error_message=(latest.ai_output or {}).get("error") if latest.status == "rejected" else None,
    )


# ---------------------------------------------------------------------------
# Task 11: GET /admin/insights/gtm-plan/initiatives
# ---------------------------------------------------------------------------

def _initiative_row(row: GtmInitiative, db: Session) -> InitiativeRow:
    assignee_user = None
    if row.assignee_user_id:
        assignee_user = db.query(User).filter(User.id == row.assignee_user_id).first()
    return InitiativeRow(
        id=row.id,
        period=row.period,
        objective_label=row.objective_label,
        target_value=float(row.target_value) if row.target_value is not None else None,
        target_unit=row.target_unit,
        rationale=row.rationale,
        assignee_label=row.assignee_label,
        assignee_user_id=row.assignee_user_id,
        assignee_display=_display(assignee_user) if assignee_user else row.assignee_label,
        due_at=row.due_at,
        status=row.status,
        created_at=row.created_at,
        applied_at=row.applied_at,
    )


@router.get("/insights/gtm-plan/initiatives", response_model=List[InitiativeRow])
def list_initiatives(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[InitiativeRow]:
    latest = (
        db.query(AIRequest)
        .filter(AIRequest.request_type == "gtm_retrospective", AIRequest.status == "completed")
        .order_by(AIRequest.created_at.desc())
        .first()
    )
    if not latest:
        return []
    rows = (
        db.query(GtmInitiative)
        .filter(GtmInitiative.source_ai_request_id == latest.id)
        .order_by(GtmInitiative.period.asc(), GtmInitiative.created_at.asc())
        .all()
    )
    return [_initiative_row(r, db) for r in rows]


# ---------------------------------------------------------------------------
# Task 12: POST .../initiatives/{id}/apply + /reject
# ---------------------------------------------------------------------------

def _flip_status(
    initiative_id: UUID,
    new_status: str,
    db: Session,
    user: User,
) -> InitiativeRow:
    row = db.query(GtmInitiative).filter(GtmInitiative.id == initiative_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="initiative not found")
    if row.status in ("applied", "rejected"):
        raise HTTPException(status_code=409, detail=f"initiative already {row.status}")
    row.status = new_status
    if new_status == "applied":
        row.applied_by = user.id
        row.applied_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        level="INFO",
        source="gtm_plan",
        message=f"GTM initiative {new_status} by {user.username}: {row.objective_label[:80]}",
        entity_id=row.id,
        entity_type="gtm_initiative",
        user_id=user.username,
    ))
    db.commit()
    db.refresh(row)
    return _initiative_row(row, db)


@router.post("/insights/gtm-plan/initiatives/{initiative_id}/apply", response_model=InitiativeRow)
def apply_initiative(
    initiative_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_operator),
) -> InitiativeRow:
    return _flip_status(initiative_id, "applied", db, user)


@router.post("/insights/gtm-plan/initiatives/{initiative_id}/reject", response_model=InitiativeRow)
def reject_initiative(
    initiative_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_operator),
) -> InitiativeRow:
    return _flip_status(initiative_id, "rejected", db, user)


# ---------------------------------------------------------------------------
# Task 13: GET /admin/gtm-tasks (RBAC)
# ---------------------------------------------------------------------------

def _tasks_query(db: Session, user: User, status_filter: List[str]):
    q = db.query(GtmInitiative).filter(GtmInitiative.status.in_(status_filter))
    if not _is_admin(user):
        q = q.filter(GtmInitiative.assignee_user_id == user.id)
    return q


@router.get("/gtm-tasks", response_model=List[InitiativeRow])
def list_tasks(
    period: Optional[str] = Query(None, regex="^(30d|60d|90d)$"),
    status: str = Query("suggested,applied"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[InitiativeRow]:
    status_filter = [s.strip() for s in status.split(",") if s.strip()]
    q = _tasks_query(db, user, status_filter)
    if period:
        q = q.filter(GtmInitiative.period == period)
    rows = q.order_by(GtmInitiative.due_at.asc().nullslast(), GtmInitiative.created_at.desc()).all()
    return [_initiative_row(r, db) for r in rows]


# ---------------------------------------------------------------------------
# Task 14: GET /gtm-tasks/calendar + POST /gtm-tasks/{id}/assign
# ---------------------------------------------------------------------------

@router.get("/gtm-tasks/calendar", response_model=List[CalendarItem])
def list_tasks_calendar(
    from_: datetime = Query(alias="from"),
    to: datetime = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[CalendarItem]:
    q = _tasks_query(db, user, status_filter=["suggested", "applied"])
    q = q.filter(GtmInitiative.due_at.isnot(None),
                 GtmInitiative.due_at >= from_,
                 GtmInitiative.due_at <= to)
    out: List[CalendarItem] = []
    for r in q.order_by(GtmInitiative.due_at.asc()).all():
        assignee_user = None
        if r.assignee_user_id:
            assignee_user = db.query(User).filter(User.id == r.assignee_user_id).first()
        label = r.objective_label
        if r.target_value is not None and r.target_unit:
            label = f"{label} × {r.target_value:g} {r.target_unit}"
        out.append(CalendarItem(
            id=r.id,
            label=label,
            due_at=r.due_at,
            period=r.period,
            status=r.status,
            assignee_display=_display(assignee_user) if assignee_user else r.assignee_label,
        ))
    return out


@router.post("/gtm-tasks/{initiative_id}/assign", response_model=InitiativeRow)
def assign_task(
    initiative_id: UUID,
    body: AssignRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> InitiativeRow:
    row = db.query(GtmInitiative).filter(GtmInitiative.id == initiative_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="initiative not found")
    row.assignee_user_id = body.user_id
    row.updated_at = datetime.now(timezone.utc)
    if body.user_id:
        u = db.query(User).filter(User.id == body.user_id).first()
        if u:
            row.assignee_label = u.display_name or u.username
    db.add(AuditLog(
        level="INFO",
        source="gtm_plan",
        message=f"GTM initiative reassigned by {user.username} → {body.user_id}",
        entity_id=row.id,
        entity_type="gtm_initiative",
        user_id=user.username,
    ))
    db.commit()
    db.refresh(row)
    return _initiative_row(row, db)
