-- =============================================================================
-- ES-OPS-09  ·  Complete Supabase Schema  (final state)
-- Project   : eSteps Operations Dashboard (multi-system control plane)
-- Generated : 2026-06-02
-- Revision  : 0003_dash_alignment
--             (merges 0001 + 0002 + adds strategy_assets / meet_assets
--              + cron retention jobs)
--
-- HOW TO RUN
--   1. Open Supabase Dashboard → SQL Editor → New Query
--   2. Paste this entire file and click "Run"
--   3. (Optional) Enable pg_cron in Database → Extensions for §11 to take effect
--   4. After success, rotate every webhook_secret in `systems`
--   5. Then run: python -m app.seed   (seeds real user accounts only)
--
-- IDEMPOTENT: safe to re-run. Uses CREATE TABLE IF NOT EXISTS and
-- ON CONFLICT DO NOTHING for seed rows.
-- =============================================================================

BEGIN;

-- =============================================================================
-- 1. EXTENSIONS
-- =============================================================================
-- gen_random_uuid() is built-in on Supabase. Uncomment on older plans:
-- CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- pg_cron lives in the `cron` schema; the dashboard's nightly cleanup jobs
-- (§11) need this. If your Supabase plan disallows it, comment §11 out.
CREATE EXTENSION IF NOT EXISTS pg_cron;


-- =============================================================================
-- 2. CORE REGISTRY  —  systems
-- =============================================================================

CREATE TABLE IF NOT EXISTS systems (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ,
    slug            VARCHAR(50)  NOT NULL,
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    webhook_secret  VARCHAR(255) NOT NULL,
    n8n_project_id  VARCHAR(100),
    is_active       BOOLEAN      NOT NULL DEFAULT true,
    CONSTRAINT uq_systems_slug UNIQUE (slug)
);

CREATE INDEX IF NOT EXISTS ix_systems_slug      ON systems (slug);
CREATE INDEX IF NOT EXISTS ix_systems_is_active ON systems (is_active);


-- =============================================================================
-- 3. AUTH  —  users
-- Custom JWT auth (NOT Supabase auth.users).
-- Roles in the live app: admin | operator | readonly
-- (the legacy 'service'/'viewer' values still load — Auth normalizes them.)
-- =============================================================================

