# AI Suggestion Infrastructure + Ticket Triage Consumer

> **Spec status:** Draft — pending user review.
> **Brainstorm date:** 2026-06-06.
> **Authors:** alaa + Claude (via `/superpowers-brainstorming`).
> **Related:** [PLATFORM_OVERVIEW.md](../../PLATFORM_OVERVIEW.md), [PRODUCT.md](../../PRODUCT.md), [meeting-notes spec](2026-06-05-meeting-notes-and-tickets-design.md) (the immediately-prior AI feature this builds on).

---

## 1. Problem

The platform already calls Gemini in three places (insights memo, insights assistant, meeting-notes auto-draft) but each call is fire-and-forget — the AI output is either rendered straight to the user (memo, assistant) or written straight to the data model (meeting note). There is no pattern for **"AI suggests an action, operator reviews, operator applies (maybe with edits)"** — the canonical co-pilot loop.

Two consequences:

1. **`tickets.ai_category` / `tickets.ai_priority_score` / `tickets.ai_confidence` / `tickets.human_verified` / `tickets.human_override` columns exist as stubs** (defined in the ORM, read by the stats endpoint, but **never populated by anything**). The data model anticipated AI triage; no triage exists.
2. **Future ops automations** (lead re-scoring, smart followup retry, auto-pause on bounces, suggested lead actions) all need the same review-loop primitive. Without a shared abstraction, each consumer will reinvent its own state machine.

This spec introduces the shared primitive — `ai_suggestions` — and wires the first consumer: **ticket triage**.

## 2. Goals / Non-goals

### Goals
- Add a reusable `ai_suggestions` table that any entity type can reference.
- Implement on-demand triage: operator clicks "Get AI suggestion" on a ticket row, Gemini classifies it, operator approves / edits-and-approves / rejects.
- Preserve full audit: who suggested what, who applied what (possibly different), when.
- Reuse the existing `ai_requests` log (no double-logging) and the shared `services/gemini.py` (no duplicated upstream code).
- Stay within the existing `$10/day` Gemini budget guard.
- Generic enough that a second consumer (lead, opportunity) is a payload-schema-plus-handler addition, not a redesign.

### Non-goals (v1)
- **No proactive / background triage.** Operator initiates every call. (Cost predictability + zero surprise spend.) Background triage is a future enhancement, not blocked by this design.
- **No auto-apply at high confidence.** Even at `confidence=0.99` the suggestion is `pending` until an operator clicks Apply. Trust earns auto-apply, not v1.
- **No multi-entity consumers in v1.** Tickets only. Leads / opportunities are documented as future consumers (§13).
- **No per-field atomic suggestions.** One suggestion = one composite payload. Operator edits inline before applying if they disagree with individual fields.
- **No new role.** Existing `require_operator` gate is sufficient for triage / apply / reject. Admin escalation deferred.
- **No suggestion notifications / inbox.** A `/suggestions/pending` read endpoint exists but no dashboard view in v1 (operators see pills inline in TicketsView).

## 3. Architecture overview

Three layers, no write-through:

```
┌──────────────────────────────────────────────────────────────┐
│  Existing                                                    │
│  ─────────                                                   │
│  ai_requests (call log)   ◄── services/gemini.py             │
│  tickets    (entity row)  ◄── tickets.py                     │
└──────────────────────────────────────────────────────────────┘
                       ▲
                       │ (apply writes payload to ticket cols)
                       │
┌──────────────────────────────────────────────────────────────┐
│  New                                                         │
│  ────                                                        │
│  ai_suggestions (lifecycle: pending/applied/rejected/superseded)
│      payload   JSONB  (suggested values)                     │
│      applied_payload JSONB  (what got written, if different) │
│      ai_request_id  FK to ai_requests                        │
└──────────────────────────────────────────────────────────────┘
                       ▲
                       │
┌──────────────────────────────────────────────────────────────┐
│  Frontend                                                    │
│  ─────────                                                   │
│  TicketsView row                                             │
│     ├─ no suggestion → [Get AI suggestion] button            │
│     ├─ pending       → SuggestionPill [Apply][Edit][Reject]  │
│     ├─ applied       → "AI triaged · {rel-time}" + override  │
│     │                   badge if applied != suggested        │
│     └─ rejected      → "AI suggestion rejected" + [Get AI…]  │
└──────────────────────────────────────────────────────────────┘
```

