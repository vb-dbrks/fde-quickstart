---
slug: /
title: Overview
---

# Agentic application starter

Choose a working pattern: **Chat**, **Generation**, or **Documents**. Replace schemas and prompts,
register capabilities, customize the UI, and deploy. FDE projects share the same FastAPI/React,
Databricks Apps, Lakebase and MLflow foundation without requiring a document-centric domain.

| Pattern | Try it |
| --- | --- |
| Chat | Start a conversation, stream an answer, revisit history and give feedback. |
| Generation | Enter a topic and audience, watch a structured draft, edit and accept or reject it. |
| Documents | Generate cited field proposals, compare with current values, accept changes and inspect history. |

The application owns persisted state and authorization. Stateless runners receive validated context
and emit official AG-UI events and results. Both fake and real runners use the same contract, through
in-process or HTTP transport. The browser follows an existing run through SSE with polling recovery.
A disconnect never triggers another model request.

New generated results require review before becoming business data. The template deliberately keeps
provisional output, validated results and accepted data separate.

Start with [Getting started](guides/getting-started.md), then the
[extension recipes](guides/agentic-applications.md). Read the
[run lifecycle](architecture/run-lifecycle.md) and [data model](architecture/data-model.md) for the
persistence and recovery guarantees. Persistent interrupt/resume and arbitrary generated interfaces
are later extensions, not requirements for every project.
