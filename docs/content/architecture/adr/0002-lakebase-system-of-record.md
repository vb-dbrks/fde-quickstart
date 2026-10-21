---
title: "0002: Lakebase is the system of record"
sidebar_label: "0002: Lakebase as system of record"
---

# 0002: Lakebase is the system of record

**Status:** Accepted

## Context

The app needs transactional state: documents edited by people and agents, who may see what, a history
of every change, and the runs that produced agent-written values. It needs row-level updates, locks
and constraints, with low latency for an interactive UI.

## Decision

Keep all app state in Lakebase Postgres, one project per bundle target (`resources/lakebase.postgres.yml`),
in the `app` schema. Only the app writes to it.

- Documents are stored one row per field (`document_fields`), keyed by the paths in
  `contracts/field-catalog.yaml`, with the provenance of agent-written values.
- Every agent run is mirrored in `agent_runs`, with the exact request and final response.
- Changes are audited (`audit_log`) and agent generations are versioned (`document_versions`).
- Locally and in tests, the same code runs against real Postgres from pgserver, with no Docker.

## Consequences

- One place answers "what is the current value, who set it, and why".
- Runs can be replayed from `agent_runs.request_payload`.
- The app connects as its service principal with an OAuth token fetched per connection
  (`backend/db/session.py`); there is no password to manage.
- Analytics on this data belongs in the lakehouse (for example Lakebase synced tables), not in
  queries against the app's database.