**Key invariants:**

- A suggestion is **never** auto-applied. State transitions: `pending → applied | rejected | superseded` (terminal).
- At most **one** `pending` suggestion per `(entity_type, entity_id)`. A new triage call supersedes the prior pending row in the same transaction.
- `ai_suggestions.payload` is what Gemini suggested. `ai_suggestions.applied_payload` is what the operator actually wrote. If they differ → `tickets.human_override = true`.
- `ai_suggestions.ai_request_id` links to the `ai_requests` row containing the raw Gemini call audit (cost, latency, input_preview, raw output). Suggestions never duplicate that data.

## 4. Data model

### New table: `ai_suggestions`

```sql
CREATE TABLE IF NOT EXISTS ai_suggestions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type     TEXT NOT NULL,
  entity_id       UUID NOT NULL,
  payload         JSONB NOT NULL,
  applied_payload JSONB,
  model           TEXT NOT NULL,
  confidence      DOUBLE PRECISION,
  status          TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','applied','rejected','superseded')),
  rationale       TEXT,
  applied_at      TIMESTAMPTZ,
  applied_by      TEXT,
  rejected_at     TIMESTAMPTZ,
  rejected_by     TEXT,
  rejection_reason TEXT,
  ai_request_id   UUID,                       -- FK soft (ai_requests lives in app/models)
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_suggestions_entity
  ON ai_suggestions(entity_type, entity_id);

CREATE INDEX IF NOT EXISTS ix_suggestions_pending
  ON ai_suggestions(entity_type, created_at DESC)
  WHERE status = 'pending';
```

**Notes:**
- `entity_type` is plain text in v1 (no enum) — keeps door open for future consumers without migration. App-level validation rejects unknown types.
- `payload` shape varies by `entity_type`. v1 ticket payload (§5).
- `ai_request_id` is a soft FK (not enforced at DB level) because `ai_requests` may be GDPR-purged before suggestions; we don't want suggestion deletion as a side effect.
- `rationale` is a denormalised copy of the AI's prose justification (also present in `payload.rationale`) — exposed at top level for easier list-endpoint rendering without JSONB extraction.

### Ticket payload schema (v1)

```json
{
  "category":       "billing | technical | partnership | support",
  "priority_score": 1..5,
  "assigned_to":    "<operator username>" | null,
  "rationale":      "1–2 sentence justification"
}
```

