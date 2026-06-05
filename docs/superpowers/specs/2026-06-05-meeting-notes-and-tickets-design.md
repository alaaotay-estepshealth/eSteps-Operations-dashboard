# ES-OPS-09 — Meeting Notes & Checklist (per upcoming meeting)

**Date:** 2026-06-05
**Author:** Alaa Otay
**Status:** Design — pending implementation
**Spec ID:** ES-OPS-09-MEET-NOTES

---

## 1. Problem

Operators currently see **upcoming meetings** as a read-only list in
`FollowupsView → Upcoming Meetings` (derived from `leads.meeting_scheduled_for`
+ `opportunities` + inbound conversations with meeting intent). The `MeetsView`
file explorer surfaces static prep documents (PDFs, markdown) stored in
`meet_assets`. **Neither lets the operator write per-meeting prep notes,
talking points, questions, or action items.** Prep currently happens in
external tools (paper, Notion, head) and gets lost after the call.

This spec adds a first-class **per-meeting artifact** containing:
- A markdown **prep note** (pre-call)
- A markdown **recap note** (post-call)
- A **checklist** of action items with optional due dates and assignees
- An **AI-drafted starter prep note** on first open (Gemini 2.5 Flash)
- Overdue checklist items **bubble into Followups + Briefing**

## 2. Goals / Non-goals

**Goals**
- Operator opens an upcoming meeting → sees an AI-drafted prep note + can edit
- Operator captures action items with due dates that surface globally when overdue
- After the call, operator writes a recap on the same artifact
- Decision-helper visibility: Briefing shows count of open meeting tasks and
  meetings today; Followups bubbles overdue tasks as their own section

**Non-goals (v1)**
- Sending follow-up emails from inside the meeting drawer (deferred — reply-
  from-dash spec covers this)
- AI-generated recap (manual only; humans control the source of truth)
- Real-time co-editing — last-write-wins is acceptable for the team's size
- E2E test coverage (added with reply-from-dash work)

## 3. Architecture overview

```
┌─ ops DB (Supabase eu-west-1) ─────────────────────────────────┐
│                                                                │
│  bookings  ◄── one row per upcoming/past meeting (materialized)│
│     ├── meeting_notes      (1 row, prep_md + recap_md)        │
│     └── meeting_tasks      (N rows, checklist items)          │
└────────────────────────────────────────────────────────────────┘
            ▲                          ▲
            │ FK (lead_id)             │ writes
   leads DB (eu-central-1)             │
   read-only: name, score,             │
   research_area, last_msg             │
            │                          │
            ▼                          ▼
   ┌──────────────────────────────────────────┐
   │  FastAPI routers/meetings.py             │
   │   GET    /admin/meetings                 │
   │   GET    /admin/meetings/{id}            │
   │   POST   /admin/meetings/sync            │ ← n8n calls this
   │   PATCH  /admin/meetings/{id}/notes      │
   │   POST   /admin/meetings/{id}/tasks      │
   │   PATCH  /admin/meetings/{id}/tasks/{t}  │
   │   DELETE /admin/meetings/{id}/tasks/{t}  │
   │   POST   /admin/meetings/{id}/ai-draft   │ ← Gemini
   └──────────────────────────────────────────┘
            │
   ┌────────┴───────────────────────────────┐
   │  Frontend (Vue 3)                      │
   │   FollowupsView   → drawer (existing)  │
   │   /meeting/:id    → full page (new)    │
   │   BriefingView    → tasks badge        │
   │   ContactsView    → meeting timeline   │
   └────────────────────────────────────────┘
```

**Two-DB note:** bookings/notes/tasks live in **ops** (eu-west-1).
`lead_id` references the leads DB (eu-central-1). No cross-DB FK; joins are
done in the router via separate sessions, same pattern as `bookings.py` today.

## 4. Data model

