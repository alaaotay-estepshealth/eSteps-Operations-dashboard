import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    lead_id = Column(
        UUID(as_uuid=True), ForeignKey("leads.id"), index=True, nullable=False
    )
    status = Column(String(50), default="scheduled", index=True)
    scheduled_for = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    canceled_at = Column(DateTime(timezone=True), nullable=True)
    no_show_detected = Column(Boolean, default=False)
    source = Column(String(50), nullable=True)
    external_id = Column(String(100), nullable=True)

    # ES-OPS-09-MEET-NOTES additions
    title = Column(Text, nullable=True)
    meeting_url = Column(Text, nullable=True)
    duration_min = Column(Integer, default=20)
    rescheduled_from = Column(DateTime(timezone=True), nullable=True)
