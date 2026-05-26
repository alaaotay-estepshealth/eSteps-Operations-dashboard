# eSteps Operations Dashboard — Complete System Documentation

**Project Code:** ES-OPS-09
**Version:** 2.0.0
**Author:** Alaa Otay
**Date:** May 2026

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Technology Stack](#3-technology-stack)
4. [Database Layer](#4-database-layer)
5. [Backend — FastAPI Application](#5-backend--fastapi-application)
6. [Frontend — Vue 3 Application](#6-frontend--vue-3-application)
7. [n8n Workflow Automation](#7-n8n-workflow-automation)
8. [Authentication & Security](#8-authentication--security)
9. [Data Flow Examples](#9-data-flow-examples)
10. [Deployment & Infrastructure](#10-deployment--infrastructure)
11. [Design System](#11-design-system)

---

## 1. Project Overview

### 1.1 Mission

Convert 972 academic researchers into 30–50 research partnerships through automated, personalised outreach — while giving the operations team a unified control room across every automation system.

### 1.2 What the Dashboard Does

The eSteps Operations Dashboard is a **multi-system monitoring platform** that provides a single pane of glass over 5 independent automation systems. It tracks:

- **1,408 leads** with enrichment data, email engagement, and pipeline stages
- **349+ workflow executions** synced from n8n in real time
- **1,400 emails** sent across a 5-step outreach sequence
- **AI decision audit trail** with confidence scoring and human review
- **Booking management** derived from lead meeting data and conversation analysis
- **Opportunity pipeline** combining real deals and warm conversation signals
- **Support ticket routing** with AI classification
- **GTM strategy documents** viewable directly inside the dashboard

### 1.3 Key Design Principles

| Principle | Description |
|-----------|-------------|
| **Webhook-push model** | n8n pushes execution results to the dashboard via webhooks. The dashboard never polls n8n. |
| **Read-only frontend** | All state changes go through REST API endpoints. The Vue frontend makes no direct database writes. |
| **Dual-database architecture** | The ops database stores execution data and system config. A separate read-only connection retrieves live leads from the eSteps Leads Supabase project. |
| **Per-system HMAC** | Each of the 5 automation systems has its own `webhook_secret` for HMAC-SHA256 signature validation. |
| **Non-breaking additive design** | Multi-system support was added without altering any existing single-system endpoints. |

---

## 2. System Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                                 │
│                                                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────────┐    │
│  │ eSteps Supabase │  │  WAM Supabase   │  │  Solar Supabase   │    │
│  │  (eu-central-1) │  │                 │  │                   │    │
│  └────────┬────────┘  └────────┬────────┘  └───────┬───────────┘    │
│           │                    │                   │                │
│  ┌────────┴────────┐  ┌────────┴────────┐  ┌───────┴──────────┐     │
│  │ AI Chat Supabase│  │  AI Influencer  │  │   Gmail Inbox    │     │
│  │                 │  │                 │  │   (future)       │     │
│  └────────┬────────┘  └────────┬────────┘  └──────────────────┘     │
│           │                    │                                    │
└───────────┴────────────────────┴────────────────────────────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │   n8n Self-hosted    │
              │  n8n.estepshealth.   │
              │       tech           │
              │                      │
              │  27 workflows across │
              │    5 systems         │
              └──────────┬───────────┘
                         │
            ┌────────────┴──────────────┐
            │  POST /webhooks/{slug}    │
            │  HMAC-SHA256 signed       │
            ▼                           │
┌───────────────────────┐               │
│   FastAPI Backend     │◄──────────────┘
│   (Python 3.11+)      │
│                       │         ┌──────────────────────┐
│  10 routers           │◄────────│  Ops PostgreSQL DB   │
│  35+ endpoints        │         │  (Supabase esteps-   │
│  JWT authentication   │         │   ops, eu-west-1)    │
│  RBAC (admin/operator │         └──────────────────────┘
│        /readonly)     │
│                       │         ┌──────────────────────┐
│  Dual DB connections  │◄────────│  Leads Source DB     │
│                       │         │  (eSteps Leads       │
└───────────┬───────────┘         │  Supabase,           │
            │                     │  eu-central-1)       │
            │ REST API            └──────────────────────┘
            │ JSON responses
            ▼
┌───────────────────────┐
│   Vue 3 Frontend      │
│   (Vite + Tailwind)   │
│                       │
│  16 routes            │
│  13 views             │
│  7 components         │
│  28 API methods       │
│                       │
│  Dark-mode dashboard  │
│  OKLCH colour system  │
│  Syne + DM Sans fonts │
└───────────────────────┘
```

### 2.2 Dual-Database Architecture

The system connects to **two separate PostgreSQL databases**, both hosted on Supabase:

| Database | Region | Purpose | Tables |
|----------|--------|---------|--------|
| **Ops DB** (`esteps-ops`) | eu-west-1 (Ireland) | Execution tracking, system registry, AI audit, tickets, system logs | `systems`, `workflow_executions`, `ai_requests`, `audit_logs`, `users`, `tickets` |
| **Leads Source DB** (`eSteps Leads Automation`) | eu-central-1 (Frankfurt) | Live lead data, email history, conversations, opportunities | `leads` (1,408 rows), `email_logs`, `conversations`, `opportunities`, `bookings` |

**Why two databases?** The leads data lives in the same Supabase project that the n8n workflows write to. Rather than replicating all 1,408 leads (with 50+ columns each) into the ops database, the dashboard connects read-only to the source. This ensures the dashboard always shows live production data without sync delays.

**Fallback mechanism:** If `LEADS_DATABASE_URL` is not configured, the system falls back to the ops database (which contains seeded demo data).

```python
# database.py — dual connection setup
_leads_url = settings.leads_database_url or settings.database_url
_leads_engine = create_engine(_leads_url, pool_pre_ping=True)
```

---

## 3. Technology Stack

### 3.1 Backend

| Technology | Version | Purpose |
|------------|---------|---------|
| **Python** | 3.11+ | Server language |
| **FastAPI** | 0.111+ | Web framework — async-capable, auto-generated OpenAPI docs |
| **SQLAlchemy** | 2.0+ | ORM and database toolkit |
| **Pydantic** | 2.0+ | Request/response validation via type annotations |
| **pydantic-settings** | — | Environment variable loading with `.env` support |
| **python-jose** | — | JWT token creation and validation |
| **passlib** + **bcrypt** | — | Password hashing (PBKDF2-SHA256 + bcrypt legacy support) |
| **httpx** | — | HTTP client for n8n API sync |
| **uvicorn** | — | ASGI server |
| **alembic** | — | Database schema migrations |
| **psycopg2-binary** | — | PostgreSQL driver |

### 3.2 Frontend

| Technology | Version | Purpose |
|------------|---------|---------|
| **Vue 3** | 3.4.21 | Reactive UI framework (Composition API) |
| **Vite** | 5.2.8 | Build tool — instant HMR, ES module bundling |
| **Vue Router** | 4.3.0 | Client-side routing with navigation guards |
| **Pinia** | 2.1.7 | State management (auth store) |
| **Axios** | 1.6.8 | HTTP client with interceptors for JWT |
| **Tailwind CSS** | 3.4.3 | Utility-first CSS framework |
| **Lucide Vue Next** | 0.265.0 | Icon library (13 icons used in sidebar) |

### 3.3 Infrastructure

| Service | Purpose |
|---------|---------|
| **Supabase** (x2 projects) | Managed PostgreSQL databases |
| **n8n** (self-hosted) | Workflow automation engine at `n8n.estepshealth.tech` |
| **Docker Compose** | Container orchestration for deployment |

---

## 4. Database Layer

### 4.1 Ops Database Schema

#### `systems` — System Registry (Anchor Table)

```
id              UUID PRIMARY KEY (auto-generated)
slug            VARCHAR(50) UNIQUE    -- "esteps-leads", "wam-agency", etc.
name            VARCHAR(255)          -- "eSteps Leads"
description     TEXT                  -- system purpose
webhook_secret  VARCHAR(255)          -- per-system HMAC secret
n8n_project_id  VARCHAR(100)          -- n8n project grouping
is_active       BOOLEAN DEFAULT TRUE
created_at      TIMESTAMP WITH TIME ZONE
updated_at      TIMESTAMP WITH TIME ZONE
```

**5 registered systems:**

| Slug | Name | Workflows | Purpose |
|------|------|-----------|---------|
| `esteps-leads` | eSteps Leads | 8 (EST-1 to EST-8) | Academic researcher outreach + pipeline |
| `wam-agency` | WAM Agency | 5 (WAM-1 to WAM-5) | B2B agency lead generation + nurture |
| `ai-chatbot` | AI Chatbot | 4 | Customer-facing assistant + ticket routing |
| `solar-leads` | Solar Leads | 5 (WF-A to WF-E) | Solar energy lead capture + qualification |
| `ai-influencer` | AI Influencer | 5 (Jane-1 to Jane-5) | AI-generated content + influencer outreach |

#### `workflow_executions` — Execution History

```
id                UUID PRIMARY KEY
system_id         UUID FK → systems.id (NOT NULL)
workflow_id       VARCHAR(100)         -- n8n internal workflow ID
workflow_name     VARCHAR(200)         -- "EST-2: Outreach Engine V2"
execution_id      VARCHAR(200) UNIQUE  -- n8n execution ID (dedup key)
status            VARCHAR(50)          -- running | success | failed | retrying
started_at        TIMESTAMP WITH TIME ZONE
finished_at       TIMESTAMP WITH TIME ZONE
duration_seconds  FLOAT
retry_count       INTEGER DEFAULT 0
error_message     TEXT
error_type        VARCHAR(100)         -- timeout | api_error | validation | rate_limit
resolved          BOOLEAN DEFAULT FALSE
correlation_id    VARCHAR(100)         -- trace across systems
metadata          JSONB
created_at        TIMESTAMP WITH TIME ZONE
```

**Current data:** 349 real executions synced from n8n (287 esteps-leads, 48 ai-influencer, 14 wam-agency).

#### `ai_requests` — AI Decision Audit

```
id                UUID PRIMARY KEY
system_id         UUID FK → systems.id
request_type      VARCHAR(100)         -- lead_classify | email_summarize | priority_score | draft_reply
workflow_source   VARCHAR(100)
entity_id         UUID                 -- FK to lead/ticket
entity_type       VARCHAR(50)          -- lead | ticket
provider          VARCHAR(50)          -- openai | gemini | grok
model             VARCHAR(100)
tokens_used       INTEGER
cost_usd          FLOAT
latency_ms        INTEGER
input_preview     TEXT                 -- first 200 chars (GDPR-safe)
ai_output         JSONB                -- structured AI response
confidence_score  FLOAT                -- 0.0 to 1.0
used_fallback     BOOLEAN DEFAULT FALSE
fallback_reason   VARCHAR(100)
human_verified    BOOLEAN DEFAULT FALSE
human_override    BOOLEAN DEFAULT FALSE
status            VARCHAR(50)          -- completed | pending_review | rejected
retention_until   TIMESTAMP WITH TIME ZONE
```

#### `audit_logs` — Operational Audit Trail

```
id              UUID PRIMARY KEY
system_id       UUID FK → systems.id
level           VARCHAR(20)    -- INFO | WARNING | ERROR | CRITICAL
source          VARCHAR(100)   -- fastapi | n8n | ai_service | est-2
message         TEXT
correlation_id  VARCHAR(100)
entity_id       UUID
entity_type     VARCHAR(50)
user_id         VARCHAR(100)
duration_ms     INTEGER
metadata        JSONB
created_at      TIMESTAMP WITH TIME ZONE
```

#### `users` — Dashboard Users

```
id              UUID PRIMARY KEY
username        VARCHAR(100) UNIQUE
email           VARCHAR(255) UNIQUE
hashed_password VARCHAR(255)
role            VARCHAR(50) DEFAULT 'readonly'  -- admin | operator | readonly
is_active       BOOLEAN DEFAULT TRUE
created_at      TIMESTAMP WITH TIME ZONE
```

#### `tickets` — Support Tickets

```
id                UUID PRIMARY KEY
source            VARCHAR(50)    -- email | chat | form | whatsapp
subject           VARCHAR(500)
body_preview      TEXT
ai_category       VARCHAR(50)    -- support | partnership | billing | technical
ai_priority_score INTEGER        -- 1-5
ai_confidence     FLOAT
assigned_to       VARCHAR(100)
status            VARCHAR(50) DEFAULT 'open'  -- open | in_progress | resolved
resolved_at       TIMESTAMP WITH TIME ZONE
response_time_min FLOAT
human_verified    BOOLEAN DEFAULT FALSE
human_override    BOOLEAN DEFAULT FALSE
gdpr_consent      BOOLEAN DEFAULT FALSE
retention_until   TIMESTAMP WITH TIME ZONE
```

### 4.2 Leads Source Database (Read-Only)

The leads source database is owned by the n8n workflows. The dashboard connects read-only and queries these tables with raw SQL (because the source schema has 50+ columns that differ from the ORM model):

#### `leads` — 1,408 Academic Researchers

Key columns used by the dashboard:

```
id                  UUID PRIMARY KEY
first_name          VARCHAR
last_name           VARCHAR
email               VARCHAR UNIQUE
institution         VARCHAR
position            VARCHAR
research_interest   VARCHAR          -- parkinsons | gait_analysis | etc.
research_area       TEXT
lead_score          INTEGER (0-10)
esteps_relevance_score  INTEGER
campaign_tag        VARCHAR          -- Priority_A | Priority_B | Priority_C | Below_ICP
stage               VARCHAR          -- new | introduced | pitching | call_requested | cold
touch_number        INTEGER
ab_variant          VARCHAR(1)       -- A | B
reply_received      BOOLEAN
meeting_booked_at   TIMESTAMP
meeting_scheduled_for TIMESTAMP
email1_sent_at      TIMESTAMP        -- through email5_sent_at (5-step sequence)
bounce_at           TIMESTAMP
linkedin_available  BOOLEAN
linkedin_connected  BOOLEAN
created_at          TIMESTAMP
updated_at          TIMESTAMP
```

#### `conversations` — Email Replies (18 rows)

```
id          UUID PRIMARY KEY
lead_id     UUID FK → leads.id
direction   VARCHAR    -- inbound | outbound
body        TEXT       -- email body content
created_at  TIMESTAMP
```

Used to detect warm opportunities (keyword matching: "collaboration", "interested", "discuss", "happy to") and meeting interest signals.

#### `opportunities` — Deal Pipeline (1 row)

```
id                  UUID PRIMARY KEY
lead_id             UUID FK → leads.id
stage               VARCHAR
partnership_tier    VARCHAR
deal_value_usd      FLOAT
expected_close_date TIMESTAMP
call_held_at        TIMESTAMP
assigned_to         VARCHAR
notes               TEXT
created_at          TIMESTAMP
```

#### `email_logs` — Tracked Emails (6 rows)

```
id              UUID PRIMARY KEY
lead_id         UUID FK → leads.id
sequence_step   INTEGER
ab_variant      VARCHAR(1)
email_status    VARCHAR
open_detected   BOOLEAN
sent_at         TIMESTAMP
subject         VARCHAR
email_to        VARCHAR
```

### 4.3 Data Derivation Strategy

Because the leads source database has limited rows in `email_logs` (6), `opportunities` (1), and `bookings` (0), the dashboard derives richer data by querying the `leads` table directly:

| Dashboard View | Primary Data Source | Derivation Method |
|----------------|--------------------|--------------------|
| **Email Analytics** | `leads.email1_sent_at` through `email5_sent_at` | Count non-null timestamps per step. 486 step-1, 344 step-2, 237 step-3, 234 step-4, 99 step-5 = **1,400 total emails** |
| **Bounces** | `leads.bounce_at` | Count non-null = **330 bounced** |
| **A/B Testing** | `leads.ab_variant` + `conversations` | Join inbound conversations to leads by variant, calculate reply rate per variant |
| **Bookings** | `leads.meeting_booked_at` + `opportunities.call_held_at` + `conversations` with ILIKE keywords | UNION ALL three sources, tag source as 'calendly', 'n8n-workflow', 'gmail-reply' |
| **Opportunities** | `opportunities` + `leads` at advanced stages + `conversations` with positive intent | Combine real deals with derived "qualified_lead" (score ≥ 7) and "warm_reply" stages. Assign estimated values: Priority_A = $15k, Priority_B = $10k |

---

## 5. Backend — FastAPI Application

### 5.1 Application Structure

```
backend/
├── requirements.txt
├── .env                          ← environment configuration
├── alembic/
│   └── versions/
│       ├── 0001_initial_schema.py
│       └── 0002_multi_system.py  ← systems table + system_id FKs
└── app/
    ├── main.py                   ← FastAPI init, CORS, 10 routers
    ├── config.py                 ← Settings (13 env vars)
    ├── database.py               ← Dual SQLAlchemy sessions (ops + leads)
    ├── auth.py                   ← JWT auth + RBAC dependencies
    ├── dependencies.py           ← get_system() DI dependency
    ├── seed.py                   ← Seeds 5 systems + demo data
    ├── sync_n8n.py               ← n8n REST API execution sync
    ├── models/                   ← 11 SQLAlchemy ORM models
    ├── routers/                  ← 10 route modules
    └── schemas/
        └── responses.py          ← 30+ Pydantic response models
```

### 5.2 Configuration (`config.py`)

All configuration is loaded from environment variables via `pydantic-settings`:

| Setting | Default | Purpose |
|---------|---------|---------|
| `DATABASE_URL` | `postgresql://...localhost` | Ops DB connection (Supabase esteps-ops) |
| `LEADS_DATABASE_URL` | `""` (falls back to ops) | Leads source DB (eSteps Leads Supabase) |
| `JWT_SECRET` | — | HMAC key for JWT token signing |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_EXPIRE_MINUTES` | `1440` (24 hours) | Token expiration |
| `AI_DAILY_BUDGET_USD` | `10.0` | AI cost budget for dashboard display |
| `N8N_WEBHOOK_SECRET` | — | HMAC secret for webhook validation |
| `N8N_BASE_URL` | `https://n8n.estepshealth.tech` | n8n instance URL |
| `N8N_API_KEY` | — | n8n REST API authentication key |
| `ENVIRONMENT` | `development` | dev = auto-create tables; prod = enforce HMAC |
| `AUTO_CREATE_DB` | `true` | Auto-create tables on startup (dev only) |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Comma-separated allowed origins |
| `STRATEGY_DIR` | `""` | Semicolon-separated paths for GTM strategy files |

### 5.3 Application Initialisation (`main.py`)

```python
# Simplified — what happens at startup
app = FastAPI(title="eSteps Ops Dashboard API", version="2.0.0")

# CORS middleware allows frontend access
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins_list, ...)

# 10 routers registered (order does not matter)
app.include_router(auth.router)          # /auth/*
app.include_router(admin.router)         # /admin/*  (dashboard + pipeline + AI + logs + sync)
app.include_router(webhooks.router)      # /webhooks/*
app.include_router(systems_router.router) # /admin/systems/*
app.include_router(n8n_proxy.router)     # /proxy/n8n/*
app.include_router(email_logs.router)    # /admin/emails/*
app.include_router(bookings.router)      # /admin/bookings/*
app.include_router(opportunities.router) # /admin/opportunities/*
app.include_router(tickets.router)       # /admin/tickets/*
app.include_router(gtm.router)           # /admin/gtm/*

# Health check
@app.get("/health")
def health():
    return {"status": "ok", "service": "eSteps Ops API"}
```

In development mode, `Base.metadata.create_all(bind=engine)` auto-creates all tables if they don't exist.

### 5.4 Complete API Endpoint Reference

#### Authentication (`routers/auth.py`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `POST` | `/auth/token` | None | Login — returns JWT access token + role. Accepts OAuth2 form data (username, password). |

#### Dashboard & Pipeline (`routers/admin.py`) — 9 endpoints

| Method | Path | Auth | DB | Purpose |
|--------|------|------|-----|---------|
| `GET` | `/admin/dashboard/metrics` | User | Both | Global KPIs: total leads (1,408), automation rate (34.5%), hours saved, AI accuracy, pipeline funnel, priority breakdown, delta indicators |
| `GET` | `/admin/pipeline/leads` | User | Leads | Paginated + filtered lead list. Filters: `stage`, `research_interest`, `score_min`, `score_max`, `campaign_tag`. Params: `limit`, `offset` |
| `GET` | `/admin/pipeline/research-stats` | User | Leads | Research area performance — group by `research_interest`: lead count, avg score, reply rate |
| `GET` | `/admin/workflows/status` | User | Ops | Per-workflow health: success rate, total/failed/running counts, recent failures |
| `GET` | `/admin/workflows/executions/daily` | User | Ops | Daily execution counts aggregated by date. Param: `days` (default 14) |
| `GET` | `/admin/ai/decisions` | User | Ops | AI request log. Filters: `request_type`, `status`, `min_confidence`, `max_confidence`. Returns budget usage. |
| `GET` | `/admin/logs/operations` | User | Ops | Audit log viewer. Filters: `level`, `source`, `hours`. Param: `limit` |
| `GET` | `/admin/human-review/queue` | User | Ops | Pending AI decisions (status = `pending_review`) sorted by SLA breach urgency |
| `POST` | `/admin/human-review/queue/{id}/resolve` | Operator+ | Ops | Resolve review item. Body: `{ action: approve|reject|override, reviewer_notes? }` |
| `POST` | `/admin/sync-n8n` | Admin | Ops | Trigger n8n execution sync. Query param: `limit` (default 100) |

#### Multi-System (`routers/systems.py`) — 4 endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/admin/systems` | User | List all active systems |
| `GET` | `/admin/systems/overview` | User | Cross-system KPIs: total executions, success rate, avg duration + per-system summary |
| `GET` | `/admin/systems/{slug}` | User | Single system stats: execution counts, success/fail rate, avg duration, last run |
| `GET` | `/admin/systems/{slug}/executions` | User | Paginated execution history for one system. Filters: `status`. Params: `limit`, `offset` |

#### n8n Proxy (`routers/n8n_proxy.py`) — 4 endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/proxy/n8n/workflows` | User | List all n8n workflows (proxied from n8n REST API) |
| `POST` | `/proxy/n8n/workflows/{id}/execute` | Operator+ | Trigger a workflow execution in n8n |
| `POST` | `/proxy/n8n/workflows/{id}/activate` | Operator+ | Activate an n8n workflow |
| `POST` | `/proxy/n8n/workflows/{id}/deactivate` | Operator+ | Deactivate an n8n workflow |

#### Email Analytics (`routers/email_logs.py`) — 2 endpoints

| Method | Path | Auth | DB | Purpose |
|--------|------|------|-----|---------|
| `GET` | `/admin/emails/stats` | User | Leads | Total sent (1,400), delivered (1,070), bounced (330), per-step metrics, A/B comparison with winner |
| `GET` | `/admin/emails/logs` | User | Leads | Paginated email log. Filters: `status`, `ab_variant`, `sequence_step`. Falls back to leads-derived data if `email_logs` table is sparse. |

#### Bookings (`routers/bookings.py`) — 2 endpoints

| Method | Path | Auth | DB | Purpose |
|--------|------|------|-----|---------|
| `GET` | `/admin/bookings/stats` | User | Leads | Combined booking counts from leads + opportunities + conversations with meeting-intent keywords |
| `GET` | `/admin/bookings` | User | Leads | UNION ALL of 3 sources (leads, opportunities, conversations) with status derivation. Filter: `status` |

#### Opportunities (`routers/opportunities.py`) — 2 endpoints

| Method | Path | Auth | DB | Purpose |
|--------|------|------|-----|---------|
| `GET` | `/admin/opportunities/stats` | User | Leads | Pipeline value, won value, active deals, tier breakdown. Combines real opportunities + derived qualified leads + warm conversation replies |
| `GET` | `/admin/opportunities` | User | Leads | UNION ALL of opportunities table and inbound conversations. Filters: `stage`, `partnership_tier` |

#### Tickets (`routers/tickets.py`) — 3 endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/admin/tickets/stats` | User | Open/in-progress/resolved counts, category breakdown, avg response time |
| `GET` | `/admin/tickets` | User | Paginated ticket list. Filters: `status`, `category` |
| `PATCH` | `/admin/tickets/{id}/status` | Admin | Update ticket status inline |

#### GTM Strategy (`routers/gtm.py`) — 2 endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/admin/gtm/strategies` | User | List strategy markdown files with metadata (name, directory, size, modified date) |
| `GET` | `/admin/gtm/strategy/{path}` | User | Read raw markdown content. Path-traversal protected. |

#### Webhooks (`routers/webhooks.py`) — 3 endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `POST` | `/webhooks/{system_slug}` | HMAC | Per-system n8n callback. Validates HMAC signature against system's `webhook_secret`. Creates `workflow_execution` + `audit_log` entries. |
| `POST` | `/webhooks/n8n` | HMAC | Legacy eSteps Leads callback (backward compatible) |
| `POST` | `/webhooks/n8n/simulate` | None (dev) | Simulation endpoint for testing (development only) |

**Total: 35 endpoints** across 10 routers + 1 health check.

### 5.5 n8n Execution Sync (`sync_n8n.py`)

A standalone module that pulls execution history from n8n's REST API and inserts it into the ops database. This is used because n8n doesn't always fire webhooks for every execution (especially for scheduled workflows).

**How it works:**

1. Fetches executions from `GET /api/v1/executions` with cursor-based pagination
2. Maps each execution's `workflowId` to a system slug using a hardcoded 27-entry lookup table
3. Maps n8n status (`success`, `error`, `crashed`, `running`, `waiting`, `new`) to dashboard status (`success`, `failed`, `running`)
4. Inserts into `workflow_executions` with `ON CONFLICT (execution_id) DO NOTHING` for idempotency
5. Uses `result.rowcount > 0` to distinguish real inserts from conflict skips

**Usage:**
```bash
python -m app.sync_n8n              # sync last 100 executions
python -m app.sync_n8n --limit 500  # sync last 500
```

Also available via `POST /admin/sync-n8n` (admin-only) and the "Sync n8n" button in the frontend.

### 5.6 Pydantic Response Models (`schemas/responses.py`)

All API responses are validated through Pydantic models. Key models:

| Model | Used By | Fields |
|-------|---------|--------|
| `DashboardMetrics` | `/admin/dashboard/metrics` | total_leads, automation_rate, hours_saved, avg_processing_time, ai_accuracy, active_workflows, pipeline stages, priority breakdown, delta indicators |
| `WorkflowStatusItem` | `/admin/workflows/status` | workflow_id, workflow_name, total, success, failed, running, success_rate, recent_failures |
| `PipelineLead` | `/admin/pipeline/leads` | id, name, email, institution, stage, lead_score, research_interest, campaign_tag, ab_variant, touch_number, reply_received |
| `OpportunityStats` | `/admin/opportunities/stats` | total_pipeline_value, won_value, active_deals, avg_deal_value, stages[], tiers[] |
| `EmailStats` | `/admin/emails/stats` | total_sent/delivered/bounced/opened, rates, step_metrics[], ab_comparison |
| `BookingStats` | `/admin/bookings/stats` | total, upcoming, completed, canceled, no_shows, rates |
| `TicketStats` | `/admin/tickets/stats` | open, in_progress, resolved, categories[], avg_response_time |

---

## 6. Frontend — Vue 3 Application

### 6.1 Application Structure

```
frontend/
├── package.json                   ← 5 runtime deps, 5 dev deps
├── vite.config.js                 ← Vue plugin, dev server proxy
├── tailwind.config.js             ← colour tokens + fonts
├── index.html                     ← SPA entry point
└── src/
    ├── main.js                    ← createApp + Pinia + Router
    ├── App.vue                    ← Root shell (sidebar + topbar + router-view)
    ├── style.css                  ← OKLCH design tokens + Tailwind layers
    ├── api/
    │   └── index.js               ← Axios instance + 7 API namespaces (28 methods)
    ├── composables/
    │   └── useStaleFetch.js       ← Stale-while-revalidate (60s TTL)
    ├── stores/
    │   ├── auth.js                ← JWT token + role state (Pinia)
    │   └── system.js              ← Multi-system filter store (Pinia)
    ├── router/
    │   └── index.js               ← 16 routes, navigation guard
    ├── views/                     ← 13 page components
    │   ├── Login.vue
    │   ├── Overview.vue
    │   ├── Pipeline.vue
    │   ├── Workflows.vue
    │   ├── AIMonitor.vue
    │   ├── HumanReview.vue
    │   ├── N8nWorkflows.vue
    │   ├── SystemLogs.vue
    │   ├── SystemsOverview.vue
    │   ├── SystemDetail.vue
    │   ├── EmailAnalytics.vue
    │   ├── BookingsView.vue
    │   ├── OpportunitiesDeals.vue
    │   ├── TicketsView.vue
    │   └── GTMStrategy.vue
    └── components/
        ├── Sidebar.vue            ← 4-section navigation (13 items)
        ├── TopBar.vue             ← Page title + refresh button
        └── ui/
            ├── Badge.vue          ← Coloured status pill
            ├── EmptyState.vue     ← No-data placeholder
            ├── SectionContainer.vue ← Titled section wrapper
            ├── StatRow.vue        ← Horizontal KPI strip with deltas
            └── Table.vue          ← Generic data table with skeleton loading
```

### 6.2 Routing (16 Routes)

| Path | View Component | Purpose |
|------|---------------|---------|
| `/login` | Login.vue | Authentication (only public route) |
| `/` | — | Redirects to `/overview` |
| `/overview` | Overview.vue | Executive KPI dashboard |
| `/pipeline` | Pipeline.vue | Lead funnel + filterable lead table |
| `/workflows` | Workflows.vue | Workflow execution health + bar chart |
| `/ai` | AIMonitor.vue | AI decision monitoring + budget |
| `/review` | HumanReview.vue | AI review queue (approve/reject/override) |
| `/n8n` | N8nWorkflows.vue | Live n8n workflow management |
| `/system` | SystemLogs.vue | Operational audit log viewer |
| `/systems` | SystemsOverview.vue | Cross-system health dashboard |
| `/systems/:slug` | SystemDetail.vue | Per-system detail drill-down |
| `/emails` | EmailAnalytics.vue | Email campaign analytics + A/B |
| `/bookings` | BookingsView.vue | Meeting management |
| `/opportunities` | OpportunitiesDeals.vue | Deal pipeline + CRM |
| `/tickets` | TicketsView.vue | Support ticket queue |
| `/gtm` | GTMStrategy.vue | Strategy document viewer |

**Navigation guard:** All non-public routes check `localStorage.getItem('token')`. Unauthenticated users are redirected to `/login`.

All view components are **lazy-loaded** using dynamic imports (`() => import(...)`) for code-splitting.

### 6.3 API Client (28 Methods)

The API client is a shared Axios instance with two interceptors:

1. **Request interceptor:** Attaches `Authorization: Bearer {token}` header from localStorage
2. **Response interceptor:** On 401 status, clears the token and redirects to `/login`

**7 API namespaces:**

```javascript
authAPI           // 1 method  — login
adminAPI          // 11 methods — metrics, workflows, AI, logs, pipeline, review, sync
systemsAPI        // 4 methods  — systems overview, stats, executions
n8nAPI            // 4 methods  — list, execute, activate, deactivate
emailsAPI         // 2 methods  — stats, logs
bookingsAPI       // 2 methods  — stats, list
opportunitiesAPI  // 2 methods  — stats, list
ticketsAPI        // 3 methods  — stats, list, updateStatus
gtmAPI            // 2 methods  — listStrategies, getStrategy
```

### 6.4 State Management (Pinia)

#### `useAuthStore` — Authentication State

```
State:
  token    ← from localStorage (persists across tabs)
  role     ← from localStorage ("admin" | "operator" | "readonly")

Getters:
  isAuthenticated → boolean
  isAdmin         → boolean

Actions:
  login(username, password) → calls API, stores token + role
  logout()                  → clears state + localStorage
```

#### `useSystemStore` — System Selection (Scaffolded)

```
State:
  systems     ← array of system records
  activeSlug  ← current system filter (null = all)
  loading     ← boolean
  error       ← string

Computed:
  activeSystem → finds system matching activeSlug

Actions:
  loadSystems()    → fetches from API (one-time cache)
  setActive(slug)  → sets active system
  syncFromUrl(route) → reads system from URL query param
```

### 6.5 Composable: `useStaleFetch`

Every view (except Login) uses this composable for data fetching:

```javascript
const { load, lastFetched } = useStaleFetch(async () => {
  // fetch data from API
})
```

**Behaviour:**
- `onMounted`: Calls `load()` immediately
- Listens for `window 'app:refresh'` event (fired by TopBar's Refresh button)
- `onActivated` (within `<keep-alive>`): Only re-fetches if last fetch was >60 seconds ago
- Cleans up event listener on unmount

This gives a **stale-while-revalidate** experience — cached views show instantly, but refresh if stale.

### 6.6 View Details

#### Overview (`/overview`) — Executive Dashboard

**Data sources:** `adminAPI.getMetrics()` + `adminAPI.getWorkflowStatus()`

**Sections:**
1. **KPI Strip** (6 stats): Total leads, automation rate, hours saved, avg processing time, AI accuracy, active workflows — each with optional delta indicator
2. **Pipeline Funnel**: 4 horizontal progress bars (total → contacted → replied → meetings) with counts
3. **Workflow Health**: List of active workflows with success rate badges (≥90% green, ≥70% yellow, <70% red)
4. **AI Activity Grid**: 6-cell grid showing AI cost, tokens, latency, provider mix
5. **Lead Priority Breakdown**: Tiles showing Priority_A/B/C/Below_ICP distribution

#### Pipeline (`/pipeline`) — Lead Management

**Data sources:** `adminAPI.getMetrics()` + `adminAPI.getResearchStats()` + `adminAPI.getPipelineLeads(params)`

**Sections:**
1. **Funnel metrics**: Same 4-stage funnel as Overview
2. **ICP Priority breakdown**: Priority_A, B, C, Below_ICP counts
3. **Research Area Table**: Performance by research interest — count, avg score, reply rate
4. **Leads Table**: Paginated (20/page), filterable by stage, research interest, score range. Columns: name, institution, score, stage, campaign tag

#### Email Analytics (`/emails`)

**Data sources:** `emailsAPI.getStats()` + `emailsAPI.getLogs(params)`

**Sections:**
1. **KPI Strip**: Total sent (1,400), delivery rate (76.4%), open rate, bounce rate (23.6%)
2. **Per-Step Table**: Steps 1-5 showing sent/delivered/bounced/opened per step
3. **A/B Comparison**: Side-by-side variant A vs B rates with winner indicator
4. **Email Log Table**: Paginated with status and variant filters

#### Workflows (`/workflows`)

**Data sources:** `adminAPI.getWorkflowStatus()` + `adminAPI.getDailyExecutions(14)`

**Sections:**
1. **Workflow Health List**: Per-workflow status badges
2. **14-Day Bar Chart**: Custom CSS bar chart — bar colour encodes failure rate (green = all success, red = all failed, gradient in between). Height encodes count.
3. **Daily Breakdown Table**: Date, total, success, failed counts
4. **Recent Failures Table**: Last failures across all workflows

#### N8n Workflows (`/n8n`)

**Data source:** `n8nAPI.listWorkflows()`

**Features:**
- Lists all n8n workflows (proxied from n8n REST API)
- Search filter by name or ID
- **Trigger button**: Executes workflow immediately (admin/operator only)
- **Active/Inactive toggle**: Activate or deactivate workflows (admin/operator only)
- Role-gated: action buttons only visible to admin/operator roles

#### AI Monitor (`/ai`)

**Data source:** `adminAPI.getAIDecisions(params)`

**Sections:**
1. **KPI Strip**: Total decisions, avg confidence, budget used, daily cost
2. **Confidence Distribution**: Visual breakdown by confidence level
3. **Request Type Breakdown**: Table by type (lead_classify, email_summarize, etc.)
4. **Decisions Table**: Filterable by type, status, confidence range

#### Human Review (`/review`)

**Data source:** `adminAPI.getReviewQueue()` + `adminAPI.resolveReview(id, payload)`

**Features:**
- Queue of AI decisions with `status = pending_review`
- SLA breach counter (decisions waiting too long)
- Three action buttons: **Approve** (green), **Reject** (red), **Override** (amber)
- Inline reviewer notes textarea — expands on action click, requires confirmation
- Session-level resolved counter

#### Systems Overview (`/systems`)

**Data source:** `systemsAPI.getOverview()` + `adminAPI.syncN8n()`

**Features:**
- Cross-system KPI strip (total executions, overall success rate, active systems)
- Card grid: one card per system with health stats, last run time, clickable navigation
- "Sync n8n" button: triggers `POST /admin/sync-n8n` to pull latest executions
- Cards link to `/systems/:slug` for detail drill-down

#### Bookings (`/bookings`)

**Data source:** `bookingsAPI.getStats()` + `bookingsAPI.list(params)`

**Features:**
- KPI strip: upcoming, completed, no-shows, completion rate
- Split view: upcoming meetings (scheduled_for > now) and past meetings
- Status filter for past meetings
- Source tags: 'calendly', 'n8n-workflow', 'gmail-reply'

#### Opportunities / Deals (`/opportunities`)

**Data source:** `opportunitiesAPI.getStats()` + `opportunitiesAPI.list(params)`

**Features:**
- KPI strip: pipeline value, won value, active deals, avg deal value
- Stage funnel: progress bars per pipeline stage
- Tier breakdown: strategic_partner, research_partner, pilot
- Paginated deals table with stage filter

#### Tickets (`/tickets`)

**Data source:** `ticketsAPI.getStats()` + `ticketsAPI.list(params)` + `ticketsAPI.updateStatus()`

**Features:**
- KPI strip: open, in-progress, resolved, avg response time
- Category breakdown tiles (support, partnership, billing, technical)
- Filterable ticket table
- **Admin-only**: inline status dropdown to update ticket status directly

#### GTM Strategy (`/gtm`)

**Data source:** `gtmAPI.listStrategies()` + `gtmAPI.getStrategy(path)`

**Features:**
- File tree sidebar grouped by directory
- Click any `.md` file to load content
- Lightweight Markdown renderer (regex-based: headings, lists, bold, italic, code)
- Serves 13+ strategy files from configurable directory paths

#### System Logs (`/system`)

**Data source:** `adminAPI.getLogs(params)`

**Features:**
- KPI strip: INFO/WARNING/ERROR/CRITICAL counts
- Filter toolbar: level dropdown, source text filter, time window (6h/24h/72h/7d)
- Apply button triggers re-fetch
- Colour-coded log messages based on level

### 6.7 UI Component Library

| Component | Purpose | Key Feature |
|-----------|---------|-------------|
| `StatRow` | Horizontal KPI strip | Supports delta indicators (up/down arrows with colour), loading skeletons, status colouring |
| `Table` | Generic data table | Column slot system (`#cell-{key}`) for custom cell rendering, skeleton loading with randomised widths, empty state with icon |
| `Badge` | Status pill | 6 variants (success/warning/error/info/pending/default) with coloured dot |
| `SectionContainer` | Section wrapper | Title + subtitle header with hairline divider, optional action slot for toolbar |
| `EmptyState` | No-data placeholder | Icon + message + optional subtext/action slot |
| `Sidebar` | Main navigation | 13 items in 4 sections, active state indicator bar, role display, logout |
| `TopBar` | Page header | Route-derived title, last sync timestamp, global refresh button |

---

## 7. n8n Workflow Automation

### 7.1 The 5 Automation Systems

The dashboard monitors 5 independent automation systems, each with its own set of n8n workflows:

#### System 1: eSteps Leads (8 workflows)

The core academic outreach system — the primary focus of the project.

| ID | Name | Purpose |
|----|------|---------|
| EST-1 | Lead Intake & Enrichment | Imports CSV leads, enriches with LinkedIn data, calculates initial scores |
| EST-2 | Outreach Engine V2 | Sends personalised 5-step email sequences via Gmail, respects A/B variants |
| EST-3 | Reply Handler | Monitors Gmail for inbound replies, parses intent (meeting request, research inquiry), creates opportunities |
| EST-4 | RAG Ingestion | Ingests research papers and institution data into vector store for AI-powered personalisation |
| EST-5 | Booking & CRM Sync | Syncs Calendly bookings with the lead database, sends meeting prep materials |
| EST-6 | LinkedIn Actions | Sends LinkedIn connection requests and messages to high-scoring leads |
| EST-7 | Follow-up & No-Response Logic | Re-engages cold leads, adjusts stage and touch count |
| EST-8 | Lead Scoring & Segmentation | Recalculates lead scores based on engagement signals, updates campaign tags |

**Current production stats:** 287 executions tracked, 88% success rate, 35 failures.

#### System 2: WAM Agency (5 workflows)

B2B agency lead generation — a second client implementation.

| ID | Name | Purpose |
|----|------|---------|
| WAM-1 | Lead Import | Imports agency prospect lists |
| WAM-2 | Outreach Sequence Engine | Multi-channel outreach (email + WhatsApp) |
| WAM-3 | Reply Handler | Email reply parsing |
| WAM-4 | WhatsApp Reply Handler | WhatsApp Business message processing |
| WAM-5 | RAG Ingestion | Knowledge base building for personalisation |

**Current production stats:** 14 executions, all failed (configuration issue in n8n — identified via dashboard).

#### System 3: AI Chatbot (4 workflows)

Customer-facing AI support assistant for eSteps Health.

| ID | Name | Purpose |
|----|------|---------|
| — | eSteps Health AI Chatbot v4.2 | Latest production chatbot |
| — | Support Ticket Classifier | AI-classifies incoming tickets by category and priority |
| — | Customer Chatbot v3 | Previous version (archived) |
| — | eSteps Health AI Customer Chatbot | Customer-facing variant |

#### System 4: Solar Leads (5 workflows)

Solar energy lead capture system.

| ID | Name | Purpose |
|----|------|---------|
| WF-A | Ingestion & Strategy Engine | Imports solar leads and applies qualification strategy |
| WF-B | Nurturer Sequence Dispatcher | Drip campaign for solar prospects |
| WF-C | AI Sales Agent | Automated sales conversation agent |
| WF-D | Daily Digest & CRM Sync | Aggregates daily activity and syncs to CRM |
| WF-E | Error Handler | Catches and logs errors across Solar workflows |

#### System 5: AI Influencer (5 workflows)

AI influencer persona ("Jane") for content creation and outreach.

| ID | Name | Purpose |
|----|------|---------|
| Jane-1 | Brand Import | Imports brand partnership prospects |
| Jane-2 | Daily Outreach Engine | Scheduled outreach to brands |
| Jane-3 | Reply Handler | Processes brand responses |
| Jane-4 | New Brand Outreach (Manual) | Manually triggered outreach for new brands |
| Jane-5 | Call Booked Handler | Processes confirmed brand meetings |

**Current production stats:** 48 executions, 100% success rate.

### 7.2 Webhook Integration

When an n8n workflow completes, it sends a POST request to the dashboard:

```
POST /webhooks/{system_slug}
Headers:
  Content-Type: application/json
  X-N8N-Signature: sha256=<hex-digest>

Body:
{
  "workflow_id": "est-2",
  "workflow_name": "EST-2: Outreach Engine V2",
  "execution_id": "exec_abc123",
  "status": "success",
  "duration_seconds": 4.2,
  "error_message": null,
  "error_type": null,
  "correlation_id": "corr_def456",
  "metadata": {}
}
```

**Validation:** The backend computes `HMAC-SHA256(body, system.webhook_secret)` and compares it against the `X-N8N-Signature` header. In production mode, mismatched signatures return `403 Forbidden`.

### 7.3 Execution Sync (REST API)

In addition to webhooks, the dashboard can pull execution history directly from n8n's REST API:

```
GET https://n8n.estepshealth.tech/api/v1/executions
Headers: X-N8N-API-KEY: <api-key>
```

The sync uses cursor-based pagination to retrieve up to 500 executions per run. The 27 n8n workflow IDs are mapped to system slugs via a hardcoded lookup table in `sync_n8n.py`.

---

## 8. Authentication & Security

### 8.1 JWT Authentication

The system uses **stateless JWT tokens** for authentication:

1. User submits username + password to `POST /auth/token`
2. Backend verifies credentials against the `users` table (PBKDF2-SHA256 or bcrypt)
3. Returns a signed JWT token with 24-hour expiration
4. Frontend stores the token in `localStorage` and attaches it to every request via Axios interceptor
5. Backend decodes and validates the JWT on every protected endpoint

**Token payload:**
```json
{
  "sub": "admin",        // username
  "exp": 1716940800      // expiration timestamp
}
```

### 8.2 Role-Based Access Control (RBAC)

Three roles with escalating permissions:

| Role | Read Data | Trigger Workflows | Manage Tickets | Resolve Reviews | Sync n8n |
|------|-----------|-------------------|----------------|-----------------|----------|
| `readonly` | Yes | No | No | No | No |
| `operator` | Yes | Yes | No | Yes | No |
| `admin` | Yes | Yes | Yes | Yes | Yes |

**FastAPI dependency chain:**

```python
get_current_user    → validates JWT, returns User object    (any authenticated user)
require_operator    → checks role in (admin, operator)      (workflow + review actions)
require_admin       → checks role == admin                  (ticket status + n8n sync)
```

### 8.3 Password Security

- Primary: **PBKDF2-SHA256** via passlib
- Legacy: **bcrypt** support for backward compatibility (detected by `$2a$`/`$2b$`/`$2y$` prefix)
- Passwords are never stored in plaintext

### 8.4 HMAC Webhook Verification

Each of the 5 systems has its own `webhook_secret` stored in the `systems` table. When n8n sends a webhook:

```python
expected = hmac.new(system.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
actual = request.headers.get("X-N8N-Signature", "").removeprefix("sha256=")
if not hmac.compare_digest(expected, actual):
    raise HTTPException(403, "Invalid signature")
```

### 8.5 CORS Configuration

CORS middleware restricts which origins can access the API:

```
Default: http://localhost:5173, http://localhost:3000, http://frontend:5173
```

Configurable via the `CORS_ORIGINS` environment variable.

---

## 9. Data Flow Examples

### 9.1 Flow 1: User Views the Overview Dashboard

```
1. User navigates to /overview
2. Vue Router loads Overview.vue (lazy import, code-split)
3. useStaleFetch calls load() on mount
4. load() calls adminAPI.getMetrics() and adminAPI.getWorkflowStatus()
5. Axios attaches JWT token via request interceptor
6. FastAPI receives GET /admin/dashboard/metrics
7. get_current_user dependency validates JWT
8. Handler queries BOTH databases:
   - Ops DB: workflow_executions count, ai_requests cost
   - Leads DB: leads count (1,408), email counts, reply rates
9. Pydantic serialises DashboardMetrics response
10. Vue computed properties transform data into StatRow format
11. Template renders KPI strip, funnel, health list, AI grid
```

### 9.2 Flow 2: n8n Workflow Completes and Sends Webhook

```
1. EST-2 (Outreach Engine) finishes at 09:15 AM
2. n8n HTTP Request node POSTs to /webhooks/esteps-leads
3. Headers include X-N8N-Signature: sha256=<digest>
4. FastAPI /webhooks/{system_slug} handler runs:
   a. Looks up system by slug → finds esteps-leads
   b. Reads webhook_secret from systems table
   c. Computes HMAC-SHA256 of request body
   d. Compares against header signature → valid
5. Creates WorkflowExecution record in ops DB
6. Creates AuditLog entry (level=INFO, source=n8n)
7. Returns 200 OK
8. Next time a user visits /systems or /workflows, the execution appears
```

### 9.3 Flow 3: Admin Resolves an AI Review Item

```
1. Admin navigates to /review
2. HumanReview.vue loads review queue
3. Admin clicks "Override" on an AI classification
4. Reviewer notes textarea expands inline
5. Admin types notes and clicks "Confirm Override"
6. Frontend POSTs to /admin/human-review/queue/{id}/resolve:
   { "action": "override", "reviewer_notes": "Misclassified — actually priority A" }
7. Backend verifies admin/operator role
8. Updates ai_requests record: human_override=true, status=rejected
9. Creates AuditLog entry recording the override
10. Frontend removes item from queue, increments resolved counter
```

### 9.4 Flow 4: Admin Triggers a Workflow from Dashboard

```
1. Admin navigates to /n8n
2. N8nWorkflows.vue loads workflow list from n8n proxy
3. Admin clicks "Trigger" on EST-2
4. Confirm dialog appears → admin confirms
5. Frontend POSTs to /proxy/n8n/workflows/{id}/execute
6. Backend proxies request to n8n REST API:
   POST https://n8n.estepshealth.tech/api/v1/executions
   Body: { "workflowId": "Qpr7fVyFFhdi9CFy" }
7. n8n starts the workflow
8. When workflow completes, n8n fires webhook → back to flow 9.2
```

### 9.5 Flow 5: Syncing n8n Executions

```
1. Admin clicks "Sync n8n" on SystemsOverview page
2. Frontend POSTs to /admin/sync-n8n?limit=200
3. Backend calls sync_n8n.sync(limit=200):
   a. GET /api/v1/executions from n8n (cursor pagination)
   b. Fetches up to 200 executions
   c. For each execution:
      - Map workflowId → system slug (27-entry lookup)
      - Map n8n status → dashboard status
      - INSERT with ON CONFLICT DO NOTHING
   d. Return { inserted: N, skipped: M, unmapped: K }
4. Frontend displays result toast
```

---

## 10. Deployment & Infrastructure

### 10.1 Development Setup

```bash
# Backend
cd dashboard-system/backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m app.seed                # seeds 5 systems + demo data
python -m app.sync_n8n --limit 500  # sync real n8n executions
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend
cd dashboard-system/frontend
npm install
npm run dev                       # → http://localhost:5173
```

**Default login:** `admin / admin123`
**API docs:** `http://localhost:8000/docs` (Swagger UI, auto-generated by FastAPI)

### 10.2 Environment Variables

```bash
# backend/.env

# Ops DB (Supabase esteps-ops, eu-west-1 Ireland, Transaction pooler)
DATABASE_URL=postgresql://postgres.[ref]:[pass]@aws-0-eu-west-1.pooler.supabase.com:6543/postgres

# Leads Source DB (eSteps Leads Automation, eu-central-1 Frankfurt, Transaction pooler)
LEADS_DATABASE_URL=postgresql://postgres.[ref]:[pass]@aws-0-eu-central-1.pooler.supabase.com:6543/postgres

# Security
JWT_SECRET=<32-char-hex-string>
N8N_WEBHOOK_SECRET=<shared-secret-with-n8n>
N8N_API_KEY=<n8n-rest-api-key>

# n8n
N8N_BASE_URL=https://n8n.estepshealth.tech

# Mode
ENVIRONMENT=development
AUTO_CREATE_DB=true
```

### 10.3 Docker Compose (Production)

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

No local database container — both databases are on Supabase. The Docker image contains only the FastAPI backend + Vue frontend build output.

### 10.4 Database Migrations

```bash
cd backend
alembic upgrade head
```

Two migration files:
1. `0001_initial_schema.py` — base tables (leads, workflow_executions, users, etc.)
2. `0002_multi_system.py` — adds `systems` table and `system_id` FK columns

---

## 11. Design System

### 11.1 Visual Language

**"Control Room Minimalism"** — a dark-mode industrial dashboard aesthetic designed for operational monitoring.

- **Theme:** Dark-mode only (no light mode)
- **Colour space:** OKLCH (perceptually uniform — colours maintain consistent contrast)
- **Background:** Near-black `oklch(10% 0.008 245)`
- **Foreground:** Near-white `oklch(92% 0.004 245)`

### 11.2 Typography

| Role | Font | Usage |
|------|------|-------|
| **Display** | Syne | Section headings, labels, page titles |
| **Body** | DM Sans | Paragraph text, descriptions |
| **Data** | JetBrains Mono | Numbers, table cells, code — with `tabular-nums` for alignment |

### 11.3 Colour Tokens

**Neutral scale (6 stops):**

| Token | OKLCH | Role |
|-------|-------|------|
| `--ctrl-100` | `oklch(92% 0.004 245)` | Primary text |
| `--ctrl-700` | `oklch(27% 0.013 245)` | Borders, dividers |
| `--ctrl-850` | `oklch(20% 0.010 245)` | Panel backgrounds |
| `--ctrl-900` | `oklch(14% 0.010 245)` | Surface backgrounds |

**Semantic status colours:**

| Token | Colour | Meaning |
|-------|--------|---------|
| `--status-success` | Green | OK, passed, active |
| `--status-error` | Red/orange | Failed, blocked |
| `--status-warn` | Yellow | Attention needed |
| `--status-info` | Blue | Informational, accent |

### 11.4 Spacing Scale

`--space-1` (0.25rem) through `--space-6` (2rem), used with Tailwind utility classes.

### 11.5 Component Patterns

- **Badge:** 6-variant status pill with coloured dot indicator
- **StatRow:** Horizontal KPI strip with delta arrows (green up / red down)
- **Table:** Column-based slot system for custom cell rendering
- **SectionContainer:** Title bar with hairline `::after` pseudo-element divider

### 11.6 Layout

```
┌──────────────────────────────────────────────────────────┐
│ ┌──────────┐ ┌──────────────────────────────────────────┐│
│ │          │ │ TopBar (sticky 48px)                     ││
│ │ Sidebar  │ ├──────────────────────────────────────────┤│
│ │ (fixed   │ │                                          ││
│ │  224px)  │ │  Main Content Area                       ││
│ │          │ │  (scrollable, px-7 py-7 padding)         ││
│ │ 4 nav    │ │                                          ││
│ │ sections │ │  Views render here via <router-view>     ││
│ │ 13 items │ │  wrapped in <keep-alive :max="10">       ││
│ │          │ │                                          ││
│ │ Role     │ │                                          ││
│ │ Logout   │ │                                          ││
│ └──────────┘ └──────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────┘
```

---

## Summary Statistics

| Metric | Count |
|--------|-------|
| Backend routers | 10 |
| API endpoints | 35 |
| Database models (ORM) | 11 |
| Pydantic schemas | 30+ |
| Frontend views | 13 |
| Frontend components | 7 |
| Frontend routes | 16 |
| API client methods | 28 |
| Pinia stores | 2 |
| n8n workflows monitored | 27 |
| Automation systems | 5 |
| Leads in production | 1,408 |
| Emails tracked | 1,400 |
| Executions synced | 349+ |
| Lines of Python (backend) | ~3,000 |
| Lines of Vue/JS (frontend) | ~2,500 |
| Total lines of code | ~5,500 |

---

*This document covers the complete system as of May 2026. For setup instructions, see the project README. For API testing, visit the Swagger UI at `http://localhost:8000/docs`.*
