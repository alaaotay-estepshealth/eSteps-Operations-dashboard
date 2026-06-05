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
