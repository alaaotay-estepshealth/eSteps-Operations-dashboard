# eSteps Ops Dashboard — ES-OPS-09

**Multi-system operations dashboard for monitoring 5+ automation pipelines.** Vue 3 frontend, FastAPI backend, single central PostgreSQL (Ops DB). n8n pushes execution data via webhooks — dashboard never queries per-system Supabase projects directly.

---

## Mission

Convert 972 academic researchers into 30–50 research partnerships through automated, personalized outreach — while giving the ops team a unified control room across every automation system.

---

## System Architecture

```
[eSteps Supabase]  ─┐
[WAM Supabase]     ─┤  n8n workflows  →  POST /webhooks/{system_slug}
[Solar Supabase]   ─┤                              │
[AI Chat Supabase] ─┘                     [Ops PostgreSQL DB]
[AI Influencer]    ─┘                              │
                                           FastAPI Backend
                                                   │
                                           Vue 3 Dashboard (15 views)
                                    /systems  /overview  /pipeline  /emails
                                    /bookings  /opportunities  /workflows
                                    /n8n  /ai  /review  /tickets  /gtm  /system
```

### Key principles

- **Webhook-push model**: n8n reads each system's Supabase, runs automation, pushes execution results to the central Ops DB. Dashboard receives, not polls.
- **Read-only frontend**: All state changes go through API endpoints — no direct DB writes.
- **Per-system HMAC**: Each system has its own `webhook_secret` stored in the `systems` table.
- **Non-breaking**: All existing eSteps Leads endpoints unchanged. Multi-system is additive.

---

## The Five Systems

| Slug | Name | What it automates |
|---|---|---|
| `esteps-leads` | eSteps Leads | Academic researcher outreach + pipeline |
| `wam-agency` | WAM Agency | B2B agency lead generation + nurture |
| `ai-chatbot` | AI Chatbot | Customer-facing assistant + ticket routing |
| `solar-leads` | Solar Leads | Solar energy lead capture + qualification |
| `ai-influencer` | AI Influencer | AI-generated content + influencer outreach |

---

## Dashboard Views (21 routes)

### Operations
| Route | View | Purpose |
|---|---|---|
| `/briefing` | BriefingView | **Landing page** — since-yesterday changes, today's priorities, recommended-to-contact-today queue, AI memo, recent activity |
| `/systems` | SystemsOverview | Cross-system KPI grid + clickable system cards |
| `/systems/:slug` | SystemDetail | Per-system stats + activity feed + paginated execution history |
| `/overview` | Overview | Mission Control — global KPIs, activity feed, system health |
| `/insights` | Insights | Decision hub — KPIs vs GTM targets, week/month comparison, goal progress, trend, recommendations, sequence heatmap, conference timeline, AI memo + Ask-the-Assistant |

### Pipeline
| Route | View | Purpose |
|---|---|---|
| `/pipeline` | Pipeline | Lead funnel + research areas + filtered/paginated lead table + row actions |
| `/contacts` | ContactsView | People we contacted — searchable, Hot filter (score ≥ 7), per-person timeline drawer + quick actions |
| `/emails` | EmailAnalytics | Delivery/open/bounce rates, per-step metrics, A/B comparison, paginated logs |
| `/bookings` | BookingsView | Upcoming/past meetings, no-show rate, status filter |
| `/opportunities` | OpportunitiesDeals | Deal pipeline funnel, tier breakdown, paginated deals |
| `/followups` | FollowupsView | Overdue / due-today / this-week / upcoming-meetings / hot-needing-action + Reschedule/Drop actions |

### Automation
| Route | View | Purpose |
|---|---|---|
| `/workflows` | Workflows | Workflow execution health + 14-day bar chart |
| `/n8n` | N8nWorkflows | Live n8n workflows with Trigger / Activate / Deactivate actions |
| `/ai` | AIMonitor | AI decision quality + cost + confidence with type/status/confidence filters |
| `/agent` | OpenClawView | Launch OpenClaw agent actions (acts on DBs/email/CRM/drive) — admin-only, audited, confirm-gated |
| `/review` | HumanReview | AI decisions pending approval — Approve / Reject / Override with reviewer notes |

