# Meeting Notes & Checklist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-meeting prep notes (markdown), post-call recap, and a checklist of action items to every upcoming meeting, with AI auto-draft on first open and overdue tasks bubbling into Followups and the Briefing.

**Architecture:** Materialize a `bookings` row per upcoming meeting (stable `booking_id` survives reschedules). Two new ops-DB tables: `meeting_notes` (1:1, prep + recap) and `meeting_tasks` (1:N, checklist). New FastAPI router `meetings.py` plus extensions to `bookings.py`, `followups.py`, `briefing.py`. Frontend adds `MeetingDrawer.vue` (used from Followups), `MeetingView.vue` (deep-linkable `/meeting/:id`), a markdown note editor with autosave, and a Gemini service shared with insights.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic v2, PostgreSQL (Supabase), pytest, Vue 3 `<script setup>`, axios, TailwindCSS, marked + DOMPurify, Gemini 2.5 Flash via httpx.

**Spec:** [docs/superpowers/specs/2026-06-05-meeting-notes-and-tickets-design.md](../specs/2026-06-05-meeting-notes-and-tickets-design.md)

---

## File Structure

**New backend files**
- `backend/app/models/meeting_note.py` — `MeetingNote` ORM
- `backend/app/models/meeting_task.py` — `MeetingTask` ORM
- `backend/app/services/gemini.py` — shared `call_gemini(prompt)` + `gemini_today_spend_usd()`
- `backend/app/routers/meetings.py` — list / detail / sync / notes / tasks / ai-draft
- `backend/tests/test_meetings_sync.py` — sync upsert + reschedule
- `backend/tests/test_meetings_router.py` — CRUD endpoints, auth, audit
- `backend/tests/test_meetings_ai.py` — Gemini mocked: success / 503 / budget
- `backend/tests/test_followups_bubble.py` — overdue task surfacing

**Modified backend files**
- `backend/app/models/booking.py` — add columns
- `backend/app/models/__init__.py` — export new models
- `backend/app/routers/bookings.py` — extend `/calendar` payload
- `backend/app/routers/followups.py` — add `open_meeting_tasks` section
- `backend/app/routers/briefing.py` — add `meeting_open_tasks` + `meetings_today`
- `backend/app/routers/insights.py` — call shared gemini service
- `backend/app/main.py` — register `meetings.router`
- `backend/app/schemas/responses.py` — Meeting* response models
- `schema.sql` — ALTER `bookings` + CREATE 2 tables + indexes

**New frontend files**
- `frontend/src/views/MeetingView.vue` — full-page route
- `frontend/src/components/MeetingDrawer.vue` — slide-in drawer (used from Followups)
- `frontend/src/components/MeetingTaskRow.vue` — single checklist row
- `frontend/src/components/MeetingNoteEditor.vue` — markdown editor + 4s autosave

**Modified frontend files**
- `frontend/src/api/index.js` — `meetingsAPI`
- `frontend/src/router/index.js` — `/meeting/:bookingId`
- `frontend/src/views/FollowupsView.vue` — clickable row → drawer; new section
- `frontend/src/views/BriefingView.vue` — "Meetings today" card + open-tasks badge
- `frontend/src/views/ContactsView.vue` — meeting bubble deep-link

---

## Task 1: Schema migration

**Files:**
- Modify: `dashboard-system/schema.sql` (append at end)

- [ ] **Step 1: Add the migration SQL**

Append to `schema.sql`:

```sql
-- ─── Meeting prep (ES-OPS-09-MEET-NOTES, 2026-06-05) ────────────────────────

ALTER TABLE bookings
  ADD COLUMN IF NOT EXISTS title TEXT,
  ADD COLUMN IF NOT EXISTS meeting_url TEXT,
  ADD COLUMN IF NOT EXISTS duration_min INT DEFAULT 20,
  ADD COLUMN IF NOT EXISTS rescheduled_from TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ix_bookings_scheduled_for ON bookings(scheduled_for);
CREATE INDEX IF NOT EXISTS ix_bookings_lead_status   ON bookings(lead_id, status);

CREATE TABLE IF NOT EXISTS meeting_notes (
  booking_id     UUID PRIMARY KEY REFERENCES bookings(id) ON DELETE CASCADE,
  prep_md        TEXT NOT NULL DEFAULT '',
  recap_md       TEXT NOT NULL DEFAULT '',
  ai_drafted_at  TIMESTAMPTZ,
  ai_model       TEXT,
  updated_by     TEXT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS meeting_tasks (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  booking_id   UUID NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
  title        TEXT NOT NULL,
  done         BOOLEAN NOT NULL DEFAULT FALSE,
  done_at      TIMESTAMPTZ,
  due_at       TIMESTAMPTZ,
  assignee     TEXT,
  order_index  INT NOT NULL DEFAULT 0,
  created_by   TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_tasks_booking_order ON meeting_tasks(booking_id, order_index);
CREATE INDEX IF NOT EXISTS ix_tasks_open_due
  ON meeting_tasks(due_at)
  WHERE done = FALSE AND due_at IS NOT NULL;
```

- [ ] **Step 2: Apply against the dev Supabase ops DB**

Run inside the Supabase SQL editor (project `eu-west-1` ops DB) or via `psql`. Verify with:

```sql
\d bookings
\d meeting_notes
\d meeting_tasks
```

Expected: `bookings` has the four new columns; both tables created; three indexes present.

- [ ] **Step 3: Commit**

```bash
git add schema.sql
git commit -m "feat(meetings): add bookings columns + meeting_notes/tasks tables"
```

---

## Task 2: ORM models

**Files:**
- Modify: `backend/app/models/booking.py`
- Create: `backend/app/models/meeting_note.py`
- Create: `backend/app/models/meeting_task.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Add columns to `Booking`**

Replace the content of `backend/app/models/booking.py` with:

```python
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), index=True, nullable=False)
    status = Column(String(50), default="scheduled", index=True)
    scheduled_for = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    canceled_at = Column(DateTime(timezone=True), nullable=True)
    no_show_detected = Column(Boolean, default=False)
    source = Column(String(50), nullable=True)
    external_id = Column(String(100), nullable=True)

    # ES-OPS-09-MEET-NOTES additions
    title = Column(Text, nullable=True)
    meeting_url = Column(Text, nullable=True)
    duration_min = Column(Integer, default=20)
    rescheduled_from = Column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 2: Create `MeetingNote` model**

Write `backend/app/models/meeting_note.py`:

```python
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class MeetingNote(Base):
    __tablename__ = "meeting_notes"

    booking_id = Column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        primary_key=True,
    )
    prep_md = Column(Text, nullable=False, default="")
    recap_md = Column(Text, nullable=False, default="")
    ai_drafted_at = Column(DateTime(timezone=True), nullable=True)
    ai_model = Column(Text, nullable=True)
    updated_by = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
```

- [ ] **Step 3: Create `MeetingTask` model**

Write `backend/app/models/meeting_task.py`:

```python
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class MeetingTask(Base):
    __tablename__ = "meeting_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id = Column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(Text, nullable=False)
    done = Column(Boolean, nullable=False, default=False)
    done_at = Column(DateTime(timezone=True), nullable=True)
    due_at = Column(DateTime(timezone=True), nullable=True)
    assignee = Column(Text, nullable=True)
    order_index = Column(Integer, nullable=False, default=0)
    created_by = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
```

- [ ] **Step 4: Export from package**

Edit `backend/app/models/__init__.py`. Add after the `MeetAsset` import:

```python
from app.models.meeting_note import MeetingNote
from app.models.meeting_task import MeetingTask
```

And add to `__all__`:

```python
    "MeetingNote",
    "MeetingTask",
```

- [ ] **Step 5: Smoke-import check**

Run:

```bash
cd dashboard-system/backend
python -c "from app.models import MeetingNote, MeetingTask, Booking; print(MeetingNote.__tablename__, MeetingTask.__tablename__, Booking.title)"
```

Expected: `meeting_notes meeting_tasks <sqlalchemy column>` (no ImportError, no AttributeError).

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/booking.py backend/app/models/meeting_note.py backend/app/models/meeting_task.py backend/app/models/__init__.py
git commit -m "feat(meetings): MeetingNote + MeetingTask ORM, Booking column extensions"
```

---

## Task 3: Pydantic response schemas

**Files:**
- Modify: `backend/app/schemas/responses.py`

- [ ] **Step 1: Append response models**

Append at the end of `backend/app/schemas/responses.py`:

```python
# ── Meeting notes & tasks ──────────────────────────────────────────────────

