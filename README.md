# {{project_title}}

A quick-start for Databricks Apps engagements: a FastAPI backend and a React frontend in one app,
Lakebase Postgres as the system of record, and a **stateless agent** behind a versioned async
submit/poll contract. Deployed to dev/test/prod with Declarative Automation Bundles, with CI/CD for
GitHub Actions and GitLab.

The app owns all state. For every agent run it sends the agent the full context (the document's
fields, the source documents the user picked, the recent conversation), polls the run, and
materialises the result in Lakebase - fields with provenance, a version snapshot and an audit trail -
in one transaction. The agent keeps nothing between runs. A deterministic **fake agent** speaks the
same contract, so app and agent work proceed in parallel.

| Layer | What you get |
| --- | --- |
| Backend | Python 3.12, FastAPI, async SQLAlchemy 2 + psycopg 3, Alembic migrations run at startup |
| Agent | LangChain on `ChatDatabricks` with structured output, MLflow tracing; runs in-process behind the HTTP contract and splits into its own app with one setting |
| Contract | Golden-record Markdown (`contracts/agent-api-contract.md`), frozen Pydantic models, a field catalog, tests that validate every example |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, shadcn/ui (Radix), TanStack Query, React Router, API types generated from FastAPI |
| Data | Lakebase Postgres (one project per target); local dev and tests use real Postgres via pgserver, no Docker |
| Access | Databricks Apps sign-in, app roles (viewer, editor, admin) and per-document sharing (view, edit, owner) |
| Notifications | In-app inbox with a bell menu (polling), and a webhook channel for Slack-compatible hooks |
| Evals | MLflow 3 `mlflow.genai.evaluate` with LLM judges and deterministic scorers; offline mode with the fake agent |
| Docs | Docusaurus site in `docs/`: architecture, nine ADRs and guides |
| Tooling | uv, ruff, mypy (strict), pytest, ESLint, Prettier, Vitest, one Makefile |
| CI/CD | GitHub Actions and GitLab CI: checks on every change, deploys with workload identity federation (no stored secrets) |

## Layout

```
├── app.yaml                     Databricks Apps start command and environment
├── databricks.yml               bundle: variables, sync rules, dev/test/prod targets
├── resources/                   app, Lakebase project/role/database, MLflow experiment
├── contracts/
│   ├── agent-api-contract.md    golden record: endpoints, envelopes, run kinds, steps, errors, examples
│   └── field-catalog.yaml       document types and fields; which fields the agent writes
├── backend/                     the app, run as `python -m backend`
│   ├── main.py                  lifespan: migrations, agent client, poller; serves the SPA
│   ├── api/                     /api routes: documents, agent-runs, threads, notifications, admin
│   ├── services/                agent client + payload builder, run lifecycle, materialise, documents
│   ├── db/ domain/              engine (Lakebase OAuth token per connection), models, schemas
│   ├── auth/                    identity from the Apps proxy, roles, per-document access
│   ├── middleware/ workers/     Idempotency-Key handling; background run poller
│   ├── contracts/               contract models + catalog loader (shared by app and agent)
│   ├── agents/                  the agent: server, runtime, LangChain runners, prompts, fake agent
│   └── static/                  built frontend (generated, not committed)
├── alembic/  alembic.ini        migrations (baseline 0001)
├── frontend/src/
│   ├── pages/                   Home, Documents, document workspace, Users & roles
│   ├── components/documents/    field cards, run progress, provenance, assistant, history, sharing
│   ├── lib/                     typed API client, queries, useAgentRun polling hook, permissions
│   └── api/schema.d.ts          generated from the FastAPI schema (`make api-types`)
├── tests/                       backend/ (real Postgres), agents/, contracts/
├── evals/                       MLflow evaluation of the agent
├── docs/                        documentation site (`make docs`)
├── scripts/                     init, local Postgres, dev server, lockfile helpers
├── .github/workflows/           CI and deploy (GitHub Actions)
└── .gitlab-ci.yml               CI and deploy (GitLab)
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
   | `llm_endpoint` | Model Serving endpoint the agent calls |

   `python3 scripts/init_project.py --check` lists anything still unset; `make deploy` refuses to
   run until everything is set.
3. **Set up CLI profiles**, one per workspace, for example
   `databricks auth login --host <dev-host> --profile claims-dev`. Every command that talks to a
   workspace takes `PROFILE=` explicitly; nothing uses the default profile, and each target pins its
   host, so a profile for the wrong workspace fails instead of deploying there.
4. **Choose the model endpoint**: `databricks serving-endpoints list --profile <profile>`. Until it is
   available, deploy with the fake agent (uncomment `AGENT_RUNNER: fake` in `app.yaml`).
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
10. **Replace the sample.** The `brief` document type shows the whole loop. Model your domain in
    `contracts/field-catalog.yaml` first (docs: *Adding a document type*), agree changes to the
    contract in `contracts/agent-api-contract.md`, then build app and agent in parallel.

## Everyday commands

| Command | What it does |
| --- | --- |
| `make dev` | API with auto-reload on :8000 and Vite on :5173, against a local Postgres, with the fake agent in-process. `LLM_ENDPOINT=` and `PROFILE=` switch to the real agent |
| `make agent` | the agent on its own on :9000; then `make dev` with `AGENT_TRANSPORT=http AGENT_API_BASE=http://localhost:9000` |
| `make lint` / `make fmt` | ruff, mypy, ESLint, Prettier, tsc / auto-fix and format |
| `make test` | pytest (real Postgres via pgserver) and Vitest |
| `make contract` | the contract tests only: golden record, catalog, runtime, boundary |
| `make contract-live AGENT_API_BASE=` | check a running agent against the contract over HTTP |
| `make eval DEV=1` | evaluate offline with the fake agent and the deterministic scorers |
| `make eval PROFILE= LLM_ENDPOINT=` | evaluate the real agent with MLflow judges in that workspace |
| `make build` | build the frontend into `backend/static` |
| `make api-types` | regenerate `frontend/src/api/schema.d.ts` after changing API models or routes |
| `make migration MSG="..."` | generate an Alembic migration from model changes |
| `make docs` / `make docs-build` | serve the documentation site on :3000 / build it (fails on broken links) |
| `make deploy TARGET= PROFILE=` | build, validate and deploy a target, then start the app |
| `make destroy TARGET= PROFILE=` | delete a target's resources (asks to confirm; prod's database is protected) |
| `make lock` | update `uv.lock` and the npm lockfiles (public registry URLs only) |