### Strategy
| Route | View | Purpose |
|---|---|---|
| `/tickets` | TicketsView | Ticket queue with inline admin status update, category breakdown |
| `/gtm` | GTMStrategy | Browse 13+ strategy markdown files by directory with inline viewer |
| `/system` | SystemLogs | Audit trail, filterable by level + source |

---

## Project Status & Pending Work

_Last updated: 2026-05-26_

### ✅ Done

- Core dashboard — 21 views, 18 routers, JWT + RBAC (admin/operator/readonly)
- Dual-DB live wiring — ops DB (eu-west-1) + leads source DB (eu-central-1, 1,408 leads); n8n proxy (53 live workflows)
- **AI decision ingest** — `POST /webhooks/{slug}/ai-decision` (HMAC-gated, idempotent on `decision_id`, auto-routes confidence < 0.70 to the review queue)
- **Pipeline write-back actions** — Pause / Resume / Bump priority / Mark cold (admin + operator only, audit-logged to ops DB)
- **Per-system Mission Control** — live activity feed on `/systems/:slug`
- **Active alerts** — `GET /admin/dashboard/alerts` + dashboard-wide `AlertBanner` (workflow failures, SLA breaches > 3.5h, pending review, AI budget ≥ 80%)
- **Security hardening** — HMAC enforced in production (missing signature rejected, not skipped); `.gitignore` added; test harness refuses to run against the production DB
- **Decision-helper — Strategy Insights** (`/insights`) — KPIs vs GTM targets, week- and month-over-month comparison, goal progress, 8-week outreach trend, rule-based recommendation engine ("what to focus on"), sequence-funnel + score-distribution charts
- **Decision-helper — AI strategy memo** — `POST /admin/insights/memo` (Gemini 2.5 Flash) writes a weekly memo (current state / risks / fixes / focus) from the rule-engine facts. On-demand button on Insights. Live (uses `GEMINI_API_KEY`)
- **Decision-helper — Follow-ups & Calendar** (`/followups`) — overdue / due-today / this-week / upcoming-meetings / hot-needing-action, with Reschedule + Drop quick actions
- **Decision-helper — Contacts & Hot Leads** (`/contacts`) — searchable people list, Hot filter (score ≥ 7), per-person timeline drawer (emails, replies, meetings) + quick actions; deep-linked from Follow-ups
- **Decision-helper — Morning Briefing** (`/briefing`, landing page) — `GET /admin/briefing`: since-yesterday changes, today's priorities, recommended-to-contact-today queue (heuristic priority ranking `GET /admin/contacts/priority`), AI memo, recent activity
- **Decision-helper — AI Ops Assistant** — `POST /admin/insights/assistant`: natural-language Q&A over live pipeline data (Gemini), chat panel on Insights
- **Decision-helper — deeper visualizations** — sequence heatmap (`GET /admin/insights/heatmap`, area × touch), weekly outreach trend with target line, conference & geo timeline (GTM calendar)
- **OpenClaw agent integration** (`/agent`) — launch agent actions via OpenClaw's documented `/hooks/agent` + `/hooks/wake` webhook API; **admin-only · audit-logged · explicit-confirm**; graceful 503 until configured
- **Charts** — reusable inline-SVG `BarChart` / `LineChart` / `DonutChart` / `HeatMap`; clickable drill-downs from KPI cards, chart bars, and table rows
- **Craft pass (impeccable)** — new views aligned to the Control Room Minimalism system: shared `StatRow` for display strips, established `hover:bg-ctrl-raised hover:shadow-float active:scale-[0.99]` card states, global focus-visible ring, status-only color

### ⏳ Pending — needs YOU (console / deploy / n8n)

These are the remaining actions to fully complete every phase. None block the dashboard from running; each one lights up a capability.

1. **Restart the dev server** — Vite must reload to show the new nav: **Briefing (landing), Insights, Contacts, Follow-ups, OpenClaw Agent** (`npm run dev` + hard refresh). Log in as **admin** for AI memo / assistant / agent / write actions.
2. **Activate OpenClaw** (enables the `/agent` action launcher):
   - In OpenClaw: set `hooks.enabled = true` and a dedicated `hooks.token`.
   - In `backend/.env`: `OPENCLAW_BASE_URL=https://openclaw.estepshealth.tech` and `OPENCLAW_HOOK_TOKEN=<that token>`; restart backend.
