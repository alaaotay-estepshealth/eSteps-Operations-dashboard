from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.responses import (
    PaginatedTickets,
    TicketCategoryBreakdown,
    TicketRow,
    TicketStats,
    TicketStatusUpdate,
)

router = APIRouter(prefix="/admin/tickets", tags=["tickets"])


@router.get("/stats", response_model=TicketStats)
def get_ticket_stats(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    open_count = db.query(func.count(Ticket.id)).filter(Ticket.status == "open").scalar() or 0
    in_progress = db.query(func.count(Ticket.id)).filter(Ticket.status == "in_progress").scalar() or 0
    resolved = db.query(func.count(Ticket.id)).filter(Ticket.status == "resolved").scalar() or 0
    total = open_count + in_progress + resolved

    avg_response = db.query(func.avg(Ticket.response_time_min)).filter(
        Ticket.response_time_min.isnot(None)
    ).scalar()
    avg_confidence = db.query(func.avg(Ticket.ai_confidence)).scalar() or 0
    verified_count = db.query(func.count(Ticket.id)).filter(Ticket.human_verified.is_(True)).scalar() or 0

    cat_rows = db.query(
        Ticket.ai_category,
        func.count(Ticket.id),
        func.avg(Ticket.ai_priority_score),
        func.avg(Ticket.ai_confidence),
    ).group_by(Ticket.ai_category).all()

    categories = [
        TicketCategoryBreakdown(
            category=c, count=cnt,
            avg_priority=round(float(p), 1),
            avg_confidence=round(float(conf), 3),
        )
        for c, cnt, p, conf in cat_rows
    ]

    return TicketStats(
        open_count=open_count,
        in_progress_count=in_progress,
        resolved_count=resolved,
        avg_response_time_min=round(float(avg_response), 1) if avg_response else None,
        avg_ai_confidence=round(float(avg_confidence), 3),
        human_verification_rate_pct=round(verified_count / max(total, 1) * 100, 1),
        categories=categories,
    )


@router.get("", response_model=PaginatedTickets)
def list_tickets(
    status: Optional[str] = Query(None),
    ai_category: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = db.query(Ticket)

    if status:
        query = query.filter(Ticket.status == status)
    if ai_category:
        query = query.filter(Ticket.ai_category == ai_category)

    total = query.count()
    rows = query.order_by(Ticket.created_at.desc()).offset(offset).limit(limit).all()

    tickets = [
        TicketRow(
            id=t.id,
            created_at=t.created_at,
            source=t.source,
            subject=t.subject,
            body_preview=t.body_preview,
            ai_category=t.ai_category,
            ai_priority_score=t.ai_priority_score,
            ai_confidence=t.ai_confidence,
            assigned_to=t.assigned_to,
            status=t.status,
            resolved_at=t.resolved_at,
            response_time_min=t.response_time_min,
            human_verified=t.human_verified,
        )
        for t in rows
    ]

    return PaginatedTickets(total=total, offset=offset, limit=limit, tickets=tickets)


@router.patch("/{ticket_id}/status")
def update_ticket_status(
    ticket_id: str,
    update: TicketStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket.status = update.status
    if update.assigned_to:
        ticket.assigned_to = update.assigned_to
    db.commit()

    db.add(AuditLog(
        level="INFO",
        source="admin_dashboard",
        message=f"Ticket status updated to {update.status} by {current_user.username}",
        entity_id=ticket.id,
        entity_type="ticket",
        user_id=current_user.username,
    ))
    db.commit()

    return {"status": "updated", "ticket_id": ticket_id}
