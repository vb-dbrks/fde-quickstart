# AGENTS.md

The brief for AI coding assistants (Claude Code, Cursor, Codex, Copilot, ...) and for people new to
this repo. Read it before changing code. The README says what the project is; this file says how to
change it without breaking it.

## What this is

A Databricks App: FastAPI backend + React frontend in one app, Lakebase Postgres as the system of
record, and a stateless AI agent the app calls through a versioned submit/poll contract. Three independently removable examples demonstrate standalone chat, structured generation and brief documents. New applications need no document or field catalog.

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
| `make eval-dataset PROFILE= EXPERIMENT=` | turn users' feedback on real runs (MLflow traces) into eval rows |

**Before you say you're done: `make lint test` must pass.** If you changed the API, run
`make api-types` first and commit the regenerated `frontend/src/api/schema.d.ts`.

## Rules that keep the architecture intact

1. **The app owns all state; the agent is stateless.** `backend/agents/` must not import the app
   (database, sessions, services, settings) - only `backend.contracts` and third-party packages.
   `tests/agents/test_boundary.py` enforces this. The agent gets everything it needs in the request.
2. **Never call a model from an API route.** Agent work is a *run*: the app stores it in
   `agent_runs`, submits it, polls it, and materialises the result. To add an agent capability, add a
   registration (recipe below).
3. **The contract is the golden record.** `contracts/agent-api-contract.md`,
   `backend/contracts/agent_contract_v1.py` and the fake runner (`backend/agents/fake/runner.py`)
   change together, in the same commit. Within v1 only add optional fields. Generic agents use
   `contracts/execution-v2.md` and `backend/contracts/execution.py`, carrying official AG-UI types.
4. **The field catalog belongs only to the document example.** `contracts/field-catalog.yaml` defines document types
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
10. **Users' feedback goes to the run's trace through the agent.** Record it with
    `backend/services/feedback.py` (stored in Lakebase first, delivered afterwards); never call MLflow
    from the app. Use the contract's feedback vocabulary (`FEEDBACK_NAMES`, `FEEDBACK_REASONS`) so
    traces stay comparable. See `docs/content/guides/user-feedback.md`.
11. **Workspace commands take `PROFILE=` explicitly.** Nothing uses the default Databricks CLI
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

**Add an agent capability** (`agentic-applications.md`). Define input/result schemas, register an
`AgentDefinition` in `backend/agents/example_registry.py` and an `AgentApplication` in
`backend/examples/registry.py`. Supply fake/real runners and application callbacks. Use shared
React primitives from `frontend/src/agent/` and register example routes/navigation explicitly.
Do not extend v1 run-kind enums for generic capabilities or import document code into
`backend/services/interactions.py` or `frontend/src/agent/`. Run the contract and interaction tests.

**Preserve review boundaries.** AG-UI state is provisional. Only a validated result and successful
application finalisation may publish terminal success. Acceptance is a separate operation. Never
save partial model output into accepted domain data. Document acceptance must compare captured field
revisions and write provenance/audit/version data atomically. Never resubmit when reconnecting.
Frontend tools must use registered argument schemas and claim their action before executing it.

**Keep examples removable.** `ENABLED_EXAMPLES` gates backend routes/registrations and frontend
navigation. Disabling documents must not load the field catalog. Preserve v1 history and legacy run
policy during migrations. AG-UI cursor recovery is our transport extension, not standard resumption.

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
