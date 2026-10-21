"""The agent runtime's HTTP surface, called the way the app calls it (in-process ASGI)."""

import httpx
import pytest

from backend.agents.runtime import AgentRuntime, InlineExecutor
from backend.agents.server import create_agent_app
from backend.agents.tracing import NoopTracer
from backend.contracts.agent_contract_v1 import AgentRunRequest, AgentRunStatus, FeedbackRequest
from backend.contracts.field_catalog import load_field_catalog
from backend.services.agent_client import AgentClient, AgentRemoteError, AgentRunNotFound
from tests.contracts.test_validation import make_request
from tests.helpers import RecordingTracer, fake_runtime


def agent_client() -> AgentClient:
    return AgentClient.in_process(create_agent_app(fake_runtime()), timeout=5)


async def test_submit_then_poll_round_trips_the_contract() -> None:
    client = agent_client()
    accepted = await client.submit(make_request("assistant_turn"))
    assert accepted.status == "accepted"
    done = await client.poll("run-1")
    assert done.status == "succeeded"
    assert done.output is not None
    assert done.output.answer is not None
    assert "You asked" in done.output.answer.content


async def test_unknown_runs_answer_run_not_found() -> None:
    with pytest.raises(AgentRunNotFound) as excinfo:
        await agent_client().poll("nope")
    assert excinfo.value.status_code == 404
    assert excinfo.value.retryable


async def test_invalid_requests_answer_validation_error() -> None:
    app = create_agent_app(fake_runtime())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://a"
    ) as http:
        response = await http.post("/agent/run", json={"run_kind": "generate"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    bad_field = make_request("enhance_field", enhance_context={"field_path": "brief.title"})
    with pytest.raises(AgentRemoteError) as excinfo:
        await agent_client().submit(bad_field)
    assert excinfo.value.code == "VALIDATION_ERROR"


async def test_contract_endpoint_publishes_the_schemas() -> None:
    contract = await agent_client().contract()
    assert contract["contract_version"] == "v1"
    assert contract["request_schema"] == AgentRunRequest.model_json_schema()
    assert contract["status_schema"] == AgentRunStatus.model_json_schema()
    assert contract["field_catalog_version"] == "v1"
    assert contract["step_vocabulary"]["generate"] == [
        "reading_context",
        "drafting_fields",
        "checking_citations",
    ]
    assert contract["feedback_schema"] == FeedbackRequest.model_json_schema()


def feedback_request(**changes: object) -> FeedbackRequest:
    fields: dict[str, object] = {
        "feedback_id": "fb-1",
        "trace_id": "tr-1",
        "kind": "feedback",
        "name": "field_rating",
        "value": True,
        "user": "editor@example.com",
        "metadata": {"field_path": "brief.summary"},
    }
    return FeedbackRequest.model_validate({**fields, **changes})


def client_with(tracer: NoopTracer) -> AgentClient:
    runtime = AgentRuntime(
        {}, catalog=load_field_catalog(), executor=InlineExecutor(), tracer=tracer
    )
    return AgentClient.in_process(create_agent_app(runtime), timeout=5)


async def test_feedback_is_recorded_on_the_trace() -> None:
    tracer = RecordingTracer()
    result = await client_with(tracer).send_feedback(feedback_request())
    assert (result.recorded, result.assessment_id) == (True, "a-1")
    assert tracer.recorded[0].metadata == {"field_path": "brief.summary"}


async def test_without_tracing_feedback_is_not_recorded() -> None:
    result = await agent_client().send_feedback(feedback_request())
    assert (result.recorded, result.assessment_id) == (False, None)


class RejectingTracer(RecordingTracer):
    """Answers like MLflow does when it refuses an assessment (MlflowException's error_code)."""

    def record_feedback(self, feedback: FeedbackRequest) -> str | None:
        error = ValueError("`assessment_name` must not contain '.'")
        error.error_code = "INVALID_PARAMETER_VALUE"  # type: ignore[attr-defined]
        raise error


async def test_feedback_the_trace_store_rejects_is_not_retryable() -> None:
    with pytest.raises(AgentRemoteError) as excinfo:
        await client_with(RejectingTracer()).send_feedback(feedback_request())
    assert (excinfo.value.code, excinfo.value.retryable) == ("VALIDATION_ERROR", False)


def test_assessment_names_have_no_dots() -> None:
    with pytest.raises(ValueError, match="can't contain"):
        feedback_request(kind="expectation", name="brief.risks", value=["a"])


async def test_a_failing_trace_store_is_a_retryable_error() -> None:
    with pytest.raises(AgentRemoteError) as excinfo:
        await client_with(RecordingTracer(fail=True)).send_feedback(feedback_request())
    assert (excinfo.value.code, excinfo.value.retryable) == ("FEEDBACK_FAILED", True)


def test_ratings_must_be_booleans() -> None:
    with pytest.raises(ValueError, match="booleans"):
        feedback_request(value="great")
    assert feedback_request(kind="expectation", name="brief__risks", value=["a"]).value == ["a"]


async def test_healthz_reports_the_runner_per_run_kind() -> None:
    app = create_agent_app(fake_runtime())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://a"
    ) as http:
        body = (await http.get("/healthz")).json()
    assert body["runners"] == {
        "generate": "fake",
        "enhance_field": "fake",
        "assistant_turn": "fake",
    }