## How it fits together

The documentation site (`make docs`) covers each part in depth; the ADRs explain the decisions.

**The handoff.** `POST /api/documents/{id}/agent-runs` (`generate`, `enhance_field` or
`assistant_turn`) checks permissions, builds the full request from Lakebase
(`backend/services/agent_payload_builder.py`), stores it in `agent_runs` as `queued`, and submits it.
The agent answers `accepted` at once and works in the background, recording each step.
`GET /api/agent-runs/{id}` polls the agent while the run is in progress (lazy refresh); a background
poller finishes runs nobody is watching. On the first `succeeded`, `backend/services/materialise.py`
validates the output against the field catalog and writes fields, provenance, a version and audit rows
in one transaction, guarded by `materialised_at` under `SELECT ... FOR UPDATE`. Enhance runs return a
suggestion that only lands when the user accepts it; assistant turns append to the thread. Runs that
fail, time out or are lost (the agent restarted) end as `failed` with a code, and notify the user.

**The agent.** `backend/agents/` imports nothing from the app except `backend.contracts` (a test
enforces it): no database, no sessions. `AGENT_TRANSPORT=inprocess` (the default) mounts it in the
app's process and still goes through HTTP serialisation and contract validation via
`httpx.ASGITransport`; `AGENT_TRANSPORT=http` with `AGENT_API_BASE` calls it as its own app, with the
app's service-principal token. Each run kind has a LangChain runner (a prompt and `ChatDatabricks`
with the output schema offered as a tool, see `structured()` in `backend/agents/runners/_common.py`:
newer Claude models reject LangChain's forced structured output) and a fake runner; `AGENT_RUNNER` and
`AGENT_RUNNER_OVERRIDES` pick per run kind. `FAKE_AGENT_STEP_SECONDS`, `FAKE_AGENT_FAIL_AT`,
`FAKE_AGENT_VERSION` and `FAKE_AGENT_DRIFT` make the fake slow, failing or visibly different.

**The contract.** `contracts/agent-api-contract.md` is the golden record that app and agent teams
agree on: endpoints, envelopes, step vocabulary, error codes and JSON examples. The Pydantic models in
`backend/contracts/agent_contract_v1.py` implement it, and `tests/contracts/` validates every example
in the document, so the two can't drift apart. Breaking changes mean a new version (`v2`).

