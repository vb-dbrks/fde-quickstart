"""Alembic migrations (alembic/ at the repo root), applied when the app starts.

Running them as the app - its service principal on Databricks Apps - means the app creates and owns
its schema and tables in Lakebase. New migration: `make migration MSG="describe the change"`.
"""

from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.schema import CreateSchema

from backend.db.base import APP_SCHEMA, Base
from backend.domain import models  # noqa: F401 - registers the tables for check_tables

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "alembic"
# Arbitrary constant. Serialises migrations when several app instances start at the same time.
ADVISORY_LOCK_KEY = 0x5AFE_D0C5


def include_name(name: str | None, type_: str, parent_names: Any) -> bool:
    # Autogenerate compares the app's own schema only.
    if type_ == "schema":
        return name == APP_SCHEMA
    return True


def context_options() -> dict[str, Any]:
    """Alembic context options, shared by alembic/env.py and the models-match-migrations test."""
    return {
        "version_table_schema": APP_SCHEMA,
        "include_schemas": True,
        "include_name": include_name,
        "compare_type": True,
    }


def alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


def upgrade_connection(connection: Connection) -> None:
    """Create the schema if needed and apply all pending migrations on a sync connection."""
    connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": ADVISORY_LOCK_KEY})
    connection.execute(CreateSchema(APP_SCHEMA, if_not_exists=True))
    config = alembic_config()
    config.attributes["connection"] = connection
    command.upgrade(config, "head")
    check_tables(connection)


def check_tables(connection: Connection) -> None:
    """Fail at startup if a table the models need is missing after migrating.

    Alembic trusts the revision stamped in ``alembic_version``. A database created by another app, or
    by an earlier template with different migrations under the same revision ids, looks up to date
    while lacking tables - and would only fail later, on the first request that touches them.
    """
    expected = {t.name for t in Base.metadata.tables.values() if t.schema == APP_SCHEMA}
    missing = sorted(expected - set(inspect(connection).get_table_names(schema=APP_SCHEMA)))
    if missing:
        raise RuntimeError(
            f"The '{APP_SCHEMA}' schema is at the latest migration but is missing tables: "
            f"{', '.join(missing)}. It was probably created by a different app or an earlier "
            "version of this template. Point the app at a new database (or drop the schema)."
        )


async def upgrade(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(upgrade_connection)