class MeetingTaskRow(BaseModel):
    id: UUID
    booking_id: UUID
    title: str
    done: bool
    done_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    assignee: Optional[str] = None
    order_index: int
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    overdue_by_hours: Optional[float] = None


class MeetingTaskCreate(BaseModel):
    title: str
    due_at: Optional[datetime] = None
    assignee: Optional[str] = None
    order_index: Optional[int] = None


class MeetingTaskUpdate(BaseModel):
    title: Optional[str] = None
    done: Optional[bool] = None
    due_at: Optional[datetime] = None
    assignee: Optional[str] = None
    order_index: Optional[int] = None


class MeetingNoteData(BaseModel):
    prep_md: str
    recap_md: str
    ai_drafted_at: Optional[datetime] = None
    ai_model: Optional[str] = None
    ai_skipped: Optional[str] = None  # "budget_exhausted" | "upstream_error" | None
    updated_by: Optional[str] = None
    updated_at: Optional[datetime] = None


class MeetingNoteUpdate(BaseModel):
    prep_md: Optional[str] = None
    recap_md: Optional[str] = None


class MeetingLeadSummary(BaseModel):
    lead_id: UUID
    name: Optional[str] = None
    institution: Optional[str] = None
    title: Optional[str] = None
    research_area: Optional[str] = None
    lead_score: Optional[float] = None
    stage: Optional[str] = None
    bio_excerpt: Optional[str] = None
    last_inbound_at: Optional[datetime] = None
    last_inbound_excerpt: Optional[str] = None


class MeetingBookingSummary(BaseModel):
    id: UUID
    lead_id: UUID
    title: Optional[str] = None
    status: str
    scheduled_for: Optional[datetime] = None
    duration_min: Optional[int] = None
    meeting_url: Optional[str] = None
    source: Optional[str] = None
    rescheduled_from: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    canceled_at: Optional[datetime] = None
    no_show_detected: bool = False


class PreviousMeeting(BaseModel):
    booking_id: UUID
    scheduled_for: Optional[datetime] = None
    status: str


class MeetingDetail(BaseModel):
    booking: MeetingBookingSummary
    lead: MeetingLeadSummary
    notes: MeetingNoteData
    tasks: List[MeetingTaskRow]
    previous_meetings: List[PreviousMeeting]


class MeetingListItem(BaseModel):
    booking_id: UUID
    lead_id: UUID
    lead_name: Optional[str] = None
    institution: Optional[str] = None
    scheduled_for: Optional[datetime] = None
    status: str
    open_task_count: int = 0
    has_notes: bool = False
    duration_min: Optional[int] = None


class MeetingSyncResult(BaseModel):
    created: int
    updated: int
    rescheduled: int
    skipped: int
    dry_run: bool


class OpenMeetingTaskRow(BaseModel):
    task_id: UUID
    booking_id: UUID
    lead_name: Optional[str] = None
    title: str
    due_at: Optional[datetime] = None
    overdue_by_hours: Optional[float] = None
```

- [ ] **Step 2: Smoke-import check**

```bash
cd dashboard-system/backend
python -c "from app.schemas.responses import MeetingDetail, MeetingTaskRow, MeetingSyncResult; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/responses.py
git commit -m "feat(meetings): Pydantic response models"
```

---

## Task 4: Shared Gemini service

**Files:**
- Create: `backend/app/services/gemini.py`
- Modify: `backend/app/routers/insights.py`

- [ ] **Step 1: Extract the helper**

Write `backend/app/services/gemini.py`:

```python
"""Shared Gemini 2.5 Flash client + daily-spend tracker.

Two callers today: routers/insights.py (memo + assistant) and
routers/meetings.py (prep auto-draft). Centralizing keeps the upstream
error handling identical and lets us share the daily-spend cache.
"""
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings

GEMINI_MODEL = "gemini-2.5-flash"
_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

# Soft per-call cost estimate (used until we wire real cost back from Gemini).
# Flash pricing approx $0.075 / 1M in + $0.30 / 1M out — we treat each call as
# ~1500 tokens combined ≈ $0.0006. Conservative enough for the budget guard.
_COST_PER_CALL_USD = 0.0006

# In-process cache for ai_today_spend so a meeting open doesn't query
# ai_decisions every time.
_spend_cache: dict = {"value": 0.0, "expires_at": 0.0}
_SPEND_CACHE_TTL_SEC = 60


