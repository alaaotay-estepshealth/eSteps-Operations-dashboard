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
from app.services.audit import write_audit
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


def _audit(
    db: Session,
    user: User,
    action: str,
    resource_id: str,
    payload: dict | None = None,
) -> None:
    """Thin wrapper preserving the meetings.py call signature.

    All meeting-domain audit rows use resource_type='meeting'. Future
    callers should use write_audit directly with explicit resource_type.
    """
    write_audit(
        db,
        user,
        action=action,
        resource_type="meeting",
        resource_id=resource_id,
        payload=payload,
    )


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
    rows = (
        leads_db.execute(
            text(
                "SELECT id AS lead_id, meeting_scheduled_for "
                "FROM leads WHERE meeting_scheduled_for IS NOT NULL"
            )
        )
        .mappings()
        .all()
    )

    created = updated = rescheduled = skipped = 0

    for r in rows:
        lid = r["lead_id"]
        when = r["meeting_scheduled_for"]
        if when is None:
            skipped += 1
            continue

        existing = (
            db.query(Booking)
            .filter(
                Booking.lead_id == lid, Booking.status.in_(("scheduled", "rescheduled"))
            )
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
    _audit(
        db,
        user,
        "meetings.sync",
        "n/a",
        {
            "source": body.source,
            "created": created,
            "updated": updated,
            "rescheduled": rescheduled,
        },
    )
    return MeetingSyncResult(
        created=created,
        updated=updated,
        rescheduled=rescheduled,
        skipped=skipped,
        dry_run=body.dry_run,
    )


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _lead_summary(leads_db: Session, lead_id: UUID) -> MeetingLeadSummary | None:
    row = (
        leads_db.execute(
            text(
                "SELECT id, CONCAT(first_name, ' ', last_name) AS name, institution, "
                "title, research_area, lead_score, stage, "
                "LEFT(COALESCE(bio, ''), 400) AS bio_excerpt "
                "FROM leads WHERE id = :id"
            ),
            {"id": str(lead_id)},
        )
        .mappings()
        .first()
    )
    if not row:
        return None

    inbound = None
    try:
        inbound = (
            leads_db.execute(
                text(
                    "SELECT created_at, LEFT(COALESCE(body, ''), 400) AS excerpt "
                    "FROM conversations WHERE lead_id = :id AND direction = 'inbound' "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"id": str(lead_id)},
            )
            .mappings()
            .first()
        )
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
        id=b.id,
        lead_id=b.lead_id,
        title=b.title,
        status=b.status,
        scheduled_for=b.scheduled_for,
        duration_min=b.duration_min,
        meeting_url=b.meeting_url,
        source=b.source,
        rescheduled_from=b.rescheduled_from,
        completed_at=b.completed_at,
        canceled_at=b.canceled_at,
        no_show_detected=bool(b.no_show_detected),
    )


def _task_row(t: MeetingTask) -> MeetingTaskRow:
    overdue = None
    if t.due_at and not t.done:
        delta = (datetime.now(timezone.utc) - t.due_at).total_seconds() / 3600
        if delta > 0:
            overdue = round(delta, 1)
    return MeetingTaskRow(
        id=t.id,
        booking_id=t.booking_id,
        title=t.title,
        done=t.done,
        done_at=t.done_at,
        due_at=t.due_at,
        assignee=t.assignee,
        order_index=t.order_index,
        created_by=t.created_by,
        created_at=t.created_at,
        updated_at=t.updated_at,
        overdue_by_hours=overdue,
    )


