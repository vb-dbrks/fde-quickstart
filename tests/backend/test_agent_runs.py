"""The app side of the handoff: start a run, poll it, materialise the output (ADR 0003/0004)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.auth.roles import Role
from backend.contracts.agent_contract_v1 import AgentOutput, OutputField, OutputMeta
from backend.contracts.field_catalog import load_field_catalog
from backend.domain.models import AgentRun, Document, DocumentVersion, Message
from backend.services.agent_runs import RunDeps, refresh_run
from backend.services.materialise import MaterialisationError, materialise_generate
from backend.workers.agent_run_poller import AgentRunPoller
from tests.conftest import create_brief, grant
from tests.helpers import (
    EDITOR,
    OTHER_EDITOR,
    VIEWER,
    as_user,
    broken_agent_client,
    fake_runtime,
    use_runtime,
)


async def start(
    client: httpx.AsyncClient, document_id: str, email: str = EDITOR, **body: Any
) -> httpx.Response:
    return await client.post(
        f"/api/documents/{document_id}/agent-runs",
        json={"run_kind": "generate", **body},
        headers=as_user(email),
    )


async def poll(client: httpx.AsyncClient, run_id: str, email: str = EDITOR) -> dict[str, Any]:
    response = await client.get(f"/api/agent-runs/{run_id}", headers=as_user(email))
    assert response.status_code == 200, response.text
    run: dict[str, Any] = response.json()
    return run


async def test_generate_materialises_fields_with_provenance(
    client: httpx.AsyncClient, editor: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    source = await create_brief(
        client, **{"brief.title": "Survey results", "brief.goal": "Setup is slow."}
    )
    document = await create_brief(client)
    started = await start(
        client, document["id"], source_document_ids=[source["id"]], instruction="Keep it short."
    )
    assert started.status_code == 202
    assert started.json()["status"] == "accepted"

    run = await poll(client, started.json()["id"])
    assert run["status"] == "succeeded"
    assert [s["status"] for s in run["step_history"]] == ["completed"] * 3

    fresh = (await client.get(f"/api/documents/{document['id']}", headers=as_user(editor))).json()
    fields = {f["field_path"]: f for f in fresh["fields"]}
    summary = fields["brief.summary"]
    assert summary["source"] == "agent"
    assert summary["confidence"] == "medium"
    assert summary["agent_run_id"] == run["id"]
    assert summary["citations"][0]["source_document_id"] == source["id"]
    assert isinstance(fields["brief.risks"]["value"], list)
    assert fields["brief.goal"]["source"] == "user"
    assert fresh["current_version"] == 1

    versions = (
        await client.get(f"/api/documents/{document['id']}/versions", headers=as_user(editor))
    ).json()
    assert [v["version"] for v in versions] == [1]
    assert versions[0]["snapshot"]["brief.summary"] == summary["value"]
    audit = (
        await client.get(f"/api/documents/{document['id']}/audit", headers=as_user(editor))
    ).json()
    assert sum(a["action"] == "generate" for a in audit) == 4

    # The stored request carries the full context the agent saw (ADR 0004).
    async with sessions() as db:
        stored = await db.get(AgentRun, run["id"])
        assert stored is not None
        payload = stored.request_payload
        assert (
            payload["document_context"]["fields"]["brief.goal"]
            == "Reach first value in three days."
        )
        assert payload["document_context"]["user_instruction"] == "Keep it short."
        assert payload["source_documents"][0]["source_document_id"] == source["id"]
        assert stored.materialised_at is not None

    # Polling again is a no-op: no second version.
    assert (await poll(client, run["id"]))["status"] == "succeeded"
    async with sessions() as db:
        count = await db.scalar(select(func.count()).select_from(DocumentVersion))
        assert count == 1

    notifications = (await client.get("/api/notifications", headers=as_user(editor))).json()
    assert notifications["items"][0]["kind"] == "agent_run_succeeded"


async def test_regenerating_a_scope_rewrites_only_those_fields(
    client: httpx.AsyncClient, editor: str
) -> None:
    document = await create_brief(client)
    await poll(client, (await start(client, document["id"])).json()["id"])
    second = await start(client, document["id"], scope=["brief.risks"])
    await poll(client, second.json()["id"])
    audit = (
        await client.get(f"/api/documents/{document['id']}/audit", headers=as_user(editor))
    ).json()
    assert [a["field_path"] for a in audit if a["action"] == "regenerate"] == ["brief.risks"]


async def test_viewers_cannot_run_agents(client: httpx.AsyncClient, editor: str) -> None:
    document = await create_brief(client)
    await client.put(
        f"/api/documents/{document['id']}/access",
        json={"email": VIEWER, "access": "view"},
        headers=as_user(editor),
    )
    assert (await start(client, document["id"], email=VIEWER)).status_code == 403


async def test_sources_the_user_cannot_see_are_left_out(
    client: httpx.AsyncClient, editor: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await grant(client, OTHER_EDITOR, Role.EDITOR)
    private = await create_brief(client, email=OTHER_EDITOR)
    document = await create_brief(client)
    run = (await start(client, document["id"], source_document_ids=[private["id"]])).json()
    async with sessions() as db:
        stored = await db.get(AgentRun, run["id"])
        assert stored is not None
        assert stored.request_payload.get("source_documents", []) == []


async def test_enhance_suggests_and_accepting_records_provenance(
    client: httpx.AsyncClient, editor: str
) -> None:
    document = await create_brief(client)
    started = await start(
        client,
        document["id"],
        run_kind="enhance_field",
        field_path="brief.summary",
        instruction="Shorter",
    )
    assert started.json()["field_path"] == "brief.summary"
    run = await poll(client, started.json()["id"])
    suggestion = run["suggestion"]
    assert suggestion["field_path"] == "brief.summary"
    assert "Shorter" in suggestion["value"]

    # Nothing changes until the user accepts.
    fresh = (await client.get(f"/api/documents/{document['id']}", headers=as_user(editor))).json()
    assert next(f for f in fresh["fields"] if f["field_path"] == "brief.summary")["value"] is None

    accepted = await client.patch(
        f"/api/documents/{document['id']}/fields/brief.summary",
        json={"value": suggestion["value"], "accepted_from_run_id": run["id"]},
        headers=as_user(editor),
    )
    assert accepted.status_code == 200
    assert accepted.json()["source"] == "agent"
    assert accepted.json()["agent_run_id"] == run["id"]
    audit = (
        await client.get(f"/api/documents/{document['id']}/audit", headers=as_user(editor))
    ).json()
    assert audit[0]["action"] == "accept_suggestion"


async def test_enhance_requires_an_agent_field(client: httpx.AsyncClient, editor: str) -> None:
    document = await create_brief(client)
    response = await start(
        client, document["id"], run_kind="enhance_field", field_path="brief.title"
    )
    assert response.status_code == 422


async def test_assistant_turns_keep_the_conversation_in_the_app(
    client: httpx.AsyncClient, editor: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    document = await create_brief(client)
    thread = (
        await client.post(
            f"/api/documents/{document['id']}/threads", json={}, headers=as_user(editor)
        )
    ).json()
    for message in ("First question", "Second question"):
        started = await start(
            client,
            document["id"],
            run_kind="assistant_turn",
            thread_id=thread["id"],
            message=message,
        )
        run = await poll(client, started.json()["id"])
        assert run["status"] == "succeeded"
        assert message in run["answer"]

    messages = (
        await client.get(f"/api/threads/{thread['id']}/messages", headers=as_user(editor))
    ).json()
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    async with sessions() as db:
        last = await db.get(AgentRun, run["id"])
        assert last is not None
        history = last.request_payload["assistant_context"]["history"]
        assert [h["content"] for h in history][:1] == ["First question"]

    # Conversations are private to their owner.
    await client.put(
        f"/api/documents/{document['id']}/access",
        json={"email": VIEWER, "access": "view"},
        headers=as_user(editor),
    )
    assert (
        await client.get(f"/api/threads/{thread['id']}/messages", headers=as_user(VIEWER))
    ).status_code == 404
    assert (
        await client.get(f"/api/agent-runs/{run['id']}", headers=as_user(VIEWER))
    ).status_code == 404
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Message)) == 4


async def test_agent_failures_fail_the_run_and_notify(
    client: httpx.AsyncClient, app: FastAPI, editor: str
) -> None:
    use_runtime(app, fake_runtime(fake_agent_fail_at="drafting_fields"))
    document = await create_brief(client)
    run = await poll(client, (await start(client, document["id"])).json()["id"])
    assert (run["status"], run["error_code"]) == ("failed", "MODEL_ERROR")
    notes = (await client.get("/api/notifications", headers=as_user(editor))).json()
    assert notes["items"][0]["kind"] == "agent_run_failed"


async def test_a_restarted_agent_loses_the_run(
    client: httpx.AsyncClient, app: FastAPI, editor: str
) -> None:
    document = await create_brief(client)
    started = (await start(client, document["id"])).json()
    use_runtime(app, fake_runtime())  # a fresh runtime has never seen the run
    run = await poll(client, started["id"])
    assert (run["status"], run["error_code"]) == ("failed", "AGENT_RUN_LOST")


async def test_an_unreachable_agent_fails_the_submit(
    client: httpx.AsyncClient, app: FastAPI, editor: str
) -> None:
    app.state.agent_client = broken_agent_client()
    document = await create_brief(client)
    started = await start(client, document["id"])
    assert started.status_code == 202
    assert (started.json()["status"], started.json()["error_code"]) == ("failed", "SUBMIT_FAILED")


async def test_slow_runs_time_out(
    client: httpx.AsyncClient, app: FastAPI, editor: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    document = await create_brief(client)
    started = (await start(client, document["id"])).json()
    async with sessions() as db:
        await db.execute(
            update(AgentRun)
            .where(AgentRun.id == started["id"])
            .values(created_at=datetime.now(UTC) - timedelta(hours=1))
        )
        await db.commit()
    run = await poll(client, started["id"])
    assert (run["status"], run["error_code"]) == ("failed", "TIMEOUT")


async def test_the_poller_finishes_runs_nobody_watches(
    client: httpx.AsyncClient, app: FastAPI, editor: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    document = await create_brief(client)
    started = (await start(client, document["id"])).json()
    deps = RunDeps(
        client=app.state.agent_client,
        catalog=load_field_catalog(),
        settings=app.state.settings,
        notifier=app.state.notifier,
    )

    async def refresh(db: AsyncSession, run_id: str) -> object:
        return await refresh_run(db, deps, run_id)

    poller = AgentRunPoller(sessions, refresh, interval_seconds=60)
    assert await poller.sweep() == 1
    async with sessions() as db:
        run = await db.get(AgentRun, started["id"])
        assert run is not None
        assert run.status == "succeeded"
        assert run.materialised_at is not None
    assert await poller.sweep() == 0


async def test_materialisation_rechecks_the_output(
    client: httpx.AsyncClient, editor: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    document = await create_brief(client)
    started = (await start(client, document["id"])).json()
    bad = AgentOutput(
        fields=[
            OutputField(
                field_path="brief.title",
                value="x",
                confidence="low",
                confidence_reason="",
                reasoning="",
            )
        ],
        meta=OutputMeta(runner="fake", agent_version="t"),
    )
    async with sessions() as db:
        run = await db.get(AgentRun, started["id"])
        doc = await db.get(Document, document["id"])
        assert run is not None
        assert doc is not None
        with pytest.raises(MaterialisationError, match="not requested"):
            await materialise_generate(
                db, run=run, document=doc, output=bad, catalog=load_field_catalog(), trace_id=None
            )