def call_gemini(prompt: str, timeout: float = 30.0) -> str:
    """Single Gemini round-trip. Raises HTTPException on failure (caller decides)."""
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=503,
            detail="GEMINI_API_KEY not configured — add it to backend/.env.",
        )
    try:
        resp = httpx.post(
            _GEMINI_URL,
            params={"key": settings.gemini_api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except httpx.HTTPStatusError as e:
        upstream = ""
        try:
            err_json = e.response.json()
            upstream = err_json.get("error", {}).get("message", "")[:200]
        except Exception:
            upstream = (e.response.text or "")[:200]
        hint = ""
        if e.response.status_code in (401, 403):
            hint = " — check GEMINI_API_KEY is valid"
        elif e.response.status_code == 404:
            hint = f" — model '{GEMINI_MODEL}' not available on this key"
        elif e.response.status_code == 429:
            hint = " — quota exceeded; wait or upgrade plan"
        raise HTTPException(
            status_code=502,
            detail=f"Gemini upstream returned {e.response.status_code}{hint}. {upstream}".strip(),
        )
    except (KeyError, IndexError):
        raise HTTPException(status_code=502, detail="Unexpected response shape from Gemini")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="AI service unavailable")


def gemini_today_spend_usd(db: Session) -> float:
    """USD spent on Gemini today across all callers (60-s in-process cache).

    Reads from `ai_decisions` if it exists; otherwise returns 0.0. The table
    is created by webhooks/ai-decision; if it doesn't exist yet we silently
    return 0 — guard is intentionally a no-op until the table is in place.
    """
    now = time.time()
    if now < _spend_cache["expires_at"]:
        return _spend_cache["value"]
    try:
        spent = db.execute(
            text(
                "SELECT COALESCE(SUM(cost_estimate_usd), 0) FROM ai_decisions "
                "WHERE created_at::date = CURRENT_DATE"
            )
        ).scalar() or 0.0
        spent = float(spent)
    except Exception:
        spent = 0.0
    _spend_cache["value"] = spent
    _spend_cache["expires_at"] = now + _SPEND_CACHE_TTL_SEC
    return spent


def cost_per_call_usd() -> float:
    return _COST_PER_CALL_USD


def record_decision_row(
    db: Session,
    *,
    request_type: str,
    request_payload: dict,
    response_payload: dict,
    cost_estimate_usd: float = _COST_PER_CALL_USD,
    confidence: Optional[float] = None,
) -> None:
    """Best-effort write to ai_decisions. Silently no-ops if the table is missing."""
    try:
        db.execute(
            text(
                "INSERT INTO ai_decisions "
                "(request_type, request_payload, response_payload, cost_estimate_usd, "
                " confidence, created_at) "
                "VALUES (:rt, :rq::jsonb, :rs::jsonb, :cost, :conf, now())"
            ),
            {
                "rt": request_type,
                "rq": _json(request_payload),
                "rs": _json(response_payload),
                "cost": cost_estimate_usd,
                "conf": confidence,
            },
        )
        db.commit()
        # Invalidate the spend cache after a write so the next read is accurate.
        _spend_cache["expires_at"] = 0.0
    except Exception:
        db.rollback()


def _json(payload: dict) -> str:
    import json
    return json.dumps(payload, default=str)
```

- [ ] **Step 2: Switch `insights.py` to the shared helper**

In `backend/app/routers/insights.py`, replace the local `_call_gemini` (lines 313–350) with an import. At the top:

```python
from app.services.gemini import call_gemini, GEMINI_MODEL
```

And replace every `_call_gemini(prompt)` reference inside the module with `call_gemini(prompt)`. Delete the local function definition. Also replace the hard-coded model URL inside `/memo` (line ~277) with a call to `call_gemini(prompt)` — i.e. drop the inline httpx block and use the shared helper. Concretely, replace the `try: resp = httpx.post(...) ... return {"memo": memo, ...}` block with:

```python
    try:
        memo = call_gemini(prompt)
    except HTTPException:
        raise
    return {"memo": memo, "generated_at": datetime.utcnow().isoformat()}
```

- [ ] **Step 3: Smoke-import check**

```bash
cd dashboard-system/backend
python -c "from app.services.gemini import call_gemini, gemini_today_spend_usd; from app.routers import insights; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/gemini.py backend/app/routers/insights.py
git commit -m "refactor(ai): extract shared Gemini service from insights"
```

---

## Task 5: meetings router — sync (TDD)

**Files:**
- Create: `backend/tests/test_meetings_sync.py`
- Create: `backend/app/routers/meetings.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write the failing sync test**

Write `backend/tests/test_meetings_sync.py`:

```python
"""Sync upserts bookings idempotently from leads.meeting_scheduled_for."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


def _seed_lead(leads_db, *, scheduled_for=None):
    lead_id = uuid4()
    leads_db.execute(
        text(
            "INSERT INTO leads (id, first_name, last_name, institution, stage, "
            "meeting_scheduled_for, meeting_booked_at) "
            "VALUES (:id, 'Test', 'Lead', 'Mayo', 'pitching', :sched, now())"
        ),
        {"id": str(lead_id), "sched": scheduled_for},
    )
    leads_db.commit()
    return lead_id


def test_sync_creates_booking_for_each_lead_with_meeting(client, leads_db, db, admin_token):
    when = datetime.now(timezone.utc) + timedelta(days=2)
    lead_id = _seed_lead(leads_db, scheduled_for=when)

    res = client.post(
        "/admin/meetings/sync",
        json={"source": "manual"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["created"] >= 1

    rows = db.execute(
        text("SELECT id, scheduled_for FROM bookings WHERE lead_id = :lid"),
        {"lid": str(lead_id)},
    ).all()
    assert len(rows) == 1


def test_sync_is_idempotent(client, admin_token, db):
    before = db.execute(text("SELECT count(*) FROM bookings")).scalar()
    client.post("/admin/meetings/sync", json={"source": "manual"},
                headers={"Authorization": f"Bearer {admin_token}"})
    client.post("/admin/meetings/sync", json={"source": "manual"},
                headers={"Authorization": f"Bearer {admin_token}"})
    after = db.execute(text("SELECT count(*) FROM bookings")).scalar()
    assert after == before or after - before <= 1  # at most one fresh row from seed


def test_sync_updates_scheduled_for_within_window_keeps_id(client, leads_db, db, admin_token):
    original = datetime.now(timezone.utc) + timedelta(days=3)
    lead_id = _seed_lead(leads_db, scheduled_for=original)

    client.post("/admin/meetings/sync", json={"source": "manual"},
                headers={"Authorization": f"Bearer {admin_token}"})
    booking_id = db.execute(
        text("SELECT id FROM bookings WHERE lead_id = :lid"),
        {"lid": str(lead_id)},
    ).scalar()

    # Reschedule by 3 minutes (within ±5min window → same row)
    new_when = original + timedelta(minutes=3)
    leads_db.execute(
        text("UPDATE leads SET meeting_scheduled_for = :s WHERE id = :id"),
        {"s": new_when, "id": str(lead_id)},
    )
    leads_db.commit()

    res = client.post("/admin/meetings/sync", json={"source": "manual"},
                      headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    rows = db.execute(
        text("SELECT id, rescheduled_from FROM bookings WHERE lead_id = :lid"),
        {"lid": str(lead_id)},
    ).all()
    assert len(rows) == 1
    assert rows[0][0] == booking_id
    assert rows[0][1] is not None  # rescheduled_from stashed


def test_sync_dry_run_does_not_write(client, leads_db, db, admin_token):
    when = datetime.now(timezone.utc) + timedelta(days=4)
    _seed_lead(leads_db, scheduled_for=when)
    before = db.execute(text("SELECT count(*) FROM bookings")).scalar()
    res = client.post("/admin/meetings/sync", json={"source": "manual", "dry_run": True},
                      headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    after = db.execute(text("SELECT count(*) FROM bookings")).scalar()
    assert after == before
    assert res.json()["dry_run"] is True


def test_sync_requires_admin(client, operator_token):
    res = client.post("/admin/meetings/sync", json={"source": "manual"},
                      headers={"Authorization": f"Bearer {operator_token}"})
    assert res.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd dashboard-system/backend
pytest tests/test_meetings_sync.py -v
```

Expected: 5 failures — fixtures `client / leads_db / db / admin_token / operator_token` may already exist in `conftest.py`; the endpoint `/admin/meetings/sync` returns 404.

- [ ] **Step 3: Add the missing fixtures (if any are not present)**

Inspect `backend/tests/conftest.py`. If `admin_token` / `operator_token` / `leads_db` are missing, append:

```python
import pytest
from sqlalchemy.orm import Session

from app.auth import create_access_token
from app.database import get_leads_db


@pytest.fixture
def admin_token():
    return create_access_token({"sub": "test-admin", "role": "admin"})


@pytest.fixture
def operator_token():
    return create_access_token({"sub": "test-op", "role": "operator"})


@pytest.fixture
def leads_db():
    gen = get_leads_db()
    db: Session = next(gen)
    try:
        yield db
    finally:
        try:
            next(gen)
        except StopIteration:
            pass
```

- [ ] **Step 4: Implement the meetings router (sync only first)**

Write `backend/app/routers/meetings.py`:

```python
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
        if delta <= _SYNC_WINDOW.total_seconds():
            skipped += 1
            continue

        # Outside window → reschedule the existing row in place (keep id).
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
```

- [ ] **Step 5: Register the router**

In `backend/app/main.py`, add to the imports block (next to other routers):

```python
from app.routers import meetings
```

And register near the other `include_router` calls:

```python
app.include_router(meetings.router)
```

- [ ] **Step 6: Run tests — they should pass**

```bash
cd dashboard-system/backend
pytest tests/test_meetings_sync.py -v
```

Expected: 5 PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/meetings.py backend/app/main.py backend/tests/test_meetings_sync.py backend/tests/conftest.py
git commit -m "feat(meetings): /sync endpoint with upsert + reschedule window"
```

---

## Task 6: meetings router — list + detail (TDD)

**Files:**
- Create: `backend/tests/test_meetings_router.py`
- Modify: `backend/app/routers/meetings.py`

- [ ] **Step 1: Add list/detail tests**

Write `backend/tests/test_meetings_router.py`:

```python
"""List + detail endpoints for meetings."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


def _seed_booking(db, lead_id, *, when=None):
    bid = uuid4()
    db.execute(
        text(
            "INSERT INTO bookings (id, lead_id, status, scheduled_for, duration_min) "
            "VALUES (:id, :lid, 'scheduled', :when, 20)"
        ),
        {"id": str(bid), "lid": str(lead_id), "when": when or datetime.now(timezone.utc) + timedelta(hours=4)},
    )
    db.commit()
    return bid


def test_list_returns_paginated_meetings(client, db, leads_db, admin_token):
    lid = uuid4()
    leads_db.execute(
        text("INSERT INTO leads (id, first_name, last_name, institution, stage) "
             "VALUES (:id, 'X', 'Y', 'Mayo', 'pitching')"),
        {"id": str(lid)},
    )
    leads_db.commit()
    _seed_booking(db, lid)

    res = client.get("/admin/meetings", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    items = res.json()
    assert isinstance(items, list)
    assert any(str(i["lead_id"]) == str(lid) for i in items)


def test_detail_returns_booking_lead_empty_notes(client, db, leads_db, admin_token):
    lid = uuid4()
    leads_db.execute(
        text("INSERT INTO leads (id, first_name, last_name, institution, stage, lead_score) "
             "VALUES (:id, 'A', 'B', 'Stanford', 'pitching', 8.5)"),
        {"id": str(lid)},
    )
    leads_db.commit()
    bid = _seed_booking(db, lid)

    res = client.get(f"/admin/meetings/{bid}", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    body = res.json()
    assert body["booking"]["id"] == str(bid)
    assert body["lead"]["name"] == "A B"
    assert body["tasks"] == []
    assert "prep_md" in body["notes"]


def test_detail_not_found(client, admin_token):
    res = client.get(f"/admin/meetings/{uuid4()}", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 404


def test_list_requires_auth(client):
    res = client.get("/admin/meetings")
    assert res.status_code == 401
```

- [ ] **Step 2: Implement list + detail handlers**

Append to `backend/app/routers/meetings.py`:

```python
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
    lead_rows = {}
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
```

- [ ] **Step 3: Run the tests**

```bash
cd dashboard-system/backend
pytest tests/test_meetings_router.py -v
```

Expected: 4 PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/meetings.py backend/tests/test_meetings_router.py
git commit -m "feat(meetings): list + detail endpoints"
```

---

## Task 7: meetings router — notes + tasks CRUD

**Files:**
- Modify: `backend/app/routers/meetings.py`
- Modify: `backend/tests/test_meetings_router.py`

- [ ] **Step 1: Add CRUD tests**

Append to `backend/tests/test_meetings_router.py`:

```python
def test_patch_notes_updates_prep_and_recap(client, db, leads_db, operator_token, admin_token):
    lid = uuid4()
    leads_db.execute(text("INSERT INTO leads (id, first_name, last_name) VALUES (:id, 'P', 'Q')"),
                     {"id": str(lid)})
    leads_db.commit()
    bid = _seed_booking(db, lid)
    res = client.patch(
        f"/admin/meetings/{bid}/notes",
        json={"prep_md": "ask about IRB", "recap_md": ""},
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert res.status_code == 200
    detail = client.get(f"/admin/meetings/{bid}",
                        headers={"Authorization": f"Bearer {admin_token}"}).json()
    assert detail["notes"]["prep_md"] == "ask about IRB"


def test_notes_patch_requires_operator(client, db, leads_db):
    from app.auth import create_access_token
    readonly = create_access_token({"sub": "v", "role": "readonly"})
    lid = uuid4()
    leads_db.execute(text("INSERT INTO leads (id, first_name, last_name) VALUES (:id, 'R', 'O')"),
                     {"id": str(lid)})
    leads_db.commit()
    bid = _seed_booking(db, lid)
    res = client.patch(f"/admin/meetings/{bid}/notes", json={"prep_md": "nope"},
                       headers={"Authorization": f"Bearer {readonly}"})
    assert res.status_code == 403


def test_task_create_update_delete(client, db, leads_db, operator_token, admin_token):
    lid = uuid4()
    leads_db.execute(text("INSERT INTO leads (id, first_name, last_name) VALUES (:id, 'T', 'D')"),
                     {"id": str(lid)})
    leads_db.commit()
    bid = _seed_booking(db, lid)

    create = client.post(
        f"/admin/meetings/{bid}/tasks",
        json={"title": "Send case study"},
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert create.status_code == 200
    task_id = create.json()["id"]

    upd = client.patch(
        f"/admin/meetings/{bid}/tasks/{task_id}",
        json={"done": True},
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert upd.status_code == 200
    assert upd.json()["done"] is True
    assert upd.json()["done_at"] is not None

    rem = client.delete(
        f"/admin/meetings/{bid}/tasks/{task_id}",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert rem.status_code == 200

    detail = client.get(f"/admin/meetings/{bid}",
                        headers={"Authorization": f"Bearer {admin_token}"}).json()
    assert detail["tasks"] == []


def test_task_404_when_wrong_booking(client, db, leads_db, operator_token):
    lid = uuid4()
    leads_db.execute(text("INSERT INTO leads (id, first_name, last_name) VALUES (:id, 'A', 'C')"),
                     {"id": str(lid)})
    leads_db.commit()
    bid = _seed_booking(db, lid)
    create = client.post(f"/admin/meetings/{bid}/tasks", json={"title": "x"},
                         headers={"Authorization": f"Bearer {operator_token}"})
    task_id = create.json()["id"]
    other = uuid4()
    res = client.patch(f"/admin/meetings/{other}/tasks/{task_id}", json={"done": True},
                       headers={"Authorization": f"Bearer {operator_token}"})
    assert res.status_code == 404
```

- [ ] **Step 2: Implement the CRUD handlers**

Append to `backend/app/routers/meetings.py`:

```python
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
    _audit(db, user, "meetings.notes.update", str(booking_id),
           {"prep_changed": body.prep_md is not None, "recap_changed": body.recap_md is not None})
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
        order_index=body.order_index if body.order_index is not None else ((next_order or 0) + 1),
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
    _audit(db, user, "meetings.task.update", str(booking_id),
           {"task_id": str(task.id), "fields": body.model_dump(exclude_none=True)})
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
```

- [ ] **Step 3: Run the tests**

```bash
cd dashboard-system/backend
pytest tests/test_meetings_router.py -v
```

Expected: all 8 PASS (4 prior + 4 new).

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/meetings.py backend/tests/test_meetings_router.py
git commit -m "feat(meetings): notes + tasks CRUD with role gates + audit"
```

---

## Task 8: AI auto-draft (TDD)

**Files:**
- Create: `backend/tests/test_meetings_ai.py`
- Modify: `backend/app/routers/meetings.py`

- [ ] **Step 1: Write the AI tests**

Write `backend/tests/test_meetings_ai.py`:

```python
"""Auto-draft on first detail open + manual /ai-draft endpoint."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


def _seed(db, leads_db):
    lid = uuid4()
    leads_db.execute(
        text("INSERT INTO leads (id, first_name, last_name, institution, research_area, "
             "lead_score, stage, bio) VALUES (:id, 'Jane', 'Elder', 'Mayo', 'Cardiology', 9.0, "
             "'pitching', 'Cardiology research, IRB-approved studies')"),
        {"id": str(lid)},
    )
    leads_db.commit()
    bid = uuid4()
    db.execute(
        text("INSERT INTO bookings (id, lead_id, status, scheduled_for, duration_min) "
             "VALUES (:id, :lid, 'scheduled', :when, 20)"),
        {"id": str(bid), "lid": str(lid),
         "when": datetime.now(timezone.utc) + timedelta(hours=6)},
    )
    db.commit()
    return bid


def test_first_detail_open_autodrafts_prep(monkeypatch, client, db, leads_db, admin_token):
    bid = _seed(db, leads_db)
    monkeypatch.setattr(
        "app.routers.meetings.call_gemini",
        lambda prompt, timeout=30.0: "## Why this lead matters\nStrong cardiology fit.",
    )
    res = client.get(f"/admin/meetings/{bid}", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    body = res.json()
    assert "Why this lead matters" in body["notes"]["prep_md"]
    assert body["notes"]["ai_drafted_at"] is not None
    assert body["notes"]["ai_model"] == "gemini-2.5-flash"


def test_second_open_does_not_redraft(monkeypatch, client, db, leads_db, admin_token):
    bid = _seed(db, leads_db)
    calls = {"n": 0}

    def fake(prompt, timeout=30.0):
        calls["n"] += 1
        return "draft once"

    monkeypatch.setattr("app.routers.meetings.call_gemini", fake)
    client.get(f"/admin/meetings/{bid}", headers={"Authorization": f"Bearer {admin_token}"})
    client.get(f"/admin/meetings/{bid}", headers={"Authorization": f"Bearer {admin_token}"})
    assert calls["n"] == 1


def test_gemini_5xx_skips_draft_gracefully(monkeypatch, client, db, leads_db, admin_token):
    from fastapi import HTTPException

    def boom(prompt, timeout=30.0):
        raise HTTPException(status_code=502, detail="Gemini upstream returned 503")

    monkeypatch.setattr("app.routers.meetings.call_gemini", boom)
    bid = _seed(db, leads_db)
    res = client.get(f"/admin/meetings/{bid}", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    notes = res.json()["notes"]
    assert notes["prep_md"] == ""
    assert notes["ai_skipped"] == "upstream_error"


def test_budget_exhausted_skips_draft(monkeypatch, client, db, leads_db, admin_token):
    monkeypatch.setattr("app.routers.meetings.gemini_today_spend_usd", lambda db_: 999.0)
    monkeypatch.setattr("app.routers.meetings.call_gemini",
                        lambda *a, **kw: pytest.fail("should not be called"))
    bid = _seed(db, leads_db)
    res = client.get(f"/admin/meetings/{bid}", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    assert res.json()["notes"]["ai_skipped"] == "budget_exhausted"


def test_force_ai_draft_overrides(monkeypatch, client, db, leads_db, admin_token, operator_token):
    bid = _seed(db, leads_db)
    monkeypatch.setattr("app.routers.meetings.call_gemini", lambda *a, **kw: "first draft")
    client.get(f"/admin/meetings/{bid}", headers={"Authorization": f"Bearer {admin_token}"})

    monkeypatch.setattr("app.routers.meetings.call_gemini", lambda *a, **kw: "second draft")
    # operator can re-draft (without force) only when existing note allows; with force needs admin
    res = client.post(
        f"/admin/meetings/{bid}/ai-draft",
        json={"force": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    assert "second draft" in res.json()["prep_md"]
```

- [ ] **Step 2: Implement the AI draft logic**

Append to `backend/app/routers/meetings.py`:

```python
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
        delta = (booking.scheduled_for - datetime.now(timezone.utc)).total_seconds() / 3600
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
    parts.append(f"Meeting in {hours_until} hours · duration {booking.duration_min or 20} min")
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
    needs_draft = force or (note is None) or (note.ai_drafted_at is None and (note.prep_md or "") == "")
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
        request_payload={"booking_id": str(booking.id), "lead_id": str(booking.lead_id)},
        response_payload={"chars": len(text_out)},
        cost_estimate_usd=cost_per_call_usd(),
    )
    return note, None
```

Then modify `get_meeting` to call `_try_autodraft` before building the response. Replace the body of the existing handler with:

```python
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
        db, booking, lead, actor=getattr(user, "username", None) or getattr(user, "email", None)
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
            PreviousMeeting(booking_id=p.id, scheduled_for=p.scheduled_for, status=p.status)
            for p in prev
        ],
    )


@router.post("/{booking_id}/ai-draft", response_model=MeetingNoteData)
def force_ai_draft(
    booking_id: UUID,
    body: AIDraftBody,
    db: Session = Depends(get_db),
    leads_db: Session = Depends(get_leads_db),
    user: User = Depends(require_operator),
) -> MeetingNoteData:
    if body.force and getattr(user, "role", "") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required for force=true")
    booking = _get_booking_or_404(db, booking_id)
    lead = _lead_summary(leads_db, booking.lead_id) or MeetingLeadSummary(
        lead_id=booking.lead_id, name="(lead not found)"
    )
    note, skipped = _try_autodraft(
        db, booking, lead, force=body.force,
        actor=getattr(user, "username", None) or getattr(user, "email", None),
    )
    payload = _notes_data(note)
    if skipped:
        payload.ai_skipped = skipped
    return payload
```

- [ ] **Step 3: Run the AI tests**

```bash
cd dashboard-system/backend
pytest tests/test_meetings_ai.py -v
```

Expected: 5 PASS.

- [ ] **Step 4: Re-run all meeting tests**

```bash
pytest tests/test_meetings_router.py tests/test_meetings_sync.py tests/test_meetings_ai.py -v
```

Expected: 17 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/meetings.py backend/tests/test_meetings_ai.py
git commit -m "feat(meetings): AI auto-draft on first open + force ai-draft endpoint"
```

---

## Task 9: Followups + briefing wiring (TDD)

**Files:**
- Create: `backend/tests/test_followups_bubble.py`
- Modify: `backend/app/routers/followups.py`
- Modify: `backend/app/routers/briefing.py`
- Modify: `backend/app/routers/bookings.py`

- [ ] **Step 1: Bubble test**

Write `backend/tests/test_followups_bubble.py`:

```python
"""Overdue meeting tasks bubble into /admin/followups + briefing counts."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


def test_overdue_meeting_task_appears_in_followups(client, db, leads_db, admin_token):
    lid = uuid4()
    leads_db.execute(
        text("INSERT INTO leads (id, first_name, last_name, stage) "
             "VALUES (:id, 'A', 'B', 'pitching')"),
        {"id": str(lid)},
    )
    leads_db.commit()
    bid = uuid4()
    db.execute(
        text("INSERT INTO bookings (id, lead_id, status, scheduled_for) "
             "VALUES (:id, :lid, 'scheduled', :w)"),
        {"id": str(bid), "lid": str(lid),
         "w": datetime.now(timezone.utc) + timedelta(days=2)},
    )
    db.execute(
        text("INSERT INTO meeting_tasks (id, booking_id, title, due_at) "
             "VALUES (:id, :bid, 'Send PDF', :d)"),
        {"id": str(uuid4()), "bid": str(bid),
         "d": datetime.now(timezone.utc) - timedelta(hours=4)},
    )
    db.commit()

    res = client.get("/admin/followups", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    body = res.json()
    assert "open_meeting_tasks" in body
    assert body["open_meeting_tasks"]["count"] >= 1
    titles = [t["title"] for t in body["open_meeting_tasks"]["tasks"]]
    assert "Send PDF" in titles


def test_briefing_includes_meeting_open_tasks(client, db, leads_db, admin_token):
    res = client.get("/admin/briefing", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    body = res.json()
    assert "meeting_open_tasks" in body["priorities"]
    assert "meetings_today" in body["priorities"]


def test_calendar_includes_booking_id_and_task_counts(client, admin_token):
    res = client.get("/admin/bookings/calendar",
                     headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    meetings = res.json().get("meetings", [])
    if meetings:
        sample = meetings[0]
        assert "booking_id" in sample
        assert "open_task_count" in sample
        assert "has_notes" in sample
```

- [ ] **Step 2: Wire `followups.py`**

Replace `backend/app/routers/followups.py` entirely with:

```python
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
```

- [ ] **Step 3: Wire `briefing.py`**

Modify `backend/app/routers/briefing.py`. Add inside `get_briefing` before the return:

```python
    try:
        open_meeting_tasks = db.execute(
            text("SELECT count(*) FROM meeting_tasks WHERE done = FALSE")
        ).scalar() or 0
    except Exception:
        open_meeting_tasks = 0
    try:
        meetings_today = db.execute(
            text("SELECT count(*) FROM bookings "
                 "WHERE scheduled_for >= date_trunc('day', now()) "
                 "AND scheduled_for <  date_trunc('day', now()) + interval '1 day'")
        ).scalar() or 0
    except Exception:
        meetings_today = 0
```

And extend the `priorities` dict in the return value:

```python
        "priorities": {
            "overdue": overdue,
            "due_today": due_today,
            "upcoming_meetings": upcoming_meetings,
            "hot_uncontacted": hot_uncontacted,
            "meeting_open_tasks": open_meeting_tasks,
            "meetings_today": meetings_today,
        },
```

- [ ] **Step 4: Extend `/admin/bookings/calendar`**

In `backend/app/routers/bookings.py`, modify `calendar_meetings`. After the existing query, also fetch a `bookings`-table view, then merge:

Replace the function with:

```python
@router.get("/calendar")
def calendar_meetings(
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = Query(None),
    leads_db: Session = Depends(get_leads_db),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    today = date.today()
    start = from_ or (today.replace(day=1))
    if to is None:
        next_month_first = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        end = (next_month_first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    else:
        end = to
    if end < start:
        raise HTTPException(status_code=400, detail="`to` must be >= `from`")

    # Bookings table (ops) first — these can have booking_id / notes / tasks.
    booking_rows = db.execute(
        text(
            "SELECT id AS booking_id, lead_id, scheduled_for, status "
            "FROM bookings WHERE scheduled_for >= :start AND scheduled_for < :end_excl "
            "ORDER BY scheduled_for ASC"
        ),
        {"start": start, "end_excl": end + timedelta(days=1)},
    ).mappings().all()

    booking_ids = [r["booking_id"] for r in booking_rows]
    has_notes = {
        str(b)
        for (b,) in db.execute(
            text("SELECT booking_id FROM meeting_notes WHERE booking_id = ANY(:ids)"),
            {"ids": [str(i) for i in booking_ids]},
        ).all() if booking_ids
    }
    open_counts = {
        str(bid): int(cnt)
        for bid, cnt in db.execute(
            text("SELECT booking_id, count(*) FROM meeting_tasks "
                 "WHERE done = FALSE AND booking_id = ANY(:ids) GROUP BY booking_id"),
            {"ids": [str(i) for i in booking_ids]},
        ).all() if booking_ids
    }

    lead_ids = list({r["lead_id"] for r in booking_rows})
    leads_by_id = {}
    if lead_ids:
        for r in leads_db.execute(
            text("SELECT id, CONCAT(first_name, ' ', last_name) AS name, institution "
                 "FROM leads WHERE id = ANY(:ids)"),
            {"ids": [str(i) for i in lead_ids]},
        ).mappings().all():
            leads_by_id[str(r["id"])] = r

    bookings_payload = []
    seen_lead_times: set = set()
    for r in booking_rows:
        lead = leads_by_id.get(str(r["lead_id"]), {})
        when = r["scheduled_for"]
        seen_lead_times.add((str(r["lead_id"]), when.isoformat() if when else None))
        bookings_payload.append({
            "booking_id": str(r["booking_id"]),
            "lead_id": str(r["lead_id"]),
            "lead_name": lead.get("name"),
            "institution": lead.get("institution"),
            "when": when.isoformat() if when else None,
            "source": "booking",
            "status": "past" if when and when < datetime.now(tz=when.tzinfo).replace(tzinfo=when.tzinfo) else "upcoming",
            "open_task_count": open_counts.get(str(r["booking_id"]), 0),
            "has_notes": str(r["booking_id"]) in has_notes,
        })

    # Fallback: lead-derived meetings without a bookings row yet.
    rows = leads_db.execute(
        text(
            "SELECT id AS lead_id, CONCAT(first_name, ' ', last_name) AS lead_name, "
            "institution, meeting_scheduled_for AS when_ "
            "FROM leads WHERE meeting_scheduled_for IS NOT NULL "
            "AND meeting_scheduled_for >= :start AND meeting_scheduled_for < :end_excl "
            "ORDER BY meeting_scheduled_for ASC"
        ),
        {"start": start, "end_excl": end + timedelta(days=1)},
    ).mappings().all()
    for r in rows:
        when = r["when_"]
        key = (str(r["lead_id"]), when.isoformat() if when else None)
        if key in seen_lead_times:
            continue
        bookings_payload.append({
            "booking_id": None,
            "lead_id": str(r["lead_id"]),
            "lead_name": r["lead_name"],
            "institution": r["institution"],
            "when": when.isoformat() if when else None,
            "source": "lead",
            "status": "past" if when and when <= datetime.now(tz=when.tzinfo).replace(tzinfo=when.tzinfo) else "upcoming",
            "open_task_count": 0,
            "has_notes": False,
        })

    return {"from": start.isoformat(), "to": end.isoformat(), "meetings": bookings_payload}
```

Add at top of file:

```python
from app.database import get_db
```

- [ ] **Step 5: Run the bubble tests**

```bash
cd dashboard-system/backend
pytest tests/test_followups_bubble.py -v
```

Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/followups.py backend/app/routers/briefing.py backend/app/routers/bookings.py backend/tests/test_followups_bubble.py
git commit -m "feat(meetings): bubble overdue tasks into followups + briefing"
```

---

## Task 10: Frontend API client

**Files:**
- Modify: `frontend/src/api/index.js`

- [ ] **Step 1: Add `meetingsAPI`**

Insert before the `export default api` line:

```javascript
export const meetingsAPI = {
  list:    (params = {}) => api.get('/admin/meetings', { params }),
  get:     (bookingId) => api.get(`/admin/meetings/${bookingId}`),
  patchNotes: (bookingId, body) => api.patch(`/admin/meetings/${bookingId}/notes`, body),
  createTask: (bookingId, body) => api.post(`/admin/meetings/${bookingId}/tasks`, body),
  updateTask: (bookingId, taskId, body) =>
    api.patch(`/admin/meetings/${bookingId}/tasks/${taskId}`, body),
  deleteTask: (bookingId, taskId) =>
    api.delete(`/admin/meetings/${bookingId}/tasks/${taskId}`),
  aiDraft: (bookingId, force = false) =>
    api.post(`/admin/meetings/${bookingId}/ai-draft`, { force }),
  sync: (body = { source: 'manual' }) => api.post('/admin/meetings/sync', body),
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/index.js
git commit -m "feat(meetings): meetingsAPI client"
```

---

## Task 11: Markdown editor + task row components

**Files:**
- Create: `frontend/src/components/MeetingNoteEditor.vue`
- Create: `frontend/src/components/MeetingTaskRow.vue`

- [ ] **Step 1: Write `MeetingNoteEditor.vue`**

```vue
<template>
  <div class="space-y-2">
    <div class="flex items-center justify-between text-2xs text-ctrl-muted">
      <span v-if="aiDraftedAt">AI-drafted · {{ aiModel }} · {{ relTime(aiDraftedAt) }}</span>
      <span v-else>{{ updatedBy ? `Edited by ${updatedBy}` : 'No content yet' }}</span>
      <span :class="dirty ? 'text-status-warn' : 'text-ctrl-dim'">
        {{ dirty ? 'Saving…' : 'Saved' }}
      </span>
    </div>
    <textarea
      v-model="local"
      :placeholder="placeholder"
      class="w-full min-h-[300px] bg-ctrl-panel border border-ctrl-border rounded p-3 text-sm font-mono text-ctrl-text focus:outline-none focus:border-status-info"
      @input="onInput"
    />
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: 'Write notes in markdown…' },
  aiDraftedAt: { type: String, default: null },
  aiModel: { type: String, default: null },
  updatedBy: { type: String, default: null },
})
const emit = defineEmits(['update:modelValue', 'save'])

const local = ref(props.modelValue || '')
const dirty = ref(false)
let timer = null

watch(() => props.modelValue, (v) => {
  if (!dirty.value) local.value = v || ''
})

function onInput() {
  dirty.value = true
  emit('update:modelValue', local.value)
  if (timer) clearTimeout(timer)
  timer = setTimeout(async () => {
    try {
      await emit('save', local.value)
      dirty.value = false
    } catch {
      // Toast handled by parent
    }
  }, 4000)
}

function relTime(iso) {
  if (!iso) return ''
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return `${Math.round(diff)}s ago`
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
  return `${Math.round(diff / 86400)}d ago`
}
</script>
```

- [ ] **Step 2: Write `MeetingTaskRow.vue`**

```vue
<template>
  <div class="group flex items-center gap-2 py-1.5 border-b border-ctrl-border/40 last:border-0">
    <input
      type="checkbox"
      :checked="task.done"
      class="w-4 h-4 accent-status-ok cursor-pointer"
      @change="$emit('toggle', !task.done)"
    />
    <div class="flex-1 min-w-0">
      <input
        v-if="editing"
        v-model="draft"
        @keyup.enter="commit"
        @blur="commit"
        class="w-full bg-transparent border-b border-ctrl-border text-sm text-ctrl-text focus:outline-none focus:border-status-info"
      />
      <span
        v-else
        :class="task.done ? 'line-through text-ctrl-dim' : 'text-ctrl-text'"
        class="text-sm cursor-text"
        @click="startEdit"
      >{{ task.title }}</span>
    </div>
    <span
      v-if="task.due_at"
      :class="task.overdue_by_hours ? 'text-status-err' : 'text-ctrl-muted'"
      class="text-2xs tabnum"
    >
      {{ formatDue(task) }}
    </span>
    <button
      class="opacity-0 group-hover:opacity-100 text-ctrl-dim hover:text-status-err transition-opacity text-2xs"
      @click="$emit('delete')"
      title="Delete task"
    >×</button>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  task: { type: Object, required: true },
})
const emit = defineEmits(['toggle', 'rename', 'delete'])

