"""Shared FastAPI dependencies. Everything comes from ``app.state``, set up in backend.main."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.contracts.field_catalog import FieldCatalog, load_field_catalog
from backend.services.agent_client import AgentClient
from backend.services.notifications import Notifier
from backend.settings import Settings


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_sessionmaker(request: Request) -> async_sessionmaker[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    return factory


async def get_session(
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_sessionmaker)],
) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        yield session


def get_notifier(request: Request) -> Notifier:
    notifier: Notifier = request.app.state.notifier
    return notifier


def get_agent_client(request: Request) -> AgentClient:
    client: AgentClient = request.app.state.agent_client
    return client


def get_catalog() -> FieldCatalog:
    return load_field_catalog()


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
NotifierDep = Annotated[Notifier, Depends(get_notifier)]
AgentClientDep = Annotated[AgentClient, Depends(get_agent_client)]
CatalogDep = Annotated[FieldCatalog, Depends(get_catalog)]
