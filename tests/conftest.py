"""Shared fixtures: a real Postgres (pgserver, no Docker) and the app wired to it."""

import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pgserver
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.main import create_app
from tests.helpers import ADMIN, DEV_USER, IsolatedSettings

TABLES = "app.notes, app.notifications, app.role_assignments"


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    # Keep the path short: Postgres puts its Unix socket here, and socket paths max out at ~100 chars.
    pgdata = Path(tempfile.mkdtemp(prefix="pgtest-"))
    server = pgserver.get_server(pgdata, cleanup_mode="stop")
    try:
        server.psql("CREATE DATABASE app_test;")
        yield server.get_uri("app_test").replace("postgresql://", "postgresql+psycopg://", 1)
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
        llm_endpoint=None,
        mlflow_experiment_id=None,
        notification_webhook_url=None,
        static_dir=static_dir,
    )


@pytest.fixture(scope="session")
def app(settings: Settings) -> Iterator[FastAPI]:
    application = create_app(settings)
    with TestClient(application):  # runs startup: connects and applies the migrations
        yield application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    yield TestClient(app)
    app.dependency_overrides.clear()
    with app.state.engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY"))


@pytest.fixture
def sessions(app: FastAPI, client: TestClient) -> sessionmaker[Session]:
    """Session factory; depends on ``client`` so the tables are cleaned up afterwards."""
    factory: sessionmaker[Session] = app.state.sessionmaker
    return factory