const editing = ref(false)
const draft = ref(props.task.title)

function startEdit() {
  draft.value = props.task.title
  editing.value = true
}

function commit() {
  if (!editing.value) return
  editing.value = false
  const next = (draft.value || '').trim()
  if (next && next !== props.task.title) emit('rename', next)
}

function formatDue(t) {
  if (!t.due_at) return ''
  if (t.overdue_by_hours) return `${Math.round(t.overdue_by_hours)}h overdue`
  const diffH = (new Date(t.due_at).getTime() - Date.now()) / 3600000
  if (diffH < 24) return `due in ${Math.round(diffH)}h`
  return `due in ${Math.round(diffH / 24)}d`
}
</script>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/MeetingNoteEditor.vue frontend/src/components/MeetingTaskRow.vue
git commit -m "feat(meetings): note editor + task row components"
```

---

## Task 12: `MeetingDrawer.vue`

**Files:**
- Create: `frontend/src/components/MeetingDrawer.vue`

- [ ] **Step 1: Write the drawer**

```vue
<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
      @click="$emit('close')"
    />
    <aside
      v-if="open"
      class="fixed top-0 right-0 z-50 h-full w-full md:w-[80vw] lg:w-[60vw] bg-ctrl-bg border-l border-ctrl-border flex flex-col"
    >
      <header class="flex items-center justify-between p-4 border-b border-ctrl-border">
        <div class="min-w-0">
          <div class="font-display text-sm text-ctrl-text truncate">
            {{ detail?.lead?.name || '…' }}
            <span v-if="detail?.lead?.institution" class="text-ctrl-muted">· {{ detail.lead.institution }}</span>
          </div>
          <div class="text-2xs text-ctrl-muted">
            <span v-if="detail?.booking?.scheduled_for">{{ whenLabel }}</span>
            <span v-if="detail?.booking?.rescheduled_from" class="ml-2 text-status-warn">
              Rescheduled from {{ fmt(detail.booking.rescheduled_from) }}
            </span>
          </div>
          <div v-if="detail?.previous_meetings?.length" class="text-2xs text-ctrl-dim mt-1">
            Previous: {{ detail.previous_meetings.length }} meeting{{ detail.previous_meetings.length === 1 ? '' : 's' }}
            (last {{ relPast(detail.previous_meetings[0].scheduled_for) }})
          </div>
        </div>
        <div class="flex items-center gap-2">
          <RouterLink
            v-if="bookingId"
            :to="`/meeting/${bookingId}`"
            class="px-2 py-1 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text"
          >Open full page ↗</RouterLink>
          <button class="px-2 py-1 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-status-ok" @click="markHeld">Mark held</button>
          <button class="px-2 py-1 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-status-err" @click="markNoShow">No-show</button>
          <button class="text-ctrl-muted hover:text-ctrl-text" @click="$emit('close')" aria-label="Close">×</button>
        </div>
      </header>

      <div class="flex items-center gap-1 px-4 pt-3 border-b border-ctrl-border">
        <button
          v-for="t in ['Prep', 'Recap', `Checklist ${doneCount}/${totalCount}`]"
          :key="t"
          @click="tab = t.split(' ')[0].toLowerCase()"
          :class="tab === t.split(' ')[0].toLowerCase()
            ? 'border-status-info text-ctrl-text'
            : 'border-transparent text-ctrl-muted hover:text-ctrl-text'"
          class="px-3 py-1.5 text-xs border-b-2 transition-colors"
        >{{ t }}</button>
      </div>

      <div class="flex-1 overflow-y-auto p-4 space-y-3">
        <div v-if="loading" class="text-xs text-ctrl-muted">Loading…</div>
        <div v-else-if="error" class="text-xs text-status-err">{{ error }}</div>
        <template v-else-if="detail">
          <div v-if="detail.notes?.ai_skipped === 'budget_exhausted'"
               class="text-2xs text-status-warn p-2 border border-status-warn/40 rounded">
            AI draft skipped — daily budget exhausted.
            <button v-if="isAdmin" class="ml-2 underline" @click="redraft(true)">Force redraft</button>
          </div>
          <div v-else-if="detail.notes?.ai_skipped === 'upstream_error'"
               class="text-2xs text-status-warn p-2 border border-status-warn/40 rounded">
            AI draft failed — Gemini upstream error.
            <button class="ml-2 underline" @click="redraft(false)">Retry</button>
          </div>

          <MeetingNoteEditor
            v-if="tab === 'prep'"
            v-model="prepDraft"
            placeholder="Prep notes…"
            :ai-drafted-at="detail.notes?.ai_drafted_at"
            :ai-model="detail.notes?.ai_model"
            :updated-by="detail.notes?.updated_by"
            @save="savePrep"
          />
          <MeetingNoteEditor
            v-else-if="tab === 'recap'"
            v-model="recapDraft"
            placeholder="What happened, what was agreed, next steps…"
            :updated-by="detail.notes?.updated_by"
            @save="saveRecap"
          />
          <div v-else class="space-y-1">
            <form @submit.prevent="addTask" class="flex items-center gap-2 mb-2">
              <input
                v-model="newTask"
                placeholder="+ Add task and press Enter"
                class="flex-1 bg-ctrl-panel border border-ctrl-border rounded px-3 py-1.5 text-sm text-ctrl-text focus:outline-none focus:border-status-info"
              />
            </form>
            <MeetingTaskRow
              v-for="t in detail.tasks"
              :key="t.id"
              :task="t"
              @toggle="(d) => toggleTask(t, d)"
              @rename="(n) => renameTask(t, n)"
              @delete="deleteTask(t)"
            />
            <div v-if="!detail.tasks.length" class="text-2xs text-ctrl-dim py-3">No tasks yet.</div>
          </div>
        </template>
      </div>
    </aside>
  </Teleport>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { meetingsAPI } from '../api/index.js'