```sql
-- 1. bookings — extend existing model; materialize rows
ALTER TABLE bookings
  ADD COLUMN IF NOT EXISTS title TEXT,
  ADD COLUMN IF NOT EXISTS meeting_url TEXT,
  ADD COLUMN IF NOT EXISTS duration_min INT DEFAULT 20,
  ADD COLUMN IF NOT EXISTS rescheduled_from TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ix_bookings_scheduled_for ON bookings(scheduled_for);
CREATE INDEX IF NOT EXISTS ix_bookings_lead_status   ON bookings(lead_id, status);

-- 2. meeting_notes — 1 row per booking, lazy-created on first open
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

-- 3. meeting_tasks — N rows per booking
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

**Reschedule semantics:** `/meetings/sync` upserts on `(lead_id, scheduled_for ±5min)`.
Inside the window → update + stash `rescheduled_from`; outside → new booking
row. `booking_id` is stable → notes + checklist follow automatically.

**Delete cascade:** `ON DELETE CASCADE` removes notes + tasks when a booking is
purged. Bookings are never hard-deleted from the API; only `status='canceled'`.

## 5. API

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/admin/meetings` | viewer+ | filters: `status`, `from`, `to`, `has_open_tasks` |
| GET | `/admin/meetings/{booking_id}` | viewer+ | returns `{ booking, lead, notes, tasks[], lead_signals, previous_meetings: [{ booking_id, scheduled_for, status }] }`. Triggers AI auto-draft if no note exists. |
| PATCH | `/admin/meetings/{booking_id}/notes` | operator+ | body: `{ prep_md?, recap_md? }` |
| POST | `/admin/meetings/{booking_id}/tasks` | operator+ | body: `{ title, due_at?, assignee?, order_index? }` |
| PATCH | `/admin/meetings/{booking_id}/tasks/{task_id}` | operator+ | body: `{ title?, done?, due_at?, assignee?, order_index? }` |
| DELETE | `/admin/meetings/{booking_id}/tasks/{task_id}` | operator+ | |
| POST | `/admin/meetings/{booking_id}/ai-draft` | operator+ (`force=true` admin only) | body: `{ force?: bool }` |
| POST | `/admin/meetings/sync` | admin only | body: `{ source: 'n8n'\|'manual', dry_run?: bool }` |

**Extended responses:**
- `GET /admin/followups` adds `open_meeting_tasks: { count, tasks: [...] }`
- `GET /admin/briefing` adds `meeting_open_tasks: int` + `meetings_today: int`
- `GET /admin/bookings/calendar` adds per row: `booking_id`, `open_task_count`, `has_notes`

**Audit:** all writes → `audit_logs`.

## 6. AI auto-draft

**Trigger:** first `GET /admin/meetings/{id}` for a booking, when
`meeting_notes` row missing OR `ai_drafted_at IS NULL AND prep_md = ''`.
Synchronous Gemini call (≈1–2 s); result persisted before the response returns.

**Context built in router (not LLM-generated):**

```
Lead: {first_name} {last_name}, {title} @ {institution}
Research area: {research_area}   Score: {lead_score}/10   Stage: {stage}
Bio excerpt: {bio[:400]}
Last inbound reply ({days_ago}d ago): {last_inbound_body[:400]}
Last 3 touchpoints: {sequence_summary}
Meeting in {hours_until} hours · duration {duration_min} min
```

**Instruction (system text):**
> Draft a concise 20-min discovery-call prep note in markdown for an eSteps
> Health partnership rep. Sections: **Why this lead matters** (1–2 lines),
> **Key questions to ask** (3–5 bullets, research-anchored), **Talking points**
> (3 bullets tying eSteps capabilities to their research), **Watch-outs** (1–2
> sensitivities), **Next-step ask** (one concrete CTA). No filler. No
> hallucinated citations.

**Model:** `gemini-2.5-flash` via a shared `app/services/gemini.py` (extract
the existing `_call_gemini` helper from `insights.py` so both routers share it).

**Cost guard:** soft cap from `settings.ai_daily_budget_usd`. `ai_today_spend`
is computed as `SUM(cost_estimate_usd)` from `ai_decisions` where
`created_at::date = current_date` (cached in-memory per process for 60 s to
avoid hammering the table on every meeting open). If
`ai_today_spend >= budget`, return empty note with `ai_skipped:'budget_exhausted'`.
Operator can retry via `POST /ai-draft {force:true}` (admin only — forces a
call regardless of budget).

**Failure modes:** Gemini 5xx → return empty note + `ai_skipped:'upstream_error'`,
log to `ai_decisions`. No exception bubbles up. UI renders a yellow "Draft
failed — click to retry" pill.

**Audit:** every Gemini call writes one row to `ai_decisions`
(`request_type='meeting_prep'`, `request_payload`, `response_payload`,
`cost_estimate_usd`). Existing AIMonitor view surfaces them automatically.

