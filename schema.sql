-- =============================================================================
-- ES-OPS-09  ·  Complete Supabase Schema
-- Project   : eSteps Operations Dashboard (multi-system)
-- Generated : 2026-05-14
-- Revision  : 0002_multi_system  (final state — merges both Alembic migrations)
--
-- HOW TO RUN
-- 1. Open Supabase Dashboard → SQL Editor → New Query
-- 2. Paste this entire file and click "Run"
-- 3. After success, update webhook_secret for each system row (Section 5)
-- 4. Then run: docker compose -f docker-compose.prod.yml exec backend python -m app.seed
--    (seeds 972 leads + demo executions; skips tables that already have rows)
--
-- IDEMPOTENT: Safe to run multiple times — uses CREATE TABLE IF NOT EXISTS
--             and ON CONFLICT DO NOTHING for seed rows.
-- =============================================================================

BEGIN;

-- =============================================================================
-- 1. EXTENSION
-- gen_random_uuid() is built-in on Supabase (pgcrypto enabled by default).
-- Uncomment if your Supabase project is on an older plan:
-- CREATE EXTENSION IF NOT EXISTS "pgcrypto";
-- =============================================================================


-- =============================================================================
-- 2. CORE REGISTRY  —  systems
-- Must be created first; workflow_executions / ai_requests / audit_logs FK here.
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
-- Custom JWT auth table (NOT Supabase auth.users).
-- =============================================================================

