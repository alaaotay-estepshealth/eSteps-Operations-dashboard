"""Minimal Lead stub.

The authoritative `leads` table lives in a separate Supabase project
(eu-central-1, accessed via `LEADS_DATABASE_URL`). This stub exists only so
`Base.metadata.create_all` succeeds in the test DB — the test DB never holds
real lead rows; cross-DB FKs from `bookings.lead_id` are unenforced in prod.
"""
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.database import Base


class Lead(Base):
    __tablename__ = "leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
