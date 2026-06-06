# ES-OPS-09 — Platform Overview
> One-stop technical map of the eSteps Operations Dashboard. For mission/status see [README](../README.md); for product strategy see [PRODUCT.md](PRODUCT.md); for design tokens see [DESIGN.md](DESIGN.md).

**Last refreshed:** 2026-06-06 (after meeting-notes feature ship — commits 0b95ef5..1395c7e)

## Table of contents
1. [Architecture at a glance](#architecture-at-a-glance)
2. [The Five Systems](#the-five-systems)
3. [Authentication & RBAC](#authentication--rbac)
4. [Data model](#data-model)
5. [Views catalog (25)](#views-catalog-25)
6. [API reference (68+ endpoints)](#api-reference)
7. [AI / Gemini integration](#ai--gemini-integration)
8. [Meeting prep (Notes / Tasks / AI auto-draft)](#meeting-prep)
9. [GTM Strategy + Meet Prep asset explorers](#asset-explorers)
10. [OpenClaw agent integration](#openclaw-agent-integration)
11. [n8n workflows (EST-1 → EST-8)](#n8n-workflows)
12. [Email outreach + A/B testing](#email-outreach)
13. [Briefing / Daily memo / Insights](#briefing-and-insights)
14. [Webhooks](#webhooks)
15. [Frontend design system](#frontend-design-system)
16. [Configuration & environment](#configuration--environment)
17. [Testing](#testing)
18. [Deployment notes](#deployment-notes)

---

## Architecture at a glance

ES-OPS-09 is a three-tier system. Workflow automation runs in n8n, two Supabase Postgres databases hold the data (operational and leads-source), and a FastAPI backend serves a Vue 3 SPA. The dashboard is read-mostly: every state change passes through a REST endpoint that emits an audit log.

```
                                  ┌────────────────────────┐
                                  │ leads-source DB        │  read-mostly
                                  │ (Supabase eu-central-1)│  leads, email_logs,
                                  │                        │  opportunities,
                                  └──────────▲─────────────┘  conversations
                                             │
┌──────────────┐      webhooks       ┌───────┴────────┐      ┌────────────────────┐
│ n8n (8 wfls) │────HMAC POST───────▶│ FastAPI        │◀────▶│ ops DB (Supabase)  │
│ EST-1..EST-8 │      ai-decisions   │ /webhooks/*    │      │ users, bookings,   │
│ Calendly,    │                     │ /admin/*       │      │ meeting_notes,     │
│ Gmail, Sheets│                     │ /proxy/n8n     │      │ meeting_tasks,     │
└──────────────┘                     │ /auth/*        │      │ workflow_executions│
                                     └───────┬────────┘      │ ai_requests,       │
                                             │ JSON          │ audit_logs,        │
                                             │ JWT           │ systems, tickets,  │
                                             ▼               │ strategy_assets,   │
                                     ┌────────────────┐      │ meet_assets        │
                                     │ Vue 3 SPA      │      └────────────────────┘
                                     │ 25 views, RBAC │
                                     │ Pinia + Axios  │
                                     └────────────────┘
```

| Tier | Stack | Role |
|------|-------|------|
| Automation | n8n cloud + Gmail OAuth + Calendly + Google Sheets | Runs the 8 EST-* workflows; POSTs callbacks/AI decisions back into the ops DB |
| Data | 2x Supabase Postgres (ops + leads-source) | Ops DB owns users / meetings / audit / asset blobs; leads-source DB is the CRM read surface |
| Service | FastAPI + SQLAlchemy + Alembic | 18 routers, 68+ endpoints, JWT auth, HMAC webhooks |
| Client | Vue 3 + Vite + Pinia + Tailwind | 25 routed views with Control Room dark tokens; SWR-style staleness; offline-friendly |

See also: [README.md](../README.md) for the project tree and dev history; [SYSTEM_DOCUMENTATION.md](SYSTEM_DOCUMENTATION.md) for the long-form pre-ship reference.

---

## The Five Systems

ES-OPS-09 was designed multi-tenant from the start. The `systems` table holds one row per logical "system" (campaign domain). Every workflow execution, AI decision, audit log, and webhook is scoped by `system_id`. Cross-system stats are aggregated via `services/system_service.py`.

| Slug | Purpose | Source of truth |
|------|---------|-----------------|
| es-ops-09 | Default eSteps lead generation campaign | leads-source DB + ops DB |
| (additional slugs) | Future campaigns / parallel domains | Same schemas, separate `system_id` |

Each system row holds: `slug` · `webhook_secret` (per-system HMAC key) · `n8n_project_id` · `is_active`. The **All Systems** view (`/systems`, admin-only) and **System Detail** (`/systems/:slug`) surface per-system metrics.

For design rationale see [docs/superpowers/specs/2026-05-05-es-ops-09-multi-system-design.md](superpowers/specs/2026-05-05-es-ops-09-multi-system-design.md).

---

## Authentication & RBAC

Stateless JWT (HS256). Three roles, normalized:

| Role | Reads | Writes | Admin actions |
|------|-------|--------|---------------|
| readonly | All dashboards | — | — |
| operator | All dashboards | Reviews, lead actions, meeting notes/tasks, AI drafts | — |
| admin | All dashboards | Everything | n8n sync, GTM/Meet uploads, user CRUD, OpenClaw, webhook secret rotation |

Implementation lives in `backend/app/auth.py`:

- Token payload: `{sub: user_id, role, exp}` — 1440 min default (`jwt_expire_minutes`).
- Passwords: PBKDF2-SHA256 primary; legacy bcrypt (`$2a/$2b/$2y`) accepted for migration.
- Injectors: `get_current_user`, `require_operator`, `require_admin`.
- Legacy `viewer` role is normalized to `readonly` on load.
- Token endpoint: `POST /auth/token` (OAuth2PasswordBearer, unauthenticated).

Frontend (`src/stores/auth.js`) persists token in localStorage, exposes `isAdmin / isOperator / isReadonly / canWrite` getters, and wires `hasRole(role)` for guard checks. Axios interceptors (`src/api/index.js`) attach `Authorization: Bearer …` on every request and auto-logout on 401.

---

## Data model

14 tables across two databases. Ops DB owns operational state; leads-source DB is the CRM read surface (mostly read; n8n writes lead stage transitions).

### Ops DB

| Table | PK | FKs | Key columns | Purpose |
|-------|----|----|-------------|---------|
| users | id (UUID) | — | username, email, role, is_active | JWT auth |
| bookings | id (UUID) | lead_id | status, scheduled_for, completed_at, title, meeting_url, duration_min, rescheduled_from | Calendly meetings. **NEW columns** (2026-06-05): title, meeting_url, duration_min, rescheduled_from |
| **meeting_notes** | booking_id (UUID) | booking_id (CASCADE) | prep_md, recap_md, ai_drafted_at, ai_model, updated_by | **NEW** — markdown prep + recap notes |
| **meeting_tasks** | id (UUID) | booking_id (CASCADE) | title, due_at, done, done_at, assignee, order_index, overdue_by_hours (computed) | **NEW** — per-meeting checklist |
| workflow_executions | id (UUID) | system_id | workflow_id, status, started_at, duration_seconds, error_type, retry_count | n8n run audit |
| ai_requests | id (UUID) | system_id | request_type, provider, confidence_score, status, human_verified, human_override, retention_until | AI decision log |
| audit_logs | id (UUID) | system_id | level, source, correlation_id, created_at, message | System audit |
| systems | id (UUID) | — | slug, webhook_secret, n8n_project_id, is_active | Multi-system registry |
| tickets | id (UUID) | — | source, ai_category, ai_priority_score, assigned_to, status, response_time_min, human_verified | Support tickets |
| strategy_assets | id (UUID) | — | relative_path (unique), parent_path, is_folder, mime_type, size_bytes, content (BLOB), uploaded_by | GTM file store |
| meet_assets | id (UUID) | — | (same shape as strategy_assets) | Meet prep file store |

### Leads-source DB (read-mostly, eu-central-1)

| Table | PK | Key columns | Purpose |
|-------|----|-------------|---------|
| leads | id (UUID) | lead_id, email, stage, campaign_tag, lead_score, meeting_booked_at, meeting_scheduled_for, title, bio | Lead CRM — single source of truth for researcher records |
| email_logs | id (UUID) lead_id | sequence_step, ab_variant, email_status, open_detected, sent_at | Outreach tracking + A/B variant tag |
| opportunities | id (UUID) lead_id | stage, partnership_tier, deal_value_usd, expected_close_date | Deals pipeline |

**Lead stages:** `new → introduced → pitching → call_requested → cold (terminal)`. Plus `dead`, `bounced`. The active set is `stage NOT IN ('cold', 'dead', 'bounced', 'Cold')`.

### Migrations

- `alembic/versions/0001_initial_schema` — full ops DB baseline
- `alembic/versions/0002_multi_system` — system_id scoping + systems table
- `schema.sql` — final consolidated state, kept in sync with migrations. Section 12 added with ES-OPS-09-MEET-NOTES additions: 4 new booking columns + `meeting_notes` + `meeting_tasks` + `ix_tasks_open_due` partial index for fast "open tasks past due" queries.

Schemas are exposed to the frontend via Pydantic models in `backend/app/schemas/responses.py`, grouped: Auth · Dashboard metrics · Workflow status · Activity & alerts · AI decisions & logs · Pipeline & leads · Email campaigns · Bookings & calendar · Opportunities · Meetings (`MeetingListItem`, `MeetingDetail`, `MeetingBookingSummary`, `MeetingLeadSummary`, `MeetingNoteData`, `MeetingNoteUpdate`, `MeetingTaskRow`, `MeetingTaskCreate`, `MeetingTaskUpdate`, `MeetingSyncResult`, `PreviousMeeting`, `OpenMeetingTaskRow`) · Tickets · GTM & Meet Strategy · Human review · Webhooks/Ingest.

---

## Views catalog (25)

Path → Component map. Roles use the constants `ALL = ['admin','operator','readonly']`, `OPS = ['admin','operator']`, `ADM = ['admin']`.

| Path | Component | Roles | Purpose |
|------|-----------|-------|---------|
| /login | Login | public | Auth entry |
| / | — | — | Redirects to /briefing |
| /briefing | BriefingView | ALL | Daily briefing: overnight, priorities, AI memo, recommended contacts |
| /overview | Overview | ALL | Campaign funnel, stage breakdown, KPI snapshot |
| /insights | Insights | ALL | KPI dashboard, AI heatmap, assistant chat |
| /pipeline | Pipeline | ALL | Funnel + ICP priority breakdown |
| /contacts | ContactsView | ALL | Filterable contacts table + detail drawer |
| /followups | FollowupsView | OPS | overdue / due_today / this_week / upcoming_meetings / open_meeting_tasks |
| /workflows | Workflows | OPS | Workflow management UI |
| /ai | AIMonitor | ALL | AI confidence distribution + type breakdown |
| /review | HumanReview | OPS | Human review queue with approve/reject/override |
| /n8n | N8nWorkflows | OPS | Proxied n8n workflow browser |
| /agent | OpenClawView | OPS | OpenClaw agent launcher |
| /system | SystemLogs | ALL | Operation logs |
| /systems | SystemsOverview | ADM | All systems dashboard |
| /systems/:slug | SystemDetail | ADM | Per-system stats |
| /emails | EmailAnalytics | ALL | Email stats + logs |
| /opportunities | OpportunitiesDeals | OPS | Deals pipeline |
| /bookings | BookingsView | ALL | Bookings stats + list |
| /calendar | CalendarView | ALL | Meeting calendar grid |
| **/meeting/:bookingId** | **MeetingView** | ALL | **NEW (2026-06-05)** — single-meeting deep-link page wrapping MeetingDrawer |
| /tickets | TicketsView | OPS | Support tickets + status updates |
| /gtm | GTMStrategy | ADM | GTM strategy tree + asset explorer |
| /meets | MeetsView | ALL | Meet prep asset explorer |
| /report | ReportView | ALL | Executive report |
| /users | UsersView | ADM | User management |

Auth guard in `router.beforeEach` redirects unauthenticated users to `/login` and role mismatches to `/briefing`. Views are wrapped in `<keep-alive max="10">` so the most recent 10 views retain scroll/filter state.

### Sidebar grouping

The left rail (`components/Sidebar.vue`) buckets routes for cognitive scanning:

- **Operations:** Briefing · All Systems (ADM) · Overview · Insights
- **Pipeline:** Pipeline · Contacts · Email Analytics · Bookings · Calendar · Meet Prep · Deals (OPS) · Follow-ups (OPS)
- **Automation:** Workflows (OPS) · n8n Workflows (OPS) · AI Monitor · OpenClaw Agent (OPS) · Review Queue (OPS)
- **Strategy:** Tickets (OPS) · GTM Strategy (ADM) · System Logs · Report
- **Admin:** Users (ADM)

Icons come from `lucide-vue-next`. The collapsed/expanded preference is persisted via `useSidebarState()` against `esteps:sidebar-collapsed`.

---

## API reference

68+ endpoints across 18 routers. The Pydantic request/response shapes live in `backend/app/schemas/responses.py`; the canonical interactive reference is `/docs` (Swagger UI on the running backend). The table below is a single master map sorted by URL prefix.

### `/auth`

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | /auth/token | public | OAuth2 password grant → JWT |

### `/admin` (admin.py)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | /admin/dashboard/metrics | any | Top-line KPIs |
| GET | /admin/workflows/status | any | Workflow state matrix |
| GET | /admin/workflows/executions/daily | any | Run history by day |
| GET | /admin/ai/decisions | any | Recent AI decisions |
| GET | /admin/logs/operations | any | Live ops log feed |
| GET | /admin/logs | any | Audit log search |
| GET | /admin/pipeline/leads | any | Funnel by stage |
| GET | /admin/pipeline/research-stats | any | Research-area breakdown |
| GET | /admin/human-review/queue | any | Items awaiting review |
| GET | /admin/dashboard/activity-feed | any | Recent activity stream |
| GET | /admin/dashboard/system-health | any | Health checks |
| GET | /admin/dashboard/alerts | any | Active alerts |
| POST | /admin/human-review/queue/{id}/resolve | operator | Approve / reject / override |
| POST | /admin/sync-n8n | admin | Force pull workflow status from n8n |

### `/admin/bookings` (bookings.py)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | /admin/bookings/stats | any | Bookings KPIs |
| GET | /admin/bookings | any | Bookings list |
| GET | /admin/bookings/calendar | any | Calendar grid payload |

### `/admin/briefing` (briefing.py)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | /admin/briefing | any | Overnight summary + priorities bubble |

### `/admin/contacts` (contacts.py)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | /admin/contacts | any | Filterable contacts list |
| GET | /admin/contacts/priority | any | Highest-priority contacts |
| GET | /admin/contacts/{lead_id} | any | Detail drawer payload |

### `/admin/emails` (email_logs.py)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | /admin/emails/stats | any | Send/open/reply rates + A/B variants |
| GET | /admin/emails/logs | any | Email log search |

### `/admin/followups` (followups.py)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | /admin/followups | any | overdue / due_today / this_week / upcoming_meetings / hot_needs_action / open_meeting_tasks |

### `/admin/gtm` (gtm.py)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | /admin/gtm/strategies | admin | Top-level list |
| GET | /admin/gtm/tree | admin | Folder tree |
| GET | /admin/gtm/strategy/{path} | admin | Read file |
| GET | /admin/gtm/download/{path} | admin | Download file |
| POST | /admin/gtm/upload | admin | Upload asset |
| POST | /admin/gtm/folder | admin | Create folder |
| POST | /admin/gtm/sync | admin | Sync from filesystem mirror |
| DELETE | /admin/gtm/{path} | admin | Remove asset |

### `/admin/insights` (insights.py)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | /admin/insights | any | KPI dashboard payload |
| GET | /admin/insights/memo | any | Gemini-generated daily memo |
| GET | /admin/insights/ask-assistant | any | Gemini chat over insights data |

### `/admin/leads` (lead_actions.py)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | /admin/leads/{lead_id}/action | operator | pause/resume/mark_cold/set_priority/set_engaged/unset_engaged/schedule_meeting |

### `/admin/meetings` (meetings.py) — **NEW (2026-06-05)**

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | /admin/meetings/sync | admin | Pull bookings from Calendly via n8n; reconcile reschedules |
| GET | /admin/meetings | any | List with status / window filters |
| GET | /admin/meetings/{booking_id} | any | Detail + notes + tasks; triggers AI auto-draft if prep_md empty |
| PATCH | /admin/meetings/{booking_id}/notes | operator | Update prep_md / recap_md |
| POST | /admin/meetings/{booking_id}/tasks | operator | Create task |
| PATCH | /admin/meetings/{booking_id}/tasks/{task_id} | operator | Update task (toggle done, edit title/due_at) |
| DELETE | /admin/meetings/{booking_id}/tasks/{task_id} | operator | Remove task |
| POST | /admin/meetings/{booking_id}/ai-draft | operator | Force regenerate AI prep |

### `/admin/meets` (meets.py)

Asset explorer parallel to `/admin/gtm`. Same endpoint shape — `strategies / tree / strategy/{path} / download/{path}`, plus admin POST `upload / folder / sync` and DELETE `{path}`.

### `/admin/openclaw` (openclaw.py)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | /admin/openclaw/status | operator | Check config presence (no secrets returned) |
| POST | /admin/openclaw/agent | admin | Synchronous agent dispatch (120 s timeout) |
| POST | /admin/openclaw/wake-event | admin | Async wake event |

### `/admin/opportunities` (opportunities.py)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | /admin/opportunities/stats | any | Deal KPIs |
| GET | /admin/opportunities | any | Deals list |

### `/admin/systems` (systems.py)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | /admin/systems | any | All systems |
| GET | /admin/systems/overview | any | Cross-system aggregate |
| GET | /admin/systems/{slug} | any | Single system + stats |
| GET | /admin/systems/{slug}/activity | any | Per-system activity feed |

### `/admin/tickets` (tickets.py)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | /admin/tickets/stats | any | Tickets KPIs |
| GET | /admin/tickets | any | Tickets list + filters |

### `/admin/users` (users.py)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | /admin/users | admin | List users |
| GET | /admin/users/{id} | admin | Detail |
| POST | /admin/users | admin | Create |
| PATCH | /admin/users/{id} | admin | Update |
| DELETE | /admin/users/{id} | admin | Remove |

### `/proxy/n8n` (n8n_proxy.py)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | /proxy/n8n/workflows | any | List workflows from n8n cloud |
| GET | /proxy/n8n/workflows/{id} | any | Single workflow definition |
| POST | /proxy/n8n/workflows/{id}/execute | operator | Trigger workflow |
| POST | /proxy/n8n/workflows/{id}/activate | operator | Activate |
| POST | /proxy/n8n/workflows/{id}/deactivate | operator | Deactivate |

### `/webhooks` (webhooks.py)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | /webhooks/{system_slug}/callback | HMAC | n8n execution callback |
| POST | /webhooks/{system_slug}/ai-decision | HMAC | AI decision ingestion |

For the full request/response shape of every endpoint, the Swagger UI at `http://localhost:8000/docs` is the source of truth. Pydantic models are exported from `backend/app/schemas/responses.py`.

---

## AI / Gemini integration

All AI decisions go through `services/gemini.py`. Model: **`gemini-2.5-flash`**. Conservative cost estimate: **$0.0006 per call** (derived from $0.075/1M input + $0.30/1M output tokens). Daily cap: `settings.ai_daily_budget_usd = 10.0`.

### Service surface

| Function | Behaviour |
|----------|-----------|
| `call_gemini(prompt, …)` | Sends prompt, returns `(response_text, usage_dict)`; raises `BudgetExhausted` if today's spend ≥ cap |
| `cost_per_call_usd(usage)` | Computes per-call cost from token usage |
| `gemini_today_spend_usd(db)` | Spend so far today, 60 s in-process cache |
| `record_decision_row(db, …)` | Inserts row into `ai_requests` with full lineage |

### Decision lifecycle

```
prompt ─▶ Gemini ─▶ response + token usage
                        │
                        ▼
                ai_requests row written
                (provider, model, tokens_used,
                 cost_usd, latency_ms, input_preview,
                 ai_output JSONB, confidence_score,
                 used_fallback, fallback_reason,
                 human_verified, human_override,
                 status, retention_until)
                        │
                  confidence < 0.70?
                        │
                    ┌───┴────┐
                   YES       NO
                    │         │
                    ▼         ▼
        Human review queue   Auto-actioned
        (24 h SLA)           (logged only)
```

### Consumers

| Endpoint | Use |
|----------|-----|
| `GET /admin/insights/memo` | Daily AI-generated strategic memo |
| `GET /admin/insights/ask-assistant` | Free-form chat over insights data |
| `GET /admin/meetings/{id}` | Auto-drafts `prep_md` if absent (see [Meeting prep](#meeting-prep)) |
| `POST /admin/meetings/{id}/ai-draft` | Force regenerate prep |

### Budget enforcement

`call_gemini` checks `gemini_today_spend_usd()` before every call. When over budget it raises `BudgetExhausted`, which routes lift to a 503 / `status="budget_exhausted"` row so callers degrade gracefully.

---

## Meeting prep

**Shipped 2026-06-05, commits 0b95ef5..1395c7e.** Single biggest feature of the sprint. See [docs/superpowers/specs/2026-06-05-meeting-notes-and-tickets-design.md](superpowers/specs/2026-06-05-meeting-notes-and-tickets-design.md) for the original spec and [docs/superpowers/plans/2026-06-05-meeting-notes-and-tickets.md](superpowers/plans/2026-06-05-meeting-notes-and-tickets.md) for implementation history.

### Data model (3 tables)

- **bookings** extended with `title`, `meeting_url`, `duration_min`, `rescheduled_from` — Calendly metadata so the dashboard can render meeting cards without round-tripping to the source.
- **meeting_notes** (1:1 with booking, CASCADE delete) — `prep_md` (markdown prep notes) + `recap_md` (post-meeting recap) + AI lineage (`ai_drafted_at`, `ai_model`) + `updated_by`.
- **meeting_tasks** (N:1 with booking, CASCADE delete) — `title`, `due_at`, `done`, `done_at`, `assignee`, `order_index`. The computed column `overdue_by_hours` powers the "overdue" badge across the app. Partial index `ix_tasks_open_due` optimises the open-tasks-past-due query.

### Sync semantics

`POST /admin/meetings/sync` is admin-only and pulls bookings from Calendly via n8n. Reschedules within a **5-minute window** are reconciled rather than treated as new bookings — the existing booking row keeps its notes/tasks and `rescheduled_from` records the prior start time.

### AI auto-draft

First call to `GET /admin/meetings/{booking_id}` with no `meeting_notes` row triggers a background Gemini draft of `prep_md` (lead context + research area + suggested talking points). Failure modes the UI handles:

| Status | Cause | UX |
|--------|-------|-----|
| `budget_exhausted` | Daily Gemini cap hit | Banner: "AI prep unavailable — daily budget reached". Manual prep still works. |
| `upstream_error` | Gemini API error | Banner with retry button. |
| `drafted` | Success | Markdown rendered in editor with "AI draft" pill + timestamp. |

`POST /admin/meetings/{booking_id}/ai-draft` lets operators force a redraft (overwrites only if explicit).

### UI

| Component | Role |
|-----------|------|
| `MeetingView` (`/meeting/:bookingId`) | Single-meeting deep-link page wrapping the drawer for shareable links |
| `MeetingDrawer` | Slide-over from list views (Calendar, Bookings, Followups) |
| `MeetingNoteEditor` | Markdown editor for `prep_md` + `recap_md` |
| `MeetingTaskRow` | Single task row: toggle done, edit title, edit due, delete |

### RBAC

| Action | Role |
|--------|------|
| View meeting / notes / tasks | any |
| Edit notes, create/update/delete tasks, request AI draft | operator |
| Force re-draft, run sync, manage webhook secret rotation | admin |

### Where it surfaces

- **Followups** view — `open_meeting_tasks` bucket lists every undone task past due across all meetings, with bubble counts on the sidebar badge (covered by `test_followups_bubble.py`).
- **Briefing** — `priorities.meeting_open_tasks` and `priorities.meetings_today` counters.
- **Calendar** — clicking a tile opens `MeetingDrawer`.
- **Sidebar bubble** — total open overdue tasks.

---

## Asset explorers

`/gtm` and `/meets` share an identical file-explorer pattern backed by two tables (`strategy_assets`, `meet_assets`). Files live as BLOBs in Postgres (not on disk) so deploys stay stateless.

### Schema

Both tables share: `relative_path` (unique) · `parent_path` · `is_folder` · `mime_type` · `size_bytes` · `content` (BLOB) · `uploaded_by`.

### Allowed file types

`md, txt, rst, json, yaml, csv, pdf, docx, pptx, xlsx, png, jpg, svg, zip, log`. Max upload size: **25 MB**.

### Endpoints (per explorer)

- `GET /strategies` — top-level
- `GET /tree` — folder tree
- `GET /strategy/{path}` — read file
- `GET /download/{path}` — download
- `POST /upload` — upload (admin)
- `POST /folder` — create folder (admin)
- `POST /sync` — sync from filesystem mirror (admin)
- `DELETE /{path}` — remove (admin)

### Roles

- `/gtm` — admin only (sensitive GTM strategy)
- `/meets` — all roles can read; admin uploads

### Source filesystem (mirror)

`Final planning/` on the repo holds the canonical GTM material with 8 subdirectories: `01_Strategy`, `02_Channel_Stack`, `03_Workflows`, `04_Messaging_System`, `05_Execution_Plan`, `06_KPIs_and_Testing`, `07_Risks_and_Compliance`, `08_Presentation`. Key docs include `unified_strategy.md`, `channel_matrix.md`, `7day_golive.md`, V3 reviews. `POST /admin/gtm/sync` walks this tree and upserts assets.

---

## OpenClaw agent integration

OpenClaw is an external autonomous agent service. Integration is **optional** — when `OPENCLAW_BASE_URL` or `OPENCLAW_HOOK_TOKEN` is unset, the routes return **503** and the `/agent` view shows a graceful disabled state.

### Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | /admin/openclaw/status | operator | Reports config presence (booleans only, no secrets) |
| POST | /admin/openclaw/agent | admin | Synchronous run — body `{message, name?, timeout_seconds?}`, returns `agent_response`. 120 s upper bound. |
| POST | /admin/openclaw/wake-event | admin | Async fire-and-forget — body `{text, mode?}` |

Every call writes an `audit_logs` row tagged `openclaw.*` with the user, target, and outcome.

---

## n8n workflows

Eight production workflows. JSON exports live in `Final planning/03_Workflows/` (with timestamped backups).

| ID | File | Trigger | Reads | Writes |
|----|------|---------|-------|--------|
| EST-1 | Lead_Intake | Manual / scheduled | CSV + email validation | leads, email_valid flags |
| EST-2 | Outreach_Engine_V2 | 09:00 weekdays | Leads in stages new / introduced / pitching / call_requested | leads emailN_sent_at + stage |
| EST-3 | Reply_Handler | Gmail webhook | Conversations (inbound) | conversations, opportunities, AI decisions |
| EST-4 | RAG_Ingestion | Scheduled | Docs / knowledge base | Gemini embeddings → knowledge_base |
| EST-5 | Booking_Sync | Calendly webhook | Calendly + leads | bookings + confirmation emails |
| EST-6 | LinkedIn_Actions | Manual | LinkedIn enrichment | engagement log |
| EST-7 | Followup_Logic | Daily | leads (next_send_date, stage) | follow-up emails |
| EST-8 | Lead_Scoring | On import | Profile fields | lead_score, esteps_relevance_score |

All workflows post back to the dashboard:

- `POST /webhooks/{system_slug}/callback` — execution outcome (HMAC-signed)
- `POST /webhooks/{system_slug}/ai-decision` — AI decision ingestion

The dashboard also pulls workflow status proactively: `App.vue` calls `adminAPI.syncN8n(200)` every 15 minutes, and admins can force a sync via `POST /admin/sync-n8n`. The `/n8n` view proxies the live n8n cloud project via `/proxy/n8n/*`.

---

## Email outreach

EST-2 sends via Gmail (OAuth credential `gmail-cred`, sender `hello@estepshealth.com`). HTML uses eSteps green (`#2ECC71`).

### Sequence

| Touch | Day | Triggers on stage | Transitions to | Score |
|-------|-----|-------------------|----------------|-------|
| 1 | 0 | new | introduced | 5 |
| 2 | 5 | introduced | pitching | 6 |
| 3 | 10 | pitching | pitching | 7 |
| 4 | 15 | pitching | call_requested | 9 |
| 5 | 21 | call_requested | cold | 8 |

A reply at any stage can reactivate the lead (touch 5 specifically can re-open from cold). UTMs on Calendly links carry `utm_source=email&utm_medium=outreach&utm_campaign=esteps&utm_content={touch}`.

### Segments

Five research segments with segment-specific copy: **gait**, **neuro**, **rehab**, **ortho**, **sports**.

### A/B testing

`email_logs.ab_variant` tags each send with the variant id (e.g. `subjA` / `subjB`). The Email Analytics view splits reply / open rates by variant.

---

## Briefing and Insights

### `GET /admin/briefing`

The morning briefing aggregates the overnight window (last 24 h) and surfaces priorities. Shape:

```json
{
  "generated_at": "2026-06-06T07:00:00Z",
  "overnight": {
    "window": "24h",
    "new_replies": 4,
    "new_contacted": 27,
    "executions": 12,
    "failures": 0,
    "new_ai_decisions": 6
  },
  "priorities": {
    "overdue": 3,
    "due_today": 5,
    "upcoming_meetings": 2,
    "hot_uncontacted": 8,
    "meeting_open_tasks": 7,
    "meetings_today": 2
  }
}
```

The Briefing view also renders the AI memo (from `/admin/insights/memo`) and recommended contacts (from `/admin/contacts/priority`).

### Insights KPIs

| KPI | Target |
|-----|--------|
| `TARGET_REPLY_RATE` | 8.0 % |
| `TARGET_MEETING_RATE` | 3.0 % |
| `TARGET_ACTIVATION` | 60.0 % |
| `TARGET_WEEKLY_OUTREACH` | 100 sends/week |
| `HOT_SCORE` | 7 |

Status colors: green when ≥ target, amber 60–99 %, red < 60 %.

The Insights view combines: KPI cards (reply / meeting / activation / weekly outreach), a confidence heatmap of AI decisions, and a chat assistant (`/admin/insights/ask-assistant`).

---

## Webhooks

Two endpoints, both HMAC-verified. The signing secret is per-system (`systems.webhook_secret`) and matched against header `X-N8N-SIGNATURE`.

### `POST /webhooks/{system_slug}/callback`

```json
{
  "workflow_id": "EST-2-Outreach",
  "execution_id": "unique-execution-id",
  "status": "success",
  "completed_at": "2026-04-29T14:30:00Z",
  "duration_seconds": 45,
  "items_processed": 15,
  "items_failed": 0,
  "error_message": null,
  "metadata": { "...": "..." }
}
```

Writes one `workflow_executions` row + one `audit_logs` row.

### `POST /webhooks/{system_slug}/ai-decision`

```json
{
  "request_type": "reply_intent_classification",
  "provider": "gemini",
  "model": "gemini-2.5-flash",
  "confidence_score": 0.82,
  "ai_output": { "intent": "meeting_request", "reason": "..." },
  "cost_usd": 0.0006,
  "tokens_used": 412,
  "latency_ms": 940
}
```

Routes to `human_review` queue if `confidence_score < 0.70`, otherwise marked auto-actioned.

### HMAC verification

```python
secret = system.webhook_secret  # from `systems` table
expected_sig = hmac.new(
    secret.encode(), body.encode(), hashlib.sha256
).hexdigest()
assert hmac.compare_digest(expected_sig, request.headers["X-N8N-SIGNATURE"])
```

Failures return 401 with no body to avoid leaking the secret status.

---

## Frontend design system

Full token reference: [DESIGN.md](DESIGN.md). Summary below for orientation.

### Tailwind tokens (Control Room dark)

| Group | Tokens |
|-------|--------|
| Surface | `ctrl-bg`, `ctrl-surface`, `ctrl-panel`, `ctrl-raised` |
| Border | `ctrl-border`, `ctrl-divide` |
| Text | `ctrl-text`, `ctrl-muted`, `ctrl-dim` |
| Status | `status-ok`, `status-info`, `status-warn`, `status-err` (each with `-bg` variant) |

All colors are OKLCH for perceptual uniformity.

### Typography

| Class | Family |
|-------|--------|
| `font-display` | Syne |
| `font-sans` | DM Sans |
| `font-mono` | JetBrains Mono |
| `text-2xs` | 0.625 rem |
| `letterSpacing.label` | 0.12 em |

### Elevation

| Token | Use |
|-------|-----|
| `shadow-panel` | Cards, panels |
| `shadow-float` | Drawers, dialogs |
| `rounded-none/sm/base/md/lg/xl` | Standard radius scale |

### Component library

Root widgets: `Sidebar`, `TopBar`, `AlertBanner`, `AssistantPanel`, `MeetingDrawer` (NEW), `MeetingNoteEditor` (NEW), `MeetingTaskRow` (NEW), `GTMTreeNode`.

UI primitives (`components/ui/`): `Badge`, `SectionContainer`, `Table`, `EmptyState`, `StatRow`, `Sparkline`, `BarChart`, `DonutChart`, `LineChart`, `HeatMap`, `Markdown`, `ConfirmDialog`, `PromptDialog`.

### Data flow

| Pattern | Implementation |
|---------|----------------|
| Stale-while-revalidate | `useStaleFetch(fetchFn)` — 60 s TTL + custom `app:refresh` event |
| View retention | `<keep-alive max="10">` retains scroll/filter on the 10 most-recent views |
| Background sync | `App.vue` runs `adminAPI.syncN8n(200)` every 15 min |
| Daily memo cache | `useDailyMemo()` — localStorage `esteps:strategy-memo` with midnight expiry |
| Auth state | Pinia `useAuthStore` — `{ token, role }` + role getters + `login/logout` |
| Multi-system | Pinia `useSystemStore` — `{ systems, activeSlug, loading, error }` + `syncFromUrl` |

### Build & runtime

- Vue 3.4.21 · Vite 5.2.8 · Pinia 2.1.7 · vue-router 4.3.0
- axios 1.6.8 · marked 18.0.4 · dompurify 3.4.7 · lucide-vue-next 0.265.0 · tailwindcss 3.4.3

### API client

`src/api/index.js` exports one named client per domain: `authAPI`, `adminAPI`, `systemsAPI`, `n8nAPI`, `openclawAPI`, `emailsAPI`, `bookingsAPI`, `opportunitiesAPI`, `ticketsAPI`, `calendarAPI`, `usersAPI`, `gtmAPI` (+ `assetExplorerAPI`), `meetsAPI` (+ `assetExplorerAPI`), and `meetingsAPI` (NEW: `list`, `get`, `patchNotes`, `createTask`, `updateTask`, `deleteTask`, `aiDraft`, `sync`).

Two interceptors: a **request** interceptor that attaches the bearer token, and a **response** interceptor that auto-logs out on 401 by clearing localStorage and redirecting to `/login`.

---

## Configuration & environment

All settings live in `backend/app/config.py` as a single `Settings` pydantic model. Defaults and types below.

| Key | Type | Default | Required | Secret |
|-----|------|---------|----------|--------|
| `database_url` | str | — | ✓ | ✓ |
| `jwt_secret` | str | — | ✓ | ✓ |
| `jwt_algorithm` | str | `HS256` | | |
| `jwt_expire_minutes` | int | `1440` | | |
| `ai_daily_budget_usd` | float | `10.0` | | |
| `n8n_webhook_secret` | str | — | ✓ (for legacy single-system) | ✓ |
| `n8n_base_url` | str | `https://n8n.estepshealth.tech` | | |
| `n8n_api_key` | str | — | ✓ (for `/proxy/n8n`) | ✓ |
| `environment` | str | `development` | | |
| `auto_create_db` | bool | `false` | | |
| `cors_origins` | list[str] | `[…]` | | |
| `leads_database_url` | str | falls back to `database_url` | | ✓ |
| `strategy_dir` | str | `Final planning/` | | |
| `meet_dir` | str | `Meet prep/` | | |
| `gemini_api_key` | str | — | ✓ (for AI features) | ✓ |
| `openclaw_base_url` | str | — | optional | |
| `openclaw_hook_token` | str | — | optional | ✓ |

Per-system `webhook_secret` is held inside the `systems` table, not in env, so adding a system does not require a redeploy.

For production wiring (Supabase URLs, n8n cloud, Gmail OAuth) see [PRODUCTION_SETUP.md](../PRODUCTION_SETUP.md).

---

## Testing

Pytest suite in `backend/tests/`. Run against an isolated DB by setting `TEST_DATABASE_URL`:

```bash
TEST_DATABASE_URL=postgresql://… pytest -q
```

### Test files

| File | Coverage |
|------|----------|
| `test_admin_endpoints.py` | Dashboard endpoints, pipeline, KPIs |
| `test_auth.py` | Token issuance, role injection, password hashing |
| `test_followups_bubble.py` (NEW) | Followups sidebar bubble + open-meeting-tasks bucket |
| `test_meetings_ai.py` (NEW) | AI auto-draft happy path + budget_exhausted + upstream_error |
| `test_meetings_router.py` (NEW) | CRUD on notes / tasks; RBAC enforcement |
| `test_meetings_sync.py` (NEW) | 5-minute reschedule reconciliation |

### Fixtures (`conftest.py`)

| Fixture | Scope | Behaviour |
|---------|-------|-----------|
| `setup_database` | session, autouse | Builds schema once |
| `db_session` | function | Yields ops DB session |
| `clean_db` | function, autouse | Truncates between tests |
| `client` | function | `TestClient` with `get_db` dependency override |
| `admin_token` | function | Issues admin JWT |
| `operator_token` | function | Issues operator JWT |
| `leads_db` | function | Yields leads-source DB session |

Frontend currently has no automated test layer (Playwright/Vitest not wired); manual smoke checks via `/docs` Swagger UI and the SPA cover most regressions.

---

## Deployment notes

The repo ships `docker-compose.prod.yml` for a single-host production deploy (backend + nginx + Postgres ops DB; leads-source DB lives in Supabase).

For the canonical go-live checklist — including Supabase project setup, Gmail OAuth, Calendly webhook wiring, n8n credentials, and the **7-step "Linking to Real Data"** flow — see [PRODUCTION_SETUP.md](../PRODUCTION_SETUP.md). That doc is the single source of truth for severity-flagged setup steps.

Key reminders, summarised:

- Both `database_url` and `leads_database_url` should point at Supabase pooler URLs (port 6543) in production for connection efficiency.
- Rotate `jwt_secret` and every per-system `webhook_secret` before exposing the dashboard publicly.
- `n8n_api_key` is required for `/proxy/n8n/*` and for the 15-minute background sync.
- `gemini_api_key` is required for Insights memo, the assistant, and meeting AI auto-draft. Without it those endpoints degrade to a "AI unavailable" banner.
- Set a real `cors_origins` list — the development default is permissive.

---

## What's NOT here

Deliberately out of scope for this document:

| Out of scope | Where to look |
|--------------|---------------|
| n8n workflow JSON internals (node graph, parameter shapes) | Open the JSON exports in `Final planning/03_Workflows/` directly in the n8n GUI |
| Gmail OAuth setup (token issuance, scope grant) | n8n credential page → `gmail-cred` |
| Calendly account config (event types, webhook URL) | Calendly admin → integrations |
| Production hosting infra (DNS, TLS, monitoring, log shipping) | Hosting-provider documentation; not committed to this repo |
| Vue component-level prop shapes | Read the SFC directly — components are short and self-documenting |
| Field-by-field Pydantic schema docs | `backend/app/schemas/responses.py` + `/docs` Swagger UI |
| Lead-scoring formula details | EST-8 workflow JSON + `Final planning/01_Strategy/` |

For anything else, the four anchor docs are: [README](../README.md), [PRODUCT](PRODUCT.md), [DESIGN](DESIGN.md), and the older [SYSTEM_DOCUMENTATION](SYSTEM_DOCUMENTATION.md) which retains long-form historical context.
