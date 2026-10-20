"""Application factory. Run with ``python -m app`` (Databricks Apps) or ``make dev`` (local)."""

import logging
import platform
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from app import migrations
from app.agents.registry import build_registry, configure_tracing
from app.config import Settings
from app.db import create_db_engine, create_sessionmaker
from app.notifications.channels import build_channels
from app.notifications.service import Notifier
from app.routes import api_router
from app.spa import mount_spa

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("Starting %s on Python %s", settings.app_title, platform.python_version())
        engine = create_db_engine(settings)
        if settings.run_migrations:
            await run_in_threadpool(migrations.upgrade, engine)
        app.state.engine = engine
        app.state.sessionmaker = create_sessionmaker(engine)
        configure_tracing(settings)
        yield
        engine.dispose()

    app = FastAPI(
        title=settings.app_title,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.state.notifier = Notifier(build_channels(settings.notification_webhook_url))
    app.state.agents = build_registry(settings)

    app.include_router(api_router, prefix="/api")
    mount_spa(app, settings.static_dir)
    return app
