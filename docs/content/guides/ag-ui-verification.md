---
title: AG-UI implementation verification
---

# AG-UI implementation verification

Verified locally on 2026-10-21, with lint, generated types and the full test suite rechecked after
review fixes on 2026-10-22. These results cover the supplied fake runners and scripted real-model
fixtures; they do not imply a live Databricks deployment or model smoke test.

| Check | Outcome |
| --- | --- |
| `make api-types` | OpenAPI TypeScript definitions regenerated; strict TypeScript check passes |
| `make lint test` | Ruff, formatting, strict mypy, ESLint, Prettier and TypeScript pass; 174 Python and 31 frontend tests pass |
| `make contract` | Contract, boundary, fake runtime and scripted real-runner checks pass |
| `make eval DEV=1` | 7 offline evaluation rows, 0 failed checks |
| `make build` | Production frontend builds; Vite reports an advisory bundle-size warning |
| `make docs-build` | Documentation compiles with internal link checks |
| `make check-lock` | Dependency lockfiles use public registries |
| Standalone HTTP | 8 smoke tests pass against a separate local fake runtime, including app collection/persistence/review and all supported v1/v2 operations |

The default suite skips the 8 live-agent tests unless `AGENT_API_BASE` is set. They were run separately
against `http://127.0.0.1:19000` with `AGENT_RUNNER=fake` and `FAKE_AGENT_STEP_SECONDS=0`.

## Acceptance coverage

- Chat/history/feedback and structured generation without documents; no field catalog load when documents are disabled.
- Every example disabled independently; a fourth test agent registered without changing lifecycle or transport.
- Fake and scripted real runners, partial chunks and parse-retry replacement.
- Idempotent submission, journal replay, duplicate event suppression, SSE interruption, missing-heartbeat polling fallback and React StrictMode reattachment.
- Failed finalization cannot publish success or make output reviewable; explicit edited acceptance and rejection; stale document proposals cannot overwrite newer edits.
- Review regressions: viewers cannot reject shared proposals; edits during context preparation invalidate proposals; finalization flush errors persist a replayable failure without saving results.
- Owner/application access checks, renewed subscription authorization, registered tool validation and durable action claims/outcomes.
- A populated v1 database migration preserves identifiers, messages, feedback, snapshots and outstanding legacy-run policy.
- Shared runtime and frontend import boundaries are checked by tests.

## Live Databricks smoke tests

**Not run:** no configured Databricks profile and serving endpoint were available for this task.
Live model streaming, Apps proxy buffering/authentication and Lakebase/MLflow integration still need
a deployment-specific smoke test. Some tracing tests produce expected credential/export warnings
when run without Databricks credentials; offline assertions pass.

When configured, record the named profile, endpoint, target, date and outcomes here. Check each
example with a real model, trace/feedback delivery, SSE through the Apps proxy, browser reload and
explicit draft acceptance. Use a named profile rather than the CLI default.