Validation rules:
- `category` MUST be one of the four enum values. Anything else → 502, no suggestion row.
- `priority_score` MUST be integer in `[1, 5]`. Out of range → 502.
- `assigned_to` MUST be `null` OR an existing `users.username` where `role IN ('admin','operator') AND is_active=true`. Unknown username → set to `null` (don't fail the whole suggestion).
- `rationale` MUST be non-empty. Missing → 502.

### No changes to existing tables

`tickets` already has all the columns needed for the applied state:
- `ai_category` ← suggestion.payload.category
- `ai_priority_score` ← suggestion.payload.priority_score
- `ai_confidence` ← suggestion.confidence
- `assigned_to` ← suggestion.payload.assigned_to
- `human_verified` ← `true` on apply
- `human_override` ← `true` if `applied_payload != payload`

`ai_requests` already has all the columns needed for the call log. The triage endpoint sets:
- `request_type = 'ticket_triage'`
- `ai_output` = the parsed JSON (also denormalised into the suggestion)
- `entity_type = 'ticket'`, `entity_id` = ticket id
- `confidence_score`, `tokens_used`, `cost_usd`, etc as already populated by `services/gemini.py`

## 5. API

### 5.1 Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `POST` | `/admin/tickets/{ticket_id}/ai-triage` | `require_operator` | Call Gemini, create a `pending` suggestion. Supersedes any existing pending suggestion for the ticket. Returns `SuggestionDetail`. |
| `POST` | `/admin/suggestions/{id}/apply` | `require_operator` | Apply a suggestion. Body: `{override_payload?: <same shape as suggestion.payload>}`. Writes to ticket, marks suggestion `applied`. Returns updated `SuggestionDetail`. |
| `POST` | `/admin/suggestions/{id}/reject` | `require_operator` | Body: `{reason?: string}`. Marks suggestion `rejected`. Returns updated `SuggestionDetail`. |
| `GET`  | `/admin/suggestions/pending` | `get_current_user` | Cross-entity pending queue. Query params: `entity_type?`, `limit=50`, `offset=0`. |
| `GET`  | `/admin/tickets/{ticket_id}/suggestions` | `get_current_user` | All suggestions for one ticket (paginated, newest first). |

### 5.2 Pydantic response shapes (`schemas/responses.py` additions)

```python
class SuggestionPayloadTicket(BaseModel):
    category: Literal["billing", "technical", "partnership", "support"]
    priority_score: int = Field(ge=1, le=5)
    assigned_to: Optional[str] = None
    rationale: str

class SuggestionDetail(BaseModel):
    id: UUID
    entity_type: str
    entity_id: UUID
    payload: dict                       # type-narrowed in v2; dict for v1 to keep generic
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

### 5.3 Triage endpoint logic (sketch)

```python
@router.post("/{ticket_id}/ai-triage", response_model=SuggestionDetail)
def triage_ticket(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_operator),
) -> SuggestionDetail:
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    if ticket.status == "resolved":
        raise HTTPException(409, "Cannot triage resolved ticket")

    if gemini_today_spend_usd(db) >= settings.ai_daily_budget_usd:
        raise HTTPException(503, "Daily Gemini budget exhausted")

    # Supersede prior pending suggestion in same txn
    db.execute(
        text("UPDATE ai_suggestions SET status='superseded', updated_at=now() "
             "WHERE entity_type='ticket' AND entity_id=:tid AND status='pending'"),
        {"tid": str(ticket_id)},
    )

    operators = _available_operators(db)
    prompt = _build_triage_prompt(ticket, operators)

    try:
        raw = call_gemini(prompt)
    except HTTPException:
        raise  # bubbles 502/503 to caller; no suggestion row created

    parsed = _parse_and_validate_triage(raw, operators)  # returns payload dict or raises 502

    # NOTE: requires a small backwards-compatible change to services/gemini.py —
    # record_decision_row currently returns None; the plan must extend it to
    # return the inserted ai_requests.id (UUID). Spec assumes the updated signature.
    ai_req_id = record_decision_row(
        db,
        request_type="ticket_triage",
        request_payload={"ticket_id": str(ticket_id)},
        response_payload=parsed,
        cost_estimate_usd=cost_per_call_usd(),
        confidence=parsed.get("confidence"),
    )  # -> Optional[UUID]; None if best-effort write failed silently

    suggestion = AISuggestion(
        entity_type="ticket",
        entity_id=ticket_id,
        payload=parsed,
        model=GEMINI_MODEL,
        confidence=parsed.get("confidence"),
        rationale=parsed.get("rationale"),
        ai_request_id=ai_req_id,  # soft FK; may be NULL if ai_requests insert no-op'd
        status="pending",
    )
    db.add(suggestion)
    db.commit()
    db.refresh(suggestion)

    # _audit() reuses the helper defined in routers/meetings.py:_audit (writes
    # to audit_logs). Plan task: lift _audit out to a shared helper module
    # (e.g. app/services/audit.py) so suggestions.py + tickets.py + meetings.py
    # don't each re-define it. Low risk, ~10 LOC move.
    _audit(db, user, "ai.triage.request", str(ticket_id),
           {"suggestion_id": str(suggestion.id), "confidence": parsed.get("confidence")})

    return SuggestionDetail.model_validate(suggestion, from_attributes=True)
