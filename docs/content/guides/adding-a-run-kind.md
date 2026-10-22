---
title: Adding a run kind
---

# Adding a run kind

A run kind is one thing the agent can do, such as `generate`. Adding one touches both halves and the
contract between them. Work in this order; each step leaves the tests passing. The example adds
`review`: the agent reviews a document and returns comments.

For new generic capabilities, use [the agent registration recipe](agentic-applications.md). The steps
below describe the legacy v1 document interface only; do not extend it for independent applications.

## 1. The contract

1. `contracts/agent-api-contract.md`: add the run kind to the request and response tables, its step
   names to the step vocabulary, its context and output rules, and JSON examples of the request and a
   succeeded status. Add a row to the version table. A new run kind is additive, so it stays v1.
2. `backend/contracts/agent_contract_v1.py`:
   - add it to `AgentRunKind` and `RUN_KINDS`;
   - add its steps to `STEP_VOCABULARY`;
   - add a context model (e.g. `ReviewContext`) and an optional field for it on `AgentRunRequest`,
     and extend `_context_matches_run_kind`;
   - if the output has a new shape, add an optional field to `AgentOutput`.
3. `backend/contracts/validation.py`: what `requested_fields` returns for it, and its rules in
   `check_output`.
4. `tests/contracts/`: `test_golden_record.py` picks up the new examples by itself; add cases to
   `test_validation.py` (its `make_request` helper needs a default context for the new kind).

## 2. The agent

1. `backend/agents/fake/runner.py`: a method that walks the steps and returns deterministic output,
   and an entry in `runners()`.
2. `backend/agents/prompts/review.md`, plus its version in `PROMPT_VERSIONS`
   (`backend/agents/runners/_common.py`).
3. `backend/agents/runners/review.py`: a `make_review_runner` that builds
   `prompt | structured(model(), Schema)` and maps the result to `AgentOutput`. Copy
   `enhance_field.py` as a starting point. Use `structured()` rather than LangChain's
   `with_structured_output()`: that forces a tool call or sends `response_format`, and newer Claude
   models on Databricks reject both. End the prompt with "Answer by calling the provided tool once."
4. `backend/agents/runners/__init__.py`: register it in `real_runners`.
5. `tests/agents/`: the fake and the real runner (with the scripted model in `test_real_runners.py`).

`build_runtime` picks fake or real per kind from `AGENT_RUNNER` and `AGENT_RUNNER_OVERRIDES`; nothing
else to wire.

## 3. The app

1. `backend/domain/schemas.py`: add the kind to `AgentRunCreate.run_kind` and `AgentRunOut.run_kind`,
   any new request fields, and a field on `AgentRunOut` if the UI shows the result.
2. `backend/services/agent_payload_builder.py`: build the new context in `build_request`.
3. `backend/services/agent_runs.py`: validation in `_validate` (which access the run needs), what
   materialising means in `_materialise`, and a label in `RUN_LABELS` for notifications.
4. `backend/api/presenters.py`: present the result in `run_out`.
5. If materialising writes new data, a model change and `make migration MSG="..."`.
6. `tests/backend/test_agent_runs.py`: the run end to end with the fake agent.

## 4. The UI and evals

1. `make api-types`, then the UI: start the run with `useStartAgentRun` and follow it with
   `useAgentRun` (`frontend/src/lib/agentRuns.ts`); `RunProgress` renders its steps.
2. `evals/dataset.jsonl`: rows for the new kind. Check `evals/scorers.py` handles it.

## 5. If the agent runs separately

Deploy the agent before the app. An older agent answers the new kind with `400 VALIDATION_ERROR`, and
the app fails the run with `SUBMIT_FAILED`.