3. **AI views need data** — add an HTTP node in each n8n AI workflow to POST decisions to `/webhooks/{slug}/ai-decision`; `ai_requests` is empty so AI Monitor / Review stay hollow until then.
4. **Confirm pause semantics** — `Pause` / `Reschedule` clear/reset `next_send_date`; verify the EST-2 outreach workflow selects leads by `next_send_date` (else `Mark cold` / `Drop` always stops outreach).
5. **Alert / digest delivery** — n8n job polling `GET /admin/dashboard/alerts` → Slack/email; optional daily `/report` PDF digest.
6. **Rotate secrets** — n8n API key, ops + leads DB passwords, `JWT_SECRET`, `GEMINI_API_KEY`, and the OpenClaw `hooks.token` (all were in plaintext env / shared in chat). Already gitignored; keep them out of any pushed repo.
7. **Deploy hardening** — set `ENVIRONMENT=production` (enables HMAC), add the prod frontend origin to `CORS_ORIGINS`, and set `GEMINI_API_KEY` + `OPENCLAW_*` in the deployed environment (else those features 503 gracefully).

### ⏳ Pending — code (ready to build)

- **Router tests** — harness is now safe; the newer routers (emails / bookings / opportunities / tickets / gtm / systems / n8n_proxy / webhooks / insights / followups / contacts / lead_actions) still need tests. Requires `TEST_DATABASE_URL` (throwaway Postgres) to run — never the prod Supabase URL.
- **Reply-from-dash** — Human Review approve → send the drafted reply via n8n (needs an n8n send-webhook URL).

### 🔭 Larger / infra projects

- Gmail inbox integration (IMAP or Gmail API + OAuth)
- WebSocket live updates (replace the 60s poll + 15-min sync)
- Real email open/bounce tracking (provider webhook; currently derived from `email1..5_sent_at`)

---

## Data Model

### systems (new registry anchor)

```sql
id          UUID PK
slug        VARCHAR(50) UNIQUE   -- "esteps-leads"
name        VARCHAR(255)
description TEXT
webhook_secret  VARCHAR(255)     -- per-system HMAC secret
n8n_project_id  VARCHAR(100)
is_active   BOOLEAN
```

### system_id FK on shared tables

`workflow_executions`, `ai_requests`, `audit_logs` all carry a `system_id UUID NOT NULL` FK → `systems.id`.

Tables untouched: `leads`, `email_logs`, `bookings`, `opportunities`, `tickets`, `users`.

---

## API Endpoints

### Auth
```
POST   /auth/token
```

### Multi-system (new)
```
GET    /admin/systems                       → list all active systems
GET    /admin/systems/overview              → cross-system KPIs + per-system summary
GET    /admin/systems/{slug}                → single system stats
GET    /admin/systems/{slug}/executions     → paginated execution history
```

### n8n proxy
```
GET    /proxy/n8n/workflows                 → list n8n workflows
POST   /proxy/n8n/workflows/{id}/execute    → trigger execution (admin/operator only)
POST   /proxy/n8n/workflows/{id}/activate   → activate workflow (admin/operator only)
POST   /proxy/n8n/workflows/{id}/deactivate → deactivate workflow (admin/operator only)
```

### Webhooks
```
POST   /webhooks/{system_slug}              → per-system n8n callback
POST   /webhooks/n8n                        → legacy eSteps Leads callback
POST   /webhooks/n8n/simulate               → dev-only simulation
```

### eSteps Leads (enhanced)
```
GET    /admin/dashboard/metrics             → global KPIs with delta indicators
GET    /admin/pipeline/leads                → paginated + filtered (stage, research_interest, score_min, score_max)
GET    /admin/pipeline/research-stats
GET    /admin/workflows/status
GET    /admin/workflows/executions/daily
GET    /admin/ai/decisions                  → filtered (request_type, status, min/max_confidence)
GET    /admin/logs/operations
GET    /admin/human-review/queue
POST   /admin/human-review/queue/{id}/resolve  → supports action + reviewer_notes
```