import { useAuthStore } from '../stores/auth.js'
import MeetingNoteEditor from './MeetingNoteEditor.vue'
import MeetingTaskRow from './MeetingTaskRow.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  bookingId: { type: String, default: null },
})
const emit = defineEmits(['close', 'changed'])

const auth = useAuthStore()
const isAdmin = computed(() => auth.role === 'admin')

const tab = ref('prep')
const loading = ref(false)
const error = ref('')
const detail = ref(null)
const prepDraft = ref('')
const recapDraft = ref('')
const newTask = ref('')

const totalCount = computed(() => detail.value?.tasks?.length ?? 0)
const doneCount = computed(() => detail.value?.tasks?.filter(t => t.done).length ?? 0)
const whenLabel = computed(() => fmt(detail.value?.booking?.scheduled_for))

watch(() => [props.open, props.bookingId], async ([open, id]) => {
  if (open && id) await load()
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await meetingsAPI.get(props.bookingId)
    detail.value = data
    prepDraft.value = data.notes.prep_md
    recapDraft.value = data.notes.recap_md
  } catch (err) {
    error.value = err?.response?.data?.detail ?? 'Failed to load meeting.'
  } finally {
    loading.value = false
  }
}

async function savePrep(val) {
  await meetingsAPI.patchNotes(props.bookingId, { prep_md: val })
  emit('changed')
}
async function saveRecap(val) {
  await meetingsAPI.patchNotes(props.bookingId, { recap_md: val })
  emit('changed')
}

