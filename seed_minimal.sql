-- =============================================================================
-- MINIMAL SEED — eSteps Ops Dashboard
-- Run in: Supabase SQL Editor, AFTER schema.sql
-- Date: 2026-06-02
--
-- Seeds ONLY what's needed to log in and run the dashboard:
--   1. Three accounts: admin / operator / readonly
--   2. Five system rows (the multi-system control plane registry)
--
-- DOES NOT seed:
--   - leads / email_logs / bookings / opportunities  (real data lives in the
--     upstream eSteps Leads Supabase project, eu-central-1)
--   - workflow_executions / ai_requests / audit_logs / tickets  (these populate
--     themselves as soon as n8n starts posting webhooks)
--   - strategy_assets / meet_assets  (auto-seed from disk on first /gtm /meets hit)
--
-- IDEMPOTENT: safe to re-run. Existing usernames/system slugs are left alone.
-- ROTATE the seeded passwords before shipping — they are obviously not secret.
-- =============================================================================

BEGIN;

-- pgcrypto gives us `crypt()` for proper bcrypt hashes. Default on Supabase.
CREATE EXTENSION IF NOT EXISTS pgcrypto;


-- =============================================================================
-- 1. ACCOUNTS
--
-- Default passwords (rotate before prod):
--   admin    / admin123
--   operator / operator123
--   viewer   / viewer123   (role = readonly)
--
-- The dashboard's auth layer accepts bcrypt ($2b$...) OR pbkdf2_sha256 hashes;
-- crypt(..., gen_salt('bf', 12)) generates standard bcrypt with cost factor 12.
-- The frontend treats role 'viewer' as 'readonly' — both work.
-- =============================================================================

-- Use bare `ON CONFLICT DO NOTHING` so we tolerate dupes on EITHER unique key
-- (username OR email). If you want to also _reset_ existing passwords, run
-- §1b below instead of (or after) this insert.
INSERT INTO users (username, email, hashed_password, role, is_active)
VALUES
    ('admin',    'admin@estepshealth.com',    crypt('admin123',    gen_salt('bf', 12)), 'admin',    true),
    ('operator', 'operator@estepshealth.com', crypt('operator123', gen_salt('bf', 12)), 'operator', true),
    ('viewer',   'viewer@estepshealth.com',   crypt('viewer123',   gen_salt('bf', 12)), 'readonly', true)
ON CONFLICT DO NOTHING;

-- §1b. (Optional) FORCE-reset the three demo accounts' passwords + role.
-- Uncomment if a previous seed left them in a bad state. Safe to re-run.
-- UPDATE users SET hashed_password = crypt('admin123',    gen_salt('bf', 12)), role = 'admin',    is_active = true WHERE username = 'admin';
-- UPDATE users SET hashed_password = crypt('operator123', gen_salt('bf', 12)), role = 'operator', is_active = true WHERE username = 'operator';
-- UPDATE users SET hashed_password = crypt('viewer123',   gen_salt('bf', 12)), role = 'readonly', is_active = true WHERE username = 'viewer';


-- =============================================================================
-- 2. SYSTEMS
--
-- One row per automation pipeline. The webhook_secret here is a fresh random
-- 48-char hex value — copy it into the matching n8n HTTP Request node BEFORE
-- enabling the workflow, otherwise HMAC verification will reject every POST.
-- =============================================================================

INSERT INTO systems (slug, name, description, webhook_secret, n8n_project_id, is_active)
VALUES
    ('esteps-leads',
     'eSteps Leads',
     'Academic researcher outreach and partnership pipeline. Upstream Supabase: eu-central-1.',
     encode(gen_random_bytes(24), 'hex'),
     'eSteps Leads Automation System',
     true),

    ('wam-agency',
     'WAM Agency',
     'B2B agency lead generation and nurture automation.',
     encode(gen_random_bytes(24), 'hex'),
     'Wam Agency Leads',
     true),

    ('ai-chatbot',
     'eSteps Support',
     'Customer-facing AI chatbot, ticket classification, RAG-powered responses.',
     encode(gen_random_bytes(24), 'hex'),
     'eSteps Support',
     true),

    ('solar-leads',
     'Solar Leads',
     'Solar energy lead capture and qualification pipeline.',
     encode(gen_random_bytes(24), 'hex'),
     'Solar Leads',
     true),

    ('ai-influencer',
     'AI Influencer',
     'AI-generated brand outreach and influencer automation.',
     encode(gen_random_bytes(24), 'hex'),
     'AI Influencer Automation — Jane Mautin',
     true)
ON CONFLICT (slug) DO NOTHING;


COMMIT;


-- =============================================================================
-- POST-RUN
-- =============================================================================
--
-- a) Verify accounts created:
--      SELECT username, role, is_active FROM users ORDER BY username;
--
-- b) Verify systems created and grab the secrets to wire n8n:
--      SELECT slug, length(webhook_secret) AS secret_len, is_active
--      FROM systems ORDER BY slug;
--      -- all 5 rows, secret_len = 48
--
--      SELECT slug, webhook_secret FROM systems ORDER BY slug;
--      -- copy each secret into the X-N8N-Signature HMAC node for that system
--
-- c) Smoke-test login from the dashboard:
--      • admin    / admin123    → footer reads ADMIN / Full access
--      • operator / operator123
--      • viewer   / viewer123
--
-- d) ROTATE the demo passwords before going live:
--      UPDATE users SET hashed_password = crypt('NEW_SECURE_PASSWORD', gen_salt('bf', 12))
--      WHERE username = 'admin';
--
-- =============================================================================