### Email Logs
```
GET    /admin/emails/stats                  → delivery/open/bounce rates, per-step, A/B comparison
GET    /admin/emails/logs                   → paginated (status, ab_variant, sequence_step filters)
```

### Bookings
```
GET    /admin/bookings/stats                → upcoming/completed/no-show counts + rates
GET    /admin/bookings                      → paginated with status filter
```

### Opportunities
```
GET    /admin/opportunities/stats           → pipeline value, stage/tier summaries
GET    /admin/opportunities                 → paginated with stage/tier filters
```

### Tickets
```
GET    /admin/tickets/stats                 → open/in-progress/resolved, category breakdown
GET    /admin/tickets                       → paginated with status/category filters
PATCH  /admin/tickets/{id}/status           → admin-only status update
```

### GTM Strategy
```
GET    /admin/gtm/strategies                → list strategy markdown files with metadata
GET    /admin/gtm/strategy/{path}           → read markdown content (path-traversal protected)
```

---

## Webhook Payload (n8n → Backend)

```json
{
  "workflow_id": "est-2",
  "workflow_name": "EST-2: Outreach Engine",
  "execution_id": "exec_abc123",
  "status": "success",
  "duration_seconds": 4.2,
  "error_message": null,
  "error_type": null,
  "correlation_id": "corr_def456",
  "metadata": {}
}
```

HMAC header: `X-N8N-Signature: sha256=<hex>` — validated against `system.webhook_secret` from DB.

---

## Project Structure

