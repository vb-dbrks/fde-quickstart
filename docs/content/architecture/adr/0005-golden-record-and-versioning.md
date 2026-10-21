---
title: "0005: Golden record and contract versioning"
sidebar_label: "0005: Golden record"
---

# 0005: Golden record and contract versioning

**Status:** Accepted

## Context

The app and agent are built in parallel, often by different people. A contract that exists only in
code drifts; one that exists only in prose is never checked.

## Decision

- `contracts/agent-api-contract.md` is the golden record: endpoints, request and response tables, step
  vocabulary, error codes, output rules, and a JSON example of every request and status.
- `backend/contracts/agent_contract_v1.py` mirrors it one to one, as frozen Pydantic v2 models that
  forbid unknown fields.
- `tests/contracts/test_golden_record.py` validates every JSON example in the document against the
  models, so a change to one without the other fails CI.
- `contracts/field-catalog.yaml` is part of the contract: it defines the fields an agent may write.
- `GET /contract` serves the version, run kinds, step vocabulary and JSON schemas;
  `make contract-live` checks a running agent against them.
- v1 accepts only additive, optional changes. Renaming, removing, requiring or retyping a field is v2,
  served side by side until the app has moved. A change updates the document, the models and the
  fake runner in the same pull request.

## Consequences

- Reviewers read one Markdown file to understand the integration.
- Both sides can work against the contract alone: the agent team with `make contract-live`, the app
  team with the fake agent.
- Breaking changes are deliberate and visible.