CREATE TABLE IF NOT EXISTS users (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    username        VARCHAR(100) NOT NULL,
    email           VARCHAR(255) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role            VARCHAR(50)  NOT NULL DEFAULT 'readonly',  -- admin | service | readonly
    is_active       BOOLEAN      NOT NULL DEFAULT true
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email    ON users (email);


-- =============================================================================
-- 4. LEAD PIPELINE  —  leads, email_logs, bookings, opportunities
-- =============================================================================

-- 4a. leads ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS leads (
    id                      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id                 VARCHAR(50),
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ,

    -- Identity
    first_name              VARCHAR(100),
    last_name               VARCHAR(100),
    email                   VARCHAR(255),
    institution             VARCHAR(255),
    position                VARCHAR(100),

    -- Research profile
    research_interest       VARCHAR(50),   -- parkinsons | gait_analysis | rehabilitation | etc.
    research_area           TEXT,

    -- Scoring
    lead_score              INTEGER      NOT NULL DEFAULT 0,
    esteps_relevance_score  INTEGER      NOT NULL DEFAULT 0,

    -- Pipeline
    campaign_tag            VARCHAR(50),   -- Priority_A | Priority_B | Priority_C | Below_ICP
    source                  VARCHAR(100)  NOT NULL DEFAULT 'import',  -- csv_import | linkedin | manual | conference | referral
    status                  VARCHAR(50)   NOT NULL DEFAULT 'active',  -- active | inactive
    stage                   VARCHAR(50)   NOT NULL DEFAULT 'new',     -- new | introduced | pitching | call_requested | engaged | meeting_booked | cold | dead
    touch_number            INTEGER       NOT NULL DEFAULT 0,

    -- Engagement
    reply_received          BOOLEAN       NOT NULL DEFAULT false,
    meeting_booked_at       TIMESTAMPTZ,

    -- Processing metrics (ES-OPS-09)
    processed_at            TIMESTAMPTZ,
    process_duration_min    FLOAT,
    ai_classified           BOOLEAN       NOT NULL DEFAULT false,
    human_verified          BOOLEAN       NOT NULL DEFAULT false,
    human_override          BOOLEAN       NOT NULL DEFAULT false,

    -- LinkedIn
    linkedin_available      BOOLEAN       NOT NULL DEFAULT false,
    linkedin_connected      BOOLEAN       NOT NULL DEFAULT false,

    -- A/B
    ab_variant              VARCHAR(1),

    -- GDPR
    gdpr_consent            BOOLEAN       NOT NULL DEFAULT false
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_leads_lead_id           ON leads (lead_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_leads_email             ON leads (email);
CREATE INDEX        IF NOT EXISTS ix_leads_research_interest ON leads (research_interest);
CREATE INDEX        IF NOT EXISTS ix_leads_campaign_tag      ON leads (campaign_tag);
CREATE INDEX        IF NOT EXISTS ix_leads_source            ON leads (source);
CREATE INDEX        IF NOT EXISTS ix_leads_status            ON leads (status);
CREATE INDEX        IF NOT EXISTS ix_leads_stage             ON leads (stage);


-- 4b. email_logs -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS email_logs (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ,
    lead_id         UUID         NOT NULL REFERENCES leads(id),
    sequence_step   INTEGER      NOT NULL DEFAULT 1,
    ab_variant      VARCHAR(1),
    email_status    VARCHAR(50)  NOT NULL DEFAULT 'sent',  -- sent | delivered | bounced
    open_detected   BOOLEAN      NOT NULL DEFAULT false,
    sent_at         TIMESTAMPTZ,
    delivered_at    TIMESTAMPTZ,
    subject         VARCHAR(255),
    provider        VARCHAR(50),   -- gmail | sendgrid | outlook
    message_id      VARCHAR(255),
    bounce_reason   TEXT
);

CREATE INDEX IF NOT EXISTS ix_email_logs_lead_id      ON email_logs (lead_id);
CREATE INDEX IF NOT EXISTS ix_email_logs_email_status ON email_logs (email_status);


-- 4c. bookings ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bookings (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ,
    lead_id             UUID         NOT NULL REFERENCES leads(id),
    status              VARCHAR(50)  NOT NULL DEFAULT 'scheduled',  -- scheduled | completed | canceled | no_show
    scheduled_for       TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    canceled_at         TIMESTAMPTZ,
    no_show_detected    BOOLEAN      NOT NULL DEFAULT false,
    source              VARCHAR(50),    -- calendly | manual
    external_id         VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS ix_bookings_lead_id ON bookings (lead_id);
CREATE INDEX IF NOT EXISTS ix_bookings_status  ON bookings (status);


-- 4d. opportunities ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS opportunities (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ,
    lead_id             UUID         NOT NULL REFERENCES leads(id),
    stage               VARCHAR(50)  NOT NULL DEFAULT 'meeting_booked',  -- meeting_booked | call_held | proposal_sent | pilot_active | closed_won | closed_lost
    partnership_tier    VARCHAR(50),   -- pilot | research_partner | strategic_partner
    deal_value_usd      FLOAT,
    expected_close_date TIMESTAMPTZ,
    closed_at           TIMESTAMPTZ,
    notes               TEXT
);

CREATE INDEX IF NOT EXISTS ix_opportunities_lead_id ON opportunities (lead_id);
CREATE INDEX IF NOT EXISTS ix_opportunities_stage   ON opportunities (stage);


-- =============================================================================
-- 5. SUPPORT  —  tickets
-- AI-classified inbound messages (email | chat | form | whatsapp).
-- =============================================================================

CREATE TABLE IF NOT EXISTS tickets (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ,

    -- Source
    source              VARCHAR(50),   -- email | chat | form | whatsapp
    subject             VARCHAR(500),
    body_preview        TEXT,

    -- AI classification
    ai_category         VARCHAR(50),   -- support | partnership | billing | technical
    ai_priority_score   INTEGER,       -- 1-5
    ai_confidence       FLOAT,

    -- Routing
    assigned_to         VARCHAR(100),
    status              VARCHAR(50)   NOT NULL DEFAULT 'open',  -- open | in_progress | resolved
    resolved_at         TIMESTAMPTZ,
    response_time_min   FLOAT,

    -- Human review
    human_verified      BOOLEAN       NOT NULL DEFAULT false,
    human_override      BOOLEAN       NOT NULL DEFAULT false,

    -- GDPR
    gdpr_consent        BOOLEAN       NOT NULL DEFAULT false,
    retention_until     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_tickets_status ON tickets (status);


-- =============================================================================
-- 6. AUTOMATION  —  workflow_executions
-- One row per n8n execution callback received via POST /webhooks/{system_slug}.
-- execution_id is UNIQUE to support idempotent re-delivery.
-- =============================================================================

CREATE TABLE IF NOT EXISTS workflow_executions (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ,

    -- FK to systems (NOT NULL — every execution belongs to a system)
    -- ON DELETE SET NULL is intentional: prevents accidental system row deletion
    -- while keeping the FK semantic clear. A SET NULL on a NOT NULL column
    -- causes the DELETE to fail (acts as RESTRICT in practice).
    system_id        UUID         NOT NULL REFERENCES systems(id) ON DELETE SET NULL,

    -- Workflow identity
    workflow_id      VARCHAR(100),   -- est-2 | wam-enrich | chat-router | etc.
    workflow_name    VARCHAR(200),
    execution_id     VARCHAR(200),   -- n8n execution ID — must be unique for idempotency

    -- Result
    status           VARCHAR(50),    -- running | success | failed | retrying
    started_at       TIMESTAMPTZ,
    finished_at      TIMESTAMPTZ,
    duration_seconds FLOAT,
    retry_count      INTEGER       NOT NULL DEFAULT 0,
    error_message    TEXT,
    error_type       VARCHAR(100),   -- timeout | api_error | validation | rate_limit | delivery_error
    resolved         BOOLEAN       NOT NULL DEFAULT false,

    -- Correlation
    correlation_id   VARCHAR(100),
    metadata         JSONB
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_workflow_executions_execution_id   ON workflow_executions (execution_id);
CREATE INDEX        IF NOT EXISTS ix_workflow_executions_system_id      ON workflow_executions (system_id);
CREATE INDEX        IF NOT EXISTS ix_workflow_executions_workflow_id    ON workflow_executions (workflow_id);
CREATE INDEX        IF NOT EXISTS ix_workflow_executions_status         ON workflow_executions (status);
CREATE INDEX        IF NOT EXISTS ix_workflow_executions_correlation_id ON workflow_executions (correlation_id);


-- =============================================================================
-- 7. AI  —  ai_requests
-- Every call to an AI provider (OpenAI / Gemini / Grok) logged here.
-- Drives the AI Ops dashboard: cost tracking, confidence, human review queue.
-- =============================================================================

CREATE TABLE IF NOT EXISTS ai_requests (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ,

    system_id        UUID         NOT NULL REFERENCES systems(id) ON DELETE SET NULL,

    -- Classification
    request_type     VARCHAR(100),   -- lead_classify | email_summarize | priority_score | draft_reply | log_summarize
    workflow_source  VARCHAR(100),   -- fastapi | n8n | ai_service | est-2 | est-3 | est-5
    entity_id        UUID,
    entity_type      VARCHAR(50),    -- lead | ticket

    -- Provider
    provider         VARCHAR(50),    -- openai | gemini | grok
    model            VARCHAR(100),   -- gpt-4o | gpt-4o-mini | gemini-1.5-flash
    tokens_used      INTEGER,
    cost_usd         FLOAT,
    latency_ms       INTEGER,

    -- Input / output
    input_preview    TEXT,           -- first 200 chars only (GDPR-safe)
    ai_output        JSONB,
    confidence_score FLOAT,          -- 0.0 – 1.0

    -- Safety controls
    used_fallback    BOOLEAN       NOT NULL DEFAULT false,
    fallback_reason  VARCHAR(100),   -- rate_limited | timeout | error
    human_verified   BOOLEAN       NOT NULL DEFAULT false,
    human_override   BOOLEAN       NOT NULL DEFAULT false,
    status           VARCHAR(50)   NOT NULL DEFAULT 'completed',  -- completed | pending_review | rejected

    -- GDPR
    retention_until  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_ai_requests_system_id       ON ai_requests (system_id);
CREATE INDEX IF NOT EXISTS ix_ai_requests_request_type    ON ai_requests (request_type);
CREATE INDEX IF NOT EXISTS ix_ai_requests_workflow_source ON ai_requests (workflow_source);
CREATE INDEX IF NOT EXISTS ix_ai_requests_status          ON ai_requests (status);


-- =============================================================================
-- 8. OBSERVABILITY  —  audit_logs
-- Append-only log: FastAPI events, n8n callbacks, AI decisions, HMAC failures.
-- system_id is NULLABLE here — logs from non-system sources (auth, admin) allowed.
-- =============================================================================

CREATE TABLE IF NOT EXISTS audit_logs (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),

    -- Nullable FK — audit events from non-system sources are valid
    system_id       UUID         REFERENCES systems(id) ON DELETE SET NULL,

    level           VARCHAR(20),    -- INFO | WARNING | ERROR | CRITICAL
    source          VARCHAR(100),   -- fastapi | n8n | ai_service | est-2 | est-3 | est-5
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
-- 9. ALEMBIC VERSION
-- Tells the Alembic migration runner this DB is already at revision 0002.
-- Without this row, running "alembic upgrade head" would try to re-apply
-- 0001 and 0002 and fail on duplicate table errors.
-- =============================================================================

CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

INSERT INTO alembic_version (version_num)
VALUES ('0002_multi_system')
ON CONFLICT DO NOTHING;


COMMIT;


-- =============================================================================
-- 10. SEED  —  5 systems
-- These are configuration rows, not demo data.
-- webhook_secret values are PLACEHOLDERS — change them before wiring n8n.
-- Generate a secret: python -c "import secrets; print(secrets.token_hex(24))"
-- Update via SQL:
--   UPDATE systems SET webhook_secret = 'your-real-secret' WHERE slug = 'esteps-leads';
-- =============================================================================

BEGIN;

INSERT INTO systems (slug, name, description, webhook_secret, n8n_project_id, is_active)
VALUES
    (
        'esteps-leads',
        'eSteps Leads',
        'Academic researcher outreach and partnership pipeline',
        'esteps-leads-secret-CHANGE-ME',
        NULL,
        true
    ),
    (
        'wam-agency',
        'WAM Agency',
        'B2B agency lead generation and nurture automation',
        'wam-agency-secret-CHANGE-ME',
        NULL,
        true
    ),
    (
        'ai-chatbot',
        'AI Chatbot',
        'Customer-facing AI assistant and ticket routing',
        'ai-chatbot-secret-CHANGE-ME',
        NULL,
        true
    ),
    (
        'solar-leads',
        'Solar Leads',
        'Solar energy lead capture and qualification pipeline',
        'solar-leads-secret-CHANGE-ME',
        NULL,
        true
    ),
    (
        'ai-influencer',
        'AI Influencer',
        'AI-generated content and influencer outreach automation',
        'ai-influencer-secret-CHANGE-ME',
        NULL,
        true
    )
ON CONFLICT (slug) DO NOTHING;

COMMIT;


-- =============================================================================
-- 11. SEED  —  admin user
-- hashed_password here is a PLACEHOLDER bcrypt hash (not a real hash).
-- REQUIRED: after running this file, run seed.py to get proper bcrypt hashes:
--   docker compose -f docker-compose.prod.yml exec backend python -m app.seed
-- seed.py checks if users table is empty before inserting — safe to run after.
--
-- If you need the admin user immediately without seed.py, generate the hash:
--   python -c "from passlib.context import CryptContext; \
--               ctx = CryptContext(schemes=['bcrypt']); \
--               print(ctx.hash('admin123'))"
-- Then replace the placeholder below and uncomment:
-- =============================================================================

-- INSERT INTO users (username, email, hashed_password, role, is_active)
-- VALUES
--     ('admin',  'admin@estepshealth.com',  '$2b$12$REPLACE_WITH_REAL_BCRYPT_HASH', 'admin',    'true'),
--     ('viewer', 'viewer@estepshealth.com', '$2b$12$REPLACE_WITH_REAL_BCRYPT_HASH', 'readonly', 'true')
-- ON CONFLICT DO NOTHING;


-- =============================================================================
-- 12. POST-RUN CHECKLIST
-- =============================================================================
--
-- After running this file in Supabase SQL Editor:
--
-- [ ] Tables created:
--       SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1;
--       Expected: ai_requests, alembic_version, audit_logs, bookings,
--                 email_logs, leads, opportunities, systems, tickets,
--                 users, workflow_executions
--
-- [ ] 5 system rows exist:
--       SELECT slug, is_active FROM systems ORDER BY slug;
--
-- [ ] Alembic version locked:
--       SELECT * FROM alembic_version;
--       Expected: 0002_multi_system
--
-- [ ] Update DATABASE_URL in backend/.env (Transaction Pooler — eu-west-1, IPv4):
--       postgresql://postgres.lsihimpxtahvnyjlqsix:[PASSWORD]@aws-0-eu-west-1.pooler.supabase.com:6543/postgres?sslmode=require
--       Note: username must be postgres.[project-ref] for the pooler (not just postgres)
--
-- [ ] Run seed.py for demo data + real bcrypt users:
--       docker compose -f docker-compose.prod.yml exec backend python -m app.seed
--
-- [ ] Generate and set REAL webhook secrets (never use the CHANGE-ME placeholders):
--       UPDATE systems SET webhook_secret = 'real-secret' WHERE slug = 'esteps-leads';
--       ... repeat for each slug
--
-- [ ] Verify backend health:
--       curl http://localhost:8000/health
--       curl http://localhost:8000/admin/systems   (with JWT)
--
-- =============================================================================
