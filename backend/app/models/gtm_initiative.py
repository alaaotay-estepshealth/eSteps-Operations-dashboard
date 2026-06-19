"""GTM Initiative — one extracted 30/60/90-day KPI/objective.

Sourced from a Claude Opus 4.7 read of GTM-2026-OS markdown. Advisory by
design: a row is created with status='suggested' and stays that way until an
operator+ flips it to 'applied' or 'rejected'. Re-runs supersede prior
'suggested' rows for the same period but leave applied/rejected untouched.
"""
from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class GtmInitiative(Base):
    __tablename__ = "gtm_initiatives"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    period = Column(String(8), nullable=False)
    objective_label = Column(Text, nullable=False)
    target_value = Column(Numeric, nullable=True)
    target_unit = Column(String(50), nullable=True)
    rationale = Column(Text, nullable=True)

    assignee_label = Column(Text, nullable=True)
    assignee_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    due_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="suggested")

    source_ai_request_id = Column(UUID(as_uuid=True), ForeignKey("ai_requests.id", ondelete="SET NULL"), nullable=True)

    applied_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    applied_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
