---
title: "0011: Generic AG-UI interactions and reviewed results"
---

# 0011: Generic AG-UI interactions and reviewed results

Status: accepted.

## Context

FDEs use this template for chat, generation and domain-specific workflows. Requiring every run to
reference a document and a field catalog prevents simple independent applications. Browser polling
alone also loses progressive interaction detail and does not provide a reusable tool/state contract.

## Decision

Use a generic application lifecycle and execution-v2 contract, with explicit agent/application/example
registrations. Adopt official AG-UI types and the official JavaScript client through an `AbstractAgent`
adapter. Keep async submit/status separate from browser interactions. Persist ordered interaction
events in Lakebase and provide SSE with heartbeat-driven polling recovery over the same cursor journal.

Runtime runners receive validated context and produce events/results; app callbacks own authorization,
context construction and finalization. Persist validated drafts before publishing success. Accepting
business data is a separate transaction. The existing v1 document interface stays behind a compatibility
adapter; migration preserves identities/history and the policy of pre-existing runs.

## Consequences

New applications do not need document imports or a core run-kind enum change. Chat, generation and
documents are independently disabled. The explicit registrations are understandable application code.
Polling recovery is a custom application transport extension, not standard AG-UI SSE resumption.
Events survive disconnects but do not make model execution durable. Claimed frontend actions are
at most once; a crash after claim can skip an optional UI action. Interrupt/resume and generated
interfaces remain later extensions behind the same boundaries.
