"""Health, SPA serving, identity, roles, notifications, idempotency and migrations."""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import FastAPI, HTTPException
from sqlalchemy import Connection, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.requests import Request

from backend.auth.identity import identity_from_request
from backend.auth.roles import Permission, Role, permissions_for
from backend.db import migrations
from backend.db.base import Base
from backend.domain.models import IdempotencyKey
from backend.settings import Settings
from tests.conftest import create_brief, grant
from tests.helpers import ADMIN, DEV_USER, EDITOR, VIEWER, IsolatedSettings, as_user


def make_request(headers: dict[str, str]) -> Request:
    raw = [(name.lower().encode(), value.encode()) for name, value in headers.items()]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": raw})


# ---- health and SPA --------------------------------------------------------------------------


async def test_health_reports_the_database_and_agent(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/health")).json()
    assert (body["status"], body["database"]) == ("ok", "ok")
    assert body["agent"]["transport"] == "inprocess"
    assert body["agent"]["runners"]["generate"] == "fake"


async def test_client_side_routes_serve_the_spa(client: httpx.AsyncClient) -> None:
    for path in ("/", "/documents/abc", "/admin/roles"):
        response = await client.get(path)
        assert response.status_code == 200, path
        assert "<title>test app</title>" in response.text
    assert (await client.get("/favicon.svg")).text == "<svg></svg>"
    assert (await client.get("/api/does-not-exist")).json() == {"detail": "Not Found"}
    assert "outside the static dir" not in (await client.get("/%2E%2E/secret.txt")).text


# ---- identity and roles ----------------------------------------------------------------------


def test_identity_comes_from_the_proxy_header(settings: Settings) -> None:
    request = make_request({"X-Forwarded-Email": "  Alice@Example.COM "})
    assert identity_from_request(request, settings).email == "alice@example.com"
    assert identity_from_request(make_request({}), settings).email == DEV_USER
    on_platform = settings.model_copy(update={"databricks_app_name": "my-app"})
    with pytest.raises(HTTPException) as excinfo:
        identity_from_request(make_request({}), on_platform)
    assert excinfo.value.status_code == 401


def test_roles_bundle_permissions() -> None:
    assert permissions_for([Role.VIEWER]) == frozenset()
    assert permissions_for([Role.EDITOR]) == {Permission.DOCUMENTS_CREATE, Permission.AGENTS_RUN}
    assert permissions_for([Role.ADMIN]) == frozenset(Permission)
    assert IsolatedSettings(app_admin_emails=" A@x.com, ,b@y.com ").admin_emails == {
        "a@x.com",
        "b@y.com",
    }


async def test_admins_grant_roles_and_users_are_notified(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/me", headers=as_user(EDITOR))).json()["roles"] == ["viewer"]
    await grant(client, EDITOR, Role.EDITOR)
    me = (await client.get("/api/me", headers=as_user(EDITOR))).json()
    assert set(me["roles"]) == {"viewer", "editor"}
    notes = (await client.get("/api/notifications", headers=as_user(EDITOR))).json()
    assert (notes["unread_count"], notes["items"][0]["kind"]) == (1, "role_granted")

    url = "/api/admin/role-assignments"
    assert (await client.get(url, headers=as_user(EDITOR))).status_code == 403
    assert (
        await client.delete(f"{url}/{EDITOR}/editor", headers=as_user(ADMIN))
    ).status_code == 204
    assert (
        await client.delete(f"{url}/{EDITOR}/editor", headers=as_user(ADMIN))
    ).status_code == 404


async def test_notifications_are_marked_read(client: httpx.AsyncClient) -> None:
    await grant(client, EDITOR, Role.EDITOR)
    await grant(client, EDITOR, Role.ADMIN)
    headers = as_user(EDITOR)
    items = (await client.get("/api/notifications", headers=headers)).json()["items"]
    assert (
        await client.post(f"/api/notifications/{items[0]['id']}/read", headers=headers)
    ).status_code == 204
    assert (
        await client.post(f"/api/notifications/{items[0]['id']}/read", headers=as_user(VIEWER))
    ).status_code == 404
    assert (await client.post("/api/notifications/read-all", headers=headers)).json() == {
        "updated": 1
    }


# ---- idempotency -----------------------------------------------------------------------------


async def test_repeated_requests_with_the_same_key_are_replayed(
    client: httpx.AsyncClient, editor: str
) -> None:
    body: dict[str, Any] = {
        "document_type": "brief",
        "fields": {"brief.title": "Once", "brief.goal": "g"},
    }
    headers = {**as_user(editor), "Idempotency-Key": "create-once"}
    first = await client.post("/api/documents", json=body, headers=headers)
    second = await client.post("/api/documents", json=body, headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert second.headers["Idempotent-Replayed"] == "true"
    assert len((await client.get("/api/documents", headers=as_user(editor))).json()) == 1

    document = first.json()
    reused = await client.patch(
        f"/api/documents/{document['id']}/fields/brief.goal", json={"value": "x"}, headers=headers
    )
    assert reused.status_code == 422


async def test_failed_requests_are_not_stored(client: httpx.AsyncClient) -> None:
    headers = {**as_user(VIEWER), "Idempotency-Key": "retry-me"}
    body = {"document_type": "brief", "fields": {"brief.title": "x", "brief.goal": "y"}}
    assert (await client.post("/api/documents", json=body, headers=headers)).status_code == 403
    await grant(client, VIEWER, Role.EDITOR)
    assert (await client.post("/api/documents", json=body, headers=headers)).status_code == 201


async def test_a_key_still_in_use_is_answered_409(
    client: httpx.AsyncClient, editor: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The key is claimed before the request runs, so a concurrent repeat can't run it again."""
    async with sessions() as db:  # a request with this key is running right now
        db.add(IdempotencyKey(key="busy", principal=editor, method="POST", path="/api/documents"))
        await db.commit()
    headers = {**as_user(editor), "Idempotency-Key": "busy"}
    body = {"document_type": "brief", "fields": {"brief.title": "x", "brief.goal": "y"}}
    busy = await client.post("/api/documents", json=body, headers=headers)
    assert (busy.status_code, busy.headers["Retry-After"]) == (409, "2")

    async with sessions() as db:  # ...or it crashed long ago: its claim expires
        await db.execute(
            update(IdempotencyKey).values(created_at=datetime.now(UTC) - timedelta(minutes=10))
        )
        await db.commit()
    assert (await client.post("/api/documents", json=body, headers=headers)).status_code == 201


async def test_no_content_responses_replay_without_a_body(
    client: httpx.AsyncClient, editor: str
) -> None:
    document = await create_brief(client)
    headers = {**as_user(editor), "Idempotency-Key": "delete-once"}
    first = await client.delete(f"/api/documents/{document['id']}", headers=headers)
    again = await client.delete(f"/api/documents/{document['id']}", headers=headers)
    assert first.status_code == again.status_code == 204
    assert again.headers["Idempotent-Replayed"] == "true"
    assert again.content == b""


# ---- migrations ------------------------------------------------------------------------------


async def test_models_match_the_migrations(app: FastAPI) -> None:
    """Fails when a model changed without a migration: run `make migration MSG=...`."""

    def diff(connection: Connection) -> list[Any]:
        context = MigrationContext.configure(connection, opts=migrations.context_options())
        return list(compare_metadata(context, Base.metadata))

    async with app.state.engine.connect() as connection:
        assert await connection.run_sync(diff) == []


async def test_upgrading_twice_is_a_no_op(app: FastAPI) -> None:
    """Every instance migrates at startup, so a second run must change nothing."""
    await migrations.upgrade(app.state.engine)

    def current(connection: Connection) -> str | None:
        context = MigrationContext.configure(connection, opts=migrations.context_options())
        return context.get_current_revision()

    head = ScriptDirectory.from_config(migrations.alembic_config()).get_current_head()
    async with app.state.engine.connect() as connection:
        assert await connection.run_sync(current) == head


async def test_a_database_from_another_schema_fails_at_startup(app: FastAPI) -> None:
    """A database stamped with a known revision but lacking the tables (e.g. made by an earlier
    template with different migrations under the same ids) must fail loudly, not on first use."""
    async with app.state.engine.connect() as connection:
        await connection.execution_options(isolation_level="AUTOCOMMIT")
        await connection.execute(text("DROP DATABASE IF EXISTS stale_app"))
        await connection.execute(text("CREATE DATABASE stale_app"))
    url = app.state.engine.url.set(database="stale_app")
    stale = create_async_engine(url)
    try:
        async with stale.begin() as connection:
            await connection.execute(text("CREATE SCHEMA app"))
            await connection.execute(text("CREATE TABLE app.notes (id int primary key)"))
            await connection.execute(
                text("CREATE TABLE app.alembic_version (version_num varchar(32) primary key)")
            )
            head = ScriptDirectory.from_config(migrations.alembic_config()).get_current_head()
            await connection.execute(
                text("INSERT INTO app.alembic_version VALUES (:head)"), {"head": head}
            )
        with pytest.raises(RuntimeError, match="missing tables: agent_runs, audit_log"):
            await migrations.upgrade(stale)
    finally:
        await stale.dispose()
