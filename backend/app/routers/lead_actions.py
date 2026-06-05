from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import desc, text
from sqlalchemy.orm import Session

from app.auth import require_operator
from app.database import get_db, get_leads_db
from app.models.audit_log import AuditLog
from app.models.system import System
from app.models.user import User
from app.schemas.responses import LeadActionRequest

router = APIRouter(prefix="/admin/leads", tags=["lead-actions"])

_VALID_PRIORITY = {"Priority_A", "Priority_B", "Priority_C"}
# Stages we'd consider "before engaged" — used as a safe fallback when we have
# no audit-log breadcrumb of what the lead was on before being engaged.
_DEFAULT_REVERT_STAGE = "pitching"


def _simple_update(action: str, value):
    """Single-statement actions: SET clause + params + description.

    Actions that need to read prior state first (set_engaged, unset_engaged)
    are handled directly in lead_action() and don't go through here.
    """
    if action == "pause":
        return "next_send_date = NULL", {}, "paused outreach"
    if action == "resume":
        return "next_send_date = CURRENT_DATE + 1", {}, "resumed outreach"
    if action == "mark_cold":
        return "stage = 'cold', next_send_date = NULL", {}, "marked cold"
    if action == "set_priority":
        if value not in _VALID_PRIORITY:
            raise HTTPException(status_code=422, detail="value must be Priority_A|Priority_B|Priority_C")
        return "campaign_tag = :val", {"val": value}, f"set priority {value}"
    if action == "schedule_meeting":
        if not value:
            raise HTTPException(status_code=422, detail="value must be the meeting datetime (ISO 8601)")
        return (
            "meeting_scheduled_for = (:val)::timestamptz, "
            "stage = 'call_requested', next_send_date = NULL",
            {"val": value},
            f"scheduled meeting for {value}",
        )
    return None  # signal "needs special handling"


def _get_lead_stage(leads_db: Session, lead_id: str) -> str:
    row = leads_db.execute(
        text("SELECT stage FROM leads WHERE lead_id = :lid"), {"lid": lead_id}
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Lead not found")
    return row[0] or ""


def _system_id(db: Session):
    sys = db.query(System).filter(System.slug == "esteps-leads").first()
    return sys.id if sys else None


def _audit(db: Session, message: str, user: User, level: str = "INFO", metadata: dict | None = None) -> None:
    db.add(AuditLog(
        system_id=_system_id(db),
        level=level,
        source="dashboard",
        message=message,
        metadata_=metadata,
    ))


@router.post("/{lead_id}/action")
def lead_action(
    body: LeadActionRequest,
    lead_id: str = Path(...),
    leads_db: Session = Depends(get_leads_db),
    db: Session = Depends(get_db),
    user: User = Depends(require_operator),
):
    # ── Toggleable engagement ─────────────────────────────────────────────
    if body.action == "set_engaged":
        prev_stage = _get_lead_stage(leads_db, lead_id)
        if prev_stage == "engaged":
            return {"status": "noop", "lead_id": lead_id, "action": body.action, "applied": "already engaged"}
        result = leads_db.execute(
            text(
                "UPDATE leads "
                "SET stage = 'engaged', next_send_date = NULL, "
                "    last_contacted = COALESCE(last_contacted, now()), updated_at = now() "
                "WHERE lead_id = :lid"
            ),
            {"lid": lead_id},
        )
        if result.rowcount == 0:
            leads_db.rollback()
            raise HTTPException(status_code=404, detail="Lead not found")
        leads_db.commit()
        _audit(
            db,
            message=f"{user.username} marked lead {lead_id} engaged (was '{prev_stage}')",
            user=user,
            metadata={"action": "set_engaged", "lead_id": lead_id, "previous_stage": prev_stage},
        )
        db.commit()
        return {"status": "ok", "lead_id": lead_id, "action": body.action, "applied": "marked engaged", "previous_stage": prev_stage}

    if body.action == "unset_engaged":
        current = _get_lead_stage(leads_db, lead_id)
        if current != "engaged":
            return {"status": "noop", "lead_id": lead_id, "action": body.action, "applied": f"already '{current}'"}
        # Find the most recent set_engaged audit row → restore its previous_stage.
        last = (
            db.query(AuditLog)
            .filter(AuditLog.metadata_["action"].astext == "set_engaged")
            .filter(AuditLog.metadata_["lead_id"].astext == lead_id)
            .order_by(desc(AuditLog.created_at))
            .first()
        )
        restored = (last.metadata_ or {}).get("previous_stage") if last else None
        if not restored or restored == "engaged":
            restored = _DEFAULT_REVERT_STAGE
        # Re-arm the drip too — the lead is back in the queue.
        result = leads_db.execute(
            text(
                "UPDATE leads "
                "SET stage = :stage, "
                "    next_send_date = COALESCE(next_send_date, CURRENT_DATE + 1), "
                "    updated_at = now() "
                "WHERE lead_id = :lid"
            ),
            {"stage": restored, "lid": lead_id},
        )
        if result.rowcount == 0:
            leads_db.rollback()
            raise HTTPException(status_code=404, detail="Lead not found")
        leads_db.commit()
        _audit(
            db,
            message=f"{user.username} unset engaged on lead {lead_id} → stage '{restored}'",
            user=user,
            metadata={"action": "unset_engaged", "lead_id": lead_id, "restored_stage": restored},
        )
        db.commit()
        return {"status": "ok", "lead_id": lead_id, "action": body.action, "applied": f"reverted to '{restored}'", "restored_stage": restored}

    # ── Single-statement actions ──────────────────────────────────────────
    resolved = _simple_update(body.action, body.value)
    if resolved is None:
        raise HTTPException(status_code=422, detail=f"Unknown action: {body.action}")
    set_clause, extra, description = resolved
    params = {"lid": lead_id, **extra}
    # `lid` lets the WHERE clause not collide with action-specific binds like `val`.
    result = leads_db.execute(
        text(f"UPDATE leads SET {set_clause}, updated_at = now() WHERE lead_id = :lid"),
        params,
    )
    if result.rowcount == 0:
        leads_db.rollback()
        raise HTTPException(status_code=404, detail="Lead not found")
    leads_db.commit()

    _audit(db, message=f"{user.username} {description} for lead {lead_id}", user=user,
           metadata={"action": body.action, "lead_id": lead_id})
    db.commit()
    return {"status": "ok", "lead_id": lead_id, "action": body.action, "applied": description}
