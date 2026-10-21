# Agent API contract — v1

The golden record for how the app and the agent runtime talk to each other. The Pydantic models in
`backend/contracts/agent_contract_v1.py` mirror this document one to one, and
`tests/contracts/test_golden_record.py` validates every JSON example below against them, so a change
to one without the other fails CI.

| | |
| --- | --- |
| Version | v1 |
| Transport | HTTP + JSON. In a single-app deployment the app calls the runtime in-process through the same JSON contract (`AGENT_TRANSPORT=inprocess`). |
| Pattern | Async submit, then poll (ADR 0003) |
| State | The agent is stateless; the app is the system of record (ADR 0004) |
| Field vocabulary | `contracts/field-catalog.yaml` |

## 1. Responsibilities

- **App** — owns documents, their fields, versions, audit history, conversations and access. Builds
  every request from its own data, stores the request and every status it polls in `agent_runs`, and
  materialises the output (writes fields, snapshots a version, audits) when a run succeeds.
- **Agent** — owns inference only. Uses nothing but the request (plus tools that need no app data),
  returns output in the shapes below, and keeps a run only until the app has polled the result.
  It never writes to the app's database.

## 2. Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/agent/run` | Submit a run. Returns `AgentRunStatus` with `status: "accepted"`. |
| `GET` | `/agent/run/{app_agent_run_id}` | Latest status. Idempotent; the caller backs off. |
| `GET` | `/contract` | Contract version, run kinds, step vocabulary, error codes and JSON schemas. |
| `GET` | `/healthz` | Liveness, and which runner (fake or real) serves each run kind. |

- **Identity of a run**: the app's `app_agent_run_id`. Submitting the same id again returns the
  existing run (idempotent).
- **Authentication** (split deployments): `Authorization: Bearer <Databricks OAuth token>` of the
  calling app's service principal. Not needed in-process.
- **Timing**: the app polls every 1.5 s, backing off to 10 s, and fails runs that are not terminal
  after `AGENT_RUN_TIMEOUT_SECONDS` (default 600) with `TIMEOUT`.
- **Errors**: non-2xx responses carry an error envelope (section 5).

## 3. Request — `AgentRunRequest`

| Field | Type | Notes |
| --- | --- | --- |
| `app_agent_run_id` | string | The app's run id; also the poll id. |
| `run_kind` | `generate` \| `enhance_field` \| `assistant_turn` | |
| `idempotency_key` | string | Stable for retries of the same user action. |
| `document_context` | object | `document_id`, `document_type`, `fields` (current value per field path), `user_instruction`. |
| `generate_context` | object | Required for `generate` only: `scope` = `"all"` or a list of field paths. |
| `enhance_context` | object | Required for `enhance_field` only: `field_path`, `current_value`, `instruction`. |
| `assistant_context` | object | Required for `assistant_turn` only: `thread_id`, `message`, `history` (oldest first), `history_truncated`. |
| `source_documents` | list | Documents the user allowed the agent to use: `source_document_id`, `title`, `text` (≤ 20 000 chars). The agent may cite only these. |
| `meta` | object | `initiator`, `submitted_at` (ISO 8601), `app_version`. |

### 3.1 `generate`

```json
{
  "app_agent_run_id": "3f9a1c2e-0b7d-4d7e-9a51-6f0c2b8e4a10",
  "run_kind": "generate",
  "idempotency_key": "3f9a1c2e-0b7d-4d7e-9a51-6f0c2b8e4a10",
  "document_context": {
    "document_id": "a2c4e6f8-1111-4222-8333-944455556666",
    "document_type": "brief",
    "fields": {
      "brief.title": "Customer onboarding refresh",
      "brief.goal": "Cut the time for a new customer to reach first value from two weeks to three days."
    },
    "user_instruction": "Keep it short."
  },
  "generate_context": {"scope": "all"},
  "source_documents": [
    {
      "source_document_id": "b1d3f5a7-2222-4333-8444-a55566667777",
      "title": "Onboarding survey results",
      "text": "Customers say setup takes too long and the first report is hard to find."
    }
  ],
  "meta": {"initiator": "editor@example.com", "submitted_at": "2026-10-20T15:00:00Z", "app_version": "0.1.0"}
}
```

### 3.2 `enhance_field`

```json
{
  "app_agent_run_id": "7c1e5b90-3a2f-4c11-8d6e-2b9f0a7c3d21",
  "run_kind": "enhance_field",
  "idempotency_key": "7c1e5b90-3a2f-4c11-8d6e-2b9f0a7c3d21",
  "document_context": {
    "document_id": "a2c4e6f8-1111-4222-8333-944455556666",
    "document_type": "brief",
    "fields": {"brief.title": "Customer onboarding refresh", "brief.summary": "We will make onboarding faster."}
  },
  "enhance_context": {
    "field_path": "brief.summary",
    "current_value": "We will make onboarding faster.",
    "instruction": "Mention the three-day target."
  },
  "meta": {"initiator": "editor@example.com", "submitted_at": "2026-10-20T15:05:00Z"}
}
```

