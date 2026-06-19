-- 202606071400_gtm_initiatives.sql
-- Adds the gtm_initiatives table + users.display_name column.
-- Idempotent: safe to re-apply.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS display_name TEXT;

UPDATE users SET display_name = username WHERE display_name IS NULL;

CREATE TABLE IF NOT EXISTS gtm_initiatives (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    period                VARCHAR(8) NOT NULL,
    objective_label       TEXT NOT NULL,
    target_value          NUMERIC,
    target_unit           VARCHAR(50),
    rationale             TEXT,
    assignee_label        TEXT,
    assignee_user_id      UUID REFERENCES users(id) ON DELETE SET NULL,
    due_at                TIMESTAMPTZ,
    status                VARCHAR(20) NOT NULL DEFAULT 'suggested',
    source_ai_request_id  UUID REFERENCES ai_requests(id) ON DELETE SET NULL,
    applied_by            UUID REFERENCES users(id) ON DELETE SET NULL,
    applied_at            TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gtm_initiatives_period_status
    ON gtm_initiatives(period, status);
CREATE INDEX IF NOT EXISTS idx_gtm_initiatives_assignee_status
    ON gtm_initiatives(assignee_user_id, status);
CREATE INDEX IF NOT EXISTS idx_gtm_initiatives_due_at
    ON gtm_initiatives(due_at) WHERE status IN ('suggested','applied');
CREATE INDEX IF NOT EXISTS idx_gtm_initiatives_source
    ON gtm_initiatives(source_ai_request_id);
