"""Defensive poller for agent runs (ADR 0003).

The UI is the main driver: while a user watches a run, ``GET /api/agent-runs/{id}`` refreshes it.
This worker is the safety net that brings runs to a terminal state - and materialises them - when
nobody is watching (closed tab, navigation away).

Concurrency: ``refresh_run`` locks the run row and materialisation is guarded by
``materialised_at``, so this worker, the UI and several app instances can all poll the same run
safely. A run polled in the last ``MIN_INTERVAL`` (``last_polled_at``) - usually by the UI - is left
for the next sweep.
"""

import asyncio
import contextlib
import logging
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.domain.enums import RunStatus
from backend.domain.models import AgentRun

logger = logging.getLogger(__name__)

Refresh = Callable[[AsyncSession, str], Awaitable[object]]
BATCH_SIZE = 50
MIN_INTERVAL = timedelta(seconds=3)
_ACTIVE = (RunStatus.QUEUED.value, RunStatus.ACCEPTED.value, RunStatus.RUNNING.value)


class AgentRunPoller:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        refresh: Refresh,
        *,
        interval_seconds: float,
    ) -> None:
        self._sessions = sessions
        self._refresh = refresh
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None

    async def sweep(self) -> int:
        """Refresh every active run that is due. Returns how many were refreshed."""
        due_before = datetime.now(UTC) - MIN_INTERVAL
        async with self._sessions() as db:
            run_ids = list(
                await db.scalars(
                    select(AgentRun.id)
                    .where(
                        AgentRun.status.in_(_ACTIVE),
                        or_(
                            AgentRun.last_polled_at.is_(None), AgentRun.last_polled_at < due_before
                        ),
                    )
                    .order_by(AgentRun.created_at)
                    .limit(BATCH_SIZE)
                )
            )
        for run_id in run_ids:
            try:
                async with self._sessions() as db:
                    await self._refresh(db, run_id)
            except Exception:
                logger.exception("Refreshing agent run %s failed", run_id)
        return len(run_ids)

    async def _loop(self) -> None:
        logger.info("Agent run poller started (every ~%ss)", self._interval)
        while True:
            jitter = random.uniform(-0.25, 0.25) * self._interval  # noqa: S311 - not cryptographic
            await asyncio.sleep(max(1.0, self._interval + jitter))
            try:
                await self.sweep()
            except Exception:
                logger.exception("Agent run poller sweep failed")

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="agent-run-poller")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
