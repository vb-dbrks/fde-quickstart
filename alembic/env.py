"""Alembic environment.

Uses the sync connection handed over by backend.db.migrations.upgrade_connection. For CLI commands
such as ``alembic revision --autogenerate`` it connects with the app's settings (DATABASE_URL).
"""

import asyncio

from alembic import context
from sqlalchemy import Connection
from sqlalchemy.schema import CreateSchema

import backend.domain.models  # noqa: F401 - registers the tables on Base.metadata
from backend.db.base import APP_SCHEMA, Base
from backend.db.migrations import context_options


def run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata, **context_options())
    with context.begin_transaction():
        context.run_migrations()


def _create_schema_and_run(connection: Connection) -> None:
    connection.execute(CreateSchema(APP_SCHEMA, if_not_exists=True))
    run_migrations(connection)


async def _run_from_cli() -> None:
    from backend.db.session import create_db_engine
    from backend.settings import Settings

    engine = create_db_engine(Settings())
    try:
        async with engine.begin() as connection:
            await connection.run_sync(_create_schema_and_run)
    finally:
        await engine.dispose()


def main() -> None:
    if context.is_offline_mode():
        raise RuntimeError("Offline (SQL script) migrations are not supported.")
    connection = context.config.attributes.get("connection")
    if connection is not None:
        run_migrations(connection)
    else:
        asyncio.run(_run_from_cli())


main()