```

`_available_operators(db)` is a new ~5-line helper in `routers/tickets.py`: `SELECT username FROM users WHERE role IN ('admin','operator') AND is_active = true` → returns a `set[str]`. Cached per-request (no module-level cache — operator membership can change mid-day).

### 5.4 Apply endpoint logic (sketch)

```python
@router.post("/{suggestion_id}/apply", response_model=SuggestionDetail)
def apply_suggestion(
    suggestion_id: UUID,
    body: SuggestionApplyBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_operator),
) -> SuggestionDetail:
    # Race-safe: only apply if still pending
    updated = db.execute(
        text("UPDATE ai_suggestions SET status='applied', applied_at=now(), "
             "applied_by=:user, applied_payload=COALESCE(:override::jsonb, payload), "
             "updated_at=now() WHERE id=:id AND status='pending' RETURNING *"),
        {"id": str(suggestion_id),
         "user": user.username,
         "override": json.dumps(body.override_payload) if body.override_payload else None},
    ).mappings().first()
    if not updated:
        # Either not found or already applied/rejected/superseded
        existing = db.query(AISuggestion).filter(AISuggestion.id == suggestion_id).first()
        if not existing:
            raise HTTPException(404, "Suggestion not found")
        raise HTTPException(409, f"Suggestion is already {existing.status}")

    applied = updated["applied_payload"]
    suggested = updated["payload"]
    override = applied != suggested

    if updated["entity_type"] == "ticket":
        ticket = db.query(Ticket).filter(Ticket.id == updated["entity_id"]).first()
        if ticket and ticket.status != "resolved":
            ticket.ai_category = applied.get("category")
            ticket.ai_priority_score = applied.get("priority_score")
            ticket.ai_confidence = updated["confidence"]
            ticket.assigned_to = applied.get("assigned_to") or ticket.assigned_to
            ticket.human_verified = True
            ticket.human_override = override
            ticket.updated_at = datetime.now(timezone.utc)

    db.commit()
    _audit(db, user, "ai.suggestion.override" if override else "ai.suggestion.apply",
           str(updated["entity_id"]),
           {"suggestion_id": str(suggestion_id), "suggested": suggested, "applied": applied})

    return SuggestionDetail.model_validate(dict(updated), from_attributes=False)
```

### 5.5 Reject endpoint

Trivial: race-safe `UPDATE … SET status='rejected', rejected_at, rejected_by, rejection_reason WHERE id=? AND status='pending' RETURNING *`. Same 404 / 409 semantics.

## 6. Frontend

### 6.1 New component: `SuggestionPill.vue`

```vue
<template>
  <div class="border border-status-info/40 bg-status-info-bg/40 rounded p-2 my-1">
    <div class="flex items-center gap-2">
      <Bot :size="14" class="text-status-info" />
      <span class="text-2xs uppercase tracking-label text-status-info">AI suggests</span>
      <span class="text-xs text-ctrl-text">
        {{ payload.category }} · priority {{ payload.priority_score }}
        <span v-if="payload.assigned_to"> · assign {{ payload.assigned_to }}</span>
      </span>
      <span v-if="confidence != null" class="ml-auto text-2xs text-ctrl-muted tabnum">
        conf {{ confidence.toFixed(2) }}
      </span>
    </div>
    <div v-if="payload.rationale" class="text-2xs text-ctrl-muted mt-1 italic">"{{ payload.rationale }}"</div>
    <div class="flex items-center gap-2 mt-2">
      <button class="px-2 py-1 text-2xs bg-status-ok-bg border border-status-ok/40 text-status-ok rounded hover:bg-status-ok/20"
              @click="$emit('apply')" :disabled="busy">Apply</button>
      <button class="px-2 py-1 text-2xs border border-ctrl-border text-ctrl-muted rounded hover:text-ctrl-text"
              @click="editing = !editing" :disabled="busy">Edit & Apply</button>
      <button class="px-2 py-1 text-2xs border border-status-err/40 text-status-err rounded hover:bg-status-err-bg/40"
              @click="$emit('reject')" :disabled="busy">Reject</button>
    </div>
    <!-- Inline edit form when editing=true: category select, priority 1-5, assignee select -->
    <SuggestionEditForm v-if="editing" :payload="payload" :operators="operators"
                        @submit="(override) => { editing = false; $emit('apply', override) }" />
  </div>
