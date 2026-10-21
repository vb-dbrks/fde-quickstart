---
title: "0001: One app, agent in-process, split-ready"
sidebar_label: "0001: One app, in-process agent"
---

# 0001: One app, agent in-process, split-ready

**Status:** Accepted

## Context

An app and an agent have different release cycles, dependencies and scaling needs, and often
different teams. Running the agent as its own service makes that explicit, but it doubles what a new
project has to deploy, secure and monitor on day one: two apps, two sets of permissions, service
principal access between them.

## Decision

Ship one Databricks App. The agent runtime (`backend/agents/`) runs inside the app process and is
mounted behind the same HTTP contract a separate agent would serve. The app calls it through
`AgentClient` with `AGENT_TRANSPORT=inprocess`, which uses `httpx.ASGITransport`: every request is
serialised to JSON and validated exactly as it would be over the network.

Keep the runtime split-ready:

- `backend.agents` imports only `backend.contracts` (`tests/agents/test_boundary.py`).
- The runtime has its own settings (`backend/agents/config.py`) and its own FastAPI app
  (`create_agent_app`), so `make agent` serves it alone on :9000.
- `AGENT_TRANSPORT=http` with `AGENT_API_BASE` points the app at an agent deployed elsewhere.

## Consequences

- One deploy, one service principal, one set of logs to start with.
- The agent's thread pool shares the app's CPU and memory. Heavy or slow agents are a reason to split.
- Splitting later is configuration plus a second app resource, not a rewrite. See
  [Splitting the agent into its own app](../../guides/splitting-the-agent.md).
- The contract is exercised from the first day, including in tests and `make dev`.