```
dashboard-system/
├── README.md                       ← You are here
├── .gitignore                      ← Excludes .env, SECRETS.md, wire_production.sql, build artifacts
├── SECRETS.md                      ← Webhook secrets reference (gitignored)
├── schema.sql                      ← Database schema (Supabase SQL Editor)
├── wire_production.sql             ← Production data wiring script (gitignored)
├── n8n-hmac-callback-node.js       ← n8n webhook HMAC helper
├── docker-compose.yml              ← Dev compose (with local Postgres)
├── docker-compose.prod.yml         ← Prod compose (Supabase only)
├── docs/                           ← All project documentation
│   ├── PRODUCT.md                  ← Dashboard product spec (users, purpose, scope)
│   ├── DESIGN.md                   ← Control Room Minimalism design system (OKLCH tokens)
│   ├── SYSTEM_DOCUMENTATION.md     ← Full architecture & technical reference
│   └── superpowers/specs/          ← Original ES-OPS-09 design specification
├── References/                     ← Final year project (PFE) documents (PDF/HTML)
│
├── backend/                        ← FastAPI Python application
│   ├── .env / .env.example         ← Environment configuration
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── alembic/versions/           ← DB migrations (0001 initial + 0002 multi-system)
│   └── app/
│       ├── main.py                 ← FastAPI init, CORS, 18 routers
│       ├── config.py               ← Settings (env vars via pydantic-settings)
│       ├── database.py             ← Dual SQLAlchemy sessions (ops + leads)
│       ├── auth.py                 ← JWT + require_admin + require_operator
│       ├── sync_n8n.py             ← n8n REST API execution sync
│       ├── seed.py                 ← Seeds 5 systems + demo data
│       ├── models/                 ← 11 ORM models (system, lead, ticket, etc.)
│       ├── routers/                ← 18 route modules
│       │   ├── admin.py            ← Dashboard + pipeline + AI + logs + alerts + sync
│       │   ├── auth.py             ← POST /auth/token
│       │   ├── webhooks.py         ← Per-system + legacy webhooks + AI-decision ingest
│       │   ├── systems.py          ← /admin/systems/* (+ per-system activity)
│       │   ├── n8n_proxy.py        ← /proxy/n8n/* (execute + toggle)
│       │   ├── email_logs.py       ← /admin/emails/*
│       │   ├── bookings.py         ← /admin/bookings/*
│       │   ├── opportunities.py    ← /admin/opportunities/*
│       │   ├── tickets.py          ← /admin/tickets/*
│       │   ├── gtm.py              ← /admin/gtm/*
│       │   ├── lead_actions.py     ← /admin/leads/{id}/action (pause/resume/cold/priority)
│       │   ├── insights.py         ← /admin/insights (+ memo, assistant, heatmap)
│       │   ├── followups.py        ← /admin/followups (overdue/today/week/meetings/hot)
│       │   ├── contacts.py         ← /admin/contacts (+ detail/timeline, priority queue)
│       │   ├── briefing.py         ← /admin/briefing (overnight deltas + priorities)
│       │   └── openclaw.py         ← /admin/openclaw/* (agent action launcher)
│       ├── services/
│       │   └── system_service.py   ← Cross-system aggregations + per-system activity
│       ├── tests/                  ← pytest (conftest guard refuses prod DB)
│       └── schemas/
│           └── responses.py        ← Pydantic response models
│
└── frontend/                       ← Vue 3 + Vite
    ├── Dockerfile
    ├── package.json
    └── src/
        ├── api/index.js            ← API namespaces (admin, systems, n8n, emails, …)
        ├── composables/useStaleFetch.js ← 60s stale-while-revalidate
        ├── stores/
        │   ├── auth.js             ← JWT token + role (Pinia)
        │   └── system.js           ← Multi-system filter (Pinia)
        ├── views/                   ← 21 views + Login
        │   ├── BriefingView.vue    ← /briefing — landing: overnight, priorities, recommended-today, memo
        │   ├── Insights.vue        ← /insights — decision hub: KPIs vs targets, charts, heatmap, memo, assistant
        │   ├── ContactsView.vue    ← /contacts — people + Hot filter + timeline drawer
        │   ├── FollowupsView.vue   ← /followups — overdue/today/week/meetings + actions
        │   ├── OpenClawView.vue    ← /agent — OpenClaw agent action launcher
        │   ├── Overview.vue        ← /overview — Mission Control (KPIs, activity, health)
        │   ├── Pipeline.vue        ← /pipeline — funnel + filters + row actions
        │   ├── EmailAnalytics.vue  ← /emails — delivery + A/B
        │   ├── BookingsView.vue    ← /bookings — meetings
        │   ├── OpportunitiesDeals.vue ← /opportunities — deal pipeline
        │   ├── Workflows.vue       ← /workflows — execution health + sparklines
        │   ├── N8nWorkflows.vue    ← /n8n — trigger + toggle
        │   ├── AIMonitor.vue       ← /ai — AI decisions + budget
        │   ├── HumanReview.vue     ← /review — approve/reject/override
        │   ├── SystemsOverview.vue ← /systems — cross-system grid
        │   ├── SystemDetail.vue    ← /systems/:slug — per-system stats + activity feed
        │   ├── TicketsView.vue     ← /tickets — support queue
        │   ├── GTMStrategy.vue     ← /gtm — strategy docs
        │   ├── SystemLogs.vue      ← /system — audit trail
        │   └── ReportView.vue      ← /report — print-friendly operations report
        ├── components/
        │   ├── Sidebar.vue         ← 4-section nav
        │   ├── TopBar.vue          ← Title + last-synced + refresh
        │   ├── AlertBanner.vue     ← Dashboard-wide active-alert banner (polls 60s)
        │   ├── AssistantPanel.vue  ← AI Ops Assistant chat (used on Insights)
        │   └── ui/                 ← StatRow, Badge, Table, SectionContainer, EmptyState, Sparkline, BarChart, LineChart, DonutChart, HeatMap
        └── style.css               ← OKLCH design tokens + Tailwind
```

---

## Quick Start

### Supabase (production / recommended)

1. Run `schema.sql` in the Supabase SQL Editor (esteps-ops project)
2. Fill in `backend/.env` — see backend README for all vars
3. Add `LEADS_DATABASE_URL` to `.env` to use live leads (see below)

```bash
# Backend
cd backend
python -m venv .venv
# Git Bash
source .venv/Scripts/activate
# PowerShell
# .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.seed                              # seeds 5 systems + demo data
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend
cd frontend && npm install && npm run dev      # → http://localhost:5173
```

### Local Docker (dev only)

