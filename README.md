# {{project_title}}

A quick-start for Databricks Apps engagements: a FastAPI backend and a React frontend in one app,
app state in Lakebase Postgres, deployed to dev/test/prod with Declarative Automation Bundles.
It ships with a permissions model, in-app notifications, an agent with an MLflow evaluation harness,
and CI/CD for GitHub Actions and GitLab.

| Layer | What you get |
| --- | --- |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 + psycopg 3, Alembic migrations run at startup |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, shadcn/ui (Radix), TanStack Query, React Router, API types generated from FastAPI |
| Data | Lakebase Postgres (one project per target); local dev and tests use real Postgres via pgserver, no Docker |
| Access | Databricks Apps sign-in, plus app roles (viewer, editor, admin) with permission checks in the API and the UI |
| Notifications | In-app inbox with a bell menu (polling), and a webhook channel for Slack-compatible hooks |
| Agents | OpenAI Agents SDK on a Databricks Model Serving endpoint, tools that act as the calling user, MLflow tracing |
| Evals | MLflow 3 `mlflow.genai.evaluate` with built-in judges and a custom scorer |
| Tooling | uv, ruff, mypy (strict), pytest, ESLint, Prettier, Vitest, one Makefile |
| CI/CD | GitHub Actions and GitLab CI: checks on every change, deploys with workload identity federation (no stored secrets) |

## Layout

```
├── app.yaml                 Databricks Apps start command and environment
├── databricks.yml           bundle: variables, sync rules, dev/test/prod targets
├── resources/               app, Lakebase project/role/database, MLflow experiment
├── backend/app/
│   ├── main.py              app factory; runs migrations on startup, serves the SPA
│   ├── config.py db.py      settings; engine with Lakebase OAuth token injection
│   ├── identity.py          user from the Databricks Apps proxy headers
│   ├── permissions/         roles → permissions, require() dependency, role grants
│   ├── notifications/       notify(), in-app and webhook channels
│   ├── agents/              agent protocol, tools, model client, example assistant, prompts
│   ├── routes/              /api: health, me, notes, notifications, admin, agents
│   ├── migrations/          Alembic
│   └── static/              built frontend (generated, not committed)
├── frontend/src/
│   ├── app/                 shell: sidebar, header, notification bell, user menu
│   ├── pages/               Home, Notes, Assistant, Users & roles, 404
│   ├── components/ui/       shadcn/ui components
│   ├── lib/                 typed API client, queries, permissions hook, theme
│   └── api/schema.d.ts      generated from the FastAPI schema (`make api-types`)
├── tests/                   pytest against real Postgres
├── evals/                   MLflow evaluation of the agent
├── scripts/                 init, local Postgres, dev server, lockfile helpers
├── .github/workflows/       CI and deploy (GitHub Actions)
└── .gitlab-ci.yml           CI and deploy (GitLab)
```

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 for you)
- Node.js 22.22 or later (CI uses 24, see `frontend/.nvmrc`)
- Databricks CLI 1.20 or later, signed in to each workspace with a named profile
- `make`

## New engagement checklist

1. **Create the repository** from this template, in the account or organisation the engagement uses
   (GitHub: *Use this template*, keep it private; GitLab: import the repository). Keep only the CI
   system you use: delete `.gitlab-ci.yml` or `.github/`.
2. **Fill in the placeholders.** The deployment files contain `{{project_name}}`-style placeholders;
   one command fills them in:

   ```bash
   make init NAME=claims-portal ADMINS=lead@example.com,dev@example.com \
     DEV_HOST=https://adb-1111.1.azuredatabricks.net LLM_ENDPOINT=databricks-claude-sonnet-5-5
   # later, once you have them:
   make init TEST_HOST=https://... PROD_HOST=https://...
   ```

   | Placeholder | Used for |
   | --- | --- |
   | `project_name` | bundle, app and Lakebase project names (3-20 characters: lowercase, digits, hyphens) |
   | `project_title` | UI title and README heading (defaults to the name in title case) |
   | `admin_emails` | users who are always admins, so someone can grant roles after the first deploy |
   | `dev_host`, `test_host`, `prod_host` | workspace URL per target |
   | `llm_endpoint` | Model Serving endpoint the agents call |

   `python3 scripts/init_project.py --check` lists anything still unset; `make deploy` refuses to
   run until everything is set.
3. **Set up CLI profiles**, one per workspace, for example
   `databricks auth login --host <dev-host> --profile claims-dev`. Every command that talks to a
   workspace takes `PROFILE=` explicitly; nothing uses the default profile, and each target pins its
   host, so a profile for the wrong workspace fails instead of deploying there.
