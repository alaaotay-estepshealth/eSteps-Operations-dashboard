from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_leads_db
from app.models.user import User
from app.schemas.responses import BookingRow, BookingStats, PaginatedBookings

router = APIRouter(prefix="/admin/bookings", tags=["bookings"])


class CalendarMeeting(BaseModel):
    lead_id: Optional[str] = None
    lead_name: Optional[str] = None
    institution: Optional[str] = None
    when: datetime
    source: str
    status: str


# NOTE: the endpoint returns a plain dict so the JSON key can stay `from`
# (Python's reserved word makes a model field tricky).


@router.get("/stats", response_model=BookingStats)
def get_booking_stats(
    db: Session = Depends(get_leads_db),
    _: User = Depends(get_current_user),
):
    _q = lambda sql: db.execute(text(sql)).scalar() or 0

    # Derive bookings from leads with meeting data + conversations with meeting intent
    booked = _q("SELECT COUNT(*) FROM leads WHERE meeting_booked_at IS NOT NULL")
    scheduled = _q("SELECT COUNT(*) FROM leads WHERE meeting_scheduled_for IS NOT NULL AND meeting_scheduled_for > NOW()")
    completed = _q("SELECT COUNT(*) FROM leads WHERE meeting_scheduled_for IS NOT NULL AND meeting_scheduled_for <= NOW()")

    # Also count from opportunities table
    opp_meetings = _q("SELECT COUNT(*) FROM opportunities WHERE stage IN ('meeting_booked', 'meeting_held')")
    opp_held = _q("SELECT COUNT(*) FROM opportunities WHERE call_held_at IS NOT NULL")

    total = max(booked + opp_meetings, 1)
    upcoming = scheduled + _q("SELECT COUNT(*) FROM opportunities WHERE stage = 'meeting_booked' AND call_held_at IS NULL")
    done = completed + opp_held

    # Conversations that indicate meeting interest
    meeting_convos = _q(
        "SELECT COUNT(*) FROM conversations WHERE direction = 'inbound' "
        "AND (body ILIKE '%meeting%' OR body ILIKE '%call%' OR body ILIKE '%happy to%' OR body ILIKE '%discuss%')"
    )

    return BookingStats(
        total=total + meeting_convos,
        upcoming=upcoming,
        completed=done,
        canceled=0,
        no_shows=0,
        no_show_rate_pct=0.0,
        completion_rate_pct=round(done / max(total, 1) * 100, 1),
    )


@router.get("", response_model=PaginatedBookings)
def list_bookings(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_leads_db),
    _: User = Depends(get_current_user),
):
    # Combine: leads with meetings + opportunities + conversations indicating meeting intent
    parts = []

    # From leads table
    parts.append(
        "SELECT l.id, l.meeting_booked_at as created_at, "
        "CONCAT(l.first_name, ' ', l.last_name) as lead_name, "
        "l.institution, "
        "CASE WHEN l.meeting_scheduled_for > NOW() THEN 'scheduled' "
        "     WHEN l.meeting_scheduled_for IS NOT NULL THEN 'completed' "
        "     ELSE 'scheduled' END as status, "
        "l.meeting_scheduled_for as scheduled_for, "
        "NULL::timestamptz as completed_at, NULL::timestamptz as canceled_at, "
        "FALSE as no_show_detected, 'calendly' as source "
        "FROM leads l WHERE l.meeting_booked_at IS NOT NULL"
    )

    # From opportunities table
    parts.append(
        "SELECT o.id, o.created_at, "
        "COALESCE(CONCAT(l.first_name, ' ', l.last_name), o.assigned_to) as lead_name, "
        "l.institution, "
        "CASE WHEN o.call_held_at IS NOT NULL THEN 'completed' ELSE 'scheduled' END as status, "
        "COALESCE(o.call_held_at, o.created_at + INTERVAL '3 days') as scheduled_for, "
        "o.call_held_at as completed_at, NULL::timestamptz as canceled_at, "
        "FALSE as no_show_detected, 'n8n-workflow' as source "
        "FROM opportunities o LEFT JOIN leads l ON o.lead_id = l.id"
    )

    # From conversations with meeting interest
    parts.append(
        "SELECT c.id, c.created_at, "
        "CONCAT(l.first_name, ' ', l.last_name) as lead_name, "
        "l.institution, 'pending' as status, "
        "NULL::timestamptz as scheduled_for, NULL::timestamptz as completed_at, "
        "NULL::timestamptz as canceled_at, FALSE as no_show_detected, "
        "'gmail-reply' as source "
        "FROM conversations c JOIN leads l ON c.lead_id = l.id "
        "WHERE c.direction = 'inbound' AND ("
        "c.body ILIKE '%meeting%' OR c.body ILIKE '%call%' "
        "OR c.body ILIKE '%happy to%' OR c.body ILIKE '%discuss%')"
    )

    union_sql = " UNION ALL ".join(parts)

    status_filter = ""
    params: dict = {"limit": limit, "offset": offset}
    if status:
        status_filter = "WHERE status = :status"
        params["status"] = status

    total = db.execute(text(
        f"SELECT COUNT(*) FROM ({union_sql}) sub {status_filter}"
    ), params).scalar() or 0

    rows = db.execute(text(
        f"SELECT * FROM ({union_sql}) sub {status_filter} "
        f"ORDER BY COALESCE(scheduled_for, created_at) DESC NULLS LAST "
        f"LIMIT :limit OFFSET :offset"
    ), params).mappings().all()

    bookings = [
        BookingRow(
            id=r["id"], created_at=r["created_at"],
            lead_name=r["lead_name"], institution=r["institution"],
            status=r["status"], scheduled_for=r["scheduled_for"],
            completed_at=r["completed_at"], canceled_at=r["canceled_at"],
            no_show_detected=r["no_show_detected"], source=r["source"],
        )
        for r in rows
    ]
    return PaginatedBookings(total=total, offset=offset, limit=limit, bookings=bookings)


@router.get("/calendar")
def calendar_meetings(
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = Query(None),
    db: Session = Depends(get_leads_db),
    _: User = Depends(get_current_user),
):
    """All scheduled meetings in a date window — feeds the calendar view."""
    today = date.today()
    start = from_ or (today.replace(day=1))
    # End of next month if no `to` was given.
    if to is None:
        next_month_first = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        end = (next_month_first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    else:
        end = to
    if end < start:
        raise HTTPException(status_code=400, detail="`to` must be >= `from`")

    rows = db.execute(text(
        """
        SELECT lead_id,
               CONCAT(first_name, ' ', last_name) AS lead_name,
               institution,
               meeting_scheduled_for AS when_,
               CASE WHEN meeting_scheduled_for <= now() THEN 'past' ELSE 'upcoming' END AS status
        FROM leads
        WHERE meeting_scheduled_for IS NOT NULL
          AND meeting_scheduled_for >= :start
          AND meeting_scheduled_for <  :end_excl
        ORDER BY meeting_scheduled_for ASC
        """
    ), {"start": start, "end_excl": end + timedelta(days=1)}).mappings().all()

    meetings = [
        CalendarMeeting(
            lead_id=r["lead_id"],
            lead_name=r["lead_name"],
            institution=r["institution"],
            when=r["when_"],
            source="lead",
            status=r["status"],
        )
        for r in rows
    ]
    return {"from": start.isoformat(), "to": end.isoformat(), "meetings": [m.model_dump(mode="json") for m in meetings]}