</template>
```

Props: `payload`, `confidence`, `operators` (list of usernames), `busy`. Emits: `apply` (optional override_payload arg), `reject`.

### 6.2 `TicketsView.vue` integration

In the row template, replace plain status display with state-driven render:

```vue
<template #row-extra="{ row }">
  <!-- No suggestion yet, no manual triage -->
  <button v-if="!row.suggestion && !row.human_verified"
          @click="getSuggestion(row)" :disabled="suggestingId === row.id"
          class="text-2xs text-status-info hover:underline">
    {{ suggestingId === row.id ? 'Asking AI…' : 'Get AI suggestion' }}
  </button>

  <!-- Pending suggestion -->
  <SuggestionPill v-else-if="row.suggestion?.status === 'pending'"
                  :payload="row.suggestion.payload"
                  :confidence="row.suggestion.confidence"
                  :operators="operators"
                  :busy="applyingId === row.suggestion.id"
                  @apply="(override) => apply(row, override)"
                  @reject="reject(row)" />

  <!-- Applied -->
  <span v-else-if="row.human_verified" class="text-2xs text-status-ok">
    ✓ AI triaged · {{ relTime(row.suggestion?.applied_at) }}
    <span v-if="row.human_override" class="ml-1 px-1 bg-status-warn-bg text-status-warn rounded text-3xs">overridden</span>
  </span>

  <!-- Rejected (offer fresh re-triage) -->
  <button v-else-if="row.suggestion?.status === 'rejected'"
          @click="getSuggestion(row)" class="text-2xs text-ctrl-muted hover:text-ctrl-text">
    Suggestion rejected · re-ask
  </button>
</template>
```

### 6.3 API client additions (`src/api/index.js`)

```javascript
export const suggestionsAPI = {
  apply:  (id, overridePayload) => api.post(`/admin/suggestions/${id}/apply`, { override_payload: overridePayload || null }),
  reject: (id, reason) => api.post(`/admin/suggestions/${id}/reject`, { reason: reason || null }),
  pending: (params = {}) => api.get('/admin/suggestions/pending', { params }),
  forTicket: (ticketId) => api.get(`/admin/tickets/${ticketId}/suggestions`),
}

// Extend ticketsAPI
ticketsAPI.aiTriage = (ticketId) => api.post(`/admin/tickets/${ticketId}/ai-triage`)
```

### 6.4 Data flow in TicketsView

On view mount: existing `ticketsAPI.list()` call now needs to **also fetch each ticket's most-recent non-superseded suggestion**. v1 server-side strategy in `tickets.py`:

```sql
LEFT JOIN LATERAL (
  SELECT id, status, payload, applied_payload, confidence, rationale,
         applied_at, applied_by, created_at
  FROM ai_suggestions
  WHERE entity_type='ticket' AND entity_id=t.id AND status != 'superseded'
  ORDER BY created_at DESC LIMIT 1
) latest_suggestion ON true
```

Single query, no N+1. The existing `TicketRow` Pydantic model gains an optional `suggestion: Optional[SuggestionDetail] = None` field — no new schema type needed.

## 7. Gemini prompt design

```
You are a triage AI for the eSteps Health operations team. Classify this incoming support ticket.

TICKET
  Source:  {source}
  Subject: {subject}
  Body:    {body_preview}

Available operator usernames (for assigned_to): {operators_csv}

Return ONLY a JSON object with these exact fields, no markdown fence, no prose around it:

{
  "category":       "billing" | "technical" | "partnership" | "support",
  "priority_score": <integer 1-5, where 5 = urgent>,
  "assigned_to":    "<one of the operator usernames above>" | null,
  "rationale":      "<1-2 sentences explaining your reasoning>",
  "confidence":     <float 0.0-1.0, how unambiguous the signals are>
}

