"""Meeting prep + checklist endpoints (ES-OPS-09-MEET-NOTES)."""
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin, require_operator
from app.database import get_db, get_leads_db
from app.models.booking import Booking
from app.models.meeting_note import MeetingNote
from app.models.meeting_task import MeetingTask
from app.models.user import User
from app.schemas.responses import (
    MeetingBookingSummary,
    MeetingDetail,
    MeetingLeadSummary,
    MeetingListItem,
    MeetingNoteData,
    MeetingNoteUpdate,
    MeetingSyncResult,
    MeetingTaskCreate,
    MeetingTaskRow,
    MeetingTaskUpdate,
    PreviousMeeting,
)
from app.services.gemini import (
    GEMINI_MODEL,
    call_gemini,
    cost_per_call_usd,
    gemini_today_spend_usd,
    record_decision_row,
)
from app.config import settings

router = APIRouter(prefix="/admin/meetings", tags=["meetings"])

_SYNC_WINDOW = timedelta(minutes=5)


class SyncBody(BaseModel):
    source: str = "manual"  # "manual" | "n8n"
    dry_run: bool = False


def _audit(db: Session, user: User, action: str, resource_id: str, payload: dict | None = None) -> None:
    try:
        from app.models.audit_log import AuditLog
        row = AuditLog(
            user_id=getattr(user, "id", None),
            action=action,
            resource="meeting",
            resource_id=str(resource_id),
            changes=payload or {},
            status="success",
        )
        db.add(row)
        db.commit()
    except Exception:
        db.rollback()


@router.post("/sync", response_model=MeetingSyncResult)
def sync_meetings(
    body: SyncBody = Body(default_factory=SyncBody),
    db: Session = Depends(get_db),
    leads_db: Session = Depends(get_leads_db),
    user: User = Depends(require_admin),
) -> MeetingSyncResult:
    """Upsert one booking row per lead with a `meeting_scheduled_for`.

    Idempotency window: reschedules within ±5 min update in place and stash the
    previous time in `rescheduled_from`. Outside the window we insert a new row
    so each distinct meeting gets its own notes.
    """
    rows = leads_db.execute(
        text(
            "SELECT id AS lead_id, meeting_scheduled_for "
            "FROM leads WHERE meeting_scheduled_for IS NOT NULL"
        )
    ).mappings().all()

    created = updated = rescheduled = skipped = 0

    for r in rows:
        lid = r["lead_id"]
        when = r["meeting_scheduled_for"]
        if when is None:
            skipped += 1
            continue

        existing = (
            db.query(Booking)
            .filter(Booking.lead_id == lid, Booking.status.in_(("scheduled", "rescheduled")))
            .order_by(Booking.scheduled_for.desc())
            .first()
        )

        if existing is None:
            if body.dry_run:
                created += 1
                continue
            db.add(
                Booking(
                    lead_id=lid,
                    status="scheduled",
                    scheduled_for=when,
                    source=body.source,
                    duration_min=20,
                )
            )
            created += 1
            continue

        if existing.scheduled_for is None:
            if not body.dry_run:
                existing.scheduled_for = when
            updated += 1
            continue

        delta = abs((existing.scheduled_for - when).total_seconds())
        if delta == 0:
            skipped += 1
            continue

        if delta <= _SYNC_WINDOW.total_seconds():
            # Within window → small reschedule: keep id, stash previous time.
            if not body.dry_run:
                existing.rescheduled_from = existing.scheduled_for
                existing.scheduled_for = when
            rescheduled += 1
            continue

        # Outside window → bigger reschedule: keep id, stash previous time,
        # mark status back to scheduled.
        if not body.dry_run:
            existing.rescheduled_from = existing.scheduled_for
            existing.scheduled_for = when
            existing.status = "scheduled"
        rescheduled += 1

    if not body.dry_run:
        db.commit()
    _audit(db, user, "meetings.sync", "n/a", {"source": body.source, "created": created,
                                              "updated": updated, "rescheduled": rescheduled})
    return MeetingSyncResult(
        created=created, updated=updated, rescheduled=rescheduled,
        skipped=skipped, dry_run=body.dry_run,
    )


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _lead_summary(leads_db: Session, lead_id: UUID) -> MeetingLeadSummary | None:
    row = leads_db.execute(
        text(
            "SELECT id, CONCAT(first_name, ' ', last_name) AS name, institution, "
            "title, research_area, lead_score, stage, "
            "LEFT(COALESCE(bio, ''), 400) AS bio_excerpt "
            "FROM leads WHERE id = :id"
        ),
        {"id": str(lead_id)},
    ).mappings().first()
    if not row:
        return None

    inbound = None
    try:
        inbound = leads_db.execute(
            text(
                "SELECT created_at, LEFT(COALESCE(body, ''), 400) AS excerpt "
                "FROM conversations WHERE lead_id = :id AND direction = 'inbound' "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"id": str(lead_id)},
        ).mappings().first()
    except Exception:
        inbound = None

    return MeetingLeadSummary(
        lead_id=row["id"],
        name=row["name"],
        institution=row["institution"],
        title=row["title"],
        research_area=row["research_area"],
        lead_score=row["lead_score"],
        stage=row["stage"],
        bio_excerpt=row["bio_excerpt"] or None,
        last_inbound_at=inbound["created_at"] if inbound else None,
        last_inbound_excerpt=inbound["excerpt"] if inbound else None,
    )


