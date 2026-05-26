from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid

from app.database import Base


class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    system_id = Column(UUID(as_uuid=True), ForeignKey("systems.id", ondelete="SET NULL"), nullable=False, index=True)

    workflow_id = Column(String(100), index=True)   # 'est-2' | 'wf_chatbot' | etc.
    workflow_name = Column(String(200))
    execution_id = Column(String(200), unique=True)  # n8n execution ID
    status = Column(String(50), index=True)          # running | success | failed | retrying
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Float, nullable=True)
    retry_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    error_type = Column(String(100), nullable=True)  # timeout | api_error | validation | rate_limit
    resolved = Column(Boolean, default=False)
    correlation_id = Column(String(100), index=True, nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=True)