Rules:
- legal / refund / chargeback / data-deletion / GDPR    -> category=billing,     priority>=4
- error / bug / crash / 500 / integration / API failure -> category=technical
- partnership / research / collaboration / grant / IRB  -> category=partnership
- otherwise                                             -> category=support
- urgent / down / blocking / payment-failed             -> priority_score=5
- ambiguous or vague body                               -> confidence<0.7, assigned_to=null
```

**Parsing** (in router):

```python
def _parse_and_validate_triage(raw: str, operators: set[str]) -> dict:
    text = raw.strip()
    # tolerate accidental markdown fence
    if text.startswith("```"):
        text = text.split("```")[1].lstrip("json").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise HTTPException(502, f"Gemini returned malformed JSON: {e}")

    if data.get("category") not in {"billing", "technical", "partnership", "support"}:
        raise HTTPException(502, f"Invalid category: {data.get('category')!r}")
    pri = data.get("priority_score")
    if not isinstance(pri, int) or not 1 <= pri <= 5:
        raise HTTPException(502, f"Invalid priority_score: {pri!r}")
    rat = (data.get("rationale") or "").strip()
    if not rat:
        raise HTTPException(502, "Missing rationale")

    # Soften assigned_to: unknown username -> null, don't fail
    assignee = data.get("assigned_to")
    if assignee and assignee not in operators:
        assignee = None

    conf = data.get("confidence")
    if not isinstance(conf, (int, float)) or not 0.0 <= conf <= 1.0:
        conf = None  # confidence is advisory

    return {
        "category": data["category"],
        "priority_score": pri,
        "assigned_to": assignee,
        "rationale": rat,
        "confidence": conf,
    }
