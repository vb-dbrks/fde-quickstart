"""Alembic migrations, applied when the app starts.

Running them as the app (its service principal on Databricks Apps) means the app creates - and owns -
its schema and tables in Lakebase. New migration: `make migration MSG="describe the change"`.
"""

from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.schema import CreateSchema

from app.db import APP_SCHEMA

MIGRATIONS_DIR = Path(__file__).parent
# Arbitrary constant. Serialises migrations when several app instances start at the same time.
ADVISORY_LOCK_KEY = 0x5AFE_D0C5


def include_name(name: str | None, type_: str, parent_names: Any) -> bool:
    # Autogenerate compares the app's own schema only.
    if type_ == "schema":
        return name == APP_SCHEMA
    return True


def context_options() -> dict[str, Any]:
    """Alembic context options, shared by env.py and the models-match-migrations test."""
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


def upgrade(engine: Engine) -> None:
    """Create the app schema if needed and apply all pending migrations."""
    config = alembic_config()
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": ADVISORY_LOCK_KEY})
        connection.execute(CreateSchema(APP_SCHEMA, if_not_exists=True))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