async function addTask() {
  const title = (newTask.value || '').trim()
  if (!title) return
  const { data } = await meetingsAPI.createTask(props.bookingId, { title })
  detail.value.tasks.push(data)
  newTask.value = ''
  emit('changed')
}
async function toggleTask(t, done) {
  const { data } = await meetingsAPI.updateTask(props.bookingId, t.id, { done })
  Object.assign(t, data)
  emit('changed')
}
async function renameTask(t, title) {
  const { data } = await meetingsAPI.updateTask(props.bookingId, t.id, { title })
  Object.assign(t, data)
}
async function deleteTask(t) {
  await meetingsAPI.deleteTask(props.bookingId, t.id)
  detail.value.tasks = detail.value.tasks.filter(x => x.id !== t.id)
  emit('changed')
}

async function redraft(force) {
  const { data } = await meetingsAPI.aiDraft(props.bookingId, force)
  detail.value.notes = { ...detail.value.notes, ...data, ai_skipped: data.ai_skipped ?? null }
  prepDraft.value = data.prep_md
}

async function markHeld() { /* status patch — wire in v1.1 */ }
async function markNoShow() { /* status patch — wire in v1.1 */ }

function fmt(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}
function relPast(iso) {
  if (!iso) return ''
  const diff = (Date.now() - new Date(iso).getTime()) / 86400000
  if (diff < 7) return `${Math.round(diff)}d ago`
  return `${Math.round(diff / 7)}w ago`
}
</script>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/MeetingDrawer.vue
git commit -m "feat(meetings): MeetingDrawer with prep/recap/checklist tabs"
```

---

## Task 13: `MeetingView.vue` (deep-link route)

**Files:**
- Create: `frontend/src/views/MeetingView.vue`
- Modify: `frontend/src/router/index.js`

- [ ] **Step 1: Write the view**

```vue
<template>
  <div class="space-y-4 max-w-5xl">
    <button @click="$router.back()" class="text-2xs text-ctrl-muted hover:text-ctrl-text">← Back</button>
    <MeetingDrawer :open="true" :booking-id="bookingId" @close="$router.back()" />
  </div>
