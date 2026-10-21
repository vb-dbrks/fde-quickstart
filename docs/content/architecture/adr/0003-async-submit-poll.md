---
title: "0003: Async submit, then poll"
sidebar_label: "0003: Async submit/poll"
---

# 0003: Async submit, then poll

**Status:** Accepted

## Context

Agent runs take seconds to minutes. The Databricks Apps proxy times requests out after 120 seconds
and buffers streamed responses, so neither a long synchronous call nor server-sent events is
reliable. Users close tabs mid-run; app instances restart.

## Decision

- `POST /agent/run` returns at once with `accepted`. The caller polls `GET /agent/run/{id}` until the
  status is `succeeded` or `failed`. `step_history` reports progress with names from a fixed
  vocabulary per run kind.
- The app records the run before submitting, so it exists even if the submit fails.
- The UI polls the app (`GET /api/agent-runs/{id}`), starting at 1.5 seconds and backing off to 10.
  Each poll refreshes the run from the agent (lazy refresh).
- A background poller in the app refreshes runs nobody is watching, so every run reaches a terminal
  state and is materialised.
- Refreshing locks the run row and materialisation is guarded by `materialised_at`, so concurrent
  pollers are safe.
- The app fails runs that stay `queued` (`ORPHANED`), run too long (`TIMEOUT`), or that the agent no
  longer knows (`AGENT_RUN_LOST`).

## Consequences

- No request outlives the proxy timeout, and progress works without streaming.
- Polling costs a few small requests per run; the backoff keeps that low.
- An agent restart loses in-flight runs. They fail with a code that tells the user to try again.
