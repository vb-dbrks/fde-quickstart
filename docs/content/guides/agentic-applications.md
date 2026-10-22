---
title: Build an agentic application
---

# Build an agentic application

Start with Chat for conversations, Generation for a form-to-artifact workflow, or Documents for
record-oriented collaboration. All three share execution, persistence, feedback and AG-UI transport.
Use `ENABLED_EXAMPLES` on the app and standalone runtime to keep the examples your project needs.

## Add an agent

1. Define independent Pydantic input and result models under `backend/contracts/`. Do not import
   application persistence there. Chat/Generation schemas in `examples.py` are small examples.
2. Write a runner accepting `ExecutionRequest` and `EventEmitter`, returning the declared result
   model. Emit official `ag_ui.core` events, such as `StateSnapshotEvent` for a preview. A runner must
   not import app services, settings or database code. Use `stream_structured` for real structured
   model output; it preserves automatic tool choice, partial previews and one parsing retry.
3. Register `AgentDefinition(id, example, description, input_model, result_model, runner, capabilities,
   tools)` in `backend/agents/example_registry.py`. Select fake/real implementation with
   `settings.runner_for(id)`. Supply a deterministic fake for offline development.
4. Register the same ID with `AgentApplication` in `backend/examples/registry.py`. Its `authorize`
   callback controls run visibility; `prepare` constructs trusted application context; `finalize`
   stores validated results. Register optional `review`/`review_state` callbacks for accepted data.
5. Add a frontend page and its route/navigation registration in `frontend/src/examples/registry.tsx`.
   The example ID must match the backend registration. New domain endpoints register explicitly in
   `backend/api/__init__.py`; no dynamic plugin loader is involved.

A test-only fourth agent in `tests/backend/test_interactions.py` registers `Echo` without changing
transport, lifecycle code or run-kind enums. Use it as a minimal registration fixture.

## Persist domain results

An application finalizer has this shape:

```python
async def finish(db: AsyncSession, run: AgentRun, result: dict[str, Any]) -> None:
    db.add(MyDraft(run_id=run.id, content=result, status="pending"))
```

The shared lifecycle validates the result first and executes this callback under the run lock in a
savepoint. Do not commit inside the callback. The app commits the draft, result and terminal event
together. Exceptions roll back finalizer writes and fail the run. Keep external side effects in an
idempotent outbox; a database savepoint cannot undo a remote API call.

Add a migration for domain tables. Use a separate review callback/route to validate edited content,
check stale versions and accept or reject it transactionally. The generation artifact and document
proposal implementations demonstrate these two levels of domain complexity.

## Add a result renderer

`AgentProvider` owns the official AG-UI client for each active run. `useInteraction(runId)` gives you
messages, shared state, events, completion and errors. It attaches to existing work; use `post('/runs',
...)` once to submit. `useSessions`, `useSessionMessages` and `useRuns` use TanStack Query for persisted
data, with shared keys for invalidation.

Compose `ChatTranscript`, `Composer`, `RunActivity`, `StructuredResult`, `ReviewCard`, `ToolActivity`
and `Citations` from `frontend/src/agent/components.tsx`, or provide your own typed renderer. They
accept data and callbacks and have no document API/catalog imports. Render provisional state while a
run is active, and offer acceptance only after a validated result exists. The development build
includes an event inspector; it is absent from production builds.

## Add a frontend tool

Register an official AG-UI `Tool` on the runtime definition, with a name, description and JSON schema.
Register the same name with a Pydantic argument model in `AgentApplication.tools`. The runner emits
`ToolCallStartEvent`, `ToolCallArgsEvent`, then `ToolCallEndEvent` using one stable call ID.

Provide an implementation to `ToolActions`:

```tsx
<ToolActions runId={run.id} interaction={interaction} tools={{
  focus_field: { execute: ({ field_path }) => focusKnownField(String(field_path)) },
}} />
```

Only completed successful runs trigger actions. Before executing, the UI claims the call on the
server, which rechecks run access and validates the registered name/arguments. The claim is durable;
replay or another tab cannot apply it twice. The outcome is recorded idempotently afterward. A tab
that closes between claim and action can skip this optional action. Do not use UI actions for
business mutations; use explicit authorized acceptance APIs for those.

The document adapter supplies `focus_field`, validates its field against the catalog and targets a
known component. It demonstrates UI control without allowing arbitrary generated code or interfaces.

## Remove an example

Set `ENABLED_EXAMPLES=chat` to run only chat. The API omits document routes, runtime omits disabled
agents, and the frontend omits navigation/cards and gates direct routes. The isolation test disables
each example independently and ensures chat/generation can run without loading the field catalog.

To physically remove code, delete its entries/imports from the runtime, application and frontend
registries, and its domain route registration. Delete only its example components/schemas/runners.
Keep shared interaction services, AG-UI primitives and platform integrations. Retain deployed
migrations and historical tables until an explicit data-retention migration removes them.

## Verify and deploy

Run `make api-types`, `make lint test`, `make contract`, `make eval DEV=1`, `make build` and
`make docs-build`. Offline fixtures cover fake/scripted-real parity, partial chunks, parse retries,
invalid results, review conflicts, event replay, SSE interruption and heartbeat fallback.

For standalone mode, run `AGENT_RUNNER=fake make agent`, then configure `AGENT_TRANSPORT=http` and
`AGENT_API_BASE=http://localhost:9000` on the app. Run
`make contract-live AGENT_API_BASE=http://localhost:9000` to check both supported execution versions.
Use [Deploy and CI/CD](deploy-and-ci.md) for Databricks Apps. Record live endpoint smoke tests
separately from offline tests, including the named profile, endpoint and outcome.