4. **Choose the model endpoint**: `databricks serving-endpoints list --profile <profile>`. If the
   engagement has no LLM use case, remove the `llm-endpoint` and `experiment` resources from
   `resources/app.app.yml` and the matching entries in `app.yaml`.
5. **Secrets.** None are needed to start: the app reaches Lakebase and Model Serving as its own
   service principal. For third-party credentials, create a secret scope and add a `secret` app
   resource (example in `resources/app.app.yml`). Never commit `.env`.
6. **Install and check**: `make setup lint test`.
7. **First deploy**: `make deploy TARGET=dev PROFILE=<profile>`. It builds the frontend, validates the
   bundle in strict mode, creates the Lakebase project, the app and the experiment, and starts the
   app; on first start the app creates and owns its `app` schema. Check it with
   `databricks apps get <name> --profile <profile>` (the `url` field) and
   `databricks apps logs <name> --profile <profile>`.
8. **Grant roles**: an admin opens *Users & roles* in the app. Who can open the app at all is
   controlled by the `app_users_group` bundle variable (default: `users`).
9. **Set up CI/CD** (below) for test and prod.
10. **Replace the sample**: `notes` (model, routes, page, tests) shows the full round trip. Rename or
    delete it once your own feature exists.

## Everyday commands

| Command | What it does |
| --- | --- |
| `make dev` | API with auto-reload on :8000 and Vite on :5173, against a local Postgres. Optional `PROFILE=` and `LLM_ENDPOINT=` to use the agent |
| `make lint` / `make fmt` | ruff, mypy, ESLint, Prettier, tsc / auto-fix and format |
| `make test` | pytest (real Postgres via pgserver) and Vitest |
| `make build` | build the frontend into `backend/app/static` |
| `make api-types` | regenerate `frontend/src/api/schema.d.ts` after changing API models or routes |
| `make migration MSG="..."` | generate an Alembic migration from model changes |
| `make deploy TARGET= PROFILE=` | build, validate and deploy a target, then start the app |
| `make destroy TARGET= PROFILE=` | delete a target's resources (asks to confirm; prod's database is protected) |
| `make eval PROFILE= LLM_ENDPOINT=` | evaluate the agent with MLflow in that workspace |
| `make lock` | update `uv.lock` and `package-lock.json` (public registry URLs only) |

## How it fits together

**Identity and permissions.** Databricks Apps signs users in and passes their identity to the app in
`X-Forwarded-*` headers (`backend/app/identity.py`). Roles are named sets of permissions defined in
`backend/app/permissions/roles.py`; assignments are rows in Lakebase. Everyone who can open the app
has the default role (viewer); the emails in `admin_emails` are always admins. Routes declare what
they need with `require(Permission.X)`, and `GET /api/me` gives the UI the same permissions for
`usePermissions()`, `<Can>` and `<RequirePermission>`. To add a permission: add it to `Permission`,
give it to roles, check it in a route, then run `make api-types`.

**Lakebase.** The bundle creates a Lakebase project per target with a database the app can connect
to (`CAN_CONNECT_AND_CREATE`). The app connects as its service principal with a short-lived OAuth
token (`backend/app/db.py`) and runs the migrations on startup under an advisory lock, so it creates
and owns the `app` schema. Deploy before pointing a local `make dev` at Lakebase; a schema created by
your own user would not be accessible to the app.

**Notifications.** `Notifier.notify()` writes to the in-app inbox and to any outbound channels
(`backend/app/notifications/channels.py`). Granting a role notifies the user, as an example. The UI
polls every 30 seconds: the Apps proxy buffers server-sent events and ends requests after 120 seconds.

**Agents.** `backend/app/agents/` holds the agents served at `/api/agents/{name}/invoke`. The example
assistant uses the OpenAI Agents SDK with a Databricks Model Serving endpoint; its tools run as the
calling user and check the same permissions as the API. `agents/llm.py` adapts Databricks responses the
SDK can't read (reasoning models can return message content as a list of parts), so keep it when
switching models. Traces go to the target's MLflow experiment.
Replies must arrive within the proxy's 120-second limit. Add an agent by copying `assistant.py`, adding
a prompt in `prompts/` and registering it in `registry.py`. Keep the package inside `app`: a top-level
`agents` package would shadow the SDK, which is also imported as `agents`.

