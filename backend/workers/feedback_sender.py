"""Delivers users' feedback to the runs' MLflow traces in the background (the outbox's worker).

Feedback is first sent straight after the request that recorded it. This worker picks up whatever
that attempt didn't deliver - the agent was unreachable, the trace store said no - with backoff
(services/feedback.py), so a slow or failing trace store never slows the app down.
"""

import asyncio
import contextlib
import logging
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.services import feedback
from backend.services.agent_client import AgentClient

logger = logging.getLogger(__name__)


class FeedbackSender:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        client: Callable[[], AgentClient],
        *,
        interval_seconds: float,
    ) -> None:
        self._sessions = sessions
        self._client = client  # looked up per sweep: the app's client can be replaced
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None

    async def sweep(self) -> int:
        return await feedback.deliver_due(self._sessions, self._client())

    async def _loop(self) -> None:
        logger.info("Feedback sender started (every %ss)", self._interval)
        while True:
            await asyncio.sleep(self._interval)
            try:
                await self.sweep()
            except Exception:
                logger.exception("Feedback sender sweep failed")

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="feedback-sender")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
