import json
import logging
from typing import Any
from unittest.mock import MagicMock

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.notifications.channels import Message, WebhookChannel
from app.permissions.roles import Role
from tests.helpers import EDITOR, VIEWER, as_user, grant


def test_granting_a_role_notifies_the_user(client: TestClient) -> None:
    grant(client, EDITOR, Role.EDITOR)
    body = client.get("/api/notifications", headers=as_user(EDITOR)).json()
    assert body["unread_count"] == 1
    [item] = body["items"]
    assert item["kind"] == "role_granted"
    assert "editor" in item["title"]
    assert item["read_at"] is None


def test_marking_notifications_read(client: TestClient) -> None:
    grant(client, EDITOR, Role.EDITOR)
    grant(client, EDITOR, Role.ADMIN)
    headers = as_user(EDITOR)
    items = client.get("/api/notifications", headers=headers).json()["items"]
    assert len(items) == 2

    assert (
        client.post(f"/api/notifications/{items[0]['id']}/read", headers=headers).status_code == 204
    )
    unread = client.get("/api/notifications?unread_only=true", headers=headers).json()
    assert unread["unread_count"] == 1
    assert len(unread["items"]) == 1

    assert client.post("/api/notifications/read-all", headers=headers).json() == {"updated": 1}
    assert client.get("/api/notifications", headers=headers).json()["unread_count"] == 0


def test_users_only_see_their_own_notifications(client: TestClient) -> None:
    grant(client, EDITOR, Role.EDITOR)
    item_id = client.get("/api/notifications", headers=as_user(EDITOR)).json()["items"][0]["id"]

    assert (
        client.post(f"/api/notifications/{item_id}/read", headers=as_user(VIEWER)).status_code
        == 404
    )
    assert client.get("/api/notifications", headers=as_user(VIEWER)).json() == {
        "items": [],
        "unread_count": 0,
    }


def test_webhook_channel_posts_the_message() -> None:
    received: list[dict[str, Any]] = []

    def hook(request: httpx2.Request) -> httpx2.Response:
        received.append(json.loads(request.content))
        return httpx2.Response(200)

    channel = WebhookChannel(
        "https://hooks.example.com/abc", client=httpx2.Client(transport=httpx2.MockTransport(hook))
    )
    channel.send(MagicMock(spec=Session), Message(EDITOR, "role_granted", "Hello", body="Details"))
    assert received == [{"text": f"*Hello* (for {EDITOR})\nDetails"}]


def test_webhook_failures_are_logged_not_raised(caplog: pytest.LogCaptureFixture) -> None:
    channel = WebhookChannel(
        "https://hooks.example.com/abc",
        client=httpx2.Client(transport=httpx2.MockTransport(lambda _: httpx2.Response(500))),
    )
    with caplog.at_level(logging.WARNING):
        channel.send(MagicMock(spec=Session), Message(EDITOR, "role_granted", "Hello"))
    assert "Webhook delivery failed" in caplog.text