```bash
docker run --name esteps-postgres \
  -e POSTGRES_USER=esteps -e POSTGRES_PASSWORD=esteps123 \
  -e POSTGRES_DB=esteps_ops -p 5432:5432 -d postgres:16

# Set ENVIRONMENT=development AUTO_CREATE_DB=true in backend/.env
cd backend && uvicorn app.main:app --reload
```

Default login: `admin / admin123`

---

## Environment Variables

```bash
# backend/.env

# Ops DB — Supabase esteps-ops (eu-west-1, use Transaction pooler for IPv4)
DATABASE_URL=postgresql://postgres.[ref]:[pass]@aws-0-eu-west-1.pooler.supabase.com:6543/postgres?sslmode=require

# Live leads — eSteps Leads Automation Syst... (eu-central-1, Transaction pooler)
# Leave empty to use seeded demo leads
LEADS_DATABASE_URL=

JWT_SECRET=<32-char hex>
N8N_BASE_URL=https://n8n.estepshealth.tech
N8N_API_KEY=<see SECRETS.md>
ENVIRONMENT=development          # production → HMAC enforced on all webhooks
AUTO_CREATE_DB=false
```

Per-system HMAC secrets live in the `systems` DB table — see `SECRETS.md`.

---

## Live Leads Setup (Pipeline View)

The Pipeline view reads leads from the **`eSteps Leads Automation Syst...`** Supabase project:

1. Go to Supabase Dashboard → `eSteps Leads Automation Syst...` → Settings → Database
2. Copy the **Transaction pooler** connection string (eu-central-1 region)
3. Add to `backend/.env`:
   ```
   LEADS_DATABASE_URL=postgresql://postgres.[ref]:[pass]@aws-0-eu-central-1.pooler.supabase.com:6543/postgres?sslmode=require
   ```
4. Restart the backend — Pipeline view now shows real leads

Without this, the Pipeline view falls back to seeded demo data in the ops DB.

---

## Docker Compose (Production, Supabase-only)

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

No local DB container — reads from Supabase. Env vars from `backend/.env`.

---

## Design System

Control Room Minimalism — dark slate, OKLCH color tokens, Syne/DM Sans/JetBrains Mono.

- CSS custom properties: `--ctrl-*` neutrals, `--status-*` semantics, `--font-*`, `--space-*`
- Tailwind tokens in `tailwind.config.js`
- UI primitives in `frontend/src/components/ui/`
- Design system spec: [`docs/DESIGN.md`](./docs/DESIGN.md)
- Full details: [`docs/SYSTEM_DOCUMENTATION.md`](./docs/SYSTEM_DOCUMENTATION.md)

---

## Documentation

All docs live in [`docs/`](./docs/):

| Doc | What |
|---|---|
| [`docs/PRODUCT.md`](./docs/PRODUCT.md) | Dashboard product spec — users, purpose, scope, anti-references |
| [`docs/DESIGN.md`](./docs/DESIGN.md) | Control Room Minimalism design system — OKLCH tokens, typography, motion |
| [`docs/SYSTEM_DOCUMENTATION.md`](./docs/SYSTEM_DOCUMENTATION.md) | Full architecture & technical reference |
| [`docs/superpowers/specs/`](./docs/superpowers/specs/) | Original ES-OPS-09 multi-system design specification |
| [`SECRETS.md`](./SECRETS.md) | Webhook/API secret reference (gitignored — never commit) |

Project-wide docs (whole lead-gen system, not just the dashboard) live one level up: `../README.md`, `../CLAUDE.md`, `../implementation_plan.md`.

---

## Troubleshooting

| Issue | Fix |
|---|---|
| Webhook 404 | Confirm system slug exists in `systems` table |
| HMAC 403 | `system.webhook_secret` in DB must match n8n's secret |
| `/systems` empty | Run `python -m app.seed` or insert systems manually |
| n8n proxy 503 | Set `N8N_API_KEY` + `N8N_BASE_URL` in `.env` |
| 401 on API | Token expired — clear localStorage, re-login |
| CORS error | Add frontend origin to `allow_origins` in `main.py` |

---

## Next Steps

### Gmail Inbox Integration

Add Gmail as a live data source for email analytics, reply tracking, and conversation threads.

**Two approaches:**

