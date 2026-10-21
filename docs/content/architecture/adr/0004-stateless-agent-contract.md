---
title: "0004: Stateless agent contract"
sidebar_label: "0004: Stateless agent"
---

# 0004: Stateless agent contract

**Status:** Accepted

## Context

If an agent reads and writes the app's data itself, the two share a schema, credentials and failure
modes, and every agent change risks app data. Conversation memory kept inside the agent is lost on
restart and invisible to the app.

## Decision

The agent is stateless. Every `AgentRunRequest` carries everything the agent needs:

- `document_context`: the document's current field values and the user's instruction;
- the run kind's context: generate scope, the field to enhance, or the chat message and history;
- `source_documents`: other documents the user chose, as text, which the agent may cite;
- `meta`: who asked and when.

The runtime keeps only a process-local registry of in-flight and recently finished runs, keyed by the
app's `app_agent_run_id`, so the app can poll them. It never connects to the app's database. The app
alone decides what to write, and checks the output again before writing it.

## Consequences

- The agent can be developed, tested, evaluated and deployed without the app's database.
- Replaying a run needs only its stored `request_payload`.
- Requests can be large: source text is capped at 20 000 characters per document, at most five
  sources per run, and chat history is truncated to the most recent messages
  (`ASSISTANT_HISTORY_LIMIT`, flagged with `history_truncated`).
- The agent can't fetch more context mid-run. Tools that need app data are added as app-side
  services that put the data in the request.
