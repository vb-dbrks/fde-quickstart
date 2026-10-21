"""Notification channels. Every notification goes to the in-app inbox; add outbound channels here.

Channels run inside the caller's database transaction, so keep them fast. Outbound channels must not
raise on delivery problems - log them instead, so a failed webhook never rolls back the change itself.
"""

import logging
from dataclasses import dataclass
from typing import Protocol

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.models import Notification

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Message:
    recipient: str
    kind: str
    title: str
    body: str | None = None
    link: str | None = None


class NotificationChannel(Protocol):
    async def send(self, db: AsyncSession, message: Message) -> None: ...


class InAppChannel:
    """Stores the notification for the bell menu in the UI."""

    async def send(self, db: AsyncSession, message: Message) -> None:
        db.add(
            Notification(
                recipient=message.recipient,
                kind=message.kind,
                title=message.title,
                body=message.body,
                link=message.link,
            )
        )


class WebhookChannel:
    """Posts each notification to a Slack-compatible incoming webhook as ``{"text": ...}``.

    Enabled when NOTIFICATION_WEBHOOK_URL is set; provide it from a secret app resource. The app's
    network egress must allow the webhook host.
    """

    def __init__(self, url: str, client: httpx.AsyncClient | None = None) -> None:
        self._url = url
        self._client = client or httpx.AsyncClient(timeout=5.0)

    async def send(self, db: AsyncSession, message: Message) -> None:
        text = f"*{message.title}* (for {message.recipient})"
        if message.body:
            text += f"\n{message.body}"
        try:
            response = await self._client.post(self._url, json={"text": text})
            response.raise_for_status()
        except httpx.HTTPError:
            logger.warning(
                "Webhook delivery failed for %r notification", message.kind, exc_info=True
            )


def build_channels(webhook_url: str | None) -> list[NotificationChannel]:
    channels: list[NotificationChannel] = [InAppChannel()]
    if webhook_url:
        channels.append(WebhookChannel(webhook_url))
    return channels
