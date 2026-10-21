"""Alembic migrations (alembic/ at the repo root), applied when the app starts.

Running them as the app - its service principal on Databricks Apps - means the app creates and owns
its schema and tables in Lakebase. New migration: `make migration MSG="describe the change"`.
"""

from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.schema import CreateSchema

from backend.db.base import APP_SCHEMA

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


async def upgrade(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(upgrade_connection)