def _booking_summary(b: Booking) -> MeetingBookingSummary:
    return MeetingBookingSummary(
        id=b.id, lead_id=b.lead_id, title=b.title, status=b.status,
        scheduled_for=b.scheduled_for, duration_min=b.duration_min,
        meeting_url=b.meeting_url, source=b.source,
        rescheduled_from=b.rescheduled_from, completed_at=b.completed_at,
        canceled_at=b.canceled_at, no_show_detected=bool(b.no_show_detected),
    )


def _task_row(t: MeetingTask) -> MeetingTaskRow:
    overdue = None
    if t.due_at and not t.done:
        delta = (datetime.now(timezone.utc) - t.due_at).total_seconds() / 3600
        if delta > 0:
            overdue = round(delta, 1)
    return MeetingTaskRow(
        id=t.id, booking_id=t.booking_id, title=t.title, done=t.done,
        done_at=t.done_at, due_at=t.due_at, assignee=t.assignee,
        order_index=t.order_index, created_by=t.created_by,
        created_at=t.created_at, updated_at=t.updated_at,
        overdue_by_hours=overdue,
    )


def _notes_data(n: MeetingNote | None) -> MeetingNoteData:
    if n is None:
        return MeetingNoteData(prep_md="", recap_md="")
    return MeetingNoteData(
        prep_md=n.prep_md, recap_md=n.recap_md,
        ai_drafted_at=n.ai_drafted_at, ai_model=n.ai_model,
        updated_by=n.updated_by, updated_at=n.updated_at,
    )


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.get("", response_model=List[MeetingListItem])
def list_meetings(
    status: Optional[str] = None,
    has_open_tasks: bool = False,
    limit: int = 100,
    db: Session = Depends(get_db),
    leads_db: Session = Depends(get_leads_db),
    _: User = Depends(get_current_user),
) -> List[MeetingListItem]:
    q = db.query(Booking)
    if status:
        q = q.filter(Booking.status == status)
    bookings = q.order_by(Booking.scheduled_for.asc().nullslast()).limit(limit).all()
    if not bookings:
        return []

    lead_ids = {b.lead_id for b in bookings}
    lead_rows: dict = {}
    if lead_ids:
        for r in leads_db.execute(
            text(
                "SELECT id, CONCAT(first_name, ' ', last_name) AS name, institution "
                "FROM leads WHERE id = ANY(:ids)"
            ),
            {"ids": [str(i) for i in lead_ids]},
        ).mappings().all():
            lead_rows[str(r["id"])] = r

    booking_ids = [b.id for b in bookings]
    has_notes = {
        str(n.booking_id)
        for n in db.query(MeetingNote.booking_id).filter(MeetingNote.booking_id.in_(booking_ids)).all()
    }
    open_counts: dict = {}
    for bid, cnt in db.execute(
        text(
            "SELECT booking_id, count(*) FROM meeting_tasks "
            "WHERE done = FALSE AND booking_id = ANY(:ids) GROUP BY booking_id"
        ),
        {"ids": [str(i) for i in booking_ids]},
    ).all():
        open_counts[str(bid)] = int(cnt)

    out: List[MeetingListItem] = []
    for b in bookings:
        if has_open_tasks and open_counts.get(str(b.id), 0) == 0:
            continue
        lr = lead_rows.get(str(b.lead_id), {})
        out.append(
            MeetingListItem(
                booking_id=b.id, lead_id=b.lead_id,
                lead_name=lr.get("name"), institution=lr.get("institution"),
                scheduled_for=b.scheduled_for, status=b.status,
                open_task_count=open_counts.get(str(b.id), 0),
                has_notes=str(b.id) in has_notes,
                duration_min=b.duration_min,
            )
        )
    return out


@router.get("/{booking_id}", response_model=MeetingDetail)
def get_meeting(
    booking_id: UUID,
    db: Session = Depends(get_db),
    leads_db: Session = Depends(get_leads_db),
    _: User = Depends(get_current_user),
) -> MeetingDetail:
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Meeting not found")

    lead = _lead_summary(leads_db, booking.lead_id)
    if lead is None:
        lead = MeetingLeadSummary(lead_id=booking.lead_id, name="(lead not found)")

    note = db.query(MeetingNote).filter(MeetingNote.booking_id == booking_id).first()
    tasks = (
        db.query(MeetingTask)
        .filter(MeetingTask.booking_id == booking_id)
        .order_by(MeetingTask.order_index.asc(), MeetingTask.created_at.asc())
        .all()
    )
    prev = (
        db.query(Booking)
        .filter(Booking.lead_id == booking.lead_id, Booking.id != booking_id)
        .order_by(Booking.scheduled_for.desc().nullslast())
        .limit(5)
        .all()
    )

    return MeetingDetail(
        booking=_booking_summary(booking),
        lead=lead,
        notes=_notes_data(note),
        tasks=[_task_row(t) for t in tasks],
        previous_meetings=[
            PreviousMeeting(booking_id=p.id, scheduled_for=p.scheduled_for, status=p.status)
            for p in prev
        ],
    )
