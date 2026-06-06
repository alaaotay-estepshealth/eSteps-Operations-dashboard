from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db, get_leads_db
from app.models.user import User

router = APIRouter(prefix="/admin/followups", tags=["followups"])

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


def _open_meeting_tasks(db: Session, leads_db: Session, limit: int = 30) -> dict:
    rows = db.execute(
        text(
            "SELECT t.id AS task_id, t.booking_id, t.title, t.due_at, "
            "b.lead_id, "
            "EXTRACT(EPOCH FROM (now() - t.due_at))/3600 AS overdue_h "
            "FROM meeting_tasks t JOIN bookings b ON b.id = t.booking_id "
            "WHERE t.done = FALSE AND t.due_at IS NOT NULL AND t.due_at < now() "
            "ORDER BY t.due_at ASC LIMIT :limit"
        ),
        {"limit": limit},
    ).mappings().all()
    if not rows:
        return {"count": 0, "tasks": []}

    lead_ids = list({str(r["lead_id"]) for r in rows})
    lead_names = {}
    if lead_ids:
        for r in leads_db.execute(
            text("SELECT id, CONCAT(first_name, ' ', last_name) AS name "
                 "FROM leads WHERE id = ANY(:ids)"),
            {"ids": lead_ids},
        ).mappings().all():
            lead_names[str(r["id"])] = r["name"]

    tasks = [
        {
            "task_id": str(r["task_id"]),
            "booking_id": str(r["booking_id"]),
            "lead_name": lead_names.get(str(r["lead_id"])),
            "title": r["title"],
            "due_at": r["due_at"].isoformat() if r["due_at"] else None,
            "overdue_by_hours": round(float(r["overdue_h"]), 1) if r["overdue_h"] else None,
        }
        for r in rows
    ]
    return {"count": len(tasks), "tasks": tasks}


@router.get("")
def get_followups(
    leads_db: Session = Depends(get_leads_db),
    db: Session = Depends(get_db),
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
        "open_meeting_tasks": _open_meeting_tasks(db, leads_db),
    }
