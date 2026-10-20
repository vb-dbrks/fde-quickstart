"""Shared FastAPI dependencies. Everything here comes from ``app.state``, set up in app.main."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from app.agents.registry import AgentRegistry
from app.config import Settings
from app.notifications.service import Notifier


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_sessionmaker(request: Request) -> sessionmaker[Session]:
    factory: sessionmaker[Session] = request.app.state.sessionmaker
    return factory


def get_session(
    factory: Annotated[sessionmaker[Session], Depends(get_sessionmaker)],
) -> Iterator[Session]:
    with factory() as session:
        yield session


def get_notifier(request: Request) -> Notifier:
    notifier: Notifier = request.app.state.notifier
    return notifier


def get_agent_registry(request: Request) -> AgentRegistry:
    registry: AgentRegistry = request.app.state.agents
    return registry


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionmakerDep = Annotated[sessionmaker[Session], Depends(get_sessionmaker)]
SessionDep = Annotated[Session, Depends(get_session)]
NotifierDep = Annotated[Notifier, Depends(get_notifier)]
AgentRegistryDep = Annotated[AgentRegistry, Depends(get_agent_registry)]