## 7. UI surfaces

**A. `FollowupsView.vue`** — Upcoming Meetings rows become clickable → open
`MeetingDrawer` (slide from right, 80 % viewport desktop / full mobile). New
section "Open meeting tasks" fed by `open_meeting_tasks` from `/admin/followups`.

**B. `MeetingDrawer.vue`** (new):

```
┌─ Drawer header ───────────────────────────────────────┐
│ Dr. Jane Elder · Mayo Clinic · in 4h 12m              │
│ [Open full page ↗] [Mark held] [No-show] [×]         │
├───────────────────────────────────────────────────────┤
│ Tabs:  [Prep] [Recap] [Checklist 3/7]                 │
│ Previous: 2 meetings (last 3w ago) →                  │
├───────────────────────────────────────────────────────┤
│ Prep tab:                                             │
│   ── AI-drafted 2h ago · gemini-2.5-flash ──         │
│   <Markdown editor — TipTap or contenteditable+marked>│
│   [Save (auto every 4s)] [Re-draft with AI]           │
│                                                       │
│ Recap tab:  same editor, separate field, autosave    │
│                                                       │
│ Checklist tab:                                        │
│   [+ Add task]                                        │
│   ☐ Ask about IRB approval timeline   due in 2d  ⋯   │
│   ☐ Send eSteps case study PDF        no due      ⋯   │
│   ☑ Verify Zoom link works            done 1h ago    │
└───────────────────────────────────────────────────────┘
```

**C. `MeetingView.vue`** (new route `/meeting/:booking_id`) — full-page render
of the same components without drawer chrome. Deep-linkable from briefing,
contacts, or shared link.

**D. `BriefingView.vue`** — new card "Meetings today" with `meetings_today`
count + "Open meeting tasks" badge (red if any overdue). Click → routes to
`/followups#open_meeting_tasks`.

**E. `ContactsView.vue`** — timeline meeting bubbles link to `/meeting/:id`.

**F. `Sidebar.vue`** — no new top-level item; deep-link route reachable from
drawer, briefing, contacts.

**Autosave:** notes editor debounces 4 s; checklist mutations immediate (PATCH
on toggle, optimistic UI; rollback + toast on 5xx).

**Components reused:** `Markdown.vue`, `ConfirmDialog.vue`, `StatRow.vue`,
`useStaleFetch`.

## 8. Edge cases

| Case | Behavior |
|---|---|
| Lead reschedules (n8n updates `meeting_scheduled_for`) | `/sync` updates row, stashes old time in `rescheduled_from`; notes preserved. Drawer shows "Rescheduled from {old}" badge. |
| Lead cancels | `status='canceled'`; notes + tasks preserved (read-only). Drawer shows red banner. Tasks no longer bubble into Followups. |
| No-show | Operator clicks "No-show" → `status='no_show'`, `no_show_detected=true`, `completed_at=now()`. Prep tab becomes read-only; Recap stays editable. |
| Meeting held | Operator clicks "Mark held" → `status='completed'`, `completed_at=now()`. UI focuses Recap with a "Add 2-line recap?" placeholder (no AI). |
| Two meetings same lead | Each gets its own `booking_id`. Drawer shows "Previous meeting (3w ago) — notes available" link. |
| Gemini 503 / budget exhausted | Empty note + yellow pill "Draft failed/skipped — click to retry". No throw. |
| Concurrent edits | Last-write-wins on notes (low contention). Tasks PATCH per-row so independent. `updated_at` returned with every write; UI shows "Updated by {user} 5 s ago" if not yours. |
| Markdown XSS | Render via existing `Markdown.vue` (`marked` + DOMPurify). Server stores raw, never executes. |
| Lead deleted (GDPR) | `bookings.lead_id` orphaned. Cron job purges bookings whose `lead_id` returns 404 from leads DB for 30 days. |
| RBAC | Viewer = read-only. Operator = edit. Admin = `/sync` + `ai-draft force=true`. |
| Sync idempotency | Upsert on `(lead_id, scheduled_for ±5min)` — collapses near-time reschedules; outside window inserts new row. |

## 9. Testing

