import uuid
from sqlalchemy import Boolean, Column, DateTime, Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class StrategyAsset(Base):
    """Persistent GTM strategy file/folder stored in the ops DB.

    Surfaces under the "uploads" root in the GTM file explorer. Folders have
    `is_folder=True` and `content=None`; files store raw bytes in `content`.
    `relative_path` is the path WITHOUT the "uploads/" prefix.
    """
    __tablename__ = "strategy_assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    relative_path = Column(String(1024), nullable=False, index=True)
    parent_path = Column(String(1024), nullable=False, default="", index=True)
    name = Column(String(255), nullable=False)
    is_folder = Column(Boolean, nullable=False, default=False)
    mime_type = Column(String(127), nullable=False, default="application/octet-stream")
    size_bytes = Column(Integer, nullable=False, default=0)
    content = Column(LargeBinary, nullable=True)
    uploaded_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("relative_path", name="uq_strategy_assets_relative_path"),
    )
