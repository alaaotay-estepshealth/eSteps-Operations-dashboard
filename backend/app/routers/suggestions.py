"""AI suggestion lifecycle endpoints: apply, reject, list-pending."""
import json
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_operator
from app.database import get_db
from app.models.ai_suggestion import AISuggestion
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.responses import (
    PaginatedSuggestions,
    SuggestionApplyBody,
    SuggestionDetail,
    SuggestionRejectBody,
)
from app.services.audit import write_audit

router = APIRouter(prefix="/admin/suggestions", tags=["suggestions"])


def _apply_to_ticket(db: Session, ticket_id, payload: dict, confidence, override: bool):
    """Write the applied payload into the entity columns."""
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None or ticket.status == "resolved":
        return False
    ticket.ai_category = payload.get("category")
    ticket.ai_priority_score = payload.get("priority_score")
    ticket.ai_confidence = confidence
    if payload.get("assigned_to"):
        ticket.assigned_to = payload["assigned_to"]
    ticket.human_verified = True
    ticket.human_override = override
    ticket.updated_at = datetime.now(timezone.utc)
    return True


@router.post("/{suggestion_id}/apply", response_model=SuggestionDetail)
def apply_suggestion(
    suggestion_id: UUID,
    body: SuggestionApplyBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_operator),
) -> SuggestionDetail:
    override = body.override_payload
    override_json = json.dumps(override) if override else None

    row = db.execute(
        text(
            "UPDATE ai_suggestions SET status='applied', applied_at=now(), "
            "applied_by=:user, "
            "applied_payload=COALESCE(:override::jsonb, payload), "
            "updated_at=now() "
            "WHERE id=:id AND status='pending' "
            "RETURNING id, entity_type, entity_id, payload, applied_payload, "
            "model, confidence, status, rationale, applied_at, applied_by, "
            "rejected_at, rejected_by, rejection_reason, ai_request_id, "
            "created_at, updated_at"
        ),
        {"id": str(suggestion_id), "user": user.username, "override": override_json},
    ).mappings().first()

    if not row:
        existing = db.query(AISuggestion).filter(
            AISuggestion.id == suggestion_id
        ).first()
        if not existing:
            raise HTTPException(status_code=404, detail="Suggestion not found")
        raise HTTPException(
            status_code=409, detail=f"Suggestion is already {existing.status}"
        )

    applied_payload = dict(row["applied_payload"])
    suggested_payload = dict(row["payload"])
    was_override = applied_payload != suggested_payload

    if row["entity_type"] == "ticket":
        _apply_to_ticket(
            db,
            row["entity_id"],
            applied_payload,
            row["confidence"],
            was_override,
        )

    db.commit()

    write_audit(
        db,
        user,
        action="ai.suggestion.override" if was_override else "ai.suggestion.apply",
        resource_type=row["entity_type"],
        resource_id=str(row["entity_id"]),
        payload={
            "suggestion_id": str(suggestion_id),
            "suggested": suggested_payload,
            "applied": applied_payload,
        },
    )

    return SuggestionDetail.model_validate(dict(row))


@router.get("/pending", response_model=PaginatedSuggestions)
def list_pending(
    entity_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PaginatedSuggestions:
    q = db.query(AISuggestion).filter(AISuggestion.status == "pending")
    if entity_type:
        q = q.filter(AISuggestion.entity_type == entity_type)
    total = q.count()
    rows = (
        q.order_by(AISuggestion.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return PaginatedSuggestions(
        total=total,
        limit=limit,
        offset=offset,
        suggestions=[
            SuggestionDetail.model_validate(r, from_attributes=True) for r in rows
        ],
    )


@router.post("/{suggestion_id}/reject", response_model=SuggestionDetail)
def reject_suggestion(
    suggestion_id: UUID,
    body: SuggestionRejectBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_operator),
) -> SuggestionDetail:
    row = db.execute(
        text(
            "UPDATE ai_suggestions SET status='rejected', rejected_at=now(), "
            "rejected_by=:user, rejection_reason=:reason, updated_at=now() "
            "WHERE id=:id AND status='pending' "
            "RETURNING id, entity_type, entity_id, payload, applied_payload, "
            "model, confidence, status, rationale, applied_at, applied_by, "
            "rejected_at, rejected_by, rejection_reason, ai_request_id, "
            "created_at, updated_at"
        ),
        {
            "id": str(suggestion_id),
            "user": user.username,
            "reason": body.reason,
        },
    ).mappings().first()

    if not row:
        existing = db.query(AISuggestion).filter(
            AISuggestion.id == suggestion_id
        ).first()
        if not existing:
            raise HTTPException(status_code=404, detail="Suggestion not found")
        raise HTTPException(
            status_code=409, detail=f"Suggestion is already {existing.status}"
        )

    db.commit()

    write_audit(
        db,
        user,
        action="ai.suggestion.reject",
        resource_type=row["entity_type"],
        resource_id=str(row["entity_id"]),
        payload={"suggestion_id": str(suggestion_id), "reason": body.reason},
    )

    return SuggestionDetail.model_validate(dict(row))
