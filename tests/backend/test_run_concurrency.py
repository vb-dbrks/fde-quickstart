"""Runs touched by several requests at once: the UI's lazy refresh, the poller, other app instances."""

from collections.abc import Awaitable, Callable

import httpx
from fastapi import FastAPI
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.contracts.agent_contract_v1 import AgentRunRequest, AgentRunStatus
from backend.contracts.field_catalog import load_field_catalog
from backend.domain.models import AgentRun, Document, DocumentVersion, Notification
from backend.services.agent_client import AgentClient
from backend.services.agent_runs import RunDeps, queued_grace, refresh_run
from backend.services.materialise import materialise_generate
from backend.settings import Settings
from tests.backend.test_agent_runs import start
from tests.conftest import create_brief

Hook = Callable[[str], Awaitable[None]]


class InterleavedClient(AgentClient):
    """The app's agent client, with something else happening just before a poll or just after a
    submit returns - the moment another request could get in between."""

    def __init__(self, inner: AgentClient, between: Hook) -> None:
        super().__init__(httpx.AsyncClient())  # unused: every call goes to `inner`
        self._inner = inner
        self._between = between

    async def poll(self, run_id: str) -> AgentRunStatus:
        await self._between(run_id)
        return await self._inner.poll(run_id)

    async def submit(self, request: AgentRunRequest) -> AgentRunStatus:
        status = await self._inner.submit(request)
        await self._between(request.app_agent_run_id)
        return status


def deps_for(app: FastAPI, client: AgentClient | None = None) -> RunDeps:
    return RunDeps(
        client=client or app.state.agent_client,
        catalog=load_field_catalog(),
        settings=app.state.settings,
        notifier=app.state.notifier,
    )


async def test_a_run_finished_elsewhere_while_polling_is_not_materialised_twice(
    client: httpx.AsyncClient, app: FastAPI, editor: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    document = await create_brief(client)
    run_id = (await start(client, document["id"])).json()["id"]

    async def finish_elsewhere(_: str) -> None:
        async with sessions() as other:
            await refresh_run(other, deps_for(app), run_id)

    racing = deps_for(app, InterleavedClient(app.state.agent_client, finish_elsewhere))
    async with sessions() as db:
        await db.get(AgentRun, run_id)  # this session now holds a copy of the run, still accepted
        run = await refresh_run(db, racing, run_id)
    assert run is not None
    assert run.status == "succeeded"

    async with sessions() as db:
        assert list(await db.scalars(select(DocumentVersion.version))) == [1]
        succeeded = select(func.count()).where(Notification.kind == "agent_run_succeeded")
        assert await db.scalar(succeeded) == 1


async def test_a_run_given_up_on_during_its_submit_stays_failed(
    client: httpx.AsyncClient, app: FastAPI, editor: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async def give_up(run_id: str) -> None:  # what the poller does to a run queued for too long
        async with sessions() as other:
            await other.execute(
                update(AgentRun)
                .where(AgentRun.id == run_id)
                .values(status="failed", error_code="ORPHANED")
            )
            await other.commit()

    app.state.agent_client = InterleavedClient(app.state.agent_client, give_up)
    document = await create_brief(client)
    run = (await start(client, document["id"])).json()
    assert (run["status"], run["error_code"]) == ("failed", "ORPHANED")


def test_queued_runs_outlast_the_slowest_submit(settings: Settings) -> None:
    attempts = 3  # AgentClient.over_http
    assert (
        queued_grace(settings).total_seconds() > attempts * settings.agent_request_timeout_seconds
    )


async def test_concurrent_generations_get_their_own_versions(
    client: httpx.AsyncClient, app: FastAPI, editor: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    document = await create_brief(client)
    run_ids = [(await start(client, document["id"])).json()["id"] for _ in range(2)]
    async with sessions() as first, sessions() as second:
        # Both sessions read the document before either run is materialised.
        copies = [await db.get(Document, document["id"]) for db in (first, second)]
        for db, copy, run_id in zip((first, second), copies, run_ids, strict=True):
            run = await db.get(AgentRun, run_id)
            status = await app.state.agent_client.poll(run_id)
            assert run is not None
            assert copy is not None
            assert status.output is not None
            await materialise_generate(
                db,
                run=run,
                document=copy,
                output=status.output,
                catalog=load_field_catalog(),
                trace_id=None,
            )
            await db.commit()
    async with sessions() as db:
        assert sorted(await db.scalars(select(DocumentVersion.version))) == [1, 2]
        fresh = await db.get(Document, document["id"])
        assert fresh is not None
        assert fresh.current_version == 2
