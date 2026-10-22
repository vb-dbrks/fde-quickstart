"""Application factory. Run with ``python -m backend`` (Databricks Apps) or ``make dev`` (local).

On startup: connect to Postgres, apply migrations, start the agent runtime (in-process) or connect to
a remote one, and start the background run poller.
"""

import logging
import platform
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.config import AgentSettings
from backend.agents.runtime import AgentRuntime
from backend.agents.server import build_runtime, create_agent_app
from backend.api import build_api_router
from backend.api import interactions as interaction_api
from backend.contracts.field_catalog import FieldCatalog, load_field_catalog
from backend.db import migrations
from backend.db.session import create_db_engine, create_sessionmaker
from backend.domain.errors import DomainError
from backend.examples.registry import applications
from backend.middleware.idempotency import IdempotencyMiddleware
from backend.services import interactions
from backend.services.agent_client import AgentClient
from backend.services.agent_runs import RunDeps, queued_grace
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
            runtime = agent_runtime or build_runtime(
                AgentSettings(enabled_examples=settings.enabled_examples)
            )
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
            catalog=load_field_catalog()
            if "documents" in settings.examples
            else FieldCatalog("disabled", {}),
            settings=settings,
            notifier=app.state.notifier,
        )

        async def refresh(db: AsyncSession, run_id: str) -> object:
            from backend.domain.models import AgentRun

            run = await db.get(AgentRun, run_id)
            if run is not None and run.contract_version == "v2":
                return await interactions.refresh(
                    db,
                    app.state.agent_client,
                    run_id,
                    app.state.agent_applications,
                    settings.agent_run_timeout_seconds,
                    queued_grace(settings).total_seconds(),
                )
            from backend.examples.document_events import refresh_document_events

            return await refresh_document_events(
                db, replace(deps, client=app.state.agent_client), run_id
            )

        app.state.refresh_run = refresh

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
    app.state.agent_applications = applications(settings.examples)
    app.state.notifier = Notifier(build_channels(settings.notification_webhook_url))
    app.add_middleware(IdempotencyMiddleware)

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse({"detail": exc.message}, status_code=exc.status_code)

    app.include_router(build_api_router(settings.examples), prefix="/api")
    app.include_router(interaction_api.router, prefix="/api")
    mount_spa(app, settings.static_dir)
    return app
