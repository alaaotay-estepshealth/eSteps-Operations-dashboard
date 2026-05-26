"""multi-system support: systems table + system_id on shared tables

Revision ID: 0002_multi_system
Revises: 0001_initial_schema
Create Date: 2026-05-05
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_multi_system"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

ESTEPS_LEADS_SLUG = "esteps-leads"
ESTEPS_LEADS_NAME = "eSteps Leads"
ESTEPS_LEADS_DESC = "Academic researcher outreach and partnership pipeline"


def upgrade() -> None:
    # 1. Create systems registry table
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS systems (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at  TIMESTAMPTZ DEFAULT now(),
            updated_at  TIMESTAMPTZ,
            slug        VARCHAR(50) NOT NULL,
            name        VARCHAR(255) NOT NULL,
            description TEXT,
            webhook_secret  VARCHAR(255) NOT NULL,
            n8n_project_id  VARCHAR(100),
            is_active   BOOLEAN NOT NULL DEFAULT true,
            CONSTRAINT uq_systems_slug UNIQUE (slug)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_systems_slug ON systems (slug)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_systems_is_active ON systems (is_active)")

    # 2. Seed esteps-leads system row (provide UUID explicitly — table may have no server-side default)
    op.execute(
        f"""
        INSERT INTO systems (id, slug, name, description, webhook_secret, is_active)
        VALUES (
            gen_random_uuid(),
            '{ESTEPS_LEADS_SLUG}',
            '{ESTEPS_LEADS_NAME}',
            '{ESTEPS_LEADS_DESC}',
            'esteps-leads-secret-change-me',
            true
        )
        ON CONFLICT (slug) DO NOTHING
        """
    )

    # 3. Add nullable system_id FK to shared tables
    for table in ("workflow_executions", "ai_requests", "audit_logs"):
        op.execute(
            f"""
            ALTER TABLE {table}
            ADD COLUMN IF NOT EXISTS system_id UUID
            REFERENCES systems(id) ON DELETE SET NULL
            """
        )
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_system_id ON {table} (system_id)"
        )

    # 4. Backfill: assign all existing rows to esteps-leads
    op.execute(
        """
        UPDATE workflow_executions
        SET system_id = (SELECT id FROM systems WHERE slug = 'esteps-leads')
        WHERE system_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE ai_requests
        SET system_id = (SELECT id FROM systems WHERE slug = 'esteps-leads')
        WHERE system_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE audit_logs
        SET system_id = (SELECT id FROM systems WHERE slug = 'esteps-leads')
        WHERE system_id IS NULL
        """
    )

    # 5. Enforce NOT NULL now that backfill is complete
    for table in ("workflow_executions", "ai_requests", "audit_logs"):
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN system_id SET NOT NULL"
        )


def downgrade() -> None:
    for table in ("workflow_executions", "ai_requests", "audit_logs"):
        op.execute(f"ALTER TABLE {table} ALTER COLUMN system_id DROP NOT NULL")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS system_id")
    op.execute("DROP TABLE IF EXISTS systems")
