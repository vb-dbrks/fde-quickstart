---
title: Getting started
---

# Getting started

## Prerequisites

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node.js 22.22 or later (`frontend/.nvmrc`)
- The Databricks CLI, for deploying. Every workspace command takes an explicit `PROFILE`; nothing
  uses the default profile.

## Run it locally

```bash
make setup     # Python and Node dependencies from the lockfiles
cp .env.example .env   # optional: your email, admin rights, agent settings
make dev       # Postgres (pgserver), the API on :8000 with reload, Vite on :5173
```

Open http://localhost:5173. `make dev` starts a local Postgres with no Docker and keeps it running
between sessions; `make db-stop` stops it. The app migrates it on startup.

Off Databricks there is no sign-in proxy, so every request runs as `DEV_USER_EMAIL`. Make that user an
admin with `APP_ADMIN_EMAILS` in `.env`; otherwise it is only a viewer and can't create documents.

Without `LLM_ENDPOINT` the agent is the fake one, in-process: runs take about a second per step and
produce placeholder text. The home page is an example selector. Agent descriptors are available from `/api/agents`.

To use a real model locally, set `DATABRICKS_CONFIG_PROFILE` (or `make dev PROFILE=<profile>`) and
`LLM_ENDPOINT` to a Model Serving endpoint in that workspace.

## Choose and adapt an example

The home page explains three patterns. Chat and Generation work without creating a document.
Document generation now produces proposals: accept selected fields or all remaining fields explicitly.

1. Choose examples with `ENABLED_EXAMPLES=chat,generation,documents` (use the same setting for a split runtime).
2. Replace the example input/output schemas and prompts.
3. Register agent capabilities and application callbacks.
4. Customize pages with shared chat, progress, structured-result and review primitives.
5. Deploy with a named Databricks profile.

Use [the extension recipes](agentic-applications.md) for each step.

## Settings

The app reads environment variables (and `.env` locally) through `backend/settings.py`; the agent
runtime has its own in `backend/agents/config.py`. The ones you are most likely to change:

| Variable | Default | Effect |
| --- | --- | --- |
| `ENABLED_EXAMPLES` | `chat,generation,documents` | Independently enabled example registrations and routes. |
| `APP_ADMIN_EMAILS` | (none) | Comma-separated emails that are always admins. |
| `DEV_USER_EMAIL` | `dev.user@example.com` | Who you are off-platform. |
| `LLM_ENDPOINT` | (none) | Model Serving endpoint; when set, runners default to `real`. |
| `AGENT_RUNNER`, `AGENT_RUNNER_OVERRIDES` | (auto) | `fake` or `real`, globally or per run kind. |
| `AGENT_TRANSPORT`, `AGENT_API_BASE` | `inprocess` | `http` calls an agent elsewhere. |
| `AGENT_RUN_TIMEOUT_SECONDS` | 600 | Runs still going after this fail with `TIMEOUT`. |
| `POLLER_ENABLED`, `POLLER_INTERVAL_SECONDS` | true, 10 | The background run poller. |
| `ASSISTANT_HISTORY_LIMIT` | 20 | Chat messages sent with each assistant turn. |
| `NOTIFICATION_WEBHOOK_URL` | (none) | Also send notifications to a Slack-compatible webhook. |
| `MLFLOW_EXPERIMENT_ID` | (none) | Trace every run to this experiment. |

## Next

- Start a new project from the template: follow **Make it yours** in the README (`make init`, your
  document types, the agent's prompts, the first deploy).
- Working with an AI coding assistant: point it at `AGENTS.md` at the repo root - the commands, the
  rules that keep the design intact, and recipes for common changes.
- Deploy: [Deploy and CI/CD](deploy-and-ci.md).
