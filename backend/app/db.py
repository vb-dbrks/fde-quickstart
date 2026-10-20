"""Database engine, ORM base and sessions.

The app connects to Postgres in one of two ways:

* ``DATABASE_URL`` - any SQLAlchemy URL. `make dev` and the tests point it at a local pgserver instance.
* ``PG*`` variables - Lakebase. Databricks Apps injects PGHOST, PGDATABASE, PGUSER, ... for the app's
  ``postgres`` resource. The app signs in as its service principal with a Databricks OAuth token as the
  password. A token is fetched for each new connection; the SDK caches and refreshes it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Engine, MetaData, create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

if TYPE_CHECKING:
    from app.config import Settings

# The app's service principal creates, and therefore owns, this schema on first start (app.migrations).
APP_SCHEMA = "app"

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(schema=APP_SCHEMA, naming_convention=NAMING_CONVENTION)


def create_db_engine(settings: Settings) -> Engine:
    if settings.database_url:
        return create_engine(settings.database_url, pool_pre_ping=True)
    if settings.pghost and settings.pgdatabase and settings.pguser:
        return _create_lakebase_engine(settings)
    raise RuntimeError(
        "No database configured. Set DATABASE_URL, or deploy with a Lakebase `postgres` app resource "
        "(which provides PGHOST, PGDATABASE and PGUSER)."
    )


def _create_lakebase_engine(settings: Settings) -> Engine:
    from databricks.sdk import WorkspaceClient

    workspace = WorkspaceClient()
    url = URL.create(
        "postgresql+psycopg",
        username=settings.pguser,
        host=settings.pghost,
        port=settings.pgport,
        database=settings.pgdatabase,
        query={"sslmode": settings.pgsslmode, "application_name": settings.pgappname or "app"},
    )
    engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5, pool_recycle=3600)

    @event.listens_for(engine, "do_connect")
    def _use_oauth_token(dialect: Any, conn_rec: Any, cargs: Any, cparams: dict[str, Any]) -> None:
        cparams["password"] = workspace.config.oauth_token().access_token

    return engine


def create_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
