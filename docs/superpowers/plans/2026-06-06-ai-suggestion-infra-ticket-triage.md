# AI Suggestion Infrastructure + Ticket Triage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the shared `ai_suggestions` lifecycle table + on-demand ticket triage via Gemini, so operators see AI-classified `(category, priority, assignee)` bundles as inline pills on TicketsView and apply / edit-and-apply / reject them with full audit trail.

**Architecture:** New `ai_suggestions` table (entity-generic) layered on top of existing `services/gemini.py` (call audit), existing `ai_requests` log (single source of truth for Gemini calls), and existing `tickets.*` cols (applied state). Three new endpoints (`POST /admin/tickets/{id}/ai-triage`, `POST /admin/suggestions/{id}/apply`, `POST /admin/suggestions/{id}/reject`) + 2 read endpoints. One new Vue component (`SuggestionPill.vue`) wired into TicketsView via a 4-state row template. No proactive triage, no auto-apply — operator drives every transition.

**Tech Stack:** FastAPI · SQLAlchemy · Pydantic v2 · PostgreSQL · pytest · Vue 3 `<script setup>` · axios · TailwindCSS · Gemini 2.5 Flash via httpx (shared service).

**Spec:** [docs/superpowers/specs/2026-06-06-ai-suggestion-infra-ticket-triage-design.md](../specs/2026-06-06-ai-suggestion-infra-ticket-triage-design.md)

---

## File Structure

### New backend files
- `backend/app/models/ai_suggestion.py` — `AISuggestion` ORM (status enum, payload JSONB)
- `backend/app/services/audit.py` — `write_audit(db, user, *, action, resource_type, resource_id, payload, status)` — lifted from `routers/meetings.py:_audit`
- `backend/app/routers/suggestions.py` — `POST /admin/suggestions/{id}/apply`, `POST /admin/suggestions/{id}/reject`, `GET /admin/suggestions/pending`
- `backend/tests/test_ai_suggestions.py` — 9 tests covering triage / apply / reject / read / RBAC / race

### Modified backend files
- `backend/app/models/__init__.py` — export `AISuggestion`
- `backend/app/services/gemini.py` — `record_decision_row()` returns `Optional[UUID]` (was `None`)
- `backend/app/routers/meetings.py` — replace local `_audit` calls with `write_audit` from shared module
- `backend/app/routers/tickets.py` — add `POST /{id}/ai-triage` + `GET /{id}/suggestions`; extend list endpoint with `LATERAL` join for latest non-superseded suggestion per row
- `backend/app/schemas/responses.py` — `SuggestionPayloadTicket`, `SuggestionDetail`, `SuggestionApplyBody`, `SuggestionRejectBody`, `PaginatedSuggestions`; extend `TicketRow` with optional `suggestion: Optional[SuggestionDetail] = None`
- `backend/app/main.py` — register `suggestions.router`
- `schema.sql` — append `ai_suggestions` table + 2 indexes

### New frontend files
- `frontend/src/components/SuggestionPill.vue` — pill UI (Apply / Edit & Apply / Reject) with inline `SuggestionEditForm` sub-block

### Modified frontend files
- `frontend/src/api/index.js` — `suggestionsAPI` (apply/reject/pending/forTicket) + `ticketsAPI.aiTriage(id)`
- `frontend/src/views/TicketsView.vue` — 4-state row template (no-suggestion / pending / applied / rejected), operator-list fetch on mount, busy flags

### Modified docs
- `docs/PLATFORM_OVERVIEW.md` — append AI Suggestion section under § 7 (AI / Gemini integration)

---

## Task 1: Schema migration

**Files:**
- Modify: `schema.sql` (append at end)

- [ ] **Step 1: Append the migration SQL**

Open `schema.sql` and append at end:

```sql
-- ─── AI Suggestions (ES-OPS-09-AI-SUGGEST, 2026-06-06) ──────────────────────

CREATE TABLE IF NOT EXISTS ai_suggestions (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type      TEXT NOT NULL,
  entity_id        UUID NOT NULL,
  payload          JSONB NOT NULL,
  applied_payload  JSONB,
  model            TEXT NOT NULL,
  confidence       DOUBLE PRECISION,
  status           TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','applied','rejected','superseded')),
  rationale        TEXT,
  applied_at       TIMESTAMPTZ,
  applied_by       TEXT,
  rejected_at      TIMESTAMPTZ,
  rejected_by      TEXT,
  rejection_reason TEXT,
  ai_request_id    UUID,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_suggestions_entity
  ON ai_suggestions(entity_type, entity_id);

CREATE INDEX IF NOT EXISTS ix_suggestions_pending
  ON ai_suggestions(entity_type, created_at DESC)
  WHERE status = 'pending';
```

- [ ] **Step 2: Verify the append**

Read last 30 lines of `schema.sql`. Confirm the `ai_suggestions` block is present and ends cleanly with the partial index `WHERE status = 'pending';`.

Run: `tail -n 30 schema.sql`
Expected: block above is present, no truncation.

- [ ] **Step 3: Do NOT apply against live Supabase**

The operator will run this manually via Supabase SQL Editor. Skip any `psql` or `apply_migration` invocation.

- [ ] **Step 4: Commit**

```bash
git add schema.sql
git commit -m "feat(ai-suggest): add ai_suggestions table + indexes"
```

Expected: 1 file changed, ~25 insertions.

---

## Task 2: ORM model + package export

**Files:**
- Create: `backend/app/models/ai_suggestion.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create the model**

Write `backend/app/models/ai_suggestion.py`:

```python
import uuid

from sqlalchemy import Column, DateTime, Float, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.database import Base


