import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class MeetingNote(Base):
    __tablename__ = "meeting_notes"

    booking_id = Column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        primary_key=True,
    )
    prep_md = Column(Text, nullable=False, default="")
    recap_md = Column(Text, nullable=False, default="")
    ai_drafted_at = Column(DateTime(timezone=True), nullable=True)
    ai_model = Column(Text, nullable=True)
    updated_by = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
