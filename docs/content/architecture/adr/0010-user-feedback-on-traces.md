---
title: "0010: Users' feedback is stored on the run's MLflow trace"
sidebar_label: "0010: Feedback on traces"
---

# 0010: Users' feedback is stored on the run's MLflow trace

**Status:** Accepted

## Context

Offline evals (ADR 0006, `evals/`) measure the agent on a fixed dataset. They don't show how the
agent does on real documents, and the dataset only grows when someone writes new rows. Users already
judge the agent's output all the time: they keep a value, change it, accept or dismiss a suggestion,
or say an answer missed the point. Each agent run already has an MLflow trace with its full request
(ADR 0004), so that judgement can sit next to exactly what the agent saw and wrote.

## Decision

1. **Traces say who and where.** Each run's trace records the user (`mlflow.trace.user`), a session
   (the conversation for chat turns, the document otherwise) and tags for the run, the document and
   the agent version, so the MLflow UI can filter and group by them.
2. **Feedback is captured where it happens**, with a small vocabulary (contract section 7):
   `field_rating` and `answer_rating` (thumbs up or down, with reasons and a comment),
   `suggestion_accepted` (accept or dismiss), and an **expectation** named after the field (`.` as `__`) when a user
   corrects a value the agent wrote - the corrected value is ground truth for that run.
3. **The app stores it first** (`feedback` table) and delivers it afterwards, so a slow or failing
   trace store never slows a user down: once straight after the request, then by a background
   worker with backoff. One row per user and target; a change replaces the earlier assessment
   (`override_feedback` keeps the old one, marked invalid).
4. **The agent writes to MLflow** (`POST /agent/feedback`). The agent owns tracing, so the app needs
   no MLflow configuration or permissions, and a split deployment works the same way.
5. **Feedback is turned into evals.** `make eval-dataset` exports traces with feedback as rows of the
   eval dataset: the real request, and corrections as expected facts.

## Consequences

- The team sees, per run, what users thought, in the same place as the trace - and can sort the
  experiment's traces by user, session, rating or reason.
- Corrections grow the eval dataset from real use, which is what keeps evals honest.
- Ratings are opt-in and sparse; corrections are implicit and plentiful. Read them together.
- Feedback holds user content. It stays in the workspace (Lakebase and the experiment); the exported
  dataset file is git-ignored.
- Without tracing (local development) feedback is still stored in the app, marked `skipped`.
