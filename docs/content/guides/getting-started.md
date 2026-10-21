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
produce placeholder text. The Home page shows which runner serves each run kind.

To use a real model locally, set `DATABRICKS_CONFIG_PROFILE` (or `make dev PROFILE=<profile>`) and
`LLM_ENDPOINT` to a Model Serving endpoint in that workspace.

## Try the flow

1. **Documents → New brief**. Enter a title and a goal; you become the owner.
2. Create a second brief, then open the first and tick the second under **Sources**.
3. **Generate**. The steps tick off as the run progresses; the agent fields fill in with an
   **Agent** badge. **Why?** shows the confidence, the reasoning and the cited sources.
4. On a field, the sparkle button asks the agent for a revision. **Accept** writes it; **Dismiss**
   drops it.
5. **Assistant** tab: ask a question. The conversation is stored in Lakebase and private to you.
6. **History** tab: versions (one per generation) and the audit trail.
7. **Share** gives other people view, edit or owner access.

## Checks

```bash
make lint      # ruff, mypy (strict), ESLint, Prettier, tsc
make test      # pytest against real Postgres, and Vitest
make contract  # the contract, runtime and boundary tests only
make eval DEV=1  # the eval harness, offline with the fake agent
make docs      # this site on :3000
```

After changing API schemas or routes, run `make api-types` to regenerate
`frontend/src/api/schema.d.ts`; CI fails if it is stale.

## Settings

The app reads environment variables (and `.env` locally) through `backend/settings.py`; the agent
runtime has its own in `backend/agents/config.py`. The ones you are most likely to change:

| Variable | Default | Effect |
| --- | --- | --- |
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

- Start a new project from the template: follow the checklist in the README (`make init`, profiles,
  first deploy).
- Deploy: [Deploy and CI/CD](deploy-and-ci.md).
