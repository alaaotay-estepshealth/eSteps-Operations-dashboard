from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class Lead(Base):
    __tablename__ = "leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(String(50), unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Identity
    first_name = Column(String(100))
    last_name = Column(String(100))
    email = Column(String(255), unique=True, index=True)
    institution = Column(String(255))
    position = Column(String(100))

    # Research profile
    research_interest = Column(String(50), index=True)  # parkinsons | gait_analysis | etc.
    research_area = Column(Text)

    # Scoring
    lead_score = Column(Integer, default=0)
    esteps_relevance_score = Column(Integer, default=0)

    # Pipeline
    campaign_tag = Column(String(50), index=True)  # Priority_A | B | C | Below_ICP
    source = Column(String(100), default="import", index=True)
    status = Column(String(50), default="active", index=True)
    stage = Column(String(50), default="new", index=True)
    touch_number = Column(Integer, default=0)

    # Engagement
    reply_received = Column(Boolean, default=False)
    meeting_booked_at = Column(DateTime(timezone=True), nullable=True)

    # Processing metrics (ES-OPS-09)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    process_duration_min = Column(Float, nullable=True)
    ai_classified = Column(Boolean, default=False)
    human_verified = Column(Boolean, default=False)
    human_override = Column(Boolean, default=False)

    # LinkedIn
    linkedin_available = Column(Boolean, default=False)
    linkedin_connected = Column(Boolean, default=False)

    # A/B
    ab_variant = Column(String(1), nullable=True)

    # GDPR
    gdpr_consent = Column(Boolean, default=False)
