from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid

from app.database import Base


class AIRequest(Base):
    __tablename__ = "ai_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    system_id = Column(UUID(as_uuid=True), ForeignKey("systems.id", ondelete="SET NULL"), nullable=False, index=True)

    request_type = Column(String(100), index=True)   # lead_classify | email_summarize | priority_score | draft_reply
    workflow_source = Column(String(100), index=True)
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    entity_type = Column(String(50), nullable=True)  # lead | ticket

    # AI provider
    provider = Column(String(50))        # openai | gemini | grok
    model = Column(String(100), nullable=True)
    tokens_used = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)
    latency_ms = Column(Integer, nullable=True)

    # Input/output
    input_preview = Column(Text, nullable=True)      # first 200 chars only
    ai_output = Column(JSONB, nullable=True)
    confidence_score = Column(Float, nullable=True)  # 0.0 to 1.0

    # Safety controls
    used_fallback = Column(Boolean, default=False)
    fallback_reason = Column(String(100), nullable=True)
    human_verified = Column(Boolean, default=False)
    human_override = Column(Boolean, default=False)
    status = Column(String(50), default="completed", index=True)  # completed | pending_review | rejected

    # GDPR
    retention_until = Column(DateTime(timezone=True), nullable=True)
