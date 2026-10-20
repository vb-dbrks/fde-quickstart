from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi import FastAPI

from app import migrations
from app.db import Base


def test_models_match_the_migrations(app: FastAPI) -> None:
    """Fails when a model changed without a migration: run `make migration MSG=...`."""
    with app.state.engine.connect() as connection:
        context = MigrationContext.configure(connection, opts=migrations.context_options())
        assert compare_metadata(context, Base.metadata) == []


def test_upgrading_twice_is_a_no_op(app: FastAPI) -> None:
    migrations.upgrade(app.state.engine)