</template>

<script setup>
import { useRoute } from 'vue-router'
import MeetingDrawer from '../components/MeetingDrawer.vue'

const route = useRoute()
const bookingId = route.params.bookingId
</script>
```

- [ ] **Step 2: Register route**

Add to `frontend/src/router/index.js` in the routes array (anywhere alongside the other routes):

```javascript
  { path: '/meeting/:bookingId', component: () => import('../views/MeetingView.vue'), meta: { roles: ALL } },
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/MeetingView.vue frontend/src/router/index.js
git commit -m "feat(meetings): /meeting/:bookingId deep-link route"
```

---

## Task 14: Wire `FollowupsView.vue`

**Files:**
- Modify: `frontend/src/views/FollowupsView.vue`

- [ ] **Step 1: Add drawer + new section**

In `frontend/src/views/FollowupsView.vue`:

1. At the top of `<script setup>`, add:

```javascript
import MeetingDrawer from '../components/MeetingDrawer.vue'

const drawerOpen = ref(false)
const drawerBookingId = ref(null)

function openMeeting(bookingId) {
  drawerBookingId.value = bookingId
  drawerOpen.value = true
}
```

2. In the `sections` array, after `upcoming_meetings`, add:

```javascript
  { key: 'open_meeting_tasks', title: 'Open Meeting Tasks', dateField: 'due_at', tone: 'warn', icon: Clock, empty: 'No open meeting tasks', isTaskList: true },