### 3.3 `assistant_turn`

```json
{
  "app_agent_run_id": "e4b8c2d6-5f1a-4b3c-9d7e-8a6f4c2e0b13",
  "run_kind": "assistant_turn",
  "idempotency_key": "e4b8c2d6-5f1a-4b3c-9d7e-8a6f4c2e0b13",
  "document_context": {
    "document_id": "a2c4e6f8-1111-4222-8333-944455556666",
    "document_type": "brief",
    "fields": {"brief.title": "Customer onboarding refresh", "brief.goal": "Reach first value in three days."}
  },
  "assistant_context": {
    "thread_id": "c0ffee00-1234-4abc-8def-001122334455",
    "message": "What is the biggest risk?",
    "history": [
      {"role": "user", "content": "Summarise the goal."},
      {"role": "assistant", "content": "Get new customers to first value in three days."}
    ],
    "history_truncated": false
  },
  "meta": {"initiator": "editor@example.com", "submitted_at": "2026-10-20T15:10:00Z"}
}
```

## 4. Response — `AgentRunStatus`

| Field | Type | Notes |
| --- | --- | --- |
| `contract_version` | `"v1"` | |
| `app_agent_run_id`, `run_kind` | | Echo the request. |
| `status` | `accepted` → `running` → `succeeded` \| `failed` | |
| `step_history` | list | `name`, `status` (`pending` \| `running` \| `completed` \| `failed`), `started_at`, `completed_at`. Names come from the step vocabulary (4.1). |
| `output` | object | Required when `succeeded`. `fields` (generate: the generated fields; enhance_field: exactly one), `answer` (assistant_turn only), `meta`. |
| `error` | object | Required when `failed`: `code`, `message`, `retryable`. |
| `trace_id` | string | MLflow trace of the run, when tracing is on. |

Each output field has `field_path`, `value` (shaped by the catalog: text = string, list = list of
strings), `confidence` (`high` \| `medium` \| `low`), `confidence_reason`, `reasoning` and
`citations` (`source_document_id`, `snippet`).

### 4.1 Step vocabulary

| Run kind | Steps, in order |
| --- | --- |
| `generate` | `reading_context`, `drafting_fields`, `checking_citations` |
| `enhance_field` | `reading_field`, `suggesting_revision` |
| `assistant_turn` | `reading_conversation`, `composing_answer` |

### 4.2 Examples

Accepted (the immediate response to `POST /agent/run`):

```json
{
  "contract_version": "v1",
  "app_agent_run_id": "3f9a1c2e-0b7d-4d7e-9a51-6f0c2b8e4a10",
  "run_kind": "generate",
  "status": "accepted",
  "step_history": [
    {"name": "reading_context", "status": "pending"},
    {"name": "drafting_fields", "status": "pending"},
    {"name": "checking_citations", "status": "pending"}
  ]
}
```

Running:

```json
{
  "contract_version": "v1",
  "app_agent_run_id": "3f9a1c2e-0b7d-4d7e-9a51-6f0c2b8e4a10",
  "run_kind": "generate",
  "status": "running",
  "step_history": [
    {"name": "reading_context", "status": "completed", "started_at": "2026-10-20T15:00:01Z", "completed_at": "2026-10-20T15:00:02Z"},
    {"name": "drafting_fields", "status": "running", "started_at": "2026-10-20T15:00:02Z"},
    {"name": "checking_citations", "status": "pending"}
  ]
}
```

Succeeded `generate`:

```json
{
  "contract_version": "v1",
  "app_agent_run_id": "3f9a1c2e-0b7d-4d7e-9a51-6f0c2b8e4a10",
  "run_kind": "generate",
  "status": "succeeded",
  "step_history": [
    {"name": "reading_context", "status": "completed"},
    {"name": "drafting_fields", "status": "completed"},
    {"name": "checking_citations", "status": "completed"}
  ],
  "output": {
    "fields": [
      {
        "field_path": "brief.summary",
        "value": "Make onboarding fast enough that new customers see value in three days.",
        "confidence": "high",
        "confidence_reason": "Stated directly in the goal.",
        "reasoning": "Restates the goal and the target.",
        "citations": []
      },
      {
        "field_path": "brief.risks",
        "value": ["Setup stays slow: start with the steps the survey calls out."],
        "confidence": "medium",
        "confidence_reason": "One survey only.",
        "reasoning": "Derived from the survey's main complaint.",
        "citations": [{"source_document_id": "b1d3f5a7-2222-4333-8444-a55566667777", "snippet": "setup takes too long"}]
      }
    ],
    "meta": {"runner": "real", "agent_version": "0.1.0", "model": "databricks-claude-sonnet-5-5", "prompt_version": "generate@1"}
  },
  "trace_id": "tr-5d1f6c0b9e2a4f7d8c3b1a0e9f8d7c6b"
}
```

