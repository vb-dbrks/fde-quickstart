"""The template must work without documents and keep provisional output out of saved data."""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.agents.interaction import AgentDefinition, EventEmitter
from backend.contracts.execution import ExecutionRequest
from backend.domain.models import AgentRun, Document, GenerationArtifact, RunEvent
from backend.services.interactions import AgentApplication
from tests.conftest import create_brief
from tests.helpers import OTHER_EDITOR, as_user


async def execute(
    client: httpx.AsyncClient, editor: str, agent: str, payload: dict[str, Any], **kwargs: Any
) -> dict[str, Any]:
    response = await client.post(
        "/api/runs", json={"agent_id": agent, "input": payload, **kwargs}, headers=as_user(editor)
    )
    assert response.status_code == 202, response.text
    run_id = response.json()["id"]
    result = await client.get(f"/api/runs/{run_id}", headers=as_user(editor))
    assert result.status_code == 200, result.text
    body: dict[str, Any] = result.json()
    return body


async def test_chat_uses_sessions_without_documents(
    client: httpx.AsyncClient, editor: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    session = await client.post("/api/sessions", json={"agent_id": "chat"}, headers=as_user(editor))
    assert session.status_code == 201
    sid = session.json()["id"]
    run = await execute(
        client, editor, "chat", {"message": "Hello", "context": "Be concise"}, session_id=sid
    )
    assert run["status"] == "succeeded", run
    assert "Hello" in run["result"]["content"]
    messages = (await client.get(f"/api/sessions/{sid}/messages", headers=as_user(editor))).json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    again = await execute(client, editor, "chat", {"message": "Follow up"}, session_id=sid)
    assert "2 earlier" in again["result"]["content"]
    rating = await client.post(
        f"/api/runs/{run['id']}/feedback", json={"rating": True}, headers=as_user(editor)
    )
    assert rating.status_code == 200, rating.text
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Document)) == 0


