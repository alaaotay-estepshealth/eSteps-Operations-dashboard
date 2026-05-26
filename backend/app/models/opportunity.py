from sqlalchemy import Column, DateTime, Float, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class Opportunity(Base):
    __tablename__ = "opportunities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), index=True, nullable=False)
    stage = Column(String(50), default="meeting_booked", index=True)
    partnership_tier = Column(String(50), nullable=True)
    deal_value_usd = Column(Float, nullable=True)
    expected_close_date = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
