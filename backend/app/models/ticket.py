from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    source = Column(String(50))       # email | chat | form | whatsapp
    subject = Column(String(500))
    body_preview = Column(Text)

    # AI classification
    ai_category = Column(String(50))  # support | partnership | billing | technical
    ai_priority_score = Column(Integer)  # 1-5
    ai_confidence = Column(Float)

    # Routing
    assigned_to = Column(String(100))
    status = Column(String(50), default="open", index=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    response_time_min = Column(Float, nullable=True)

    # Human review
    human_verified = Column(Boolean, default=False)
    human_override = Column(Boolean, default=False)

    # GDPR
    gdpr_consent = Column(Boolean, default=False)
    retention_until = Column(DateTime(timezone=True), nullable=True)
