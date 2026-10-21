---
title: The agent contract
---

# The agent contract

The full contract is `contracts/agent-api-contract.md` in the repository: the golden record, with a
JSON example of every request and status. This page is a summary. When they disagree, the file wins;
`tests/contracts/test_golden_record.py` keeps it in step with the models in
`backend/contracts/agent_contract_v1.py`.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/agent/run` | Submit a run; returns `accepted`. Submitting the same `app_agent_run_id` again returns the existing run. |
| `GET` | `/agent/run/{app_agent_run_id}` | Latest status. `404 RUN_NOT_FOUND` if the agent doesn't know the run. |
| `GET` | `/contract` | Version, run kinds, step vocabulary, error codes, JSON schemas. |
| `GET` | `/healthz` | Liveness, and the runner (fake or real) per run kind. |

## Run kinds

| Run kind | Context | Output | Steps |
| --- | --- | --- | --- |
| `generate` | `generate_context.scope`: `"all"` or a list of field paths | The requested agent fields | `reading_context`, `drafting_fields`, `checking_citations` |
| `enhance_field` | `enhance_context`: `field_path`, `current_value`, `instruction` | Exactly that one field | `reading_field`, `suggesting_revision` |
| `assistant_turn` | `assistant_context`: `thread_id`, `message`, `history`, `history_truncated` | `answer` and no fields | `reading_conversation`, `composing_answer` |

Every request also carries `document_context` (the document's current fields and the user's
instruction), `source_documents` (text the agent may cite), `idempotency_key` and `meta`.

Each output field has a value shaped by the field catalog (text is a string, list is a list of
strings), a `confidence` of `high`, `medium` or `low` with a reason, the `reasoning`, and `citations`
of the provided sources.

## Output rules

The runtime checks these before reporting `succeeded`, and the app checks them again before writing
(`backend/contracts/validation.py`). A violation fails the run with `OUTPUT_INVALID`.

1. `generate` returns only fields in its scope that the catalog marks `agent_generates: true`.
2. `enhance_field` returns exactly the requested field.
3. `assistant_turn` returns an answer and no fields.
4. Values match the catalog type.
5. Citations reference only the request's `source_documents`.

## Errors

| Code | Where | Meaning |
| --- | --- | --- |
| `VALIDATION_ERROR` | HTTP 400 on submit | The request breaks the contract or the field catalog. |
| `RUN_NOT_FOUND` | HTTP 404 on poll | Unknown run, usually after an agent restart. |
| `MODEL_ERROR` | `failed` status | The model endpoint failed or returned nothing usable (retryable). |
| `OUTPUT_INVALID` | `failed` status | The output broke the output rules. |
| `INTERNAL_ERROR` | `failed` status | Anything else (retryable). |

The app adds its own codes on `agent_runs`; see [Run lifecycle](../architecture/run-lifecycle.md).

## Changing the contract

- Additive, optional fields stay v1. Anything else is v2, served side by side.
- Update `contracts/agent-api-contract.md`, `backend/contracts/agent_contract_v1.py` and the fake
  runner in the same pull request, and add a row to the version table at the end of the contract.
- `make contract` runs the contract tests; `make contract-live AGENT_API_BASE=...` checks a running
  agent over HTTP.