Succeeded `enhance_field` (a suggestion; the app applies it only when the user accepts):

```json
{
  "contract_version": "v1",
  "app_agent_run_id": "7c1e5b90-3a2f-4c11-8d6e-2b9f0a7c3d21",
  "run_kind": "enhance_field",
  "status": "succeeded",
  "step_history": [
    {"name": "reading_field", "status": "completed"},
    {"name": "suggesting_revision", "status": "completed"}
  ],
  "output": {
    "fields": [
      {
        "field_path": "brief.summary",
        "value": "We will cut onboarding so new customers reach first value within three days.",
        "confidence": "high",
        "confidence_reason": "Follows the instruction.",
        "reasoning": "Added the three-day target.",
        "citations": []
      }
    ],
    "meta": {"runner": "fake", "agent_version": "fake-agent"}
  }
}
```

Succeeded `assistant_turn`:

```json
{
  "contract_version": "v1",
  "app_agent_run_id": "e4b8c2d6-5f1a-4b3c-9d7e-8a6f4c2e0b13",
  "run_kind": "assistant_turn",
  "status": "succeeded",
  "step_history": [
    {"name": "reading_conversation", "status": "completed"},
    {"name": "composing_answer", "status": "completed"}
  ],
  "output": {
    "answer": {"content": "Setup time: if it stays slow, the three-day target is out of reach.", "citations": []},
    "meta": {"runner": "real", "agent_version": "0.1.0", "model": "databricks-claude-sonnet-5-5"}
  }
}
```

Failed:

```json
{
  "contract_version": "v1",
  "app_agent_run_id": "3f9a1c2e-0b7d-4d7e-9a51-6f0c2b8e4a10",
  "run_kind": "generate",
  "status": "failed",
  "step_history": [
    {"name": "reading_context", "status": "completed"},
    {"name": "drafting_fields", "status": "failed"},
    {"name": "checking_citations", "status": "pending"}
  ],
  "error": {"code": "MODEL_ERROR", "message": "The model endpoint returned an error.", "retryable": true}
}
```

## 5. Errors

Non-2xx responses carry an envelope:

```json
{"error": {"code": "RUN_NOT_FOUND", "message": "Agent run 'abc' was not found.", "retryable": true}}
```

| Code | Where | Meaning |
| --- | --- | --- |
| `VALIDATION_ERROR` | HTTP 400 on submit | The request does not match this contract or the field catalog. |
| `RUN_NOT_FOUND` | HTTP 404 on poll | Unknown run id — usually the agent restarted. The app fails the run as `AGENT_RUN_LOST`; the user can start it again. |
| `MODEL_ERROR` | `failed` status | The model endpoint failed or returned nothing usable. |
| `OUTPUT_INVALID` | `failed` status | The agent's output broke the contract or the catalog (checked before `succeeded`). |
| `INTERNAL_ERROR` | `failed` status | Anything else. |

The app adds its own codes on `agent_runs` (never sent by the agent):

| Code | Meaning |
| --- | --- |
| `SUBMIT_FAILED` | The agent could not be reached or rejected the request at submit. |
| `ORPHANED` | The run stayed `queued` (never accepted) past the grace period. |
| `TIMEOUT` | The run did not finish within `AGENT_RUN_TIMEOUT_SECONDS`. |
| `AGENT_RUN_LOST` | The agent answered `RUN_NOT_FOUND` for a run it had accepted. |
| `CONTRACT_ERROR` | A poll response did not match this contract. |
| `MATERIALISATION_FAILED` | The output passed the agent's checks but not the app's, so nothing was written. |

## 6. Output rules

1. `generate` returns only fields in its `scope` that the catalog marks `agent_generates: true`.
2. `enhance_field` returns exactly one field: the requested `field_path`.
3. `assistant_turn` returns `answer` and no fields.
4. Values match the catalog type (text = string; list = list of strings).
5. Citations reference only `source_documents` from the request.

The runtime enforces these before reporting `succeeded`; the app checks them again before
materialising.

## 7. Versioning

- v1 accepts additive, optional fields. Anything else — renaming, removing, making a field required,
  changing a type — is v2, served side by side until the app has moved.
- Both sides ignore fields they don't know, so either can ship a new optional field first.
- A change updates this document, `backend/contracts/agent_contract_v1.py` and the fake runner in the
  same pull request.

| Version | Date | Change |
| --- | --- | --- |
| v1 | 2026-10-20 | Initial contract: generate, enhance_field, assistant_turn. |