async def test_generation_review_is_explicit_and_idempotent(
    client: httpx.AsyncClient, editor: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    run = await execute(client, editor, "generation", {"topic": "AG-UI", "audience": "FDEs"})
    assert run["status"] == "succeeded", run
    async with sessions() as db:
        artifact = await db.get(GenerationArtifact, run["id"])
        assert artifact is not None
        assert artifact.status == "pending"
    value = {**run["result"], "title": "Edited"}
    url = f"/api/runs/{run['id']}/review"
    for _ in range(2):
        accepted = await client.post(
            url, json={"decision": "accepted", "value": value}, headers=as_user(editor)
        )
        assert accepted.status_code == 200, accepted.text
    assert (
        await client.post(url, json={"decision": "rejected"}, headers=as_user(editor))
    ).status_code == 409
    async with sessions() as db:
        artifact = await db.get(GenerationArtifact, run["id"])
        assert artifact is not None
        assert artifact.value["title"] == "Edited"
        assert await db.scalar(select(func.count()).select_from(Document)) == 0


async def test_events_replay_and_terminal_commit(
    client: httpx.AsyncClient, editor: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    run = await execute(client, editor, "chat", {"message": "Stream me"})
    url = f"/api/runs/{run['id']}/events"
    batch = (await client.get(url, headers=as_user(editor))).json()
    events = batch["events"]
    assert events[0]["event"]["type"] == "RUN_STARTED"
    assert events[-1]["event"]["type"] == "RUN_FINISHED"
    assert batch["terminal"]
    assert [e["sequence"] for e in events] == list(range(1, len(events) + 1))
    replay = (await client.get(f"{url}?after=2", headers=as_user(editor))).json()
    assert replay["events"] == events[2:]
    sse = await client.get(url, headers={**as_user(editor), "Accept": "text/event-stream"})
    assert sse.status_code == 200
    assert "event: complete" in sse.text
    async with sessions() as db:
        assert await db.scalar(
            select(func.count()).select_from(RunEvent).where(RunEvent.run_id == run["id"])
        ) == len(events)


async def test_sessions_runs_events_and_results_are_private(
    client: httpx.AsyncClient, editor: str
) -> None:
    run = await execute(client, editor, "generation", {"topic": "Private"})
    for suffix in ("", "/events", "/review", "/tools"):
        assert (
            await client.get(f"/api/runs/{run['id']}{suffix}", headers=as_user(OTHER_EDITOR))
        ).status_code == 404
    assert (
        await client.post(
            f"/api/runs/{run['id']}/review",
            json={"decision": "accepted"},
            headers=as_user(OTHER_EDITOR),
        )
    ).status_code == 404


async def test_fourth_agent_needs_only_registration(
    client: httpx.AsyncClient, editor: str, app: FastAPI
) -> None:
    class Echo(BaseModel):
        value: str

    def echo(request: ExecutionRequest, events: EventEmitter) -> BaseModel:
        return Echo.model_validate(request.input)

    runtime = app.state.agent_runtime.interactions
    runtime.definitions["echo"] = AgentDefinition(
        "echo", "test", "An independent example", Echo, Echo, echo
    )
    app.state.agent_applications["echo"] = AgentApplication("test", Echo, Echo)
    try:
        run = await execute(client, editor, "echo", {"value": "fourth"})
        assert run["result"] == {"value": "fourth"}
        assert run["status"] == "succeeded"
    finally:
        del runtime.definitions["echo"]
        del app.state.agent_applications["echo"]


async def test_invalid_result_is_never_successful(
    client: httpx.AsyncClient, editor: str, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def reject(*args: Any) -> None:
        raise ValueError("Cannot save")

    from dataclasses import replace

    original = app.state.agent_applications["generation"]
    monkeypatch.setitem(
        app.state.agent_applications, "generation", replace(original, finalize=reject)
    )
    run = await execute(client, editor, "generation", {"topic": "Failure"})
    assert run["status"] == "failed"
    assert run["result"] is None
    batch = (await client.get(f"/api/runs/{run['id']}/events", headers=as_user(editor))).json()
    assert batch["events"][-1]["event"]["type"] == "RUN_ERROR"
    assert (
        await client.post(
            f"/api/runs/{run['id']}/review", json={"decision": "accepted"}, headers=as_user(editor)
        )
    ).status_code == 409


async def test_finalization_flush_failure_is_durable_and_replayable(
    client: httpx.AsyncClient,
    editor: str,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    from dataclasses import replace

    async def violate_constraint(db: AsyncSession, run: AgentRun, result: dict[str, Any]) -> None:
        # Fail on savepoint exit, after the runtime has staged its validated result and event.
        db.add_all(
            [GenerationArtifact(run_id=run.id, value=result, status="pending") for _ in range(2)]
        )

    monkeypatch.setitem(
        app.state.agent_applications,
        "generation",
        replace(app.state.agent_applications["generation"], finalize=violate_constraint),
    )
    run = await execute(client, editor, "generation", {"topic": "Constraint failure"})
    assert run["status"] == "failed"
    assert run["result"] is None
    async with sessions() as db:
        stored = await db.get(AgentRun, run["id"])
        assert stored is not None
        assert stored.status == "failed"
        assert stored.error_code == "MATERIALISATION_FAILED"
        assert stored.materialised_at is None
        assert stored.completed_at is not None
        assert await db.get(GenerationArtifact, run["id"]) is None
    url = f"/api/runs/{run['id']}/events"
    batch = (await client.get(url, headers=as_user(editor))).json()
    assert batch["terminal"]
    events = batch["events"]
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    assert events[-1]["event"]["type"] == "RUN_ERROR"
    assert not any(
        event["event"]["type"] == "RUN_FINISHED"
        or event["event"].get("snapshot", {}).get("provisional") is False
        for event in events
    )
    assert (await client.get(url, headers=as_user(editor))).json() == batch
    assert (
        await client.post(
            f"/api/runs/{run['id']}/review", json={"decision": "accepted"}, headers=as_user(editor)
        )
    ).status_code == 409


async def test_document_draft_stays_unsaved_and_detects_conflicts(
    client: httpx.AsyncClient, editor: str
) -> None:
    doc = await create_brief(client)
    run = (
        await client.post(
            f"/api/documents/{doc['id']}/agent-runs",
            json={"run_kind": "generate"},
            headers=as_user(editor),
        )
    ).json()
    await client.get(f"/api/agent-runs/{run['id']}", headers=as_user(editor))
    fresh = (await client.get(f"/api/documents/{doc['id']}", headers=as_user(editor))).json()
    assert next(f for f in fresh["fields"] if f["field_path"] == "brief.summary")["value"] is None
    proposals = (
        await client.get(f"/api/documents/{doc['id']}/proposals", headers=as_user(editor))
    ).json()
    assert len(proposals) == 4
    assert (
        await client.patch(
            f"/api/documents/{doc['id']}/fields/brief.summary",
            json={"value": "Manual edit"},
            headers=as_user(editor),
        )
    ).status_code == 200
    values = {p["field_path"]: p["output"]["value"] for p in proposals}
    url = f"/api/documents/{doc['id']}/proposals/{run['id']}/review"
    conflict = await client.post(url, json={"accept": values}, headers=as_user(editor))
    assert conflict.status_code == 409, conflict.text
    values.pop("brief.summary")
    for _ in range(2):
        accepted = await client.post(url, json={"accept": values}, headers=as_user(editor))
        assert accepted.status_code == 200, accepted.text
    fresh = (await client.get(f"/api/documents/{doc['id']}", headers=as_user(editor))).json()
    assert fresh["current_version"] == 1
    assert (
        next(f for f in fresh["fields"] if f["field_path"] == "brief.summary")["value"]
        == "Manual edit"
    )


async def test_missing_agent_runtime_is_explicit(
    client: httpx.AsyncClient, editor: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with sessions() as db:
        run = AgentRun(
            agent_id="chat",
            contract_version="v2",
            run_kind="chat",
            triggered_by=editor,
            status="running",
            request_payload={},
            step_history=[],
        )
        db.add(run)
        await db.commit()
        run_id = run.id
    response = await client.get(f"/api/runs/{run_id}", headers=as_user(editor))
    assert response.json()["status"] == "failed"


@pytest.mark.parametrize("enabled", ["chat,generation", "chat,documents", "generation,documents"])
async def test_each_example_can_be_disabled(
    client: httpx.AsyncClient,
    editor: str,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    enabled: str,
) -> None:
    from backend.agents.config import AgentSettings
    from backend.agents.runtime import InlineExecutor
    from backend.agents.server import build_runtime
    from backend.main import create_app

    def no_catalog() -> None:
        raise AssertionError("Independent examples must not load the document catalog")

    if "documents" not in enabled:
        monkeypatch.setattr("backend.main.load_field_catalog", no_catalog)
        monkeypatch.setattr("backend.agents.server.load_field_catalog", no_catalog)
    runtime = build_runtime(
        AgentSettings(_env_file=None, enabled_examples=enabled, fake_agent_step_seconds=0),
        executor=InlineExecutor(),
    )
    isolated = create_app(
        app.state.settings.model_copy(update={"enabled_examples": enabled}), agent_runtime=runtime
    )
    async with (
        isolated.router.lifespan_context(isolated),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=isolated), base_url="http://test"
        ) as http,
    ):
        assert (await http.get("/api/examples")).json() == sorted(enabled.split(","))
        for name, payload in [("chat", {"message": "Hi"}), ("generation", {"topic": "Test"})]:
            if name in enabled:
                assert (await execute(http, editor, name, payload))["status"] == "succeeded"
            else:
                assert (
                    await http.post(
                        "/api/runs",
                        json={"agent_id": name, "input": payload},
                        headers=as_user(editor),
                    )
                ).status_code == 404
        if "documents" not in enabled:
            assert (await http.get("/api/documents", headers=as_user(editor))).status_code == 404


async def test_duplicate_submission_creates_one_run_and_one_pair_of_messages(
    client: httpx.AsyncClient, editor: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    from backend.domain.models import Message

    sid = (
        await client.post("/api/sessions", json={"agent_id": "chat"}, headers=as_user(editor))
    ).json()["id"]
    body = {"agent_id": "chat", "session_id": sid, "input": {"message": "Once"}}
    headers = {**as_user(editor), "Idempotency-Key": "one-chat-turn"}
    first = await client.post("/api/runs", json=body, headers=headers)
    second = await client.post("/api/runs", json=body, headers=headers)
    assert first.json()["id"] == second.json()["id"]
    for _ in range(2):
        await client.get(f"/api/runs/{first.json()['id']}/events", headers=as_user(editor))
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(AgentRun)) == 1
        assert await db.scalar(select(func.count()).select_from(Message)) == 2
    assert (
        await client.get(f"/api/sessions/{sid}/messages", headers=as_user(OTHER_EDITOR))
    ).status_code == 404


async def test_frontend_tool_claim_and_outcome_are_authorized_and_idempotent(
    client: httpx.AsyncClient, editor: str
) -> None:
    document = await create_brief(client)
    thread = (
        await client.post(
            f"/api/documents/{document['id']}/threads", json={}, headers=as_user(editor)
        )
    ).json()
    run = (
        await client.post(
            f"/api/documents/{document['id']}/agent-runs",
            json={
                "run_kind": "assistant_turn",
                "thread_id": thread["id"],
                "message": "Show the summary",
            },
            headers=as_user(editor),
        )
    ).json()
    url = f"/api/runs/{run['id']}"
    batch = (await client.get(f"{url}/events", headers=as_user(editor))).json()
    calls = [e["event"] for e in batch["events"] if e["event"]["type"] == "TOOL_CALL_END"]
    assert len(calls) == 1
    tool = f"{url}/tools/{calls[0]['toolCallId']}"
    assert (
        await client.post(f"{tool}/claim", json={}, headers=as_user(OTHER_EDITOR))
    ).status_code == 404
    assert (await client.post(f"{tool}/claim", json={}, headers=as_user(editor))).json() == {
        "execute": True
    }
    assert (await client.post(f"{tool}/claim", json={}, headers=as_user(editor))).json() == {
        "execute": False
    }
    for _ in range(2):
        assert (
            await client.post(tool, json={"status": "completed"}, headers=as_user(editor))
        ).json() == {"status": "completed"}
    assert (
        await client.post(f"{url}/tools/invented", json={}, headers=as_user(editor))
    ).status_code == 404


async def test_subscription_rechecks_access_after_connection(
    client: httpx.AsyncClient, editor: str, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.api import interactions as api
    from backend.domain.errors import ForbiddenError

    run = (
        await client.post(
            "/api/runs",
            json={"agent_id": "chat", "input": {"message": "Wait"}},
            headers=as_user(editor),
        )
    ).json()
    from backend.auth.principal import resolve_principal

    resolve = resolve_principal
    checks = 0

    async def renewed(*args: Any) -> Any:
        nonlocal checks
        checks += 1
        if checks > 1:
            raise ForbiddenError("Access revoked")
        return await resolve(*args)

    async def no_refresh(*args: Any) -> None:
        return None

    monkeypatch.setattr(api, "resolve_principal", renewed)
    monkeypatch.setattr(app.state, "refresh_run", no_refresh)
    response = await client.get(
        f"/api/runs/{run['id']}/events", headers={**as_user(editor), "Accept": "text/event-stream"}
    )
    assert "event: access-denied" in response.text
    assert "event: complete" not in response.text
    assert checks == 2