```

3. In `<template>`, just before `</div>` at the bottom of the root element, add:

```vue
    <MeetingDrawer
      :open="drawerOpen"
      :booking-id="drawerBookingId"
      @close="drawerOpen = false"
    />
```

4. In the row for the `upcoming_meetings` section, replace the `name` cell handler so clicking opens the drawer when a `booking_id` exists (use `row.booking_id` once `/admin/followups` exposes it; for v1 we open with the lead's most recent upcoming booking — fall back to `null` to use the deep-link route). Replace the existing `#cell-name` template with:

```vue
        <template #cell-name="{ row }">
          <button
            v-if="row.booking_id"
            @click="openMeeting(row.booking_id)"
            class="font-medium text-ctrl-text hover:text-status-info transition-colors text-left"
          >{{ row.name || row.lead_name }}</button>
          <button
            v-else
            @click="openContact(row.lead_id)"
            class="font-medium text-ctrl-text hover:text-status-info transition-colors text-left"
          >{{ row.name || row.lead_name }}</button>
        </template>
```

5. Add a `columnsFor(sec)` branch so the Open Meeting Tasks section renders task rows:

```javascript
// inside the existing columnsFor function — append:
  if (sec.isTaskList) {
    return [
      { key: 'name', label: 'Lead' },
      { key: 'title', label: 'Task' },
      { key: 'date', label: 'Due' },
    ]
  }
```

(If `columnsFor` doesn't already exist, locate the existing column-building code and adapt the same branch.)

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/FollowupsView.vue
git commit -m "feat(meetings): clickable Upcoming Meetings rows + Open Meeting Tasks section"
```

---

## Task 15: Briefing badge + Contacts deep-link

**Files:**
- Modify: `frontend/src/views/BriefingView.vue`
- Modify: `frontend/src/views/ContactsView.vue`

- [ ] **Step 1: Briefing — add meetings card**

In `frontend/src/views/BriefingView.vue`, locate the StatRow with overnight stats and add a new card consuming `data.priorities.meetings_today` and `data.priorities.meeting_open_tasks`. Append a new section in the template:

```vue
    <SectionContainer title="Meetings & Tasks" subtitle="Today's calendar + open meeting work">
      <div class="grid grid-cols-2 gap-3">
        <RouterLink to="/calendar" class="block p-3 border border-ctrl-border rounded hover:border-status-info">
          <div class="text-2xs uppercase text-ctrl-muted">Meetings today</div>
          <div class="text-2xl font-display text-ctrl-text tabnum">{{ data?.priorities?.meetings_today ?? 0 }}</div>
        </RouterLink>
        <RouterLink to="/followups#open_meeting_tasks" class="block p-3 border border-ctrl-border rounded hover:border-status-info">
          <div class="text-2xs uppercase text-ctrl-muted">Open meeting tasks</div>
          <div :class="(data?.priorities?.meeting_open_tasks ?? 0) > 0 ? 'text-status-warn' : 'text-ctrl-text'"
               class="text-2xl font-display tabnum">
            {{ data?.priorities?.meeting_open_tasks ?? 0 }}
          </div>
        </RouterLink>
      </div>
    </SectionContainer>
```

If `SectionContainer` and `RouterLink` aren't already imported, add them.

- [ ] **Step 2: Contacts — make meeting bubbles linkable**

In `frontend/src/views/ContactsView.vue`, find the timeline section that renders meeting items. Wrap the existing meeting bubble in:

```vue
<RouterLink
  v-if="item.kind === 'meeting' && item.booking_id"
  :to="`/meeting/${item.booking_id}`"
  class="text-status-info hover:underline"
>
  {{ item.label }}
</RouterLink>
<span v-else>{{ item.label }}</span>
```

(adapt the exact field names to whatever the current ContactsView uses for timeline entries; if no `booking_id` is exposed yet, leave as a plain span — non-blocking.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/BriefingView.vue frontend/src/views/ContactsView.vue
git commit -m "feat(meetings): briefing meetings card + contacts meeting link"
```

---

## Task 16: Smoke check + final commit

- [ ] **Step 1: Backend lint + tests**

```bash
cd dashboard-system/backend
ruff check app/ tests/
black --check app/ tests/
pytest tests/test_meetings_router.py tests/test_meetings_sync.py tests/test_meetings_ai.py tests/test_followups_bubble.py -v
```

Expected: ruff/black clean (or auto-fix and re-commit), all targeted tests pass.

- [ ] **Step 2: Backend boots**

```bash
cd dashboard-system/backend
uvicorn app.main:app --reload
```

Open `http://localhost:8000/docs`. Confirm `/admin/meetings/*` endpoints appear with the new schemas.

- [ ] **Step 3: Frontend builds**

```bash
cd dashboard-system/frontend
npm run build
```

Expected: build green, dist contains `MeetingView-*.js`, `MeetingDrawer-*.js`.

- [ ] **Step 4: Manual smoke**

`npm run dev`, log in, visit `/followups`. Confirm:
1. Upcoming Meetings rows are clickable → drawer opens
2. First open of an unseen meeting auto-drafts a Gemini prep note (or shows the yellow skip pill if budget/upstream guard fires)
3. Adding a task with a past `due_at` makes it appear in the new "Open Meeting Tasks" section
4. `/meeting/:id` renders the same content full-page
5. Briefing shows the two new counters

- [ ] **Step 5: Final commit if anything was tweaked**

```bash
git add -A
git commit -m "chore(meetings): smoke fixes from manual check"
```

---

## Self-Review

**Spec coverage walk-through (each spec section → task):**
- Spec §3 architecture diagram → Tasks 5–9 + 12–15
- Spec §4 data model → Task 1
- Spec §5 API table (8 endpoints + 3 extensions) → Tasks 5 (sync), 6 (list+detail), 7 (notes+tasks CRUD), 8 (ai-draft), 9 (followups/briefing/calendar extensions)
- Spec §6 AI auto-draft (trigger, prompt, cost guard, failure modes, audit) → Task 8
- Spec §7 UI A–F (Followups / Drawer / MeetingView / Briefing / Contacts / Sidebar) → Tasks 11–15 (Sidebar intentionally untouched per spec)
- Spec §8 edge cases — reschedule (Task 5), cancel/no-show/held (Drawer stubs in Task 12; full status PATCH deferred to v1.1 — flagged in code as such), markdown XSS (existing `Markdown.vue` is rendered via `marked + DOMPurify`; Task 12 sticks to a textarea editor in v1 so no untrusted markdown is rendered until the operator re-opens — acceptable), RBAC (Tasks 5, 7, 8), Gemini failure (Task 8), idempotency (Task 5)
- Spec §9 tests → Tasks 5, 6, 7, 8, 9
- Spec §10 files touched → matches Tasks 1–15
- Spec §11 migration/rollout → README `Needs-YOU` already covers manual SQL apply + n8n hook + `GEMINI_AUTO_DRAFT_ENABLED` toggle. Task 16 covers verification.

**Placeholder scan:** none. Every code step shows the full block.

**Type consistency:**
- `MeetingNoteData` carries `ai_skipped` (Task 3); `_notes_data` returns it; `_try_autodraft` sets it via `notes_payload.ai_skipped = skipped` in Task 8
- `MeetingTaskRow.overdue_by_hours` computed in `_task_row` (Task 6) and consumed by the frontend row (Task 11)
- `meetingsAPI.aiDraft(bookingId, force)` matches `force_ai_draft` POST `/ai-draft` body shape
- `_get_booking_or_404` is shared between the notes + tasks handlers (Task 7) and the AI draft handler (Task 8)

**Final note for the executor:** if a step's commit message conflicts with the repo's stated convention (`feat: …` lower-case scope), adapt the prefix but keep the body. The existing dashboard repo allows scoped commits (`feat(meetings): …`).