| Approach | Setup | Capability |
|---|---|---|
| **IMAP + App Password** | Add 1 env var, zero Google Cloud setup | Read inbox/sent, basic metadata |
| **Gmail API + OAuth** | Google Cloud project, OAuth consent screen | Full access, labels, threads, search |

**IMAP (recommended for quick start):**
1. Enable 2FA on the outreach Gmail account (`hello@estepshealth.com`)
2. Generate App Password: Google Account → Security → 2-Step Verification → App Passwords
3. Add to `backend/.env`:
   ```
   GMAIL_ADDRESS=hello@estepshealth.com
   GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
   ```
4. Build `sync_gmail.py` — pulls sent/received emails via IMAP, stores in `conversations` table
5. Add `/admin/inbox` endpoint + Inbox view to frontend
6. Wire refresh button or scheduled sync (similar to `sync_n8n.py`)

**Gmail API (full power, later):**
1. Create Google Cloud project → enable Gmail API
2. Configure OAuth consent screen (internal if Workspace, external if consumer)
3. Create OAuth2 credentials → download `credentials.json`
4. Add to `backend/.env`:
   ```
   GOOGLE_CREDENTIALS_PATH=credentials.json
   GMAIL_ADDRESS=hello@estepshealth.com
   ```
5. Build OAuth token flow (one-time browser auth → refresh token stored in DB)
6. Full Gmail API: threads, labels, search, real-time push via Pub/Sub

**What this unlocks:**
- Real-time inbox view in dashboard (sent/received/threads)
- Accurate open/reply tracking matched to leads
- Conversation timeline per lead
- Reply detection independent of n8n EST-3 workflow

### Other Enhancements

- **WebSocket live updates** — push execution data to dashboard without polling
- **Scheduled n8n sync** — cron job running `python -m app.sync_n8n` every 15 min
- **Email preview/testing** — preview outreach emails before sending
- **Bulk lead import/export** — CSV upload + download from Pipeline view
- **Advanced charting** — time-series charts for email delivery, execution trends
- **Role-based UI restrictions** — hide admin actions for viewer/operator roles

### Dashboard UX Enhancement Plan

Goal: "Open dashboard → instantly know agent progress."

| # | Enhancement | Hours | Impact |
|---|---|---|---|
| 1 | **Overview → Mission Control** | 4-5h | Highest — immediate "what's happening" answer |
| 2 | **Last Updated awareness** | 1h | Eliminates stale-data confusion |
| 3 | **Workflow sparklines** | 3h | Visual trend at a glance |
| 4 | **Auto-scheduled n8n sync** | 1h | Eliminates manual sync step |
| 5 | **Report/Print view** | 2-3h | Presentation-ready for final year defense |

**Status:** #1 ✅ Done · #2 ✅ Done · #3 ✅ Done · #4 ✅ Done · #5 ✅ Done

#### 1. Overview → Mission Control (Done)

- Campaign Progress bar — horizontal stacked funnel (Loaded → Contacted → Replied → Meeting Booked)
- Activity Feed — last 12 events from workflows + AI + system events, chronological with relative timestamps
- System Health dots — colored pulse indicators per system (healthy/warning/error/idle)
- New endpoints: `GET /admin/dashboard/activity-feed`, `GET /admin/dashboard/system-health`

#### 2. Last Updated Awareness (Done)

- TopBar shows relative "last synced" time (auto-updates every 10s)
- Refresh button with spin animation during fetch
- `useStaleFetch` composable exposes revalidating state with pulse animation on StatRow

#### 3. Workflow Timeline Sparklines (Done)

- `Sparkline.vue` component — 7-day inline SVG polyline per workflow
- Color-coded by success rate (green ≥90%, amber ≥70%, red <70%)
- Wired into Workflows view table

#### 4. Auto-Scheduled n8n Sync (Done)

- App.vue runs `adminAPI.syncN8n(200)` every 15 minutes via `setInterval`
- Only fires when JWT token present (logged in)
- Removes need to manually click "Sync n8n" button

#### 5. Report/Print View (Done)