**Evals.** `make eval` runs the assistant locally against a seeded throwaway Postgres, calls the model
endpoint in the profile's workspace, and scores the answers with MLflow's built-in judges and the
scorers in `evals/scorers.py`. Grow `evals/dataset.jsonl` from real questions.

**Frontend.** Vite builds into `backend/app/static`, which FastAPI serves with client-side routing, so
the UI and API share one origin and one app. The API client (`frontend/src/lib/api.ts`) is typed from
the backend's OpenAPI schema; CI fails if the generated types are stale. Add a page in
`frontend/src/pages/`, then register it in `routes.tsx` and `app/nav.ts`.

## CI/CD

Both pipelines run ruff, mypy, pytest, ESLint, tsc, Vitest, a frontend build, a lockfile check and an
API-types check on every change. Deploys run `make ci-deploy TARGET=<target>`: pushes to the default
branch deploy dev; test and prod are deployed by hand (a manual job or workflow run).

Deploys sign in as a service principal through **workload identity federation**: the pipeline's OIDC
token is exchanged for a Databricks token, so no Databricks secret is stored in CI. For each workspace:

1. Create a service principal for the pipeline (account console or
   `databricks account service-principals create`), add it to the workspace, and allow it to create
   apps, Lakebase projects and MLflow experiments there. The deploying principal owns the deployed
   resources.
2. Create a federation policy for it (account admin):

   ```bash
   databricks account service-principal-federation-policy create <service-principal-id> \
     --profile <account-profile> --json '{"oidc_policy": {
       "issuer": "https://token.actions.githubusercontent.com",
       "audiences": ["<databricks-account-id>"],
       "subject": "repo:<org>/<repo>:environment:prod"}}'
   ```

   - **GitHub**: one policy per environment (`dev`, `test`, `prod`). GitHub repositories created
     after 15 July 2026 use numeric IDs in the subject (`repo:<org>@<org-id>/<repo>@<repo-id>:environment:prod`).
   - **GitLab**: issuer `https://gitlab.com` (or your GitLab URL) and subject
     `project_path:<group>/<project>:ref_type:branch:ref:main`.
3. Configure the pipeline:
   - **GitHub**: create environments `dev`, `test` and `prod` (add required reviewers to `prod`) with
     the variables `DATABRICKS_HOST` and `DATABRICKS_CLIENT_ID` (the service principal's application
     ID).
   - **GitLab**: set `DATABRICKS_ACCOUNT_ID`, and `DATABRICKS_HOST` and `DATABRICKS_CLIENT_ID` scoped
     to the `dev`, `test` and `prod` environments. Protect the `prod` environment.
4. Turn deploys on with the variable `DEPLOY_ENABLED=true` (GitHub: a repository variable; GitLab: a
   CI/CD variable). Until then only the checks run, so a new repository's first push stays green.

If federation is not available, use OAuth machine-to-machine credentials instead: set
`DATABRICKS_CLIENT_SECRET` as a masked, protected secret and drop `DATABRICKS_AUTH_TYPE` from the
workflow.

## Lockfiles and package mirrors

CI and Databricks Apps install from `uv.lock` and `frontend/package-lock.json`, so both must point at
the public registries. `frontend/.npmrc` keeps registry URLs out of the npm lockfile.
`scripts/relock.sh` (used by `make lock`) locks through a PyPI mirror when pypi.org is unreachable and
rewrites the mirror's URLs to public PyPI. `scripts/check_lockfiles.sh` fails CI if a mirror URL slips
in. Set `PYPI_MIRROR` if your mirror is not the default one in the script.

## Things to know

- **Python 3.12** comes from uv: with `pyproject.toml` and `uv.lock` (and no `requirements.txt`),
  Databricks Apps installs with uv and uses `requires-python`. If a workspace cannot download Python
  3.12 at deploy time (restricted egress), switch to the runtime's built-in 3.11: set
  `requires-python = ">=3.11,<3.12"` and `.python-version` to `3.11`, then run `make lock`.
- **The dev target is shared.** Development mode does not make the app or Lakebase project names
  per-user, so one person (or CI) deploys dev in a workspace.
- **Lakebase vs. local Postgres**: Lakebase runs Postgres 17, pgserver runs 16. Avoid 17-only features
  or test them against a dev deployment.
- **Request time limit**: the Apps proxy ends requests after 120 seconds, without an error in the app
  logs. Keep agent turns short, or move long work to a Lakeflow job.
- **Egress**: the app needs PyPI (or `UV_INDEX_URL`) at deploy time, and the webhook channel needs
  the webhook host.