class AISuggestion(Base):
    __tablename__ = "ai_suggestions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(Text, nullable=False, index=True)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    payload = Column(JSONB, nullable=False)
    applied_payload = Column(JSONB, nullable=True)
    model = Column(Text, nullable=False)
    confidence = Column(Float, nullable=True)
    status = Column(Text, nullable=False, default="pending", index=True)
    rationale = Column(Text, nullable=True)
    applied_at = Column(DateTime(timezone=True), nullable=True)
    applied_by = Column(Text, nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    rejected_by = Column(Text, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    ai_request_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
```

- [ ] **Step 2: Export from package**

Edit `backend/app/models/__init__.py`. Add after the last existing import (likely after `MeetingTask`):

```python
from app.models.ai_suggestion import AISuggestion
```

And add to the `__all__` list (preserve existing tab indentation):

```python
	"AISuggestion",
```

- [ ] **Step 3: Smoke-import check**

Run from `backend/`:

```bash
python -c "from app.models import AISuggestion; print(AISuggestion.__tablename__, AISuggestion.__table__.columns.keys())"
```

Expected output: `ai_suggestions ['id', 'entity_type', 'entity_id', 'payload', 'applied_payload', 'model', 'confidence', 'status', 'rationale', 'applied_at', 'applied_by', 'rejected_at', 'rejected_by', 'rejection_reason', 'ai_request_id', 'created_at', 'updated_at']`

If `ImportError`: check `__init__.py` import line. If `AttributeError`: check class name.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/ai_suggestion.py backend/app/models/__init__.py
git commit -m "feat(ai-suggest): AISuggestion ORM model"
```

Expected: 2 files changed, ~50 insertions.

---

## Task 3: Pydantic response schemas

**Files:**
- Modify: `backend/app/schemas/responses.py`

- [ ] **Step 1: Verify required imports at top of `responses.py`**

Read top of file. Confirm presence of: `BaseModel`, `Field`, `datetime`, `UUID`, `Optional`, `List`, `Literal`. If `Literal` is missing, add to the existing `from typing import …` line.

- [ ] **Step 2: Append the new models at end of file**

```python
# ── AI Suggestions ─────────────────────────────────────────────────────────


class SuggestionPayloadTicket(BaseModel):
    """Validated shape of a ticket-triage suggestion payload."""

    category: Literal["billing", "technical", "partnership", "support"]
    priority_score: int = Field(ge=1, le=5)
    assigned_to: Optional[str] = None
    rationale: str
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class SuggestionDetail(BaseModel):
    id: UUID
    entity_type: str
    entity_id: UUID
    payload: dict
    applied_payload: Optional[dict] = None
    model: str
    confidence: Optional[float] = None
    status: Literal["pending", "applied", "rejected", "superseded"]
    rationale: Optional[str] = None
    applied_at: Optional[datetime] = None
    applied_by: Optional[str] = None
    rejected_at: Optional[datetime] = None
    rejected_by: Optional[str] = None
    rejection_reason: Optional[str] = None
    ai_request_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class SuggestionApplyBody(BaseModel):
    override_payload: Optional[dict] = None


class SuggestionRejectBody(BaseModel):
    reason: Optional[str] = None


class PaginatedSuggestions(BaseModel):
    total: int
    limit: int
    offset: int
    suggestions: List[SuggestionDetail]
```

- [ ] **Step 3: Extend `TicketRow` with optional suggestion field**

Find the existing `TicketRow` class in `responses.py` (grep for `class TicketRow`). Add a single field at the end of the class body, preserving its existing order:

```python
    suggestion: Optional["SuggestionDetail"] = None
```

`SuggestionDetail` is forward-referenced because it's defined later in the file; Pydantic v2 resolves this automatically at runtime.

- [ ] **Step 4: Smoke-import check**

```bash
python -c "from app.schemas.responses import SuggestionDetail, SuggestionApplyBody, SuggestionRejectBody, PaginatedSuggestions, SuggestionPayloadTicket, TicketRow; print('ok'); print('TicketRow.suggestion =', TicketRow.model_fields.get('suggestion'))"
```

Expected: `ok` followed by a line showing the suggestion field exists with default `None`.

If `NameError: Literal not defined` → add `Literal` to typing import (Step 1).
If `TicketRow` doesn't have `suggestion` field → forward-ref didn't resolve; call `TicketRow.model_rebuild()` at module bottom.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/responses.py
git commit -m "feat(ai-suggest): Pydantic response models + TicketRow suggestion field"
```

Expected: 1 file changed, ~55 insertions.

---

## Task 4: Lift `_audit` helper to shared service

**Files:**
- Create: `backend/app/services/audit.py`
- Modify: `backend/app/routers/meetings.py`

- [ ] **Step 1: Create the shared module**

Write `backend/app/services/audit.py`:

```python
"""Shared audit_logs writer.

Lifted from routers/meetings.py:_audit so suggestions.py and tickets.py
(triage endpoint) can reuse it without copy-paste. Resource type is now
explicit instead of hardcoded to 'meeting'.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import User


def write_audit(
    db: Session,
    user: User,
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    payload: Optional[dict] = None,
    status: str = "success",
) -> None:
    """Best-effort write to audit_logs. Silently rolls back on failure.

    Mirrors the original meetings._audit contract: never raises, never
    blocks the caller's main flow.
    """
    try:
        from app.models.audit_log import AuditLog

        row = AuditLog(
            user_id=getattr(user, "id", None),
            action=action,
            resource=resource_type,
            resource_id=str(resource_id),
            changes=payload or {},
            status=status,
        )
        db.add(row)
        db.commit()
    except Exception:
        db.rollback()
```

- [ ] **Step 2: Update `routers/meetings.py` to use the shared helper**

Open `backend/app/routers/meetings.py`. Find the local `_audit` function definition (grep for `def _audit`). Replace its body with a delegation:

```python
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
```

Add the import at the top of `meetings.py` (after other `from app.services...` imports):

```python
from app.services.audit import write_audit
```

- [ ] **Step 3: Smoke-import + existing meetings tests still parse**

```bash
python -c "from app.services.audit import write_audit; from app.routers import meetings; print('ok')"
```

Expected: `ok`.

Then verify meetings tests still collect (collect-only, doesn't need DB):

```bash
python -m pytest tests/test_meetings_router.py tests/test_meetings_sync.py tests/test_meetings_ai.py --collect-only --no-header 2>&1 | tail -10
```

Expected: collected ~17 items (or similar), no collection errors.

If env error (TEST_DATABASE_URL): EXPECTED — collection still works against syntax. Look for `errors during collection` text only.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/audit.py backend/app/routers/meetings.py
git commit -m "refactor(audit): lift _audit helper to shared services/audit.py"
```

Expected: 2 files changed, ~40 insertions, ~15 deletions.

---

## Task 5: `record_decision_row` returns inserted UUID

**Files:**
- Modify: `backend/app/services/gemini.py`

- [ ] **Step 1: Update the function to return `Optional[UUID]`**

Open `backend/app/services/gemini.py`. Find the `record_decision_row` function. Replace it with:

```python
def record_decision_row(
    db: Session,
    *,
    request_type: str,
    request_payload: dict,
    response_payload: dict,
    cost_estimate_usd: float = _COST_PER_CALL_USD,
    confidence: Optional[float] = None,
) -> Optional[str]:
    """Best-effort write to ai_decisions. Silently no-ops if the table is missing.

    Returns the inserted row's id as a string, or None if the write was
    skipped (table missing, transient DB error, etc.). Callers use the
    returned id as a soft FK from ai_suggestions.ai_request_id.
    """
    try:
        row = db.execute(
            text(
                "INSERT INTO ai_decisions "
                "(request_type, request_payload, response_payload, cost_estimate_usd, "
                " confidence, created_at) "
                "VALUES (:rt, :rq::jsonb, :rs::jsonb, :cost, :conf, now()) "
                "RETURNING id"
            ),
            {
                "rt": request_type,
                "rq": _json(request_payload),
                "rs": _json(response_payload),
                "cost": cost_estimate_usd,
                "conf": confidence,
            },
        ).scalar()
        db.commit()
        _spend_cache["expires_at"] = 0.0
        return str(row) if row is not None else None
    except Exception:
        db.rollback()
        return None
```

The signature change is backwards-compatible: existing callers in `routers/insights.py` (memo + assistant) discard the return value and continue to work unchanged.

- [ ] **Step 2: Smoke-import**

```bash
python -c "from app.services.gemini import record_decision_row, call_gemini, gemini_today_spend_usd, cost_per_call_usd; from app.routers import insights, meetings; print('ok')"
```

Expected: `ok`. Any ImportError → fix.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/gemini.py
git commit -m "refactor(gemini): record_decision_row returns inserted ai_decisions.id"
```

Expected: 1 file changed, ~10 insertions, ~5 deletions.

---

## Task 6: Triage endpoint (TDD)

**Files:**
- Create: `backend/tests/test_ai_suggestions.py`
- Modify: `backend/app/routers/tickets.py`

- [ ] **Step 1: Write the failing tests (RED)**

Write `backend/tests/test_ai_suggestions.py`:

```python
"""AI suggestion lifecycle tests — triage, apply, reject, read, RBAC, race."""
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


def _seed_ticket(db, *, status="open"):
    tid = uuid4()
    db.execute(
        text(
            "INSERT INTO tickets (id, source, subject, body_preview, status) "
            "VALUES (:id, 'email', 'Refund request Q3', "
            "'Hi, I would like a refund for invoice #4521', :st)"
        ),
        {"id": str(tid), "st": status},
    )
    db.commit()
    return tid


def _fake_gemini_ok(prompt, timeout=30.0):
    return json.dumps(
        {
            "category": "billing",
            "priority_score": 4,
            "assigned_to": None,
            "rationale": "Refund language clearly indicates billing concern.",
            "confidence": 0.86,
        }
    )


def test_triage_creates_pending_suggestion(monkeypatch, client, db, admin_token):
    monkeypatch.setattr("app.routers.tickets.call_gemini", _fake_gemini_ok)
    tid = _seed_ticket(db)

    res = client.post(
        f"/admin/tickets/{tid}/ai-triage",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["entity_type"] == "ticket"
    assert body["status"] == "pending"
    assert body["payload"]["category"] == "billing"
    assert body["payload"]["priority_score"] == 4
    assert body["confidence"] == 0.86

    row = db.execute(
        text(
            "SELECT count(*) FROM ai_suggestions "
            "WHERE entity_type='ticket' AND entity_id=:tid AND status='pending'"
        ),
        {"tid": str(tid)},
    ).scalar()
    assert row == 1


def test_triage_supersedes_existing_pending(monkeypatch, client, db, admin_token):
    monkeypatch.setattr("app.routers.tickets.call_gemini", _fake_gemini_ok)
    tid = _seed_ticket(db)
    client.post(
        f"/admin/tickets/{tid}/ai-triage",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    client.post(
        f"/admin/tickets/{tid}/ai-triage",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    pending = db.execute(
        text(
            "SELECT count(*) FROM ai_suggestions "
            "WHERE entity_type='ticket' AND entity_id=:tid AND status='pending'"
        ),
        {"tid": str(tid)},
    ).scalar()
    superseded = db.execute(
        text(
            "SELECT count(*) FROM ai_suggestions "
            "WHERE entity_type='ticket' AND entity_id=:tid AND status='superseded'"
        ),
        {"tid": str(tid)},
    ).scalar()
    assert pending == 1
    assert superseded == 1


def test_triage_parse_error_returns_502(monkeypatch, client, db, admin_token):
    monkeypatch.setattr(
        "app.routers.tickets.call_gemini",
        lambda prompt, timeout=30.0: "not json at all",
    )
    tid = _seed_ticket(db)

    res = client.post(
        f"/admin/tickets/{tid}/ai-triage",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 502
    assert "malformed JSON" in res.text or "Invalid" in res.text

    row = db.execute(
        text("SELECT count(*) FROM ai_suggestions WHERE entity_id=:tid"),
        {"tid": str(tid)},
    ).scalar()
    assert row == 0


def test_triage_resolved_ticket_returns_409(monkeypatch, client, db, admin_token):
    called = {"n": 0}

    def sentinel(prompt, timeout=30.0):
        called["n"] += 1
        return _fake_gemini_ok(prompt)

    monkeypatch.setattr("app.routers.tickets.call_gemini", sentinel)
    tid = _seed_ticket(db, status="resolved")

    res = client.post(
        f"/admin/tickets/{tid}/ai-triage",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 409
    assert called["n"] == 0


def test_triage_requires_operator_403_for_readonly(monkeypatch, client, db):
    from app.auth import create_access_token

    readonly = create_access_token({"sub": "viewer", "role": "readonly"})
    monkeypatch.setattr("app.routers.tickets.call_gemini", _fake_gemini_ok)
    tid = _seed_ticket(db)

    res = client.post(
        f"/admin/tickets/{tid}/ai-triage",
        headers={"Authorization": f"Bearer {readonly}"},
    )
    assert res.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail (RED)**

```bash
cd backend
python -m pytest tests/test_ai_suggestions.py -v --no-header 2>&1 | tail -20
```

Expected: env error from `conftest.py` (`RuntimeError: Tests need a database. Set TEST_DATABASE_URL`) — same RED-only pattern as the meeting-notes ship. This is OK; commit anyway.

If TEST_DATABASE_URL is set: expect 5 failures, all 404 on `/admin/tickets/{id}/ai-triage` because the endpoint doesn't exist yet.

- [ ] **Step 3: Implement the helpers**

Open `backend/app/routers/tickets.py`. Add to the top imports (after existing app imports):

```python
import json
from typing import Set

from fastapi import HTTPException
from sqlalchemy import text

from app.auth import require_operator
from app.models.ai_suggestion import AISuggestion
from app.models.user import User
from app.schemas.responses import SuggestionDetail
from app.services.audit import write_audit
from app.services.gemini import (
    GEMINI_MODEL,
    call_gemini,
    cost_per_call_usd,
    gemini_today_spend_usd,
    record_decision_row,
)
from app.config import settings
```

Add at module bottom (after the existing endpoints):

```python
_VALID_CATEGORIES = {"billing", "technical", "partnership", "support"}

_TRIAGE_INSTRUCTION = (
    "You are a triage AI for the eSteps Health operations team. "
    "Classify this incoming support ticket.\n\n"
    "TICKET\n"
    "  Source:  {source}\n"
    "  Subject: {subject}\n"
    "  Body:    {body}\n\n"
    "Available operator usernames (for assigned_to): {operators_csv}\n\n"
    "Return ONLY a JSON object with these exact fields, no markdown fence, "
    "no prose around it:\n"
    "{{\n"
    '  "category":       "billing" | "technical" | "partnership" | "support",\n'
    '  "priority_score": <integer 1-5, where 5 = urgent>,\n'
    '  "assigned_to":    "<one of the operator usernames above>" | null,\n'
    '  "rationale":      "<1-2 sentences explaining your reasoning>",\n'
    '  "confidence":     <float 0.0-1.0, how unambiguous the signals are>\n'
    "}}\n\n"
    "Rules:\n"
    "- legal/refund/chargeback/data-deletion/GDPR -> category=billing, priority>=4\n"
    "- error/bug/crash/500/integration/API failure -> category=technical\n"
    "- partnership/research/collaboration/grant/IRB -> category=partnership\n"
    "- otherwise -> category=support\n"
    "- urgent/down/blocking/payment-failed -> priority_score=5\n"
    "- ambiguous body -> confidence<0.7, assigned_to=null"
)


def _available_operators(db: Session) -> Set[str]:
    rows = db.execute(
        text(
            "SELECT username FROM users "
            "WHERE role IN ('admin','operator') AND is_active = true"
        )
    ).all()
    return {r[0] for r in rows}


def _build_triage_prompt(ticket, operators: Set[str]) -> str:
    return _TRIAGE_INSTRUCTION.format(
        source=ticket.source or "—",
        subject=(ticket.subject or "")[:200],
        body=(ticket.body_preview or "")[:1000],
        operators_csv=", ".join(sorted(operators)) or "(none configured)",
    )


def _parse_and_validate_triage(raw: str, operators: Set[str]) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # Tolerate accidental markdown fence
        cleaned = cleaned.split("```")[1].lstrip("json").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=502, detail=f"Gemini returned malformed JSON: {e}"
        )

    if data.get("category") not in _VALID_CATEGORIES:
        raise HTTPException(
            status_code=502, detail=f"Invalid category: {data.get('category')!r}"
        )
    pri = data.get("priority_score")
    if not isinstance(pri, int) or not 1 <= pri <= 5:
        raise HTTPException(
            status_code=502, detail=f"Invalid priority_score: {pri!r}"
        )
    rationale = (data.get("rationale") or "").strip()
    if not rationale:
        raise HTTPException(status_code=502, detail="Missing rationale")

    assignee = data.get("assigned_to")
    if assignee and assignee not in operators:
        assignee = None

    conf = data.get("confidence")
    if not isinstance(conf, (int, float)) or not 0.0 <= float(conf) <= 1.0:
        conf = None

    return {
        "category": data["category"],
        "priority_score": pri,
        "assigned_to": assignee,
        "rationale": rationale,
        "confidence": float(conf) if conf is not None else None,
    }
```

- [ ] **Step 4: Implement the triage endpoint**

Append to the same `tickets.py` file:

```python
@router.post("/{ticket_id}/ai-triage", response_model=SuggestionDetail)
def triage_ticket(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_operator),
) -> SuggestionDetail:
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.status == "resolved":
        raise HTTPException(status_code=409, detail="Cannot triage resolved ticket")

    if gemini_today_spend_usd(db) >= settings.ai_daily_budget_usd:
        raise HTTPException(
            status_code=503,
            detail="Daily Gemini budget exhausted, retry after midnight UTC",
        )

    # Supersede any existing pending suggestion in the same transaction.
    db.execute(
        text(
            "UPDATE ai_suggestions SET status='superseded', updated_at=now() "
            "WHERE entity_type='ticket' AND entity_id=:tid AND status='pending'"
        ),
        {"tid": str(ticket_id)},
    )

    operators = _available_operators(db)
    prompt = _build_triage_prompt(ticket, operators)

    # call_gemini raises HTTPException on upstream / budget / 5xx.
    raw = call_gemini(prompt)
    parsed = _parse_and_validate_triage(raw, operators)

    ai_req_id = record_decision_row(
        db,
        request_type="ticket_triage",
        request_payload={"ticket_id": str(ticket_id)},
        response_payload=parsed,
        cost_estimate_usd=cost_per_call_usd(),
        confidence=parsed.get("confidence"),
    )

    suggestion = AISuggestion(
        entity_type="ticket",
        entity_id=ticket_id,
        payload=parsed,
        model=GEMINI_MODEL,
        confidence=parsed.get("confidence"),
        rationale=parsed.get("rationale"),
        ai_request_id=ai_req_id,
        status="pending",
    )
    db.add(suggestion)
    db.commit()
    db.refresh(suggestion)

    write_audit(
        db,
        user,
        action="ai.triage.request",
        resource_type="ticket",
        resource_id=str(ticket_id),
        payload={
            "suggestion_id": str(suggestion.id),
            "confidence": parsed.get("confidence"),
        },
    )

    return SuggestionDetail.model_validate(suggestion, from_attributes=True)
```

If `UUID`, `Session`, `Depends`, or `get_db` are not yet imported at the top of `tickets.py`, add them now.

- [ ] **Step 5: Run tests to verify GREEN (best-effort with env)**

```bash
cd backend
python -m pytest tests/test_ai_suggestions.py::test_triage_creates_pending_suggestion tests/test_ai_suggestions.py::test_triage_supersedes_existing_pending tests/test_ai_suggestions.py::test_triage_parse_error_returns_502 tests/test_ai_suggestions.py::test_triage_resolved_ticket_returns_409 tests/test_ai_suggestions.py::test_triage_requires_operator_403_for_readonly -v --no-header 2>&1 | tail -30
```

Expected with TEST_DATABASE_URL set: 5 PASS.
Expected without: env blocker — RED-only commit pattern, same as meeting-notes ship.

If logic errors / import errors / 502 unexpectedly: FIX the implementation, re-run.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/tickets.py backend/tests/test_ai_suggestions.py
git commit -m "feat(ai-suggest): /ai-triage endpoint + Gemini prompt+parser"
```

Expected: 2 files changed, ~250 insertions.

---

## Task 7: Suggestions router — apply endpoint (TDD)

**Files:**
- Modify: `backend/tests/test_ai_suggestions.py`
- Create: `backend/app/routers/suggestions.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Append apply tests to the test file**

Append to `backend/tests/test_ai_suggestions.py`:

```python
def _seed_pending_suggestion(db, ticket_id, *, payload=None):
    sid = uuid4()
    payload = payload or {
        "category": "billing",
        "priority_score": 4,
        "assigned_to": None,
        "rationale": "test",
        "confidence": 0.8,
    }
    db.execute(
        text(
            "INSERT INTO ai_suggestions "
            "(id, entity_type, entity_id, payload, model, confidence, status, rationale) "
            "VALUES (:id, 'ticket', :tid, :p::jsonb, 'gemini-2.5-flash', 0.8, 'pending', "
            "'test')"
        ),
        {
            "id": str(sid),
            "tid": str(ticket_id),
            "p": json.dumps(payload),
        },
    )
    db.commit()
    return sid


def test_apply_writes_to_ticket_and_marks_verified(client, db, admin_token):
    tid = _seed_ticket(db)
    sid = _seed_pending_suggestion(db, tid)

    res = client.post(
        f"/admin/suggestions/{sid}/apply",
        json={},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "applied"
    assert body["applied_at"] is not None

    ticket_row = db.execute(
        text(
            "SELECT ai_category, ai_priority_score, human_verified, human_override "
            "FROM tickets WHERE id=:tid"
        ),
        {"tid": str(tid)},
    ).mappings().first()
    assert ticket_row["ai_category"] == "billing"
    assert ticket_row["ai_priority_score"] == 4
    assert ticket_row["human_verified"] is True
    assert ticket_row["human_override"] is False


def test_apply_with_override_flips_override_flag(client, db, admin_token):
    tid = _seed_ticket(db)
    sid = _seed_pending_suggestion(db, tid)

    override = {
        "category": "support",
        "priority_score": 2,
        "assigned_to": None,
        "rationale": "operator disagrees",
        "confidence": 0.9,
    }
    res = client.post(
        f"/admin/suggestions/{sid}/apply",
        json={"override_payload": override},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    assert res.json()["applied_payload"]["category"] == "support"

    ticket_row = db.execute(
        text("SELECT ai_category, human_override FROM tickets WHERE id=:tid"),
        {"tid": str(tid)},
    ).mappings().first()
    assert ticket_row["ai_category"] == "support"
    assert ticket_row["human_override"] is True


def test_apply_race_returns_409(client, db, admin_token):
    tid = _seed_ticket(db)
    sid = _seed_pending_suggestion(db, tid)
    # Pre-set the suggestion to applied to simulate the race.
    db.execute(
        text(
            "UPDATE ai_suggestions SET status='applied', applied_at=now(), "
            "applied_by='someone-else' WHERE id=:id"
        ),
        {"id": str(sid)},
    )
    db.commit()

    res = client.post(
        f"/admin/suggestions/{sid}/apply",
        json={},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 409
    assert "already" in res.text.lower()
```

- [ ] **Step 2: Verify the new tests fail (RED)**

```bash
cd backend
python -m pytest tests/test_ai_suggestions.py::test_apply_writes_to_ticket_and_marks_verified tests/test_ai_suggestions.py::test_apply_with_override_flips_override_flag tests/test_ai_suggestions.py::test_apply_race_returns_409 --collect-only --no-header 2>&1 | tail -10
```

Expected: 3 collected. Tests would 404 on `/admin/suggestions/{id}/apply` since router doesn't exist.

- [ ] **Step 3: Create the suggestions router**

Write `backend/app/routers/suggestions.py`:

```python
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
        # Suggestion gets marked applied even if entity is gone / resolved;
        # the write to the entity is skipped to preserve audit truth.
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
```

- [ ] **Step 4: Register the router**

Open `backend/app/main.py`. Add to the imports block (next to `from app.routers import meetings`):

```python
from app.routers import suggestions
```

And add near the other `include_router` calls:

```python
app.include_router(suggestions.router)
```

- [ ] **Step 5: Run the tests (GREEN)**

```bash
cd backend
python -m pytest tests/test_ai_suggestions.py::test_apply_writes_to_ticket_and_marks_verified tests/test_ai_suggestions.py::test_apply_with_override_flips_override_flag tests/test_ai_suggestions.py::test_apply_race_returns_409 -v --no-header 2>&1 | tail -30
```

Expected with TEST_DATABASE_URL: 3 PASS.
Expected without: env blocker (commit anyway).

If GREEN fails on assertions: most likely the `RETURNING` casting (UUID → str) or `dict(row["payload"])` shape. Inspect the response body and adjust.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/suggestions.py backend/app/main.py backend/tests/test_ai_suggestions.py
git commit -m "feat(ai-suggest): /apply endpoint with override + race-safe UPDATE"
```

Expected: 3 files changed, ~150 insertions.

---

## Task 8: Suggestions router — reject endpoint (TDD)

**Files:**
- Modify: `backend/tests/test_ai_suggestions.py`
- Modify: `backend/app/routers/suggestions.py`

- [ ] **Step 1: Append reject test**

Append to `backend/tests/test_ai_suggestions.py`:

```python
def test_reject_marks_rejected_with_reason(client, db, admin_token):
    tid = _seed_ticket(db)
    sid = _seed_pending_suggestion(db, tid)

    res = client.post(
        f"/admin/suggestions/{sid}/reject",
        json={"reason": "low confidence and stale ticket"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "rejected"
    assert body["rejection_reason"] == "low confidence and stale ticket"
    assert body["rejected_at"] is not None
```

- [ ] **Step 2: Verify it would fail (collect-only)**

```bash
python -m pytest tests/test_ai_suggestions.py::test_reject_marks_rejected_with_reason --collect-only --no-header 2>&1 | tail -5
```

Expected: 1 collected. Endpoint doesn't exist yet, test would 404.

- [ ] **Step 3: Implement the reject endpoint**

Append to `backend/app/routers/suggestions.py`:

```python
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
```

- [ ] **Step 4: Run the test (GREEN)**

```bash
cd backend
python -m pytest tests/test_ai_suggestions.py::test_reject_marks_rejected_with_reason -v --no-header 2>&1 | tail -15
```

Expected with TEST_DATABASE_URL: PASS.
Expected without: env blocker.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/suggestions.py backend/tests/test_ai_suggestions.py
git commit -m "feat(ai-suggest): /reject endpoint with reason capture"
```

Expected: 2 files changed, ~55 insertions.

---

## Task 9: Read endpoints — pending list + per-ticket history (TDD)

**Files:**
- Modify: `backend/tests/test_ai_suggestions.py`
- Modify: `backend/app/routers/suggestions.py`
- Modify: `backend/app/routers/tickets.py`

- [ ] **Step 1: Append read-endpoint tests**

Append to `backend/tests/test_ai_suggestions.py`:

```python
def test_pending_lists_only_pending_across_tickets(client, db, admin_token):
    t1 = _seed_ticket(db)
    t2 = _seed_ticket(db)
    _seed_pending_suggestion(db, t1)
    s2 = _seed_pending_suggestion(db, t2)
    # Mark t2's as rejected so it should NOT appear
    db.execute(
        text("UPDATE ai_suggestions SET status='rejected' WHERE id=:id"),
        {"id": str(s2)},
    )
    db.commit()

    res = client.get(
        "/admin/suggestions/pending",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total"] >= 1
    statuses = {s["status"] for s in body["suggestions"]}
    assert statuses == {"pending"}


def test_ticket_suggestion_history_returns_all_statuses(client, db, admin_token):
    tid = _seed_ticket(db)
    s1 = _seed_pending_suggestion(db, tid)
    s2 = _seed_pending_suggestion(db, tid)
    # First was superseded by second
    db.execute(
        text("UPDATE ai_suggestions SET status='superseded' WHERE id=:id"),
        {"id": str(s1)},
    )
    db.commit()

    res = client.get(
        f"/admin/tickets/{tid}/suggestions",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2
    statuses = {s["status"] for s in body["suggestions"]}
    assert statuses == {"pending", "superseded"}
```

- [ ] **Step 2: Implement `/admin/suggestions/pending`**

Append to `backend/app/routers/suggestions.py`:

```python
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
```

- [ ] **Step 3: Implement `GET /admin/tickets/{ticket_id}/suggestions` in tickets.py**

Append to `backend/app/routers/tickets.py` (the file you modified in Task 6):

```python
@router.get("/{ticket_id}/suggestions", response_model=PaginatedSuggestions)
def list_ticket_suggestions(
    ticket_id: UUID,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PaginatedSuggestions:
    q = db.query(AISuggestion).filter(
        AISuggestion.entity_type == "ticket",
        AISuggestion.entity_id == ticket_id,
    )
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
```

`PaginatedSuggestions` and `get_current_user` are likely already imported from Task 6; verify and add if missing.

- [ ] **Step 4: Run the tests (GREEN)**

```bash
cd backend
python -m pytest tests/test_ai_suggestions.py::test_pending_lists_only_pending_across_tickets tests/test_ai_suggestions.py::test_ticket_suggestion_history_returns_all_statuses -v --no-header 2>&1 | tail -15
```

Expected with TEST_DATABASE_URL: 2 PASS.
Expected without: env blocker.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/suggestions.py backend/app/routers/tickets.py backend/tests/test_ai_suggestions.py
git commit -m "feat(ai-suggest): pending list + per-ticket history read endpoints"
```

Expected: 3 files changed, ~80 insertions.

---

## Task 10: Tickets list endpoint — LATERAL join for inline suggestion

**Files:**
- Modify: `backend/app/routers/tickets.py`
- Modify: `backend/tests/test_ai_suggestions.py` (optional verification test)

- [ ] **Step 1: Locate the existing tickets list endpoint**

Open `backend/app/routers/tickets.py`. Find the `@router.get("", response_model=PaginatedTickets)` decorator (the main list endpoint, currently returning `PaginatedTickets`). Note its existing query construction.

- [ ] **Step 2: Replace the query body with a LATERAL join**

Replace the existing list endpoint implementation (the one returning paginated rows) with this version, preserving filter params and pagination semantics:

```python
@router.get("", response_model=PaginatedTickets)
def list_tickets(
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    ai_category: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PaginatedTickets:
    filters = []
    params: dict = {"limit": limit, "offset": offset}
    if status:
        filters.append("t.status = :status")
        params["status"] = status
    if category:
        filters.append("t.ai_category = :category")
        params["category"] = category
    if ai_category:
        filters.append("t.ai_category = :ai_category")
        params["ai_category"] = ai_category
    where = "WHERE " + " AND ".join(filters) if filters else ""

    total = db.execute(
        text(f"SELECT count(*) FROM tickets t {where}"), params
    ).scalar() or 0

    rows = db.execute(
        text(
            "SELECT t.id, t.source, t.subject, t.body_preview, t.ai_category, "
            "t.ai_priority_score, t.ai_confidence, t.assigned_to, t.status, "
            "t.human_verified, t.human_override, t.created_at, t.resolved_at, "
            "t.response_time_min, "
            "s.id AS s_id, s.entity_type AS s_entity_type, "
            "s.entity_id AS s_entity_id, s.payload AS s_payload, "
            "s.applied_payload AS s_applied_payload, s.model AS s_model, "
            "s.confidence AS s_confidence, s.status AS s_status, "
            "s.rationale AS s_rationale, s.applied_at AS s_applied_at, "
            "s.applied_by AS s_applied_by, s.rejected_at AS s_rejected_at, "
            "s.rejected_by AS s_rejected_by, "
            "s.rejection_reason AS s_rejection_reason, "
            "s.ai_request_id AS s_ai_request_id, "
            "s.created_at AS s_created_at, s.updated_at AS s_updated_at "
            "FROM tickets t "
            "LEFT JOIN LATERAL ("
            "  SELECT * FROM ai_suggestions "
            "  WHERE entity_type='ticket' AND entity_id = t.id "
            "    AND status != 'superseded' "
            "  ORDER BY created_at DESC LIMIT 1"
            ") s ON true "
            f"{where} "
            "ORDER BY t.created_at DESC "
            "LIMIT :limit OFFSET :offset"
        ),
        params,
    ).mappings().all()

    tickets_out: list[TicketRow] = []
    for r in rows:
        suggestion = None
        if r["s_id"] is not None:
            suggestion = SuggestionDetail(
                id=r["s_id"],
                entity_type=r["s_entity_type"],
                entity_id=r["s_entity_id"],
                payload=r["s_payload"] or {},
                applied_payload=r["s_applied_payload"],
                model=r["s_model"],
                confidence=r["s_confidence"],
                status=r["s_status"],
                rationale=r["s_rationale"],
                applied_at=r["s_applied_at"],
                applied_by=r["s_applied_by"],
                rejected_at=r["s_rejected_at"],
                rejected_by=r["s_rejected_by"],
                rejection_reason=r["s_rejection_reason"],
                ai_request_id=r["s_ai_request_id"],
                created_at=r["s_created_at"],
                updated_at=r["s_updated_at"],
            )
        tickets_out.append(
            TicketRow(
                id=r["id"],
                source=r["source"],
                subject=r["subject"],
                body_preview=r["body_preview"],
                ai_category=r["ai_category"],
                ai_priority_score=r["ai_priority_score"],
                ai_confidence=r["ai_confidence"],
                assigned_to=r["assigned_to"],
                status=r["status"],
                human_verified=r["human_verified"],
                human_override=r["human_override"],
                created_at=r["created_at"],
                resolved_at=r["resolved_at"],
                response_time_min=r["response_time_min"],
                suggestion=suggestion,
            )
        )

    return PaginatedTickets(
        total=total,
        limit=limit,
        offset=offset,
        tickets=tickets_out,
    )
```

If the existing endpoint used different field names on `TicketRow`, adjust the kwargs to match — but the `suggestion` field is the new addition.

- [ ] **Step 3: Append a verification test**

Append to `backend/tests/test_ai_suggestions.py`:

```python
def test_ticket_list_includes_latest_pending_suggestion(client, db, admin_token):
    tid = _seed_ticket(db)
    sid = _seed_pending_suggestion(db, tid)

    res = client.get(
        "/admin/tickets",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    row = next(
        (t for t in res.json()["tickets"] if t["id"] == str(tid)), None
    )
    assert row is not None
    assert row["suggestion"] is not None
    assert row["suggestion"]["id"] == str(sid)
    assert row["suggestion"]["status"] == "pending"


def test_ticket_list_excludes_superseded(client, db, admin_token):
    tid = _seed_ticket(db)
    sid = _seed_pending_suggestion(db, tid)
    db.execute(
        text("UPDATE ai_suggestions SET status='superseded' WHERE id=:id"),
        {"id": str(sid)},
    )
    db.commit()

    res = client.get(
        "/admin/tickets",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    row = next(
        (t for t in res.json()["tickets"] if t["id"] == str(tid)), None
    )
    assert row is not None
    assert row["suggestion"] is None
```

- [ ] **Step 4: Run all suggestion tests**

```bash
cd backend
python -m pytest tests/test_ai_suggestions.py -v --no-header 2>&1 | tail -30
```

Expected with TEST_DATABASE_URL: all 11 PASS.
Expected without: env blocker.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/tickets.py backend/tests/test_ai_suggestions.py
git commit -m "feat(ai-suggest): tickets list LATERAL join for inline suggestion"
```

Expected: 2 files changed, ~120 insertions.

---

## Task 11: Frontend API client additions

**Files:**
- Modify: `frontend/src/api/index.js`

- [ ] **Step 1: Add `suggestionsAPI` block**

Open `frontend/src/api/index.js`. Find the section where `meetingsAPI` is exported (Task 10 of the prior plan). Insert this BEFORE `export default api`, AFTER the `meetingsAPI` export:

```javascript
export const suggestionsAPI = {
  apply:    (id, overridePayload) =>
    api.post(`/admin/suggestions/${id}/apply`, { override_payload: overridePayload || null }),
  reject:   (id, reason) =>
    api.post(`/admin/suggestions/${id}/reject`, { reason: reason || null }),
  pending:  (params = {}) => api.get('/admin/suggestions/pending', { params }),
  forTicket: (ticketId) => api.get(`/admin/tickets/${ticketId}/suggestions`),
}
```

- [ ] **Step 2: Extend `ticketsAPI` with `aiTriage`**

In the same file, find the existing `ticketsAPI` export. Add the `aiTriage` method to its object literal:

```javascript
export const ticketsAPI = {
  // ...existing methods...
  aiTriage: (ticketId) => api.post(`/admin/tickets/${ticketId}/ai-triage`),
}
```

Preserve any existing methods (`getStats`, `list`, `updateStatus`).

- [ ] **Step 3: Syntax check**

```bash
cd frontend
node -c src/api/index.js
```

Expected: exit code 0 (no output).

If `SyntaxError`: most likely a comma missing in the object literal or duplicate `export const ticketsAPI`. Inspect and fix.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/index.js
git commit -m "feat(ai-suggest): suggestionsAPI + ticketsAPI.aiTriage methods"
```

Expected: 1 file changed, ~10 insertions.

---

## Task 12: `SuggestionPill.vue` component

**Files:**
- Create: `frontend/src/components/SuggestionPill.vue`

- [ ] **Step 1: Write the component**

Write `frontend/src/components/SuggestionPill.vue`:

```vue
<template>
  <div class="border border-status-info/40 bg-status-info-bg/40 rounded p-2 my-1">
    <div class="flex items-center gap-2">
      <Bot :size="14" class="text-status-info shrink-0" />
      <span class="text-2xs uppercase tracking-label text-status-info">AI suggests</span>
      <span class="text-xs text-ctrl-text truncate">
        {{ payload.category }} · priority {{ payload.priority_score }}
        <template v-if="payload.assigned_to"> · assign {{ payload.assigned_to }}</template>
      </span>
      <span v-if="confidence != null" class="ml-auto text-2xs text-ctrl-muted tabnum">
        conf {{ confidence.toFixed(2) }}
      </span>
    </div>
    <div v-if="payload.rationale" class="text-2xs text-ctrl-muted italic mt-1">
      "{{ payload.rationale }}"
    </div>

    <div v-if="!editing" class="flex items-center gap-2 mt-2">
      <button
        class="px-2 py-1 text-2xs bg-status-ok-bg border border-status-ok/40 text-status-ok rounded hover:bg-status-ok/20 disabled:opacity-50"
        @click="$emit('apply')"
        :disabled="busy"
      >Apply</button>
      <button
        class="px-2 py-1 text-2xs border border-ctrl-border text-ctrl-muted rounded hover:text-ctrl-text disabled:opacity-50"
        @click="startEdit"
        :disabled="busy"
      >Edit &amp; Apply</button>
      <button
        class="px-2 py-1 text-2xs border border-status-err/40 text-status-err rounded hover:bg-status-err-bg/40 disabled:opacity-50"
        @click="$emit('reject')"
        :disabled="busy"
      >Reject</button>
    </div>

    <div v-else class="mt-2 space-y-1.5">
      <div class="grid grid-cols-3 gap-2">
        <select v-model="draft.category"
                class="bg-ctrl-panel border border-ctrl-border rounded px-2 py-1 text-2xs text-ctrl-text focus:outline-none">
          <option value="billing">billing</option>
          <option value="technical">technical</option>
          <option value="partnership">partnership</option>
          <option value="support">support</option>
        </select>
        <input v-model.number="draft.priority_score" type="number" min="1" max="5"
               class="bg-ctrl-panel border border-ctrl-border rounded px-2 py-1 text-2xs text-ctrl-text focus:outline-none tabnum" />
        <select v-model="draft.assigned_to"
                class="bg-ctrl-panel border border-ctrl-border rounded px-2 py-1 text-2xs text-ctrl-text focus:outline-none">
          <option :value="null">(unassigned)</option>
          <option v-for="op in operators" :key="op" :value="op">{{ op }}</option>
        </select>
      </div>
      <div class="flex items-center gap-2">
        <button
          class="px-2 py-1 text-2xs bg-status-ok-bg border border-status-ok/40 text-status-ok rounded hover:bg-status-ok/20 disabled:opacity-50"
          @click="commitEdit"
          :disabled="busy"
        >Apply override</button>
        <button
          class="px-2 py-1 text-2xs border border-ctrl-border text-ctrl-muted rounded hover:text-ctrl-text"
          @click="editing = false"
        >Cancel</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Bot } from 'lucide-vue-next'

const props = defineProps({
  payload:    { type: Object, required: true },
  confidence: { type: Number, default: null },
  operators:  { type: Array, default: () => [] },
  busy:       { type: Boolean, default: false },
})
const emit = defineEmits(['apply', 'reject'])

const editing = ref(false)
const draft = ref({
  category: props.payload.category,
  priority_score: props.payload.priority_score,
  assigned_to: props.payload.assigned_to ?? null,
})

function startEdit() {
  draft.value = {
    category: props.payload.category,
    priority_score: props.payload.priority_score,
    assigned_to: props.payload.assigned_to ?? null,
  }
  editing.value = true
}

function commitEdit() {
  const override = {
    ...props.payload,
    ...draft.value,
  }
  editing.value = false
  emit('apply', override)
}
</script>
```

- [ ] **Step 2: Build smoke**

```bash
cd frontend
node -e "const fs=require('fs'); const c=fs.readFileSync('src/components/SuggestionPill.vue','utf8'); ['<template>','<script setup>','defineProps','defineEmits','apply','reject','editing'].forEach(s => {if (!c.includes(s)) { console.error('missing', s); process.exit(1) }}); console.log('ok')"
```

Expected: `ok`.

Optionally a full Vite build:

```bash
cd frontend
npx vite build 2>&1 | tail -5
```

Should succeed; pill isn't imported yet by TicketsView so it produces a chunk by itself or is tree-shaken.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/SuggestionPill.vue
git commit -m "feat(ai-suggest): SuggestionPill component with inline edit form"
```

Expected: 1 file changed, ~110 insertions.

---

## Task 13: TicketsView state machine wiring

**Files:**
- Modify: `frontend/src/views/TicketsView.vue`

- [ ] **Step 1: Add imports + reactive state**

Open `frontend/src/views/TicketsView.vue`. Add to the imports inside `<script setup>`:

```javascript
import SuggestionPill from '../components/SuggestionPill.vue'
import { suggestionsAPI, usersAPI } from '../api/index.js'
```

(If `usersAPI` import already exists from another use, don't duplicate — just ensure it's in scope.)

Add to the reactive state block (next to existing refs like `stats`, `tickets`):

```javascript
const operators = ref([])
const suggestingId = ref(null)   // ticket id currently awaiting Gemini
const applyingId = ref(null)     // suggestion id currently being applied/rejected
```

Add to the `onMounted` block (or equivalent initial-load function):

```javascript
async function loadOperators() {
  try {
    const { data } = await usersAPI.list()
    operators.value = (data?.users || data || [])
      .filter(u => u.is_active && (u.role === 'admin' || u.role === 'operator'))
      .map(u => u.username)
  } catch {
    operators.value = []
  }
}

// in onMounted, alongside loadTickets():
loadOperators()
```

- [ ] **Step 2: Add the action handlers**

Add to the same `<script setup>` block:

```javascript
async function getSuggestion(row) {
  suggestingId.value = row.id
  try {
    const { data } = await ticketsAPI.aiTriage(row.id)
    row.suggestion = data
  } catch (err) {
    const msg = err?.response?.data?.detail || 'AI triage failed'
    // existing toast pattern: reuse whatever the view already uses; fallback to console
    if (typeof showToast === 'function') showToast(msg, 'error')
    else console.error('triage failed:', msg)
  } finally {
    suggestingId.value = null
  }
}

async function applySuggestion(row, overridePayload = null) {
  if (!row.suggestion) return
  applyingId.value = row.suggestion.id
  try {
    const { data } = await suggestionsAPI.apply(row.suggestion.id, overridePayload)
    row.suggestion = data
    // Mirror applied state to the row's own AI columns so the "applied" branch renders
    const applied = data.applied_payload || data.payload
    row.ai_category = applied.category
    row.ai_priority_score = applied.priority_score
    row.human_verified = true
    row.human_override = JSON.stringify(applied) !== JSON.stringify(data.payload)
  } catch (err) {
    const msg = err?.response?.data?.detail || 'Apply failed'
    if (typeof showToast === 'function') showToast(msg, 'error')
    else console.error('apply failed:', msg)
  } finally {
    applyingId.value = null
  }
}

async function rejectSuggestion(row) {
  if (!row.suggestion) return
  applyingId.value = row.suggestion.id
  try {
    const { data } = await suggestionsAPI.reject(row.suggestion.id, null)
    row.suggestion = data
  } catch (err) {
    const msg = err?.response?.data?.detail || 'Reject failed'
    if (typeof showToast === 'function') showToast(msg, 'error')
    else console.error('reject failed:', msg)
  } finally {
    applyingId.value = null
  }
}

function relTime(iso) {
  if (!iso) return ''
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return `${Math.round(diff)}s ago`
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
  return `${Math.round(diff / 86400)}d ago`
}
```

- [ ] **Step 3: Add the 4-state row template**

Find the `<Table>` row rendering inside the template. Most likely there's a slot like `#cell-status` or `#row-extra`. Add a new slot (or extend the existing actions slot) for the suggestion column. If the table has no per-row "expand" mechanism, add a row above/below the existing row via a colspanned table row — adapt to the actual table component shape:

```vue
<template #cell-actions="{ row }">
  <!-- Existing inline status PATCH stays unchanged -->

  <!-- NEW: AI suggestion zone -->
  <div class="mt-1">
    <button
      v-if="!row.suggestion && !row.human_verified"
      class="text-2xs text-status-info hover:underline disabled:opacity-50"
      :disabled="suggestingId === row.id"
      @click="getSuggestion(row)"
    >
      {{ suggestingId === row.id ? 'Asking AI…' : 'Get AI suggestion' }}
    </button>

    <SuggestionPill
      v-else-if="row.suggestion?.status === 'pending'"
      :payload="row.suggestion.payload"
      :confidence="row.suggestion.confidence"
      :operators="operators"
      :busy="applyingId === row.suggestion.id"
      @apply="(override) => applySuggestion(row, override)"
      @reject="rejectSuggestion(row)"
    />

    <span v-else-if="row.human_verified" class="text-2xs text-status-ok">
      ✓ AI triaged
      <template v-if="row.suggestion?.applied_at"> · {{ relTime(row.suggestion.applied_at) }}</template>
      <span
        v-if="row.human_override"
        class="ml-1 px-1 bg-status-warn-bg text-status-warn rounded text-3xs"
      >overridden</span>
    </span>

    <button
      v-else-if="row.suggestion?.status === 'rejected'"
      class="text-2xs text-ctrl-muted hover:text-ctrl-text"
      :disabled="suggestingId === row.id"
      @click="getSuggestion(row)"
    >
      Suggestion rejected · re-ask
    </button>
  </div>
</template>
```

If `<Table>`'s slot system differs (e.g. uses `#cell-name` instead of `#cell-actions`, or uses `#row` for the whole row), adapt the slot name but keep the v-if chain order.

- [ ] **Step 4: Build verification**

```bash
cd frontend
npx vite build 2>&1 | tail -15
```

Expected: build green. Look for `TicketsView-*.js` and `SuggestionPill-*.js` in the dist asset list.

If TypeScript-style errors about unknown props or methods: check that imports + ref declarations are in scope.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/TicketsView.vue
git commit -m "feat(ai-suggest): TicketsView 4-state row + SuggestionPill wiring"
```

Expected: 1 file changed, ~120 insertions.

---

## Task 14: PLATFORM_OVERVIEW docs update

**Files:**
- Modify: `docs/PLATFORM_OVERVIEW.md`

- [ ] **Step 1: Locate § 7 AI / Gemini integration**

Open `docs/PLATFORM_OVERVIEW.md`. Find the section header `## AI / Gemini integration` (h2). Read its current contents to know what's already documented.

- [ ] **Step 2: Append the AI suggestion subsection**

Add this block as the last subsection of § 7 (before the next h2 heading begins):

```markdown
### AI Suggestion infrastructure (ES-OPS-09-AI-SUGGEST, shipped 2026-06-06)

A reusable review-loop primitive for "Gemini suggests an action, operator approves / edits-and-approves / rejects". Builds on `services/gemini.py` (no duplicated upstream code) and `ai_requests` (no duplicated call log).

**Data model:**

| Table | Purpose |
|-------|---------|
| `ai_suggestions` | Lifecycle row per suggestion. Status: `pending` → `applied` | `rejected` | `superseded`. `payload` JSONB = what Gemini suggested; `applied_payload` JSONB = what got written (may differ on operator override). Soft FK `ai_request_id` → `ai_requests.id`. |

**Invariants:**

- At most one `pending` suggestion per `(entity_type, entity_id)`. A new triage call supersedes the prior pending row in the same transaction.
- Never auto-applied — even at `confidence=0.99` the operator clicks Apply.
- `applied_payload != payload` → entity's `human_override = true`.

**v1 consumer: ticket triage.**

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/admin/tickets/{id}/ai-triage` | require_operator | Generate a suggestion. Supersedes any prior pending. Returns SuggestionDetail. |
| POST | `/admin/suggestions/{id}/apply` | require_operator | Body: `{override_payload?}`. Writes to ticket cols, marks suggestion `applied`. |
| POST | `/admin/suggestions/{id}/reject` | require_operator | Body: `{reason?}`. Marks `rejected`. |
| GET | `/admin/suggestions/pending` | get_current_user | Cross-entity pending queue. |
| GET | `/admin/tickets/{id}/suggestions` | get_current_user | Per-ticket history (all statuses). |

**Frontend:** `SuggestionPill.vue` (4-state: no-suggestion / pending / applied / rejected) rendered inline in TicketsView row.

**Future consumers** (drop-in, same lifecycle):
- `lead` — next-action suggestions (pause / set_priority / mark_cold / schedule_meeting)
- `opportunity` — stage advance suggestion
- `lead` (re-engagement angle) — different email angle per touch
- `workflow_execution` — failure root-cause + suggested retry

See [spec](superpowers/specs/2026-06-06-ai-suggestion-infra-ticket-triage-design.md) for prompt design, parsing rules, RBAC matrix, edge cases.
```

- [ ] **Step 3: Update top-of-file "Last refreshed" if present**

If § 0 / the doc front matter has a `**Last refreshed:**` line, bump it to `2026-06-06 (added AI suggestion infrastructure)`.

- [ ] **Step 4: Commit**

```bash
git add docs/PLATFORM_OVERVIEW.md
git commit -m "docs: add AI Suggestion infrastructure section to PLATFORM_OVERVIEW"
```

Expected: 1 file changed, ~55 insertions.

---

## Task 15: Black-format the new files

**Files:**
- Modify: `backend/app/models/ai_suggestion.py`, `backend/app/services/audit.py`, `backend/app/routers/suggestions.py`, `backend/tests/test_ai_suggestions.py`

(Existing files like `tickets.py`, `meetings.py`, `responses.py`, `gemini.py`, `main.py` are NOT formatted to avoid churn vs the rest of the codebase, matching the convention set by `1395c7e chore(format): black-format new meetings module files`.)

- [ ] **Step 1: Run black on the new files only**

```bash
cd backend
python -m black app/models/ai_suggestion.py app/services/audit.py app/routers/suggestions.py tests/test_ai_suggestions.py
```

Expected: `reformatted 0-4 files`. May be 0 if you happened to write them already-formatted.

- [ ] **Step 2: Verify AST still parses**

```bash
python -c "import ast; [ast.parse(open(p).read()) for p in ['app/models/ai_suggestion.py','app/services/audit.py','app/routers/suggestions.py','tests/test_ai_suggestions.py']]; print('clean')"
```

Expected: `clean`.

- [ ] **Step 3: Commit only if files actually changed**

```bash
git diff --stat
```

If output shows any files changed:

```bash
git add backend/app/models/ai_suggestion.py backend/app/services/audit.py backend/app/routers/suggestions.py backend/tests/test_ai_suggestions.py
git commit -m "chore(format): black-format new ai_suggestion module files"
```

If no files changed, skip the commit. Move to Task 16.

---

## Task 16: Smoke check + final verification

**Files:** none (verification-only).

- [ ] **Step 1: Backend module import**

```bash
cd backend
python -c "from app.routers import suggestions, tickets; from app.services.audit import write_audit; from app.services.gemini import record_decision_row; from app.models import AISuggestion; from app.schemas.responses import SuggestionDetail; print('ok')"
```

Expected: `ok`.

- [ ] **Step 2: Verify all suggestion routes registered**

```bash
python -c "from app.main import app; routes = [(r.methods, r.path) for r in app.routes if '/suggestions' in r.path or '/ai-triage' in r.path]; [print(m, p) for m, p in routes]"
```

Expected output includes:

```
{'POST'}  /admin/tickets/{ticket_id}/ai-triage
{'POST'}  /admin/suggestions/{suggestion_id}/apply
{'POST'}  /admin/suggestions/{suggestion_id}/reject
{'GET'}   /admin/suggestions/pending
{'GET'}   /admin/tickets/{ticket_id}/suggestions
```

- [ ] **Step 3: Frontend build**

```bash
cd frontend
npx vite build 2>&1 | tail -20
```

Expected: build green. Asset list includes `SuggestionPill-*.js` (likely tree-shaken into TicketsView's chunk).

- [ ] **Step 4: Pytest attempt (best-effort, expected env blocker)**

```bash
cd backend
python -m pytest tests/test_ai_suggestions.py -v --no-header 2>&1 | tail -30
```

Expected with TEST_DATABASE_URL set: 11 PASS (5 triage + 3 apply + 1 reject + 2 read + 2 lateral-join).
Expected without: env blocker — same RED-only commit pattern as meeting-notes ship.

If any logic error surfaces: FIX implementation, re-run, re-commit as a separate `fix(ai-suggest): …` commit.

- [ ] **Step 5: Manual smoke (operator action)**

Document for the operator that the following manual steps complete the ship:

1. Apply schema.sql additions to live Supabase ops DB.
2. Set `TEST_DATABASE_URL` and re-run `pytest tests/test_ai_suggestions.py` — expect 11 PASS.
3. Log into the dashboard, visit `/tickets`.
4. Pick an unverified ticket → click "Get AI suggestion" → SuggestionPill appears.
5. Click "Apply" → row state flips to `✓ AI triaged · just now`, ticket's `ai_category` + `ai_priority_score` populated.
6. Pick another ticket → "Edit & Apply" → change category in inline form → submit → row flips to applied with `overridden` badge.
7. Pick a third → "Reject" → row shows `Suggestion rejected · re-ask`.

- [ ] **Step 6: Final commit**

If you made any smoke fixes:

```bash
git add -A
git commit -m "chore(ai-suggest): smoke fixes from manual verification"
```

If no fixes needed: skip.

- [ ] **Step 7: Verify final commit log**

```bash
git log -16 --oneline
```

Expected: 14-16 new commits in the stack, matching Tasks 1-16 (some tasks may have collapsed into a single commit per the conditions above).

---

## Self-review checklist (run before handing the plan to an executor)

### Spec coverage walk-through

| Spec section | Task that implements it |
|--------------|------------------------|
| §3 architecture (3-tier, never write-through) | Tasks 6 (triage) + 7 (apply) + 8 (reject) |
| §4 data model (ai_suggestions table) | Task 1 |
| §4 ticket payload schema | Tasks 3 (Pydantic) + 6 (parser) |
| §5.1 endpoints table (5 endpoints) | Tasks 6 (1) + 7 (1) + 8 (1) + 9 (2) |
| §5.2 Pydantic shapes | Task 3 |
| §5.3 triage endpoint sketch | Task 6 |
| §5.4 apply endpoint sketch | Task 7 |
| §5.5 reject endpoint | Task 8 |
| §6 frontend (SuggestionPill + TicketsView) | Tasks 12 + 13 |
| §6.4 LEFT JOIN LATERAL | Task 10 |
| §7 Gemini prompt + parsing | Task 6 (Step 3) |
| §8 RBAC + audit table | Tasks 6/7/8/9 (each has audit log writes) |
| §9 edge cases (12 enumerated) | Tasks 6/7/8 handle resolved-ticket-409, race-409, parse-error-502, budget-503, supersede |
| §10 test plan (9 tests) | Tasks 6 (5 tests) + 7 (3 tests) + 8 (1 test) + 9 (2 tests) + 10 (2 tests) = 13 tests (4 bonus) |
| §11 files touched (4 new + 8 modified) | Tasks 1-15 cover all 12 files + docs |
| §12 rollout | Task 16 step 5 |
| §13 future consumers | Documented in PLATFORM_OVERVIEW addition (Task 14) |
| §14 resolved open questions | Tasks 4 (audit lift) + 5 (record_decision_row return) + 3 (TicketRow extension) |

**No gaps.**

### Placeholder scan
- No "TBD" / "TODO" / "implement later" / "add appropriate validation" / "similar to Task N" in any step.
- Every step that writes code shows the actual code block.
- Every step that runs a command shows the exact command + expected output.

### Type consistency check
- `AISuggestion` (class name) — consistent across Tasks 2, 6, 7, 8, 9, 10, 16.
- `SuggestionDetail`, `SuggestionApplyBody`, `SuggestionRejectBody`, `SuggestionPayloadTicket`, `PaginatedSuggestions` — defined in Task 3, used in Tasks 6 (return type), 7 (return type + body), 8 (body + return), 9 (return), 10 (suggestion field).
- `suggestionsAPI` (frontend) — defined Task 11, used Task 13.
- `ticketsAPI.aiTriage` — added Task 11, called Task 13.
- `write_audit(db, user, *, action, resource_type, resource_id, payload, status)` — defined Task 4, called Tasks 6 (1×), 7 (1×), 8 (1×).
- `record_decision_row(...) -> Optional[str]` — signature change Task 5, consumed Task 6.
- Status enum values — `'pending' | 'applied' | 'rejected' | 'superseded'` — consistent in schema (Task 1), Pydantic (Task 3), tests (Task 6 / 7 / 8 / 9).
- Ticket entity payload keys — `category | priority_score | assigned_to | rationale | confidence` — consistent in payload schema (Task 3), parser (Task 6), applier (Task 7), pill UI (Task 12), TicketsView mirroring (Task 13).

All names match across tasks.
