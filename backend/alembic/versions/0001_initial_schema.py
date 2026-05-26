"""initial schema

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-04-29
"""

from alembic import op


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT now(),
            username VARCHAR(100) NOT NULL,
            email VARCHAR(255) NOT NULL,
            hashed_password VARCHAR(255) NOT NULL,
            role VARCHAR(50) DEFAULT 'readonly',
            is_active VARCHAR(10) DEFAULT 'true'
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS leads (
            id UUID PRIMARY KEY,
            lead_id VARCHAR(50),
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ,
            first_name VARCHAR(100),
            last_name VARCHAR(100),
            email VARCHAR(255),
            institution VARCHAR(255),
            position VARCHAR(100),
            research_interest VARCHAR(50),
            research_area TEXT,
            lead_score INTEGER DEFAULT 0,
            esteps_relevance_score INTEGER DEFAULT 0,
            campaign_tag VARCHAR(50),
            source VARCHAR(100) DEFAULT 'import',
            status VARCHAR(50) DEFAULT 'active',
            stage VARCHAR(50) DEFAULT 'new',
            touch_number INTEGER DEFAULT 0,
            reply_received BOOLEAN DEFAULT false,
            meeting_booked_at TIMESTAMPTZ,
            processed_at TIMESTAMPTZ,
            process_duration_min FLOAT,
            ai_classified BOOLEAN DEFAULT false,
            human_verified BOOLEAN DEFAULT false,
            human_override BOOLEAN DEFAULT false,
            linkedin_available BOOLEAN DEFAULT false,
            linkedin_connected BOOLEAN DEFAULT false,
            ab_variant VARCHAR(1),
            gdpr_consent BOOLEAN DEFAULT false
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_leads_lead_id ON leads (lead_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_leads_email ON leads (email)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_leads_research_interest ON leads (research_interest)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_leads_campaign_tag ON leads (campaign_tag)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_leads_source ON leads (source)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_leads_status ON leads (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_leads_stage ON leads (stage)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS email_logs (
            id UUID PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ,
            lead_id UUID NOT NULL REFERENCES leads(id),
            sequence_step INTEGER DEFAULT 1,
            ab_variant VARCHAR(1),
            email_status VARCHAR(50) DEFAULT 'sent',
            open_detected BOOLEAN DEFAULT false,
            sent_at TIMESTAMPTZ,
            delivered_at TIMESTAMPTZ,
            subject VARCHAR(255),
            provider VARCHAR(50),
            message_id VARCHAR(255),
            bounce_reason TEXT
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_logs_lead_id ON email_logs (lead_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_logs_email_status ON email_logs (email_status)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS bookings (
            id UUID PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ,
            lead_id UUID NOT NULL REFERENCES leads(id),
            status VARCHAR(50) DEFAULT 'scheduled',
            scheduled_for TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            canceled_at TIMESTAMPTZ,
            no_show_detected BOOLEAN DEFAULT false,
            source VARCHAR(50),
            external_id VARCHAR(100)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_bookings_lead_id ON bookings (lead_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_bookings_status ON bookings (status)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS opportunities (
            id UUID PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ,
            lead_id UUID NOT NULL REFERENCES leads(id),
            stage VARCHAR(50) DEFAULT 'meeting_booked',
            partnership_tier VARCHAR(50),
            deal_value_usd FLOAT,
            expected_close_date TIMESTAMPTZ,
            closed_at TIMESTAMPTZ,
            notes TEXT
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_opportunities_lead_id ON opportunities (lead_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_opportunities_stage ON opportunities (stage)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            id UUID PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ,
            source VARCHAR(50),
            subject VARCHAR(500),
            body_preview TEXT,
            ai_category VARCHAR(50),
            ai_priority_score INTEGER,
            ai_confidence FLOAT,
            assigned_to VARCHAR(100),
            status VARCHAR(50) DEFAULT 'open',
            resolved_at TIMESTAMPTZ,
            response_time_min FLOAT,
            human_verified BOOLEAN DEFAULT false,
            human_override BOOLEAN DEFAULT false,
            gdpr_consent BOOLEAN DEFAULT false,
            retention_until TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tickets_status ON tickets (status)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_executions (
            id UUID PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ,
            workflow_id VARCHAR(100),
            workflow_name VARCHAR(200),
            execution_id VARCHAR(200),
            status VARCHAR(50),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            duration_seconds FLOAT,
            retry_count INTEGER DEFAULT 0,
            error_message TEXT,
            error_type VARCHAR(100),
            resolved BOOLEAN DEFAULT false,
            correlation_id VARCHAR(100),
            metadata JSONB
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_workflow_executions_execution_id ON workflow_executions (execution_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_workflow_executions_workflow_id ON workflow_executions (workflow_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_workflow_executions_status ON workflow_executions (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_workflow_executions_correlation_id ON workflow_executions (correlation_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_requests (
            id UUID PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ,
            request_type VARCHAR(100),
            workflow_source VARCHAR(100),
            entity_id UUID,
            entity_type VARCHAR(50),
            provider VARCHAR(50),
            model VARCHAR(100),
            tokens_used INTEGER,
            cost_usd FLOAT,
            latency_ms INTEGER,
            input_preview TEXT,
            ai_output JSONB,
            confidence_score FLOAT,
            used_fallback BOOLEAN DEFAULT false,
            fallback_reason VARCHAR(100),
            human_verified BOOLEAN DEFAULT false,
            human_override BOOLEAN DEFAULT false,
            status VARCHAR(50) DEFAULT 'completed',
            retention_until TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_requests_request_type ON ai_requests (request_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_requests_workflow_source ON ai_requests (workflow_source)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_requests_status ON ai_requests (status)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id UUID PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT now(),
            level VARCHAR(20),
            source VARCHAR(100),
            message TEXT,
            correlation_id VARCHAR(100),
            entity_id UUID,
            entity_type VARCHAR(50),
            user_id VARCHAR(100),
            duration_ms INTEGER,
            metadata JSONB
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs (created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_level ON audit_logs (level)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_source ON audit_logs (source)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_correlation_id ON audit_logs (correlation_id)")


def downgrade() -> None:
    # Keep downgrade intentionally minimal for safety on already-populated local data.
    pass
