"""Checks a running agent against the contract, over HTTP.

    make agent                                          # in another terminal
    make contract-live AGENT_API_BASE=http://localhost:9000

Skipped unless AGENT_API_BASE is set. For an agent deployed as its own Databricks App, also pass
PROFILE=<cli-profile>: requests then carry that profile's token.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from backend.contracts.agent_contract_v1 import (
    AGENT_CONTRACT_VERSION,
    RUN_KINDS,
    STEP_VOCABULARY,
    AgentRunKind,
    AgentRunStatus,
)
from backend.contracts.field_catalog import load_field_catalog
from backend.contracts.validation import check_output
from backend.services.agent_client import AgentClient, AgentRunNotFound
from tests.contracts.test_validation import make_request

BASE = os.environ.get("AGENT_API_BASE")
RUN_TIMEOUT_SECONDS = 120

pytestmark = pytest.mark.skipif(not BASE, reason="set AGENT_API_BASE to check a running agent")


@pytest.fixture
async def agent() -> AsyncIterator[AgentClient]:
    assert BASE is not None
    client = AgentClient.over_http(BASE, timeout=30)  # a remote agent gets the profile's token
    yield client
    await client.aclose()


async def test_the_agent_serves_this_contract_version(agent: AgentClient) -> None:
    document = await agent.contract()
    assert document["contract_version"] == AGENT_CONTRACT_VERSION
    assert document["run_kinds"] == list(RUN_KINDS)
    assert document["step_vocabulary"] == {k: list(v) for k, v in STEP_VOCABULARY.items()}


@pytest.mark.parametrize("run_kind", RUN_KINDS)
async def test_runs_finish_within_the_contract(agent: AgentClient, run_kind: AgentRunKind) -> None:
    run_id = f"live-{uuid.uuid4()}"
    request = make_request(run_kind).model_copy(
        update={"app_agent_run_id": run_id, "idempotency_key": run_id}
    )
    status = await agent.submit(request)
    assert status.app_agent_run_id == run_id
    status = await _wait(agent, run_id, status)
    assert status.status == "succeeded", status.error
    assert status.output is not None
    assert check_output(request, status.output, load_field_catalog()) == []
    assert [step.name for step in status.step_history] == list(STEP_VOCABULARY[run_kind])


async def test_unknown_runs_are_not_found(agent: AgentClient) -> None:
    with pytest.raises(AgentRunNotFound):
        await agent.poll(f"never-submitted-{uuid.uuid4()}")


async def _wait(agent: AgentClient, run_id: str, status: AgentRunStatus) -> AgentRunStatus:
    async with asyncio.timeout(RUN_TIMEOUT_SECONDS):
        while status.status not in ("succeeded", "failed"):
            await asyncio.sleep(1)
            status = await agent.poll(run_id)
    return status


@pytest.mark.parametrize(
    ("agent_id", "payload"),
    [("chat", {"message": "Hello"}), ("generation", {"topic": "AG-UI", "audience": "FDEs"})],
)
async def test_v2_runs_over_http(
    agent: AgentClient, agent_id: str, payload: dict[str, str]
) -> None:
    from backend.contracts.execution import ExecutionRequest

    run_id = str(uuid.uuid4())
    assert agent_id in {definition.id for definition in await agent.definitions()}
    request = ExecutionRequest(
        run_id=run_id,
        thread_id=run_id,
        agent_id=agent_id,
        initiator="smoke@example.com",
        input=payload,
    )
    await agent.submit_execution(request)
    await agent.submit_execution(request)
    async with asyncio.timeout(RUN_TIMEOUT_SECONDS):
        while True:
            status = await agent.poll_execution(run_id, 0)
            if status.status in ("succeeded", "failed"):
                break
            await asyncio.sleep(0.1)
    assert status.status == "succeeded", status.error
    assert status.result
    assert status.events
    assert (await agent.poll_execution(run_id, status.cursor)).events == []


async def test_application_collects_and_reviews_a_standalone_http_run(
    app: FastAPI, client: httpx.AsyncClient, editor: str
) -> None:
    from backend.main import create_app
    from tests.helpers import as_user

    settings = app.state.settings.model_copy(
        update={"agent_transport": "http", "agent_api_base": BASE}
    )
    application = create_app(settings)
    async with (
        application.router.lifespan_context(application),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://test"
        ) as http,
    ):
        started = await http.post(
            "/api/runs",
            json={"agent_id": "generation", "input": {"topic": "HTTP transport"}},
            headers=as_user(editor),
        )
        assert started.status_code == 202
        run_id = started.json()["id"]
        async with asyncio.timeout(RUN_TIMEOUT_SECONDS):
            while True:
                # Background collection uses this exact callback with no browser attached.
                async with application.state.sessionmaker() as db:
                    run = await application.state.refresh_run(db, run_id)
                if run.status in ("succeeded", "failed"):
                    break
                await asyncio.sleep(0.1)
        assert run.status == "succeeded"
        replay = (await http.get(f"/api/runs/{run_id}/events", headers=as_user(editor))).json()
        assert replay["events"][-1]["event"]["type"] == "RUN_FINISHED"
        review = (await http.get(f"/api/runs/{run_id}/review", headers=as_user(editor))).json()
        assert review["status"] == "pending"
        assert (
            await http.post(
                f"/api/runs/{run_id}/review", json={"decision": "accepted"}, headers=as_user(editor)
            )
        ).status_code == 200