**Identity and permissions.** Databricks Apps signs users in and passes their identity in
`X-Forwarded-*` headers (`backend/auth/identity.py`). Roles are named sets of permissions in
`backend/auth/roles.py`; everyone has the default role (viewer), and the emails in `admin_emails` are
always admins. On top of that, each document has an access list: its creator is the owner and can
share it with view or edit access. Documents you can't see answer 404; actions your access doesn't
allow answer 403. `GET /api/me` gives the UI the same permissions for `<Can>` and
`<RequirePermission>`.

**Lakebase.** The bundle creates a Lakebase project per target with a database the app can connect
to (`CAN_CONNECT_AND_CREATE`). The app connects as its service principal with a short-lived OAuth
token injected on each connection (`backend/db/session.py`) and runs the migrations on startup under
an advisory lock, so it creates and owns the `app` schema. Deploy before pointing a local `make dev` at
Lakebase; a schema created by your own user would not be accessible to the app.

**Idempotency and notifications.** Mutating `/api` requests may send an `Idempotency-Key` header; a
retry with the same key replays the first response instead of running twice (the UI sends one for
creates and agent runs). `Notifier.notify()` writes to the in-app inbox and to any outbound channels;
run results and role grants notify the user. The UI polls - every 1.5 s backing off to 10 s for a run,
every 30 s for the bell - because the Apps proxy buffers server-sent events and ends requests after
120 seconds.

**Evals.** Each row of `evals/dataset.jsonl` is a contract request plus the facts a good result
contains, run through the same runtime the app uses. `make eval DEV=1` runs offline against the fake
agent with the deterministic scorers in `evals/scorers.py` (CI runs it as a test); `make eval` adds
MLflow's judges against the real model. Copy a run's `request_payload` from `agent_runs` into the
dataset to turn a real case into a test.

**Frontend.** Vite builds into `backend/static`, which FastAPI serves with client-side routing, so the
UI and API share one origin and one app. The API client (`frontend/src/lib/api.ts`) is typed from the
backend's OpenAPI schema; CI fails if the generated types are stale. `useAgentRun()`
(`frontend/src/lib/agentRuns.ts`) follows a run and refreshes the document when it finishes; runs
still in progress come back on the document as `active_runs`, so a reload resumes them.

## CI/CD

Both pipelines run, on every change:
- ruff, mypy, pytest (including the contract tests and the offline eval), ESLint, tsc, Vitest and a
  frontend build
- the lockfile check and the API-types check
- the agent on its own, checked over HTTP with `make contract-live` (the split-deployment path)
- the documentation build

Deploys run `make ci-deploy TARGET=<target>`: pushes to the default branch deploy dev; test and prod
are deployed by hand (a manual job or workflow run).

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

CI and Databricks Apps install from `uv.lock` and the npm lockfiles (`frontend/`, `docs/`), so they
must point at the public registries. Each `.npmrc` keeps registry URLs out of its lockfile.
`scripts/relock.sh` (used by `make lock`) locks through a PyPI mirror when pypi.org is unreachable and
rewrites the mirror's URLs to public PyPI. `scripts/check_lockfiles.sh` fails CI if a mirror URL slips
in. Set `PYPI_MIRROR` if your mirror is not the default one in the script.

## Things to know

- **Python 3.12** comes from uv: with `pyproject.toml` and `uv.lock` (and no `requirements.txt`),
  Databricks Apps installs with uv and uses `requires-python`. If a workspace cannot download Python
  3.12 at deploy time (restricted egress), switch to the runtime's built-in 3.11: set
  `requires-python = ">=3.11,<3.12"` and `.python-version` to `3.11`, then run `make lock`.
- **The agent dependencies are heavy.** `databricks-langchain` brings MLflow, LangChain and the
  Databricks clients, which adds to install time on the first deploy. Runs are asynchronous, so model
  latency never meets the proxy's 120-second request limit.
- **The agent's run registry lives in memory.** A restart loses runs in progress; the app fails them
  as `AGENT_RUN_LOST` and the user can retry. The results the app has materialised are safe in
  Lakebase.
- **The dev target is shared.** Development mode does not make the app or Lakebase project names
  per-user, so one person (or CI) deploys dev in a workspace.
- **Lakebase vs. local Postgres**: Lakebase runs Postgres 17, pgserver runs 16. Avoid 17-only features
  or test them against a dev deployment.
- **Egress**: the app needs PyPI (or `UV_INDEX_URL`) at deploy time, and the webhook channel needs
  the webhook host.
