from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    username = Column(String(100), unique=True, index=True)
    email = Column(String(255), unique=True)
    hashed_password = Column(String(255))
    role = Column(String(50), default="readonly")  # admin | service | readonly
    is_active = Column(Boolean, default=True)