def _notes_data(n: MeetingNote | None) -> MeetingNoteData:
    if n is None:
        return MeetingNoteData(prep_md="", recap_md="")
    return MeetingNoteData(
        prep_md=n.prep_md,
        recap_md=n.recap_md,
        ai_drafted_at=n.ai_drafted_at,
        ai_model=n.ai_model,
        updated_by=n.updated_by,
        updated_at=n.updated_at,
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
        for r in (
            leads_db.execute(
                text(
                    "SELECT id, CONCAT(first_name, ' ', last_name) AS name, institution "
                    "FROM leads WHERE id = ANY(:ids)"
                ),
                {"ids": [str(i) for i in lead_ids]},
            )
            .mappings()
            .all()
        ):
            lead_rows[str(r["id"])] = r

    booking_ids = [b.id for b in bookings]
    has_notes = {
        str(n.booking_id)
        for n in db.query(MeetingNote.booking_id)
        .filter(MeetingNote.booking_id.in_(booking_ids))
        .all()
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
                booking_id=b.id,
                lead_id=b.lead_id,
                lead_name=lr.get("name"),
                institution=lr.get("institution"),
                scheduled_for=b.scheduled_for,
                status=b.status,
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
    user: User = Depends(get_current_user),
) -> MeetingDetail:
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Meeting not found")

    lead = _lead_summary(leads_db, booking.lead_id) or MeetingLeadSummary(
        lead_id=booking.lead_id, name="(lead not found)"
    )

    note, skipped = _try_autodraft(
        db,
        booking,
        lead,
        actor=getattr(user, "username", None) or getattr(user, "email", None),
    )

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

    notes_payload = _notes_data(note)
    if skipped:
        notes_payload = MeetingNoteData(
            **notes_payload.model_dump(),
        )
        notes_payload.ai_skipped = skipped

    return MeetingDetail(
        booking=_booking_summary(booking),
        lead=lead,
        notes=notes_payload,
        tasks=[_task_row(t) for t in tasks],
        previous_meetings=[
            PreviousMeeting(
                booking_id=p.id, scheduled_for=p.scheduled_for, status=p.status
            )
            for p in prev
        ],
    )


# ─── Notes + Tasks CRUD ──────────────────────────────────────────────────────


def _get_booking_or_404(db: Session, booking_id: UUID) -> Booking:
    b = db.query(Booking).filter(Booking.id == booking_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return b


@router.patch("/{booking_id}/notes", response_model=MeetingNoteData)
def patch_notes(
    booking_id: UUID,
    body: MeetingNoteUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_operator),
) -> MeetingNoteData:
    booking = _get_booking_or_404(db, booking_id)
    note = db.query(MeetingNote).filter(MeetingNote.booking_id == booking_id).first()
    if note is None:
        note = MeetingNote(booking_id=booking_id)
        db.add(note)
    if body.prep_md is not None:
        note.prep_md = body.prep_md
    if body.recap_md is not None:
        note.recap_md = body.recap_md
    note.updated_by = getattr(user, "username", None) or getattr(user, "email", None)
    db.commit()
    db.refresh(note)
    _audit(
        db,
        user,
        "meetings.notes.update",
        str(booking_id),
        {
            "prep_changed": body.prep_md is not None,
            "recap_changed": body.recap_md is not None,
        },
    )
    _ = booking  # touched for audit context only
    return _notes_data(note)


@router.post("/{booking_id}/tasks", response_model=MeetingTaskRow)
def create_task(
    booking_id: UUID,
    body: MeetingTaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_operator),
) -> MeetingTaskRow:
    _get_booking_or_404(db, booking_id)
    next_order = (
        db.query(MeetingTask.order_index)
        .filter(MeetingTask.booking_id == booking_id)
        .order_by(MeetingTask.order_index.desc())
        .limit(1)
        .scalar()
    )
    task = MeetingTask(
        booking_id=booking_id,
        title=body.title.strip(),
        due_at=body.due_at,
        assignee=body.assignee,
        order_index=(
            body.order_index
            if body.order_index is not None
            else ((next_order or 0) + 1)
        ),
        created_by=getattr(user, "username", None) or getattr(user, "email", None),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    _audit(db, user, "meetings.task.create", str(booking_id), {"task_id": str(task.id)})
    return _task_row(task)


@router.patch("/{booking_id}/tasks/{task_id}", response_model=MeetingTaskRow)
def update_task(
    booking_id: UUID,
    task_id: UUID,
    body: MeetingTaskUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_operator),
) -> MeetingTaskRow:
    task = (
        db.query(MeetingTask)
        .filter(MeetingTask.id == task_id, MeetingTask.booking_id == booking_id)
        .first()
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if body.title is not None:
        task.title = body.title.strip()
    if body.due_at is not None:
        task.due_at = body.due_at
    if body.assignee is not None:
        task.assignee = body.assignee
    if body.order_index is not None:
        task.order_index = body.order_index
    if body.done is not None and body.done != task.done:
        task.done = body.done
        task.done_at = datetime.now(timezone.utc) if body.done else None
    db.commit()
    db.refresh(task)
    _audit(
        db,
        user,
        "meetings.task.update",
        str(booking_id),
        {"task_id": str(task.id), "fields": body.model_dump(exclude_none=True)},
    )
    return _task_row(task)


@router.delete("/{booking_id}/tasks/{task_id}")
def delete_task(
    booking_id: UUID,
    task_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_operator),
) -> dict:
    task = (
        db.query(MeetingTask)
        .filter(MeetingTask.id == task_id, MeetingTask.booking_id == booking_id)
        .first()
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    _audit(db, user, "meetings.task.delete", str(booking_id), {"task_id": str(task_id)})
    return {"deleted": str(task_id)}


# ─── AI auto-draft (Task 8) ─────────────────────────────────────────────────


class AIDraftBody(BaseModel):
    force: bool = False


_DRAFT_INSTRUCTION = (
    "Draft a concise 20-min discovery-call prep note in markdown for an eSteps "
    "Health partnership rep. Sections: **Why this lead matters** (1-2 lines), "
    "**Key questions to ask** (3-5 bullets, research-anchored), "
    "**Talking points** (3 bullets tying eSteps capabilities to their research), "
    "**Watch-outs** (1-2 sensitivities), **Next-step ask** (one concrete CTA). "
    "No filler. No hallucinated citations."
)


def _prep_prompt(lead: MeetingLeadSummary, booking: Booking) -> str:
    hours_until = "—"
    if booking.scheduled_for:
        delta = (
            booking.scheduled_for - datetime.now(timezone.utc)
        ).total_seconds() / 3600
        hours_until = f"{delta:.1f}"
    parts = [
        _DRAFT_INSTRUCTION,
        "",
        f"Lead: {lead.name or '—'}, {lead.title or '—'} @ {lead.institution or '—'}",
        f"Research area: {lead.research_area or '—'}   "
        f"Score: {lead.lead_score if lead.lead_score is not None else '—'}/10   "
        f"Stage: {lead.stage or '—'}",
    ]
    if lead.bio_excerpt:
        parts.append(f"Bio excerpt: {lead.bio_excerpt}")
    if lead.last_inbound_excerpt:
        parts.append(f"Last inbound reply: {lead.last_inbound_excerpt}")
    parts.append(
        f"Meeting in {hours_until} hours · duration {booking.duration_min or 20} min"
    )
    return "\n".join(parts)


def _try_autodraft(
    db: Session,
    booking: Booking,
    lead: MeetingLeadSummary,
    *,
    force: bool = False,
    actor: str | None = None,
) -> tuple[MeetingNote, Optional[str]]:
    """Return (note, ai_skipped_reason). Never raises Gemini errors upstream."""
    note = db.query(MeetingNote).filter(MeetingNote.booking_id == booking.id).first()
    needs_draft = (
        force
        or (note is None)
        or (note.ai_drafted_at is None and (note.prep_md or "") == "")
    )
    if not needs_draft:
        return note, None  # type: ignore[return-value]

    if gemini_today_spend_usd(db) >= settings.ai_daily_budget_usd and not force:
        if note is None:
            note = MeetingNote(booking_id=booking.id)
            db.add(note)
            db.commit()
            db.refresh(note)
        return note, "budget_exhausted"

    prompt = _prep_prompt(lead, booking)
    try:
        text_out = call_gemini(prompt)
    except HTTPException:
        if note is None:
            note = MeetingNote(booking_id=booking.id)
            db.add(note)
            db.commit()
            db.refresh(note)
        return note, "upstream_error"

    if note is None:
        note = MeetingNote(booking_id=booking.id, prep_md=text_out)
        db.add(note)
    else:
        note.prep_md = text_out
    note.ai_drafted_at = datetime.now(timezone.utc)
    note.ai_model = GEMINI_MODEL
    note.updated_by = actor or "system_ai"
    db.commit()
    db.refresh(note)

    record_decision_row(
        db,
        request_type="meeting_prep",
        request_payload={
            "booking_id": str(booking.id),
            "lead_id": str(booking.lead_id),
        },
        response_payload={"chars": len(text_out)},
        cost_estimate_usd=cost_per_call_usd(),
    )
    return note, None


@router.post("/{booking_id}/ai-draft", response_model=MeetingNoteData)
def force_ai_draft(
    booking_id: UUID,
    body: AIDraftBody,
    db: Session = Depends(get_db),
    leads_db: Session = Depends(get_leads_db),
    user: User = Depends(require_operator),
) -> MeetingNoteData:
    if body.force and getattr(user, "role", "") != "admin":
        raise HTTPException(
            status_code=403, detail="Admin role required for force=true"
        )
    booking = _get_booking_or_404(db, booking_id)
    lead = _lead_summary(leads_db, booking.lead_id) or MeetingLeadSummary(
        lead_id=booking.lead_id, name="(lead not found)"
    )
    note, skipped = _try_autodraft(
        db,
        booking,
        lead,
        force=body.force,
        actor=getattr(user, "username", None) or getattr(user, "email", None),
    )
    payload = _notes_data(note)
    if skipped:
        payload.ai_skipped = skipped
    return payload
