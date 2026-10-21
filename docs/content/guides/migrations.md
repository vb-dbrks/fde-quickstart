---
title: Database migrations
---

# Database migrations

The schema is managed with Alembic. Migrations are in `alembic/versions/` at the repo root, and the
app applies them when it starts (ADR 0009). The first one, `v0001_baseline.py` (revision `0001`),
creates every table in the `app` schema.

## Changing the schema

1. Change the models in `backend/domain/models.py`.
2. Generate a migration:

   ```bash
   make migration MSG="add due date to documents"
   ```

   This upgrades your local database (the one `make dev` uses) to the current head, then autogenerates
   a revision from the difference between the models and that database. The new file is formatted
   with ruff.
3. Read the generated file. Autogenerate misses some changes (renames, server defaults, data) and
   guesses at others.
4. `make test`. `tests/backend/test_platform.py` fails when the models and the migrations differ, and
   checks that upgrading twice is a no-op.
5. Restart `make dev`, or deploy: the app migrates on startup.

## Rules of thumb

- Several app instances, or an old and a new version, may run against the same database during a
  deploy. Add columns as nullable or with a default; remove them in a later release.
- Keep data migrations in the same revision as the schema change they need, and make them safe to
  re-run.
- Adding a field to the field catalog needs no migration: fields are stored one row each.

## How startup migration works

`backend.db.migrations.upgrade` takes an advisory lock (`0x5AFE_D0C5`) so concurrent instances migrate
one at a time, creates the `app` schema if needed, and runs `alembic upgrade head` on that
connection. On Databricks Apps this runs as the app's service principal, which therefore owns the
schema and tables. Set `RUN_MIGRATIONS=false` to skip it, for example when another process migrates.

`alembic.ini` is used only by `make migration` and the Alembic CLI; the app doesn't read it.
