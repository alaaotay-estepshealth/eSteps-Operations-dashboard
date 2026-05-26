from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.sql import func
import uuid

from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    system_id = Column(UUID(as_uuid=True), ForeignKey("systems.id", ondelete="SET NULL"), nullable=True, index=True)

    level = Column(String(20), index=True)    # INFO | WARNING | ERROR | CRITICAL
    source = Column(String(100), index=True)  # fastapi | n8n | ai_service | est-2 | etc.
    message = Column(Text)
    correlation_id = Column(String(100), index=True, nullable=True)
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    entity_type = Column(String(50), nullable=True)
    user_id = Column(String(100), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=True)
