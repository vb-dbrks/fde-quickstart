---
title: "0009: Migrations run at startup"
sidebar_label: "0009: Migrations at startup"
---

# 0009: Migrations run at startup

**Status:** Accepted

## Context

On Databricks Apps, the app connects to Lakebase as its service principal, which the bundle grants
`CAN_CONNECT_AND_CREATE` on the database. A schema created by a person would be owned by that person,
and the app could not change it. A separate migration job would need its own credentials and ordering
with the deploy.

## Decision

The app applies Alembic migrations when it starts (`backend/db/migrations.py`), before serving
requests:

1. Take a transaction-level advisory lock (`pg_advisory_xact_lock(0x5AFE_D0C5)`), so instances that
   start together migrate one at a time.
2. Create the `app` schema if it doesn't exist.
3. Run `alembic upgrade head` on the same connection.

The service principal therefore creates and owns the schema and every table. Migrations live in
`alembic/` at the repo root; `make migration MSG="..."` autogenerates a new one against a local
database. `RUN_MIGRATIONS=false` turns this off.

## Consequences

- A deploy is one step; the schema always matches the code that is running.
- Migrations must be safe to run while an older instance still serves traffic: add before you remove.
- `tests/backend/test_platform.py` fails when the models and the migrations differ, and checks that a
  second upgrade is a no-op.
- To query the tables yourself, have the app's service principal grant you access, or deploy before
  pointing `make dev` at the Lakebase database.
