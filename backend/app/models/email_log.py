from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class EmailLog(Base):
    __tablename__ = "email_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), index=True, nullable=False)
    sequence_step = Column(Integer, default=1)
    ab_variant = Column(String(1), nullable=True)
    email_status = Column(String(50), default="sent", index=True)
    open_detected = Column(Boolean, default=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    subject = Column(String(255), nullable=True)
    provider = Column(String(50), nullable=True)
    message_id = Column(String(255), nullable=True)
    bounce_reason = Column(Text, nullable=True)
