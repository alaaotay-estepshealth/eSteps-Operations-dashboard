"""dashboard tables — strategy/meet assets, meeting notes/tasks, ai suggestions, gtm initiatives

Brings Alembic in line with the ORM models that were previously only created by
`Base.metadata.create_all` (dev) or an un-wired raw-SQL file. Without this, a
clean `alembic upgrade head` deploy 500s on every GTM / meets / meetings /
suggestions / bookings-notes endpoint.

All statements are idempotent (IF NOT EXISTS / guarded) so this is safe to apply
to a fresh DB *and* to the existing live DB that was built with create_all.

Revision ID: 0003_dashboard_tables
Revises: 0002_multi_system
Create Date: 2026-06-19
"""

from alembic import op


revision = "0003_dashboard_tables"
down_revision = "0002_multi_system"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── users: add display_name + fix is_active type (0001 made it VARCHAR(10)) ──
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name TEXT")
    op.execute("UPDATE users SET display_name = username WHERE display_name IS NULL")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users'
                  AND column_name = 'is_active'
                  AND data_type <> 'boolean'
            ) THEN
                ALTER TABLE users ALTER COLUMN is_active DROP DEFAULT;
                ALTER TABLE users ALTER COLUMN is_active TYPE boolean
                    USING (lower(is_active::text) IN ('true', 't', '1'));
                ALTER TABLE users ALTER COLUMN is_active SET DEFAULT true;
            END IF;
        END$$;
        """
    )

    # ── strategy_assets (GTM file explorer "uploads" root) ───────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS strategy_assets (
            id UUID PRIMARY KEY,
            relative_path VARCHAR(1024) NOT NULL,
            parent_path VARCHAR(1024) NOT NULL DEFAULT '',
            name VARCHAR(255) NOT NULL,
            is_folder BOOLEAN NOT NULL DEFAULT false,
            mime_type VARCHAR(127) NOT NULL DEFAULT 'application/octet-stream',
            size_bytes INTEGER NOT NULL DEFAULT 0,
            content BYTEA,
            uploaded_by VARCHAR(100),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_strategy_assets_relative_path UNIQUE (relative_path)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_strategy_assets_relative_path ON strategy_assets (relative_path)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_strategy_assets_parent_path ON strategy_assets (parent_path)")

    # ── meet_assets (meeting-prep file explorer) — mirrors strategy_assets ───────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS meet_assets (
            id UUID PRIMARY KEY,
            relative_path VARCHAR(1024) NOT NULL,
            parent_path VARCHAR(1024) NOT NULL DEFAULT '',
            name VARCHAR(255) NOT NULL,
            is_folder BOOLEAN NOT NULL DEFAULT false,
            mime_type VARCHAR(127) NOT NULL DEFAULT 'application/octet-stream',
            size_bytes INTEGER NOT NULL DEFAULT 0,
            content BYTEA,
            uploaded_by VARCHAR(100),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_meet_assets_relative_path UNIQUE (relative_path)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_meet_assets_relative_path ON meet_assets (relative_path)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_meet_assets_parent_path ON meet_assets (parent_path)")

    # ── meeting_notes (1:1 with bookings) ────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS meeting_notes (
            booking_id UUID PRIMARY KEY REFERENCES bookings(id) ON DELETE CASCADE,
            prep_md TEXT NOT NULL DEFAULT '',
            recap_md TEXT NOT NULL DEFAULT '',
            ai_drafted_at TIMESTAMPTZ,
            ai_model TEXT,
            updated_by TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    # ── meeting_tasks (N per booking) ────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS meeting_tasks (
            id UUID PRIMARY KEY,
            booking_id UUID NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            done BOOLEAN NOT NULL DEFAULT false,
            done_at TIMESTAMPTZ,
            due_at TIMESTAMPTZ,
            assignee TEXT,
            order_index INTEGER NOT NULL DEFAULT 0,
            created_by TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_meeting_tasks_booking_id ON meeting_tasks (booking_id)")

    # ── ai_suggestions (per-entity AI proposals awaiting human apply/reject) ──────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_suggestions (
            id UUID PRIMARY KEY,
            entity_type TEXT NOT NULL,
            entity_id UUID NOT NULL,
            payload JSONB NOT NULL,
            applied_payload JSONB,
            model TEXT NOT NULL,
            confidence FLOAT,
            status TEXT NOT NULL DEFAULT 'pending',
            rationale TEXT,
            applied_at TIMESTAMPTZ,
            applied_by TEXT,
            rejected_at TIMESTAMPTZ,
            rejected_by TEXT,
            rejection_reason TEXT,
            ai_request_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_suggestions_entity_type ON ai_suggestions (entity_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_suggestions_status ON ai_suggestions (status)")

    # ── gtm_initiatives (extracted 30/60/90 objectives) ──────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS gtm_initiatives (
            id UUID PRIMARY KEY,
            period VARCHAR(8) NOT NULL,
            objective_label TEXT NOT NULL,
            target_value NUMERIC,
            target_unit VARCHAR(50),
            rationale TEXT,
            assignee_label TEXT,
            assignee_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            due_at TIMESTAMPTZ,
            status VARCHAR(20) NOT NULL DEFAULT 'suggested',
            source_ai_request_id UUID REFERENCES ai_requests(id) ON DELETE SET NULL,
            applied_by UUID REFERENCES users(id) ON DELETE SET NULL,
            applied_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_gtm_initiatives_period_status ON gtm_initiatives (period, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_gtm_initiatives_assignee_status ON gtm_initiatives (assignee_user_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_gtm_initiatives_due_at ON gtm_initiatives (due_at) WHERE status IN ('suggested','applied')")
    op.execute("CREATE INDEX IF NOT EXISTS idx_gtm_initiatives_source ON gtm_initiatives (source_ai_request_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gtm_initiatives")
    op.execute("DROP TABLE IF EXISTS ai_suggestions")
    op.execute("DROP TABLE IF EXISTS meeting_tasks")
    op.execute("DROP TABLE IF EXISTS meeting_notes")
    op.execute("DROP TABLE IF EXISTS meet_assets")
    op.execute("DROP TABLE IF EXISTS strategy_assets")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS display_name")
