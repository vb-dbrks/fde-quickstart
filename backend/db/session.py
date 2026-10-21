"""Async database engine and sessions.

The app connects to Postgres in one of two ways:

* ``DATABASE_URL`` - any Postgres URL. `make dev` and the tests point it at a local pgserver instance.
* ``PG*`` variables - Lakebase. Databricks Apps injects PGHOST, PGDATABASE, PGUSER, ... for the app's
  ``postgres`` resource. The app signs in as its service principal with a Databricks OAuth token as
  the password. A token is fetched for each new connection; the SDK caches and refreshes it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

if TYPE_CHECKING:
    from backend.settings import Settings

ASYNC_DRIVER = "postgresql+psycopg"


def create_db_engine(settings: Settings) -> AsyncEngine:
    if settings.database_url:
        url = make_url(settings.database_url)
        if url.drivername in ("postgresql", "postgres"):
            url = url.set(drivername=ASYNC_DRIVER)
        return create_async_engine(url, pool_pre_ping=True)
    if settings.pghost and settings.pgdatabase and settings.pguser:
        return _create_lakebase_engine(settings)
    raise RuntimeError(
        "No database configured. Set DATABASE_URL, or deploy with a Lakebase `postgres` app resource "
        "(which provides PGHOST, PGDATABASE and PGUSER)."
    )


def _create_lakebase_engine(settings: Settings) -> AsyncEngine:
    from databricks.sdk import WorkspaceClient

    workspace = WorkspaceClient()
    url = URL.create(
        ASYNC_DRIVER,
        username=settings.pguser,
        host=settings.pghost,
        port=settings.pgport,
        database=settings.pgdatabase,
        query={"sslmode": settings.pgsslmode, "application_name": settings.pgappname or "app"},
    )
    engine = create_async_engine(
        url, pool_pre_ping=True, pool_size=5, max_overflow=5, pool_recycle=3600
    )

    @event.listens_for(engine.sync_engine, "do_connect")
    def _use_oauth_token(dialect: Any, conn_rec: Any, cargs: Any, cparams: dict[str, Any]) -> None:
        cparams["password"] = workspace.config.oauth_token().access_token

    return engine


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
