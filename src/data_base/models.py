# src/user_auth/data_base/models.py
# This module contains the SQLAlchemy models for users and refresh sessions.


###### IMPORT TOOLS ######
# global imports
from datetime import datetime
from sqlalchemy import (
    String,
    func,
    DateTime,
    Integer,
    Index, ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PgUUID, JSON
from uuid import UUID as PyUUID

# local imports
from src.data_base.db import Base


###### USER MODEL ######
class User(Base):
    """User model representing application users."""
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "uq_users_email_active_only",
            "email",
            unique=True,
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


###### EVENT MODEL ######
class Events(Base):
    """Events model representing user events in the application."""
    __tablename__ = "events"
    event_id: Mapped[PyUUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"),nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    properties: Mapped[dict] = mapped_column(JSON, nullable=True)
