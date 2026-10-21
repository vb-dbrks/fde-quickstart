---
title: Evals
---

# Evals

`evals/` evaluates the agent with MLflow 3. Each row of `evals/dataset.jsonl` is a contract request
plus the facts a good result contains. Rows run through the same `AgentRuntime` the app uses, with its
request checks, steps and output checks, so an eval measures what users get.

## Two modes

```bash
make eval DEV=1                                    # offline: the fake agent, deterministic scorers
make eval PROFILE=<profile> LLM_ENDPOINT=<endpoint>  # the real agent, plus LLM judges
```

**Offline** needs no workspace. It runs every row against the fake agent and prints a line per row; it
exits non-zero if any check fails. The test suite runs it too (`tests/test_evals.py`), so the harness
and the dataset can't rot.

**Against a real endpoint**, `mlflow.genai.evaluate` runs the real runners and logs results to an
experiment in your profile's workspace (default `/Users/<you>/agent-evals`; change it with
`python -m evals.run --experiment <path>`). LangChain calls are traced, nested under each row's
evaluation trace.

## Scorers

| Scorer | Kind | Passes when |
| --- | --- | --- |
| `follows_contract` | deterministic | The run succeeded. Contract violations fail runs as `OUTPUT_INVALID`, so this covers the output rules. |
| `fields_complete` | deterministic | Every requested field came back with a value; for chat, there is an answer. |
| `cites_sources` | deterministic | With source documents in the request, the output cites at least one. Skipped without sources. |
| `concise` | deterministic | Chat answers have at most 120 words. Skipped for other run kinds. |
| `plain_text` | deterministic | No Markdown in values or answers: the app shows them as plain text. |
| `Correctness` | LLM judge | The output contains the row's `expected_facts`. |
| `Safety` | LLM judge | Nothing harmful. |

Deterministic scorers live in `evals/scorers.py`; the judges are configured in `evals/run.py`. Use
judges for meaning and code for syntax: in testing, a `Guidelines` judge asked "is this Markdown?"
flagged ordinary punctuation and JSON arrays, and judges miscount words.

## Dataset rows

```json
{
  "inputs": {
    "request": {
      "run_kind": "generate",
      "document_context": {
        "document_id": "eval-onboarding",
        "document_type": "brief",
        "fields": {"brief.title": "Onboarding refresh", "brief.goal": "..."}
      },
      "generate_context": {"scope": "all"},
      "source_documents": [{"source_document_id": "src-1", "title": "Interview notes", "text": "..."}]
    }
  },
  "expectations": {"expected_facts": ["The target is a first working dashboard within three days"]}
}
```

`app_agent_run_id`, `idempotency_key` and `meta` are optional in a row; the loader fills them in.

## Turning a real run into a test case

Every run's request is stored exactly as sent in `agent_runs.request_payload`. To keep a run that
went wrong as a regression case, copy that JSON into a new row under `inputs.request`, add the facts a
good answer contains, and run `make eval`.

Users do much of this for you: their ratings and corrections are stored on each run's trace, and
`make eval-dataset` exports the traces they gave feedback on as rows, with corrections as expected
facts ([User feedback and evaluation](user-feedback.md)).

## When to run it

- Before and after a prompt change (`backend/agents/prompts/`), and bump its version in
  `PROMPT_VERSIONS`.
- After changing a field's description in the field catalog: it is part of the prompt.
- When changing the model endpoint.
