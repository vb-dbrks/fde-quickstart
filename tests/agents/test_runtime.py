from typing import Any

import pytest

from backend.agents.runtime import (
    AgentRunFailed,
    AgentRuntime,
    InlineExecutor,
    RequestRejected,
    Steps,
)
from backend.contracts.agent_contract_v1 import (
    AgentOutput,
    AgentRunRequest,
    OutputField,
    OutputMeta,
)
from backend.contracts.field_catalog import load_field_catalog
from tests.contracts.test_validation import make_request
from tests.helpers import fake_runtime


def runtime_with(runner: Any, **options: Any) -> AgentRuntime:
    return AgentRuntime(
        {"generate": runner, "enhance_field": runner, "assistant_turn": runner},
        catalog=load_field_catalog(),
        executor=InlineExecutor(),
        **options,
    )


def test_a_fake_generate_run_succeeds_with_every_step_completed() -> None:
    runtime = fake_runtime()
    accepted = runtime.submit(make_request())
    assert accepted.status == "accepted"
    assert [step.status for step in accepted.step_history] == ["pending"] * 3

    done = runtime.poll("run-1")
    assert done is not None
    assert done.status == "succeeded"
    assert [step.status for step in done.step_history] == ["completed"] * 3
    assert done.output is not None
    assert {f.field_path for f in done.output.fields} == {
        "brief.summary",
        "brief.key_points",
        "brief.risks",
        "brief.next_steps",
    }
    assert all(f.citations[0].source_document_id == "s1" for f in done.output.fields)


def test_resubmitting_a_run_returns_the_existing_one() -> None:
    calls: list[str] = []

    def runner(request: AgentRunRequest, steps: Steps) -> AgentOutput:
        calls.append(request.app_agent_run_id)
        return fake_runtime()._runners["generate"](request, steps)

    runtime = runtime_with(runner)
    runtime.submit(make_request())
    again = runtime.submit(make_request())
    assert again.status == "succeeded"
    assert calls == ["run-1"]


def test_an_injected_failure_fails_the_run_at_that_step() -> None:
    runtime = fake_runtime(fake_agent_fail_at="drafting_fields")
    runtime.submit(make_request())
    run = runtime.poll("run-1")
    assert run is not None
    assert run.status == "failed"
    assert run.error is not None
    assert (run.error.code, run.error.retryable) == ("MODEL_ERROR", True)
    assert [s.status for s in run.step_history] == ["completed", "failed", "pending"]


def test_output_that_breaks_the_contract_fails_as_output_invalid() -> None:
    def runner(request: AgentRunRequest, steps: Steps) -> AgentOutput:
        bad = OutputField(
            field_path="brief.title",
            value="x",
            confidence="low",
            confidence_reason="",
            reasoning="",
        )
        return AgentOutput(fields=[bad], meta=OutputMeta(runner="fake", agent_version="t"))

    runtime = runtime_with(runner)
    runtime.submit(make_request())
    run = runtime.poll("run-1")
    assert run is not None
    assert run.error is not None
    assert run.error.code == "OUTPUT_INVALID"
    assert "not requested" in run.error.message


def test_runner_errors_are_reported_without_crashing() -> None:
    def explode(request: AgentRunRequest, steps: Steps) -> AgentOutput:
        raise RuntimeError("boom")

    def known(request: AgentRunRequest, steps: Steps) -> AgentOutput:
        raise AgentRunFailed("MODEL_ERROR", "endpoint down", retryable=True)

    for runner, code in ((explode, "INTERNAL_ERROR"), (known, "MODEL_ERROR")):
        runtime = runtime_with(runner)
        runtime.submit(make_request())
        run = runtime.poll("run-1")
        assert run is not None
        assert run.error is not None
        assert run.error.code == code


def test_requests_breaking_catalog_rules_are_rejected() -> None:
    request = make_request("enhance_field", enhance_context={"field_path": "brief.title"})
    with pytest.raises(RequestRejected, match="not an agent field"):
        fake_runtime().submit(request)


def test_old_finished_runs_are_evicted() -> None:
    runtime = runtime_with(fake_runtime()._runners["generate"], max_runs_kept=2)
    for n in range(3):
        runtime.submit(make_request().model_copy(update={"app_agent_run_id": f"run-{n}"}))
    assert runtime.poll("run-0") is None
    assert runtime.poll("run-2") is not None


def test_unknown_runs_are_not_found() -> None:
    assert fake_runtime().poll("nope") is None
