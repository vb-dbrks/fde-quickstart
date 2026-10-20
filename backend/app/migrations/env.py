"""Alembic environment.

Uses the connection handed over by app.migrations.upgrade. For CLI commands such as
``alembic revision --autogenerate`` it connects with the app's settings (DATABASE_URL) instead.
"""

from alembic import context
from sqlalchemy import Connection
from sqlalchemy.schema import CreateSchema

import app.models  # noqa: F401 - registers the tables on Base.metadata
from app.db import APP_SCHEMA, Base
from app.migrations import context_options


def run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata, **context_options())
    with context.begin_transaction():
        context.run_migrations()


def main() -> None:
    if context.is_offline_mode():
        raise RuntimeError("Offline (SQL script) migrations are not supported.")
    connection = context.config.attributes.get("connection")
    if connection is not None:
        run_migrations(connection)
        return

    from app.config import Settings
    from app.db import create_db_engine

    with create_db_engine(Settings()).begin() as cli_connection:
        cli_connection.execute(CreateSchema(APP_SCHEMA, if_not_exists=True))
        run_migrations(cli_connection)


main()