CREATE TABLE IF NOT EXISTS users (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    username        VARCHAR(100) NOT NULL,
    email           VARCHAR(255) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role            VARCHAR(50)  NOT NULL DEFAULT 'readonly',
    is_active       BOOLEAN      NOT NULL DEFAULT true
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email    ON users (email);


-- =============================================================================
-- 4. LEAD PIPELINE  —  bookings (leads/email_logs/opportunities live in LEADS DB)
--
-- NOTE: in production the *real* leads/email_logs/bookings/opportunities live
-- in the upstream eSteps Leads Supabase project (eu-central-1). The ops DB
-- keeps these tables as a fallback / demo target. Wire LEADS_DATABASE_URL in
-- backend/.env to read from the real source.
-- =============================================================================

-- NOTE 2026-06-06: leads/email_logs/opportunities live in the LEADS Supabase
-- project (eu-central-1, LEADS_DATABASE_URL). The OPS DB only owns `bookings`
-- (meetings the dashboard manages) and joins to leads via a soft UUID reference
-- — no FK constraint, since the parent row sits in a different database.

CREATE TABLE IF NOT EXISTS bookings (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ,
    lead_id             UUID         NOT NULL,
    status              VARCHAR(50)  NOT NULL DEFAULT 'scheduled',
    scheduled_for       TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    canceled_at         TIMESTAMPTZ,
    no_show_detected    BOOLEAN      NOT NULL DEFAULT false,
    source              VARCHAR(50),
    external_id         VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS ix_bookings_lead_id ON bookings (lead_id);
CREATE INDEX IF NOT EXISTS ix_bookings_status  ON bookings (status);


-- =============================================================================
-- 5. SUPPORT  —  tickets
-- =============================================================================

CREATE TABLE IF NOT EXISTS tickets (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ,
    source              VARCHAR(50),
    subject             VARCHAR(500),
    body_preview        TEXT,
    ai_category         VARCHAR(50),
    ai_priority_score   INTEGER,
    ai_confidence       FLOAT,
    assigned_to         VARCHAR(100),
    status              VARCHAR(50)   NOT NULL DEFAULT 'open',
    resolved_at         TIMESTAMPTZ,
    response_time_min   FLOAT,
    human_verified      BOOLEAN       NOT NULL DEFAULT false,
    human_override      BOOLEAN       NOT NULL DEFAULT false,
    gdpr_consent        BOOLEAN       NOT NULL DEFAULT false,
    retention_until     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_tickets_status         ON tickets (status);
CREATE INDEX IF NOT EXISTS ix_tickets_retention_until ON tickets (retention_until);


-- =============================================================================
-- 6. AUTOMATION  —  workflow_executions
-- =============================================================================

CREATE TABLE IF NOT EXISTS workflow_executions (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ,
    system_id        UUID         NOT NULL REFERENCES systems(id) ON DELETE SET NULL,
    workflow_id      VARCHAR(100),
    workflow_name    VARCHAR(200),
    execution_id     VARCHAR(200),
    status           VARCHAR(50),
    started_at       TIMESTAMPTZ,
    finished_at      TIMESTAMPTZ,
    duration_seconds FLOAT,
    retry_count      INTEGER       NOT NULL DEFAULT 0,
    error_message    TEXT,
    error_type       VARCHAR(100),
    resolved         BOOLEAN       NOT NULL DEFAULT false,
    correlation_id   VARCHAR(100),
    metadata         JSONB
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_workflow_executions_execution_id   ON workflow_executions (execution_id);
CREATE INDEX        IF NOT EXISTS ix_workflow_executions_system_id      ON workflow_executions (system_id);
CREATE INDEX        IF NOT EXISTS ix_workflow_executions_workflow_id    ON workflow_executions (workflow_id);
CREATE INDEX        IF NOT EXISTS ix_workflow_executions_status         ON workflow_executions (status);
CREATE INDEX        IF NOT EXISTS ix_workflow_executions_correlation_id ON workflow_executions (correlation_id);
CREATE INDEX        IF NOT EXISTS ix_workflow_executions_created_at     ON workflow_executions (created_at);


-- =============================================================================
-- 7. AI  —  ai_requests
-- =============================================================================

CREATE TABLE IF NOT EXISTS ai_requests (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ,
    system_id        UUID         NOT NULL REFERENCES systems(id) ON DELETE SET NULL,
    request_type     VARCHAR(100),
    workflow_source  VARCHAR(100),
    entity_id        UUID,
    entity_type      VARCHAR(50),
    provider         VARCHAR(50),
    model            VARCHAR(100),
    tokens_used      INTEGER,
    cost_usd         FLOAT,
    latency_ms       INTEGER,
    input_preview    TEXT,
    ai_output        JSONB,
    confidence_score FLOAT,
    used_fallback    BOOLEAN       NOT NULL DEFAULT false,
    fallback_reason  VARCHAR(100),
    human_verified   BOOLEAN       NOT NULL DEFAULT false,
    human_override   BOOLEAN       NOT NULL DEFAULT false,
    -- completed | pending_review | rejected | overridden
    status           VARCHAR(50)   NOT NULL DEFAULT 'completed',
    retention_until  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_ai_requests_system_id       ON ai_requests (system_id);
CREATE INDEX IF NOT EXISTS ix_ai_requests_request_type    ON ai_requests (request_type);
CREATE INDEX IF NOT EXISTS ix_ai_requests_workflow_source ON ai_requests (workflow_source);
CREATE INDEX IF NOT EXISTS ix_ai_requests_status          ON ai_requests (status);
CREATE INDEX IF NOT EXISTS ix_ai_requests_retention_until ON ai_requests (retention_until);


-- =============================================================================
-- 8. OBSERVABILITY  —  audit_logs
-- =============================================================================

CREATE TABLE IF NOT EXISTS audit_logs (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    system_id       UUID         REFERENCES systems(id) ON DELETE SET NULL,
    level           VARCHAR(20),
    source          VARCHAR(100),
    message         TEXT,
    correlation_id  VARCHAR(100),
    entity_id       UUID,
    entity_type     VARCHAR(50),
    user_id         VARCHAR(100),
    duration_ms     INTEGER,
    metadata        JSONB
);

CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at     ON audit_logs (created_at);
CREATE INDEX IF NOT EXISTS ix_audit_logs_system_id      ON audit_logs (system_id);
CREATE INDEX IF NOT EXISTS ix_audit_logs_level          ON audit_logs (level);
CREATE INDEX IF NOT EXISTS ix_audit_logs_source         ON audit_logs (source);
CREATE INDEX IF NOT EXISTS ix_audit_logs_correlation_id ON audit_logs (correlation_id);


-- =============================================================================
-- 9. FILE EXPLORERS  —  strategy_assets, meet_assets
-- DB-backed folder/file trees used by /gtm (Admin) and /meets.
-- Content blobs are limited to 25 MB at the application layer.
-- =============================================================================

CREATE TABLE IF NOT EXISTS strategy_assets (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    relative_path   VARCHAR(1024) NOT NULL,
    parent_path     VARCHAR(1024) NOT NULL DEFAULT '',
    name            VARCHAR(255)  NOT NULL,
    is_folder       BOOLEAN       NOT NULL DEFAULT false,
    mime_type       VARCHAR(127)  NOT NULL DEFAULT 'application/octet-stream',
    size_bytes      INTEGER       NOT NULL DEFAULT 0,
    content         BYTEA,
    uploaded_by     VARCHAR(100),
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT uq_strategy_assets_relative_path UNIQUE (relative_path)
);

CREATE INDEX IF NOT EXISTS ix_strategy_assets_relative_path ON strategy_assets (relative_path);
CREATE INDEX IF NOT EXISTS ix_strategy_assets_parent_path   ON strategy_assets (parent_path);


CREATE TABLE IF NOT EXISTS meet_assets (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    relative_path   VARCHAR(1024) NOT NULL,
    parent_path     VARCHAR(1024) NOT NULL DEFAULT '',
    name            VARCHAR(255)  NOT NULL,
    is_folder       BOOLEAN       NOT NULL DEFAULT false,
    mime_type       VARCHAR(127)  NOT NULL DEFAULT 'application/octet-stream',
    size_bytes      INTEGER       NOT NULL DEFAULT 0,
    content         BYTEA,
    uploaded_by     VARCHAR(100),
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT uq_meet_assets_relative_path UNIQUE (relative_path)
);

CREATE INDEX IF NOT EXISTS ix_meet_assets_relative_path ON meet_assets (relative_path);
CREATE INDEX IF NOT EXISTS ix_meet_assets_parent_path   ON meet_assets (parent_path);


-- =============================================================================
-- 10. ALEMBIC VERSION
-- =============================================================================

CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

INSERT INTO alembic_version (version_num) VALUES ('0003_dash_alignment')
ON CONFLICT DO NOTHING;


COMMIT;


-- =============================================================================
-- 11. RETENTION  —  pg_cron nightly cleanups
--
-- Mirrors the dashboard's `retention_until` column intent at the DB level so
-- old observability data doesn't grow forever. Skip this block if pg_cron
-- isn't available — the app keeps working, the DB just grows.
--
-- Schedule (UTC):
--   02:10 → low-value audit logs older than 90 days
--   02:20 → ai_requests where retention_until elapsed
--   02:30 → successful workflow runs older than 90 days
--   02:40 → resolved tickets older than 90 days
--
-- All jobs are unscheduled-then-rescheduled so re-running this file is safe.
-- =============================================================================

-- Reset existing schedules (no-op when first run).
SELECT cron.unschedule(jobid)
FROM cron.job
WHERE jobname IN (
    'esteps_purge_audit_logs',
    'esteps_purge_ai_requests',
    'esteps_purge_workflow_executions',
    'esteps_purge_tickets'
);

-- audit_logs: prune INFO/DEBUG older than 90 days. Keep WARNING/ERROR/CRITICAL
-- for one year (compliance window).
SELECT cron.schedule(
    'esteps_purge_audit_logs',
    '10 2 * * *',
    $$
    DELETE FROM audit_logs
    WHERE (level IN ('INFO', 'DEBUG') AND created_at < now() - INTERVAL '90 days')
       OR (level IN ('WARNING', 'ERROR', 'CRITICAL') AND created_at < now() - INTERVAL '365 days');
    $$
);

-- ai_requests: honour app-side retention_until.
SELECT cron.schedule(
    'esteps_purge_ai_requests',
    '20 2 * * *',
    $$
    DELETE FROM ai_requests
    WHERE retention_until IS NOT NULL AND retention_until < now();
    $$
);

-- workflow_executions: prune *successful* runs older than 90 days. Failed
-- runs stay until manually resolved (or 1 year) for incident review.
SELECT cron.schedule(
    'esteps_purge_workflow_executions',
    '30 2 * * *',
    $$
    DELETE FROM workflow_executions
    WHERE (status = 'success' AND created_at < now() - INTERVAL '90 days')
       OR (status IN ('failed', 'retrying') AND created_at < now() - INTERVAL '365 days');
    $$
);

-- tickets: resolved tickets older than 90 days, OR any ticket whose
-- retention_until has elapsed.
SELECT cron.schedule(
    'esteps_purge_tickets',
    '40 2 * * *',
    $$
    DELETE FROM tickets
    WHERE (status = 'resolved' AND resolved_at IS NOT NULL AND resolved_at < now() - INTERVAL '90 days')
       OR (retention_until IS NOT NULL AND retention_until < now());
    $$
);


-- =============================================================================
-- 12. POST-RUN CHECKLIST
-- =============================================================================
--
-- [ ] Tables present:
--       SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1;
--       Expected: ai_requests, alembic_version, audit_logs, bookings,
--                 email_logs, leads, meet_assets, opportunities,
--                 strategy_assets, systems, tickets, users, workflow_executions
--
-- [ ] Alembic version locked:
--       SELECT * FROM alembic_version;   -- expect '0003_dash_alignment'
--
-- [ ] Cron jobs registered:
--       SELECT jobname, schedule FROM cron.job ORDER BY jobname;
--       Expected: esteps_purge_audit_logs, esteps_purge_ai_requests,
--                 esteps_purge_workflow_executions, esteps_purge_tickets
--
-- [ ] Rotate every webhook_secret before wiring n8n. See wire_production.sql.
--
-- [ ] DATABASE_URL in backend/.env points at this Supabase project's
--     Transaction Pooler (eu-west-1, IPv4).
-- =============================================================================

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
