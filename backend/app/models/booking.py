from sqlalchemy import Boolean, Column, DateTime, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), index=True, nullable=False)
    status = Column(String(50), default="scheduled", index=True)
    scheduled_for = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    canceled_at = Column(DateTime(timezone=True), nullable=True)
    no_show_detected = Column(Boolean, default=False)
    source = Column(String(50), nullable=True)
    external_id = Column(String(100), nullable=True)