```
backend/tests/
  test_meetings_router.py     ← happy path: create note, add task, toggle, list, sync
  test_meetings_ai.py         ← Gemini mocked: success draft, 503 fallback, budget cap
  test_meetings_sync.py       ← idempotency: rerun same payload → no dupes; reschedule keeps id
  test_followups_bubble.py    ← overdue task bubbles into /admin/followups
```

Pytest fixtures: `booking_factory`, `meeting_note_factory`, `meeting_task_factory`.
`TEST_DATABASE_URL` (separate Supabase project) per the existing guard in
`tests/conftest.py`. Coverage target: 80 % on the new files.

Frontend: Vitest snapshot for `MeetingDrawer.vue` 3-tab states; manual smoke
per `web/testing.md` checklist (320 / 768 / 1440 breakpoints). No E2E for v1
— added with reply-from-dash work.

## 10. Files touched

**New (backend)**
- `backend/app/models/meeting_note.py`
- `backend/app/models/meeting_task.py`
- `backend/app/routers/meetings.py`
- `backend/app/services/gemini.py` (extracted from `routers/insights.py`)
- `backend/tests/test_meetings_*.py` (4 files)

**Modified (backend)**
- `backend/app/models/booking.py` — add `title`, `meeting_url`, `duration_min`, `rescheduled_from`
- `backend/app/routers/bookings.py` — `/calendar` returns `booking_id`, `open_task_count`, `has_notes`
- `backend/app/routers/followups.py` — new `open_meeting_tasks` section
- `backend/app/routers/briefing.py` — `meeting_open_tasks`, `meetings_today` fields
- `backend/app/routers/insights.py` — switch to shared `services/gemini.py`
- `backend/app/main.py` — register `meetings` router
- `backend/app/schemas/responses.py` — `MeetingDetail`, `MeetingNoteUpdate`, `MeetingTaskCreate`, `MeetingTaskUpdate`, `MeetingTaskRow`, `MeetingListItem`, `OpenMeetingTasksSection`
- `schema.sql` — add the three CREATE TABLE / ALTER TABLE blocks

**New (frontend)**
- `frontend/src/views/MeetingView.vue` (route `/meeting/:booking_id`)
- `frontend/src/components/MeetingDrawer.vue`
- `frontend/src/components/MeetingTaskRow.vue`
- `frontend/src/components/MeetingNoteEditor.vue` (markdown editor + autosave)

**Modified (frontend)**
- `frontend/src/views/FollowupsView.vue` — clickable rows, new section
- `frontend/src/views/BriefingView.vue` — new "Meetings today" card
- `frontend/src/views/ContactsView.vue` — meeting bubbles deep-link
- `frontend/src/router/index.js` — new route
- `frontend/src/api/index.js` — `meetingsAPI`

## 11. Migration / rollout

1. Apply `schema.sql` changes (add columns + two tables + indexes).
2. Deploy backend with `/meetings/sync` available but n8n still pushing the old
   `meeting_scheduled_for` field only. Run a one-shot manual `/sync` to
   backfill `bookings` rows from existing `leads.meeting_scheduled_for`.
3. Update the n8n EST-3 / EST-5 workflows to POST `/admin/meetings/sync` after
   booking events.
4. Deploy frontend with route + drawer behind no feature flag — the UI
   degrades gracefully if a booking has no notes/tasks yet.
5. Set `GEMINI_AUTO_DRAFT_ENABLED=false` in `.env` to ship without AI; flip on
   once cost telemetry from `ai_decisions` confirms ≤ $1/day at current
   meeting volume.

## 12. Open questions

- Should checklist `due_at` default to `scheduled_for - 24h` when a user adds
  a task without picking a date? Defer — empty default for v1, telemetry will
  tell us.
- TipTap vs `contenteditable + marked` for the note editor? TipTap is heavier
  (~80 KB gzipped) but supports `/` commands and clean paste. Decision: ship
  v1 with `contenteditable + marked` (zero new deps); revisit if operators
  ask for slash commands.
- Do we expose a public "share read-only meeting page" link? Deferred — adds
  auth complexity, no current user ask.

## 13. LOE

| Phase | Hours |
|---|---|
| Schema migration + models + sync | 4 |
| Router + schemas + AI service extraction | 6 |
| Followups + briefing wiring | 2 |
| MeetingDrawer + MeetingView + editor | 8 |
| Tests + audit + budget guard | 4 |
| Docs + n8n hook update | 2 |
| **Total** | **~26 hours** |
