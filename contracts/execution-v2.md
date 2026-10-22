# Execution v2 and AG-UI interaction transport

Execution and interaction are separate contracts. The agent executes a request; the application owns
sessions, authorization, events, results and accepted business data. Official Python `ag-ui-protocol`
and TypeScript `@ag-ui/core` / `@ag-ui/client` types define message, state and tool events.

## Runtime APIs

- `GET /agent/v2/definitions`: stable IDs, descriptions, input/result JSON schemas, capabilities and allowed tools.
- `POST /agent/v2/runs`: `ExecutionRequest` (`version: "v2"`, `run_id`, `agent_id`, `thread_id`,
  `initiator`, `input`, `context`, official AG-UI `messages`). A repeated run ID returns the existing execution.
- `GET /agent/v2/runs/{run_id}?after=0`: `ExecutionStatus`, containing status, ordered events after the
  runtime cursor, the new cursor, validated result, trace ID or a safe error. Missing runs return
  `RUN_NOT_FOUND`. The runtime keeps bounded terminal runs in memory; it does not persist model execution.

Both the in-process ASGI client and standalone HTTP client use these APIs and serialize/validate the
same data. New generic operations require v2; the app reports submission incompatibility explicitly.
The original `/agent/run`, `/agent/run/{id}` and `/contract` remain v1 for the three document operations.
Their optional `events` and `ui_action` extensions are backward compatible. A v1 document adapter
publishes the same application interaction events as v2.

Example submission:

```json
{"version":"v2","run_id":"r1","agent_id":"generation","thread_id":"r1","initiator":"fde@example.com","input":{"topic":"AG-UI","audience":"FDEs","constraints":"Be concise"},"context":{},"messages":[]}
```

## Application APIs

| Endpoint under `/api` | Purpose |
| --- | --- |
| `GET /examples`, `GET /agents` | Enabled examples and registered agent descriptors |
| `POST /sessions`, `GET /sessions?agent_id=chat` | Create and list owner-scoped conversations |
| `GET /sessions/{id}/messages` | Persisted conversation history |
| `POST /runs` | Submit `{agent_id,input,session_id?}`; use `Idempotency-Key` |
| `GET /runs?agent_id=...&session_id=...`, `GET /runs/{id}` | Reattach to existing work and read validated results |
| `GET /runs/{id}/events?after=N` | SSE or JSON batches over one journal |
| `GET/POST /runs/{id}/review` | Example-owned review state and decision callbacks |
| `POST /runs/{id}/feedback` | Persist a rating and deliver to the trace |
| `GET /runs/{id}/tools` | Previously claimed tool call IDs |
| `POST /runs/{id}/tools/{call_id}/claim` | Atomically reserve a registered, validated frontend action |
| `POST /runs/{id}/tools/{call_id}` | Idempotently persist the action outcome |

A one-shot run needs no existing session. Session history is private to its owner. Every run read,
review and tool response invokes the registered authorization callback. SSE checks identity and
access again on every batch. Document APIs additionally enforce domain access.

## Ordered interaction journal

The application writes `RUN_STARTED`, collects runtime events, validates results, runs the
application finalizer transactionally, then writes final state and `RUN_FINISHED`. Failure writes
`RUN_ERROR`. A model's claimed success alone never publishes application success. Snapshots with
`provisional: true` are previews; they are never accepted data. A parsing retry replaces the preview
and message snapshot rather than concatenating two attempts.

The durable event key is `(run_id, sequence)`; sequence is monotonically increasing within a run.
The collector locks the run and advances its runtime cursor in the same transaction as journal
inserts. Concurrent collectors therefore cannot ingest the same event twice.

With `Accept: text/event-stream`, the endpoint emits:

```text
: connected

data: {"sequence":1,"event":{"type":"RUN_STARTED","threadId":"r1","runId":"r1"}}

: heartbeat

```

Completion emits `event: complete`. Access revocation emits `event: access-denied` and closes.
Without the SSE Accept header, the endpoint returns:

```json
{"events":[{"sequence":1,"event":{"type":"RUN_STARTED","threadId":"r1","runId":"r1"}}],"cursor":1,"terminal":false}
```

`DurableAgent extends AbstractAgent` unwraps these events for the official AG-UI client. It ignores
already processed sequences, detects gaps, and switches permanently to cursor polling for that
subscription after stream interruption or 15 seconds without heartbeats. It only issues GETs;
reattachment cannot create inference. Reload replays the journal to reconstruct UI state. JSON
batches contain at most 500 events. Background collection continues with no browser connected.

**This cursor envelope is an application transport extension, not standard AG-UI SSE resumption.**
Do not connect the stock `HttpAgent` to it directly. See the official
[architecture](https://docs.ag-ui.com/concepts/architecture),
[events](https://docs.ag-ui.com/concepts/events), and
[AbstractAgent reference](https://docs.ag-ui.com/sdk/js/client/abstract-agent).

## Frontend tools and durability limits

The app validates the completed call against registered tool names and argument schemas. The UI
claims a call before applying it. A lost tab after claiming can skip an optional UI action; it cannot
repeat it on reload. This at-most-once policy is appropriate for `focus_field`; business mutations
must be server transactions with their own idempotent acceptance API. Outcomes do not resume a paused
model in this release. Interrupt/resume, arbitrary generated interfaces and other agent frameworks
can be added behind these registration/transport boundaries.

Persisted events recover viewing state, not execution. If the runtime restarts before collection,
the app reports `AGENT_RUN_LOST`; restarting inference is an explicit new user action.
