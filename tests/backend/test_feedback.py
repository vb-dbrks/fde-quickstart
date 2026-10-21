"""Users' feedback on agent output: stored in Lakebase, then delivered to the run's trace."""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.domain.models import Feedback
from backend.services import feedback as feedback_service
from tests.backend.test_agent_runs import poll, start
from tests.conftest import create_brief
from tests.helpers import VIEWER, RecordingTracer, as_user, fake_runtime, use_runtime


@pytest.fixture
def tracer(app: FastAPI, client: httpx.AsyncClient) -> RecordingTracer:
    """Runs get trace ids, and feedback sent to the agent is kept for inspection."""
    recording = RecordingTracer()
    use_runtime(app, fake_runtime(recording))
    return recording


async def generated_brief(client: httpx.AsyncClient) -> tuple[dict[str, Any], str]:
    document = await create_brief(client)
    run = await poll(client, (await start(client, document["id"])).json()["id"])
    return document, run["id"]


async def rate(
    client: httpx.AsyncClient, document_id: str, field_path: str, **body: Any
) -> httpx.Response:
    return await client.put(
        f"/api/documents/{document_id}/fields/{field_path}/rating",
        json={"rating": False, **body},
        headers=as_user("editor@example.com"),
    )


async def rows(sessions: async_sessionmaker[AsyncSession]) -> list[Feedback]:
    async with sessions() as db:
        return list(await db.scalars(select(Feedback).order_by(Feedback.created_at)))


