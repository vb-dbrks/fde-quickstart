"""Shared fixtures: a real Postgres (pgserver, no Docker), the app wired to it, and the fake agent."""

import shutil
import tempfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import pgserver
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.auth.roles import Role
from backend.main import create_app
from backend.settings import Settings
from tests.helpers import ADMIN, BRIEF, DEV_USER, EDITOR, IsolatedSettings, as_user, fake_runtime

TABLES = (
    "app.agent_runs, app.messages, app.threads, app.audit_log, app.document_versions, "
    "app.document_fields, app.document_access, app.documents, app.notifications, "
    "app.role_assignments, app.idempotency_keys"
)


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    # Keep the path short: Postgres puts its Unix socket here, and socket paths max out at ~100 chars.
    pgdata = Path(tempfile.mkdtemp(prefix="pgtest-"))
    server = pgserver.get_server(pgdata, cleanup_mode="stop")
    try:
        server.psql("CREATE DATABASE app_test;")
        yield server.get_uri("app_test")
    finally:
        server.cleanup()
        shutil.rmtree(pgdata, ignore_errors=True)


@pytest.fixture(scope="session")
def settings(database_url: str, tmp_path_factory: pytest.TempPathFactory) -> Settings:
    static_dir = tmp_path_factory.mktemp("static")
    (static_dir / "index.html").write_text("<!doctype html><title>test app</title>")
    (static_dir / "favicon.svg").write_text("<svg></svg>")
    (static_dir.parent / "secret.txt").write_text("outside the static dir")
    return IsolatedSettings(
        database_url=database_url,
        databricks_app_name=None,
        app_admin_emails=ADMIN,
        dev_user_email=DEV_USER,
        poller_enabled=False,
        notification_webhook_url=None,
        static_dir=static_dir,
    )


@pytest.fixture(scope="session")
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    application = create_app(settings, agent_runtime=fake_runtime())
    async with application.router.lifespan_context(application):  # connects and migrates
        yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    original_agent = app.state.agent_client
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.state.agent_client = original_agent
    async with app.state.engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))


@pytest.fixture
def sessions(app: FastAPI, client: httpx.AsyncClient) -> async_sessionmaker[AsyncSession]:
    """Session factory; depends on ``client`` so the tables are cleaned up afterwards."""
    factory: async_sessionmaker[AsyncSession] = app.state.sessionmaker
    return factory


async def grant(client: httpx.AsyncClient, email: str, role: Role) -> None:
    response = await client.post(
        "/api/admin/role-assignments", json={"email": email, "role": role}, headers=as_user(ADMIN)
    )
    assert response.status_code in (200, 201), response.text


async def create_brief(
    client: httpx.AsyncClient, email: str = EDITOR, **fields: Any
) -> dict[str, Any]:
    response = await client.post(
        "/api/documents",
        json={"document_type": "brief", "fields": {**BRIEF, **fields}},
        headers=as_user(email),
    )
    assert response.status_code == 201, response.text
    document: dict[str, Any] = response.json()
    return document


@pytest.fixture
async def editor(client: httpx.AsyncClient) -> str:
    await grant(client, EDITOR, Role.EDITOR)
    return EDITOR
