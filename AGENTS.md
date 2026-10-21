# AGENTS.md

The brief for AI coding assistants (Claude Code, Cursor, Codex, Copilot, ...) and for people new to
this repo. Read it before changing code. The README says what the project is; this file says how to
change it without breaking it.

## What this is

A Databricks App: FastAPI backend + React frontend in one app, Lakebase Postgres as the system of
record, and a stateless AI agent the app calls through a versioned submit/poll contract. The sample
domain is a "brief" document whose fields the agent drafts; projects replace it with their own.

## Commands

| Command | When |
| --- | --- |
| `make setup` | once, and after a lockfile changes |
| `make dev` | run locally: http://localhost:5173 (API on :8000, local Postgres, fake agent) |
| `make lint` | ruff, mypy (strict), ESLint, Prettier, tsc |
| `make test` | pytest (real Postgres, no Docker) and Vitest |
| `make api-types` | after changing any API route or schema - regenerates the frontend types |
| `make migration MSG="..."` | after changing `backend/domain/models.py` |
| `make contract` | after touching the agent, the contract or the field catalog |
| `make eval DEV=1` | after changing prompts or runners (offline, fake agent) |

**Before you say you're done: `make lint test` must pass.** If you changed the API, run
`make api-types` first and commit the regenerated `frontend/src/api/schema.d.ts`.

## Rules that keep the architecture intact

1. **The app owns all state; the agent is stateless.** `backend/agents/` must not import the app
   (database, sessions, services, settings) - only `backend.contracts` and third-party packages.
   `tests/agents/test_boundary.py` enforces this. The agent gets everything it needs in the request.
2. **Never call a model from an API route.** Agent work is a *run*: the app stores it in
   `agent_runs`, submits it, polls it, and materialises the result. To add an agent capability, add a
   run kind (recipe below).
3. **The contract is the golden record.** `contracts/agent-api-contract.md`,
   `backend/contracts/agent_contract_v1.py` and the fake runner (`backend/agents/fake/runner.py`)
   change together, in the same commit. Within v1 only add optional fields; anything else is v2.
4. **The field catalog is the domain model.** `contracts/field-catalog.yaml` defines document types
   and fields, and which fields the agent may write. Change it first; the API, the UI forms, both
   runners and the validation read it.
5. **Schema changes are migrations.** Edit `backend/domain/models.py`, then `make migration MSG=...`.
   Never edit a migration that has been deployed. The app migrates at startup.
6. **Generated files are generated.** Don't hand-edit `frontend/src/api/schema.d.ts` (use
   `make api-types`) or `backend/static/` (built by `make build`).
7. **Permissions are enforced in the API.** Routes use `require(Permission.X)` and
   `require_document(...)`; the UI only hides what the user can't do. Documents a user can't see
   answer 404, actions they can't take answer 403.
8. **Structured output from models goes through `structured()`**
   (`backend/agents/runners/_common.py`), not LangChain's `with_structured_output()` - newer Claude
   endpoints on Databricks reject forced tool calls. End prompts with "Answer by calling the provided
   tool once."
9. **No secrets in the repo.** `.env` is local and ignored. Lockfiles must point at public registries
   (`make lock`, checked by `scripts/check_lockfiles.sh`).
10. **Workspace commands take `PROFILE=` explicitly.** Nothing uses the default Databricks CLI
    profile; each bundle target pins its host.

## Where things go

| Change | Files |
| --- | --- |
| HTTP route | `backend/api/<area>.py` (register in `backend/api/__init__.py`) |
| Request/response shapes | `backend/domain/schemas.py` (then `make api-types`) |
| Business logic | `backend/services/` - routes stay thin |
| Tables | `backend/domain/models.py` + a migration in `alembic/versions/` |
| Roles and permissions | `backend/auth/roles.py` |
| Agent behaviour | `backend/agents/prompts/*.md`, `backend/agents/runners/*.py`, the fake in `backend/agents/fake/` |
| Agent wire format | `contracts/agent-api-contract.md` + `backend/contracts/agent_contract_v1.py` |
| Document types and fields | `contracts/field-catalog.yaml` |
| Page | `frontend/src/pages/` + `frontend/src/routes.tsx` + `frontend/src/app/nav.ts` |
| Data fetching | `frontend/src/lib/queries.ts` (TanStack Query hooks over the typed client) |
| UI building blocks | `frontend/src/components/ui/` (shadcn/ui), `frontend/src/components/documents/` |
| App settings | `backend/settings.py` (env vars), `backend/agents/config.py` (agent env vars) |
| Deployment | `databricks.yml`, `resources/*.yml`, `app.yaml` |

## Recipes

Each has a full guide under `docs/content/guides/`.

**Replace the sample domain** (`adding-a-document-type.md`). Add your document type to
`contracts/field-catalog.yaml` (user fields with `agent_generates: false`, agent fields with `true`;
paths are `<type>.<field>`, and every type needs a `<type>.title`). Rewrite the prompts in
`backend/agents/prompts/` for your domain. Update the fake's wording in `backend/agents/fake/runner.py`
if you like, the dataset in `evals/dataset.jsonl`, and the test fixtures that use `brief`
(`tests/helpers.py` `BRIEF`, `frontend/src/test/documents.ts`). Then delete the `brief` type.

**Add a field.** Add it to the catalog. User fields appear in the create form and the workspace; agent
fields are written by `generate` and can be enhanced. No migration: field values live in
`document_fields` rows.

**Add an agent capability (a run kind)** (`adding-a-run-kind.md`). In order: the contract (golden
record, models, validation), the fake runner, the prompt and real runner, the app (schemas, payload
builder, `_validate` and `_materialise` in `backend/services/agent_runs.py`, presenter), the UI
(`useStartAgentRun` + `useAgentRun`), evals. `make contract test` after each layer.

**Add an endpoint and a page.** Schema in `backend/domain/schemas.py`, logic in `backend/services/`,
route in `backend/api/`, test in `tests/backend/`; `make api-types`; a hook in
`frontend/src/lib/queries.ts`; the page and its route and nav entry; a Vitest test using `mockApi`
from `frontend/src/test/utils.tsx`.

**Add a permission.** Add it to `Permission`, give it to roles in `backend/auth/roles.py`, check it
with `require(Permission.X)`, then `make api-types` and gate the UI with `<Can permission=...>`.

**Use a real model locally.** In `.env`: `DATABRICKS_CONFIG_PROFILE=<profile>` and
`LLM_ENDPOINT=<serving endpoint>`. Recent Claude endpoints reject `temperature`; leave
`LLM_TEMPERATURE` unset for them. `make eval PROFILE=... LLM_ENDPOINT=...` scores the real agent.

## Testing conventions

- Backend tests run against a real Postgres started by pgserver (`tests/conftest.py`): use the
  `client`, `editor` and `sessions` fixtures and `create_brief`; the agent is the fake one, executing
  inline, so runs finish before the submit returns.
- Real runners are tested offline with `ScriptedModel` (`tests/agents/test_real_runners.py`).
- Frontend tests render the whole app with `renderApp(path)` and stub the API with `mockApi`.
- Bug fix? Add a test that fails without the fix.

## Style

Python 3.12 with type hints everywhere (mypy strict) and ruff; TypeScript strict. Keep routes thin and
logic in services. Comments explain why, not what. Match the surrounding code.
