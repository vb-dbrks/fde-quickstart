---
title: "0006: A fake agent for parallel work"
sidebar_label: "0006: Fake agent"
---

# 0006: A fake agent for parallel work

**Status:** Accepted

## Context

App and UI work needs agent responses long before the real agent is good, and tests need responses
that are fast and the same every time. Calling a model in tests is slow, costs money and is not
deterministic.

## Decision

Ship a deterministic fake agent (`backend/agents/fake/runner.py`) that implements the same contract:
the same models, step names, field catalog rules and citation rules. It drafts every requested field,
cites the first source document, and echoes chat messages.

- It is the default when `LLM_ENDPOINT` is unset; `AGENT_RUNNER` and `AGENT_RUNNER_OVERRIDES` choose
  per run kind.
- Knobs: `FAKE_AGENT_STEP_SECONDS` (pause per step), `FAKE_AGENT_FAIL_AT` (fail at a step),
  `FAKE_AGENT_VERSION`, `FAKE_AGENT_DRIFT` (prefix outputs).
- Tests and `make eval DEV=1` use it; `make dev` uses it until an endpoint is configured.

## Consequences

- The UI, materialisation and failure handling can be built and tested before any prompt exists.
- The fake must change with the contract, in the same pull request.
- Fake output says it is fake ("drafted by the fake agent"), so it is never mistaken for real output.