async def test_a_field_rating_reaches_the_trace(
    client: httpx.AsyncClient,
    editor: str,
    tracer: RecordingTracer,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    document, run_id = await generated_brief(client)
    response = await rate(
        client,
        document["id"],
        "brief.risks",
        reasons=["unsupported_by_sources", "missing_detail"],
        comment="The second risk is not in the notes.",
    )
    assert response.status_code == 200
    assert response.json() == {
        "rating": False,
        "reasons": ["missing_detail", "unsupported_by_sources"],
        "comment": "The second risk is not in the notes.",
    }

    [sent] = tracer.recorded
    assert (sent.trace_id, sent.kind, sent.name, sent.value) == (
        f"tr-{run_id}",
        "feedback",
        "field_rating",
        False,
    )
    assert sent.user == editor
    assert sent.rationale == "The second risk is not in the notes."
    assert sent.metadata == {
        "app_agent_run_id": run_id,
        "run_kind": "generate",
        "document_id": document["id"],
        "document_type": "brief",
        "field_path": "brief.risks",
        "reasons": "missing_detail,unsupported_by_sources",
    }
    [row] = await rows(sessions)
    assert (row.sync_status, row.assessment_id) == ("synced", "a-1")

    fresh = (await client.get(f"/api/documents/{document['id']}", headers=as_user(editor))).json()
    risks = next(f for f in fresh["fields"] if f["field_path"] == "brief.risks")
    assert risks["my_rating"]["rating"] is False


async def test_changing_a_rating_replaces_the_one_on_the_trace(
    client: httpx.AsyncClient,
    editor: str,
    tracer: RecordingTracer,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    document, _ = await generated_brief(client)
    await rate(client, document["id"], "brief.summary")
    await rate(client, document["id"], "brief.summary")  # same rating again: nothing new to send
    await rate(client, document["id"], "brief.summary", rating=True, reasons=["accurate"])

    first, second = tracer.recorded
    assert (first.value, first.replaces) == (False, None)
    assert (second.value, second.replaces) == (True, "a-1")
    assert first.feedback_id != second.feedback_id
    [row] = await rows(sessions)
    assert (row.revision, row.assessment_id) == (2, "a-2")


async def test_only_values_the_agent_wrote_can_be_rated(
    client: httpx.AsyncClient, editor: str, tracer: RecordingTracer
) -> None:
    document, _ = await generated_brief(client)
    assert (await rate(client, document["id"], "brief.goal")).status_code == 409
    response = await rate(client, document["id"], "brief.summary", reasons=["not_a_reason"])
    assert response.status_code == 422


async def test_accepting_and_dismissing_suggestions_are_verdicts(
    client: httpx.AsyncClient, editor: str, tracer: RecordingTracer
) -> None:
    document = await create_brief(client)
    runs = []
    for _ in range(2):
        started = await start(
            client, document["id"], run_kind="enhance_field", field_path="brief.summary"
        )
        runs.append(await poll(client, started.json()["id"]))
    accepted, dismissed = runs
    await client.patch(
        f"/api/documents/{document['id']}/fields/brief.summary",
        json={"value": accepted["suggestion"]["value"], "accepted_from_run_id": accepted["id"]},
        headers=as_user(editor),
    )
    response = await client.post(
        f"/api/agent-runs/{dismissed['id']}/dismiss", headers=as_user(editor)
    )
    assert response.status_code == 204

    verdicts = [(f.name, f.trace_id, f.value) for f in tracer.recorded]
    assert verdicts == [
        ("suggestion_accepted", f"tr-{accepted['id']}", True),
        ("suggestion_accepted", f"tr-{dismissed['id']}", False),
    ]


async def test_editing_a_value_the_agent_wrote_records_the_correction(
    client: httpx.AsyncClient, editor: str, tracer: RecordingTracer
) -> None:
    document, run_id = await generated_brief(client)
    url = f"/api/documents/{document['id']}/fields"
    await client.patch(f"{url}/brief.risks", json={"value": ["Real risk"]}, headers=as_user(editor))
    await client.patch(f"{url}/brief.goal", json={"value": "New goal"}, headers=as_user(editor))

    [correction] = tracer.recorded  # the goal was the user's own: no feedback on the agent
    assert (correction.kind, correction.name, correction.value) == (
        "expectation",
        "brief__risks",  # Databricks rejects "." in assessment names
        ["Real risk"],
    )
    assert correction.metadata["field_path"] == "brief.risks"
    assert correction.trace_id == f"tr-{run_id}"


async def test_answers_are_rated_in_your_own_conversations(
    client: httpx.AsyncClient, editor: str, tracer: RecordingTracer
) -> None:
    document = await create_brief(client)
    thread = (
        await client.post(
            f"/api/documents/{document['id']}/threads", json={}, headers=as_user(editor)
        )
    ).json()
    run = await poll(
        client,
        (
            await start(
                client,
                document["id"],
                run_kind="assistant_turn",
                thread_id=thread["id"],
                message="Hi",
            )
        ).json()["id"],
    )
    messages = (
        await client.get(f"/api/threads/{thread['id']}/messages", headers=as_user(editor))
    ).json()
    answer = next(m for m in messages if m["role"] == "assistant")

    url = f"/api/messages/{answer['id']}/rating"
    response = await client.put(url, json={"rating": True}, headers=as_user(editor))
    assert response.status_code == 200
    [sent] = tracer.recorded
    assert (sent.name, sent.trace_id) == ("answer_rating", f"tr-{run['id']}")
    assert sent.metadata["message_id"] == str(answer["id"])
    assert sent.metadata["thread_id"] == thread["id"]

    rated = (
        await client.get(f"/api/threads/{thread['id']}/messages", headers=as_user(editor))
    ).json()
    assert next(m for m in rated if m["id"] == answer["id"])["my_rating"]["rating"] is True
    assert (
        await client.put(url, json={"rating": False}, headers=as_user(VIEWER))
    ).status_code == 404


async def test_feedback_on_untraced_runs_stays_in_the_app(
    client: httpx.AsyncClient, editor: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Locally (no MLflow) runs have no trace: feedback is kept, with nothing to deliver."""
    document, _ = await generated_brief(client)
    assert (await rate(client, document["id"], "brief.summary")).status_code == 200
    [row] = await rows(sessions)
    assert (row.trace_id, row.sync_status) == (None, "skipped")


async def test_undelivered_feedback_is_retried_with_backoff(
    client: httpx.AsyncClient,
    app: FastAPI,
    editor: str,
    tracer: RecordingTracer,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    document, _ = await generated_brief(client)
    tracer.fail = True  # the trace store is down
    await rate(client, document["id"], "brief.summary")
    [row] = await rows(sessions)
    assert (row.sync_status, row.sync_attempts) == ("pending", 1)
    assert row.next_attempt_at is not None
    assert row.next_attempt_at > datetime.now(UTC)

    sender = app.state.feedback_sender
    assert await sender.sweep() == 0  # not due yet
    tracer.fail = False
    async with sessions() as db:
        await db.execute(
            update(Feedback).values(next_attempt_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await db.commit()
    assert await sender.sweep() == 1
    [row] = await rows(sessions)
    assert (row.sync_status, row.assessment_id) == ("synced", "a-1")


async def test_feedback_that_breaks_the_contract_is_not_retried(
    client: httpx.AsyncClient,
    app: FastAPI,
    editor: str,
    tracer: RecordingTracer,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    document, _ = await generated_brief(client)
    await rate(client, document["id"], "brief.summary")
    async with sessions() as db:  # a value the contract rejects: ratings are booleans
        await db.execute(update(Feedback).values(value="great", sync_status="pending"))
        await db.commit()
        row_id = await db.scalar(select(Feedback.id))
    assert row_id is not None
    async with sessions() as db:
        await feedback_service.deliver(db, app.state.agent_client, row_id)
    [row] = await rows(sessions)
    assert (row.sync_status, row.sync_attempts) == ("failed", 1)
