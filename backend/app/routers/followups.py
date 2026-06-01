from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_leads_db
from app.models.user import User

router = APIRouter(prefix="/admin/followups", tags=["followups"])

# Leads that are still in an active outreach state
ACTIVE = "stage NOT IN ('cold', 'dead', 'bounced', 'Cold')"

_FIELDS = (
    "SELECT lead_id, CONCAT(first_name, ' ', last_name) AS name, institution, "
    "lead_score, stage, campaign_tag, next_send_date, last_contacted, touch_number, "
    "meeting_scheduled_for FROM leads "
)

_LIMIT = 30


def _section(db: Session, where: str, order: str = "next_send_date ASC NULLS LAST", params=None):
    params = params or {}
    count = db.execute(text(f"SELECT count(*) FROM leads WHERE {where}"), params).scalar() or 0
    rows = db.execute(
        text(f"{_FIELDS} WHERE {where} ORDER BY {order} LIMIT :limit"),
        {**params, "limit": _LIMIT},
    ).mappings().all()
    return {"count": count, "leads": [dict(r) for r in rows]}


@router.get("")
def get_followups(
    leads_db: Session = Depends(get_leads_db),
    _: User = Depends(get_current_user),
):
    return {
        "overdue": _section(leads_db, f"next_send_date < CURRENT_DATE AND {ACTIVE}"),
        "due_today": _section(leads_db, f"next_send_date = CURRENT_DATE AND {ACTIVE}"),
        "this_week": _section(
            leads_db,
            f"next_send_date > CURRENT_DATE AND next_send_date <= CURRENT_DATE + 7 AND {ACTIVE}",
        ),
        "upcoming_meetings": _section(
            leads_db, "meeting_scheduled_for >= now()", order="meeting_scheduled_for ASC"
        ),
        "hot_needs_action": _section(
            leads_db,
            f"lead_score >= 7 AND email1_sent_at IS NOT NULL AND next_send_date < CURRENT_DATE AND {ACTIVE}",
            order="lead_score DESC, next_send_date ASC",
        ),
    }
