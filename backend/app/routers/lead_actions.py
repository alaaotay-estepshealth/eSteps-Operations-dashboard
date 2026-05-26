from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import require_operator
from app.database import get_db, get_leads_db
from app.models.audit_log import AuditLog
from app.models.system import System
from app.models.user import User
from app.schemas.responses import LeadActionRequest

router = APIRouter(prefix="/admin/leads", tags=["lead-actions"])

_VALID_PRIORITY = {"Priority_A", "Priority_B", "Priority_C"}


def _resolve_update(action: str, value):
    """Map an action to a SQL SET clause, bound params, and a human description.

    Pause clears next_send_date so the EST-2 scheduler skips the lead; resume
    re-arms it for tomorrow. mark_cold is terminal (also stops outreach).
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
    raise HTTPException(status_code=422, detail=f"Unknown action: {action}")


@router.post("/{lead_id}/action")
def lead_action(
    body: LeadActionRequest,
    lead_id: str = Path(...),
    leads_db: Session = Depends(get_leads_db),
    db: Session = Depends(get_db),
    user: User = Depends(require_operator),
):
    set_clause, extra, description = _resolve_update(body.action, body.value)
    params = {"lead_id": lead_id, **extra}

    result = leads_db.execute(
        text(f"UPDATE leads SET {set_clause}, updated_at = now() WHERE lead_id = :lead_id"),
        params,
    )
    if result.rowcount == 0:
        leads_db.rollback()
        raise HTTPException(status_code=404, detail="Lead not found")
    leads_db.commit()

    system = db.query(System).filter(System.slug == "esteps-leads").first()
    db.add(AuditLog(
        system_id=system.id if system else None,
        level="INFO",
        source="dashboard",
        message=f"{user.username} {description} for lead {lead_id}",
    ))
    db.commit()

    return {"status": "ok", "lead_id": lead_id, "action": body.action, "applied": description}
