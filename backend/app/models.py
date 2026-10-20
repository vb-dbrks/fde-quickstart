"""ORM models. Every table lives in the app-owned schema (app.db.APP_SCHEMA).

After changing a model, add a migration: `make migration MSG="describe the change"`.
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

EMAIL_LENGTH = 320


class Note(Base):
    """Sample domain object. Replace it with your engagement's own tables."""

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    owner: Mapped[str] = mapped_column(String(EMAIL_LENGTH), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RoleAssignment(Base):
    """A role granted to a user. Roles and their permissions are defined in app.permissions.roles."""

    __tablename__ = "role_assignments"

    principal: Mapped[str] = mapped_column(String(EMAIL_LENGTH), primary_key=True)
    role: Mapped[str] = mapped_column(String(32), primary_key=True)
    granted_by: Mapped[str] = mapped_column(String(EMAIL_LENGTH))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    """An in-app notification, shown in the bell menu until read."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_recipient_read_at", "recipient", "read_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    recipient: Mapped[str] = mapped_column(String(EMAIL_LENGTH))
    kind: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
