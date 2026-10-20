"""Notification channels. Every notification goes to the in-app inbox; add outbound channels here.

Channels run inside the caller's database transaction, so keep them fast. Outbound channels must not
raise on delivery problems - log them instead, so a failed webhook never rolls back the change itself.
"""

import logging
from dataclasses import dataclass
from typing import Protocol

import httpx2
from sqlalchemy.orm import Session

from app.models import Notification

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Message:
    recipient: str
    kind: str
    title: str
    body: str | None = None
    link: str | None = None


class NotificationChannel(Protocol):
    def send(self, session: Session, message: Message) -> None: ...


class InAppChannel:
    """Stores the notification for the bell menu in the UI."""

    def send(self, session: Session, message: Message) -> None:
        session.add(
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

    def __init__(self, url: str, client: httpx2.Client | None = None) -> None:
        self._url = url
        self._client = client or httpx2.Client(timeout=5.0)

    def send(self, session: Session, message: Message) -> None:
        text = f"*{message.title}* (for {message.recipient})"
        if message.body:
            text += f"\n{message.body}"
        try:
            self._client.post(self._url, json={"text": text}).raise_for_status()
        except httpx2.HTTPError:
            logger.warning(
                "Webhook delivery failed for %r notification", message.kind, exc_info=True
            )


def build_channels(webhook_url: str | None) -> list[NotificationChannel]:
    channels: list[NotificationChannel] = [InAppChannel()]
    if webhook_url:
        channels.append(WebhookChannel(webhook_url))
    return channels