- Dedicated `/report` route: Campaign Progress, KPIs, AI Ops, Workflow Health table, Priority, System Status
- Print-friendly CSS in both `ReportView.vue` (scoped) and `style.css` (global hides sidebar/topbar)
- "Print / Save PDF" button for screenshot-ready output

---

## Development History

### Phase 0 — Architecture & Planning (Apr 2026)

Started from Voltis Pro dashboard reference architecture. Original stack was Next.js 14 + Supabase + Recharts. After evaluating requirements (n8n integration, multi-DB, Python ecosystem for AI), pivoted to **FastAPI + Vue 3 + PostgreSQL**.

Produced initial build guides, specifications document (`docs/superpowers/specs/`), and formal requirements (FR01–FR23) aligned with the project report (`References/Cahier_des_Charges_ES-OPS-09_AlaaOtay.pdf`).

### Phase 1 — Core Backend & Database (Early May 2026)

- PostgreSQL schema designed (11 tables) and deployed to Supabase
- Alembic migrations: `0001_initial_schema` + `0002_multi_system`
- FastAPI app with JWT auth, RBAC (admin/operator/readonly), CORS
- Seed script populating 5 systems + demo data
- Webhook receiver with per-system HMAC-SHA256 validation

### Phase 2 — Multi-System Extension (ES-OPS-09)

- Added `systems` registry table (5 automation systems, 27 n8n workflows)
- `system_id` FK on `workflow_executions`, `ai_requests`, `audit_logs`
- Cross-system aggregation endpoints (`/admin/systems/overview`)
- n8n proxy endpoints (list, execute, activate, deactivate)
- Backward-compatible — all original single-system endpoints unchanged

### Phase 3 — Full Dashboard Views (Mid May 2026)

- 13 views built (Overview, Pipeline, Workflows, AI Monitor, Human Review, N8n Workflows, Email Analytics, Bookings, Deals, Tickets, GTM Strategy, System Logs, Systems Overview/Detail)
- Control Room Minimalism design system (OKLCH tokens, Syne/DM Sans/JetBrains Mono)
- 5 reusable UI primitives (StatRow, Badge, Table, SectionContainer, EmptyState)
- Stale-while-revalidate composable for 60s cached data fetching

### Phase 4 — Production Data Wiring (May 2026)

- Dual-database architecture: ops DB (eu-west-1) + leads source DB (eu-central-1)
- `sync_n8n.py` — REST API sync pulling 349 real executions from n8n
- Raw SQL queries against leads source (1,408 leads, 1,400 emails, 18 conversations)
- UNION ALL derivation strategy for bookings and opportunities from sparse source tables
- Email analytics from `email1_sent_at`–`email5_sent_at` columns (5-step sequence)
- A/B variant comparison via conversations × leads join

### Requirements Delivered (FR01–FR23)

| ID | Requirement | Status |
|----|-------------|--------|
| FR01 | JWT authentication with role-based access | Done |
| FR02 | Global KPI dashboard with delta indicators | Done |
| FR03 | Lead pipeline with filters + pagination | Done |
| FR04 | Workflow execution monitoring + health badges | Done |
| FR05 | AI decision audit trail with confidence scores | Done |
| FR06 | Human review queue (approve/reject/override + notes) | Done |
| FR07 | Multi-system registry + cross-system overview | Done |
| FR08 | Per-system drill-down with execution history | Done |
| FR09 | n8n workflow proxy (trigger + activate/deactivate) | Done |
| FR10 | Per-system HMAC webhook validation | Done |
| FR11 | Email analytics (delivery/open/bounce, per-step, A/B) | Done |
| FR12 | Booking management (multi-source derivation) | Done |
| FR13 | Opportunity pipeline (real + derived stages) | Done |
| FR14 | Ticket queue with admin inline status update | Done |
| FR15 | GTM strategy markdown viewer | Done |
| FR16 | System logs (level/source/time filters) | Done |
| FR17 | n8n execution sync via REST API | Done |
| FR18 | Dual-database live leads connection | Done |
| FR19 | Audit logging on all state changes | Done |
| FR20 | CORS + security headers | Done |
| FR21 | Docker Compose (dev + prod) | Done |
| FR22 | Seed script for demo data | Done |
| FR23 | Comprehensive system documentation | Done |
