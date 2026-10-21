"""The agent runtime's HTTP surface, called the way the app calls it (in-process ASGI)."""

import httpx
import pytest

from backend.agents.server import create_agent_app
from backend.contracts.agent_contract_v1 import AgentRunRequest, AgentRunStatus
from backend.services.agent_client import AgentClient, AgentRemoteError, AgentRunNotFound
from tests.contracts.test_validation import make_request
from tests.helpers import fake_runtime


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