```

## 8. RBAC + audit

| Operation | Auth gate | Audit `action` | Audit payload |
|-----------|-----------|----------------|---------------|
| `POST /admin/tickets/{id}/ai-triage` | `require_operator` | `ai.triage.request` | `{suggestion_id, confidence}` |
| `POST /admin/suggestions/{id}/apply` (no override) | `require_operator` | `ai.suggestion.apply` | `{suggestion_id, suggested, applied=null}` |
| `POST /admin/suggestions/{id}/apply` (with override) | `require_operator` | `ai.suggestion.override` | `{suggestion_id, suggested, applied}` |
| `POST /admin/suggestions/{id}/reject` | `require_operator` | `ai.suggestion.reject` | `{suggestion_id, reason}` |
| `GET /admin/suggestions/pending` | `get_current_user` | (none) | |
| `GET /admin/tickets/{id}/suggestions` | `get_current_user` | (none) | |

`audit_logs.resource = entity_id`, `audit_logs.resource_type = entity_type` (e.g. `ticket`).

No admin-only escalation. Override is operator-allowed because `tickets.human_override` already tracks the divergence — the admin doesn't need to gate operator judgment, just see it in the log.

## 9. Edge cases + failure modes

| Case | Handling |
|------|----------|
| Ticket already manually classified (`ai_category` set, `human_verified=true`) | Triage still allowed. Returns suggestion with metadata flag `was_already_verified=true` in response (optional — for UI tinting). Apply re-overwrites. |
| Ticket updated between suggestion creation and apply | If `ticket.updated_at > suggestion.created_at`: UI renders warning badge; backend does not block apply (operator decision). Future enhancement: auto-supersede if delta > 10 min and updated fields overlap. |
| Re-triage with existing pending suggestion | Old suggestion `UPDATE … SET status='superseded'` runs in same transaction as new insert. UI optimistically drops the stale pill before showing the new one. |
| Gemini JSON parse error / invalid enum / missing rationale | Endpoint returns `502` with detail. No `ai_suggestions` row created. `ai_requests` row gets `status='failed'`, `fallback_reason='parse_error'` so it shows in AI Monitor as a failure. |
| Gemini budget exhausted | Endpoint returns `503 {"detail": "Daily Gemini budget exhausted, retry after midnight UTC"}`. No suggestion row created. |
| Gemini upstream 5xx / network timeout | Endpoint returns `502 {"detail": "AI upstream unavailable"}`. `ai_requests` row gets `status='failed'`, `fallback_reason='upstream_error'`. |
| Triage on resolved ticket | `409 {"detail": "Cannot triage resolved ticket"}` |
| Apply on already-applied / rejected / superseded suggestion | `409 {"detail": "Suggestion is already <status>"}` — race-safe via the `UPDATE … WHERE status='pending' RETURNING *` pattern. |
| Apply on suggestion whose entity was deleted | The `UPDATE` succeeds but `db.query(Ticket).filter(...).first()` returns `None`. We still mark the suggestion applied (audit truth) and skip the ticket write. Log a warning. |
| Apply with override that fails the same JSON validation as Gemini's output (e.g. `priority_score=7`) | `422` from Pydantic before touching the DB. No state change. |
| Operator A and operator B race to apply the same suggestion | DB-level: only one of the two UPDATEs gets `RETURNING *`. The other gets `404` from the read-back (no rows), translated to `409`. Both operators see consistent state on their next refresh. |
| `assigned_to` user becomes inactive between suggestion and apply | Apply writes `assigned_to` anyway (suggestion is a point-in-time recommendation). Inactive operator just won't appear in future suggestions. |
| Ticket has `assigned_to` already set, apply suggests a different person | Suggestion's `assigned_to` overwrites the existing value. Operator can drop assigned_to in the override form to keep the existing assignee. |

## 10. Test plan

`backend/tests/test_ai_suggestions.py` — 9 tests, mock Gemini via `monkeypatch.setattr("app.routers.tickets.call_gemini", …)` and `…gemini_today_spend_usd`.

| # | Test | What it asserts |
|---|------|-----------------|
| 1 | `test_triage_creates_pending_suggestion` | Happy path: Gemini returns valid JSON → suggestion row exists with `status='pending'`, ai_request row linked, response payload shape matches schema. |
| 2 | `test_triage_supersedes_existing_pending` | Second triage call on same ticket → first row's status becomes `superseded`, exactly one `pending` row remains for the ticket. |
| 3 | `test_apply_writes_to_ticket_and_marks_verified` | Apply with no override → ticket.ai_category/ai_priority_score/ai_confidence/assigned_to written, ticket.human_verified=true, ticket.human_override=false, suggestion.applied_payload equals payload. |
| 4 | `test_apply_with_override_flips_override_flag` | Apply with override_payload differing from suggestion → ticket.human_override=true, suggestion.applied_payload=override, audit row action='ai.suggestion.override'. |
| 5 | `test_reject_marks_rejected_with_reason` | POST /reject with `{reason: "low confidence"}` → status='rejected', rejection_reason persisted, audit row present. |
| 6 | `test_gemini_parse_error_returns_502_no_suggestion` | Gemini returns `"not json"` → endpoint returns 502, no `ai_suggestions` row, `ai_requests` row has `status='failed'`. |
| 7 | `test_apply_race_returns_409` | Suggestion pre-set to `applied` → POST /apply returns 409 with detail mentioning current status. |
| 8 | `test_triage_requires_operator_403_for_readonly` | Readonly token → POST /ai-triage returns 403. |
| 9 | `test_triage_resolved_ticket_returns_409` | Ticket with `status='resolved'` → POST /ai-triage returns 409 before calling Gemini (assert call_gemini not invoked via monkeypatch sentinel). |

Tests follow the same RED-only-pending-TEST_DATABASE_URL pattern as the meeting-notes ship (see `backend/tests/conftest.py` env guard).

## 11. Files touched

### New (4)
- `backend/app/models/ai_suggestion.py` — `AISuggestion` ORM
- `backend/app/routers/suggestions.py` — `/apply`, `/reject`, `/pending` endpoints
- `backend/tests/test_ai_suggestions.py` — 9 tests
- `frontend/src/components/SuggestionPill.vue` — pill UI

### Modified (8)
- `backend/app/models/__init__.py` — export `AISuggestion`
- `backend/app/routers/tickets.py` — add `POST /{id}/ai-triage`; extend list endpoint to LEFT JOIN latest non-superseded suggestion per ticket
- `backend/app/schemas/responses.py` — `SuggestionDetail`, `SuggestionApplyBody`, `SuggestionRejectBody`, `PaginatedSuggestions`, `SuggestionPayloadTicket`, extend `TicketRow` with optional `suggestion: Optional[SuggestionDetail]`
- `backend/app/main.py` — register `suggestions.router`
- `schema.sql` — append `ai_suggestions` table + 2 indexes
- `frontend/src/api/index.js` — `suggestionsAPI` + `ticketsAPI.aiTriage(id)`
- `frontend/src/views/TicketsView.vue` — wire row template state machine, operator list fetch, suggesting/applying busy flags
- `docs/PLATFORM_OVERVIEW.md` — add §X "AI Suggestion infrastructure" subsection under AI / Gemini integration (~30 lines)

## 12. Rollout

1. Apply `schema.sql` ALTER (additive, no breaking changes).
2. Backend ships → restart uvicorn. New endpoints visible in `/docs`.
3. Frontend ships → users see "Get AI suggestion" button. Existing tickets unaffected until operator clicks.
4. No data migration. No backfill. Existing `tickets.ai_category` columns (currently null) get populated organically as operators triage.
5. Monitor `ai_requests` for `request_type='ticket_triage'` cost burn. Expected: ~$0.0006 per triage call, ~$0.30/day at 500 triages/day. Far below `$10/day` cap.
6. Future toggle (not in v1 scope): per-tenant or per-environment `ENABLE_AI_TRIAGE` flag if cost surprise materialises.

## 13. Future consumers (out of scope, sketched for clarity)

The shared `ai_suggestions` table is built to absorb these without redesign — each adds a new `entity_type` and a new payload validator:

| Future consumer | `entity_type` | Payload sketch | Trigger endpoint |
|-----------------|---------------|----------------|------------------|
| Lead next-action suggestion | `lead` | `{action: 'pause|set_priority|mark_cold|schedule_meeting', value, rationale}` | `POST /admin/leads/{id}/ai-suggest-action` |
| Opportunity stage advance suggestion | `opportunity` | `{next_stage, deal_value_estimate, rationale}` | `POST /admin/opportunities/{id}/ai-suggest-advance` |
| Email re-engagement angle (smart followup) | `lead` | `{angle: 'pain|social_proof|case_study|grant_alignment', template_id, rationale}` | `POST /admin/leads/{id}/ai-suggest-angle` |
| Workflow failure root-cause | `workflow_execution` | `{likely_cause, suggested_fix, retry_strategy}` | `POST /admin/workflows/executions/{id}/ai-explain` |

Each consumer reuses `services/gemini.py`, the `ai_suggestions` table, the same lifecycle states, the same apply/reject endpoints (which become entity-agnostic: `POST /admin/suggestions/{id}/apply` already takes `override_payload` as a generic JSON). The only per-consumer work is:

- A prompt builder + payload validator (~100 LOC each).
- An `_apply_<entity>(db, suggestion, applied_payload)` function dispatched on `suggestion.entity_type` inside the generic apply endpoint.

## 14. Open questions (to resolve before plan)

### Resolved during self-review
- **`record_decision_row` signature change** — must be extended to return the inserted `ai_requests.id` (currently returns `None`). Backwards-compatible: existing callers (`insights.py`, `meetings.py`) discard the return value already. Plan adds this as a prerequisite task before the suggestions router.
- **Shared `_audit` helper** — currently defined privately inside `routers/meetings.py`. Plan lifts it to `app/services/audit.py` so the new `routers/suggestions.py` and `routers/tickets.py` triage endpoint can reuse it without copy-paste.
- **`TicketRow` extension** — adds optional `suggestion: Optional[SuggestionDetail] = None`. Single Pydantic model, no new type.

### Deliberate non-decisions for v1 (not blockers)
- Whether suggestion list endpoints should return the linked `ai_requests` cost — deferred; can be added by JOIN later.
- Whether to surface suggestion KPIs (acceptance rate, override rate) on the Insights view — deferred; out of scope for v1 but trivial to add via aggregate query.
- Whether the `SuggestionPill` should support a "Snooze 24h" action — deferred; v1 only has Apply / Edit / Reject.
- Whether to enforce a per-operator daily suggestion cap (e.g. "operator can request at most 50 suggestions per day") — deferred; global budget guard suffices for v1.
