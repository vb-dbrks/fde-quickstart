---
title: Fake agent and parallel work
---

# Fake agent and parallel work

The fake agent (`backend/agents/fake/runner.py`) implements the whole contract with deterministic
output: every requested field drafted from the document's title, citations of the first source
document, chat answers that echo the message. It uses the real step names and passes the same output
checks as the real runners.

## Choosing a runner

| Setting | Effect |
| --- | --- |
| (nothing) | `real` if `LLM_ENDPOINT` is set, otherwise `fake`, for every run kind. |
| `AGENT_RUNNER=fake` or `real` | The same runner for every run kind. `real` needs `LLM_ENDPOINT`. |
| `AGENT_RUNNER_OVERRIDES=assistant_turn=real,generate=fake` | Per run kind; wins over `AGENT_RUNNER`. |

The Home page and `GET /api/health` show the choice per run kind.

## Knobs

| Variable | Default | Effect |
| --- | --- | --- |
| `FAKE_AGENT_STEP_SECONDS` | 1.0 | Pause per step, so progress is visible in the UI. Tests use 0. |
| `FAKE_AGENT_FAIL_AT` | (none) | A step name, e.g. `drafting_fields`. Runs fail there with `MODEL_ERROR`. |
| `FAKE_AGENT_VERSION` | `fake-agent` | Reported as `output.meta.agent_version`. |
| `FAKE_AGENT_DRIFT` | (empty) | Prefixed to every generated string, so outputs differ from stored ones on replay. |

## Working in parallel

The two halves meet at `contracts/agent-api-contract.md`. Agree changes there first.

**App and UI work** runs against the fake, in-process:

```bash
make dev
```

Use `FAKE_AGENT_FAIL_AT` to build the failure states, and a larger `FAKE_AGENT_STEP_SECONDS` to work on
progress and resuming after a reload.

**Agent work** runs the runtime on its own and checks it against the contract:

```bash
make agent PROFILE=<profile> LLM_ENDPOINT=<endpoint>   # the runtime alone on :9000
make contract-live AGENT_API_BASE=http://localhost:9000
make eval PROFILE=<profile> LLM_ENDPOINT=<endpoint>
```

`make contract-live` checks the contract version and vocabulary, runs every run kind to completion and
validates the output, and checks that unknown runs answer `RUN_NOT_FOUND`.

**Both together**: point the app at the separately running agent.

```bash
make agent
AGENT_TRANSPORT=http AGENT_API_BASE=http://localhost:9000 make dev
```

This is the same path a split deployment takes. See
[Splitting the agent into its own app](splitting-the-agent.md).
