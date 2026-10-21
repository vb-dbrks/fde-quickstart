"""Sending notifications, and reading them for the bell menu.

The UI polls ``GET /api/notifications`` every 30 seconds: the Apps proxy buffers server-sent events
and ends requests after 120 seconds, so polling is the simple, reliable default (ADR 0008).
"""

from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.models import Notification
from backend.services.notification_channels import Message, NotificationChannel


class Notifier:
    def __init__(self, channels: Sequence[NotificationChannel]) -> None:
        self._channels = tuple(channels)

    async def notify(self, db: AsyncSession, message: Message) -> None:
        """Send ``message`` on every channel. Commit the session to keep the in-app copy."""
        for channel in self._channels:
            await channel.send(db, message)


async def list_notifications(
    db: AsyncSession, recipient: str, *, unread_only: bool = False, limit: int = 20
) -> Sequence[Notification]:
    query = select(Notification).where(Notification.recipient == recipient)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    return (await db.scalars(query.order_by(Notification.id.desc()).limit(limit))).all()


async def unread_count(db: AsyncSession, recipient: str) -> int:
    query = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.recipient == recipient, Notification.read_at.is_(None))
    )
    return await db.scalar(query) or 0


async def mark_read(db: AsyncSession, recipient: str, notification_id: int) -> bool:
    """Mark one of ``recipient``'s notifications read. Returns False if it is not theirs."""
    updated = (
        await db.execute(
            update(Notification)
            .where(Notification.id == notification_id, Notification.recipient == recipient)
            .values(read_at=func.coalesce(Notification.read_at, func.now()))
            .returning(Notification.id)
        )
    ).first()
    return updated is not None


async def mark_all_read(db: AsyncSession, recipient: str) -> int:
    updated = (
        await db.execute(
            update(Notification)
            .where(Notification.recipient == recipient, Notification.read_at.is_(None))
            .values(read_at=func.now())
            .returning(Notification.id)
        )
    ).all()
    return len(updated)
