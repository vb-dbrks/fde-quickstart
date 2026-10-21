"""Application factory. Run with ``python -m backend`` (Databricks Apps) or ``make dev`` (local).

On startup: connect to Postgres, apply migrations, start the agent runtime (in-process) or connect to
a remote one, and start the background run poller.
"""

import logging
import platform
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.runtime import AgentRuntime
from backend.agents.server import build_runtime, create_agent_app
from backend.api import api_router
from backend.contracts.field_catalog import load_field_catalog
from backend.db import migrations
from backend.db.session import create_db_engine, create_sessionmaker
from backend.domain.errors import DomainError
from backend.middleware.idempotency import IdempotencyMiddleware
from backend.services.agent_client import AgentClient
from backend.services.agent_runs import RunDeps, refresh_run
from backend.services.notification_channels import build_channels
from backend.services.notifications import Notifier
from backend.settings import Settings
from backend.spa import mount_spa
from backend.workers.agent_run_poller import AgentRunPoller
from backend.workers.feedback_sender import FeedbackSender

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None, *, agent_runtime: AgentRuntime | None = None
) -> FastAPI:
    """``agent_runtime`` lets tests inject a runtime (e.g. the fake agent with an inline executor)."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("Starting %s on Python %s", settings.app_title, platform.python_version())
        engine = create_db_engine(settings)
        if settings.run_migrations:
            await migrations.upgrade(engine)
        sessions = create_sessionmaker(engine)
        app.state.engine = engine
        app.state.sessionmaker = sessions

        runtime = None
        if settings.agent_transport == "inprocess":
            runtime = agent_runtime or build_runtime()
            client = AgentClient.in_process(
                create_agent_app(runtime), timeout=settings.agent_request_timeout_seconds
            )
            logger.info("Agent runtime in-process, runners: %s", runtime.runner_names)
        else:
            if not settings.agent_api_base:
                raise RuntimeError("AGENT_TRANSPORT=http needs AGENT_API_BASE")
            client = AgentClient.over_http(
                settings.agent_api_base, timeout=settings.agent_request_timeout_seconds
            )
            logger.info("Agent runtime at %s", settings.agent_api_base)
        app.state.agent_runtime = runtime
        app.state.agent_client = client

        deps = RunDeps(
            client=client,
            catalog=load_field_catalog(),
            settings=settings,
            notifier=app.state.notifier,
        )

        async def refresh(db: AsyncSession, run_id: str) -> object:
            return await refresh_run(db, deps, run_id)

        poller = AgentRunPoller(
            sessions, refresh, interval_seconds=settings.poller_interval_seconds
        )
        app.state.poller = poller
        sender = FeedbackSender(
            sessions,
            lambda: app.state.agent_client,
            interval_seconds=settings.feedback_retry_interval_seconds,
        )
        app.state.feedback_sender = sender
        if settings.poller_enabled:
            poller.start()
            sender.start()
        yield
        await sender.stop()
        await poller.stop()
        await client.aclose()
        if runtime is not None:
            runtime.shutdown()
        await engine.dispose()

    app = FastAPI(
        title=settings.app_title,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.state.notifier = Notifier(build_channels(settings.notification_webhook_url))
    app.add_middleware(IdempotencyMiddleware)

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse({"detail": exc.message}, status_code=exc.status_code)

    app.include_router(api_router, prefix="/api")
    mount_spa(app, settings.static_dir)
    return app
