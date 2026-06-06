import uuid

from sqlalchemy import Column, DateTime, Float, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.database import Base


class AISuggestion(Base):
    __tablename__ = "ai_suggestions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(Text, nullable=False, index=True)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    payload = Column(JSONB, nullable=False)
    applied_payload = Column(JSONB, nullable=True)
    model = Column(Text, nullable=False)
    confidence = Column(Float, nullable=True)
    status = Column(Text, nullable=False, default="pending", index=True)
    rationale = Column(Text, nullable=True)
    applied_at = Column(DateTime(timezone=True), nullable=True)
    applied_by = Column(Text, nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    rejected_by = Column(Text, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    ai_request_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
