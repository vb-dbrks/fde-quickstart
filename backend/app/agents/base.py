"""What every agent implements, and the context it runs with."""

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from app.permissions.service import Principal


class AgentNotConfiguredError(RuntimeError):
    """The agent cannot run in this deployment, e.g. because no model endpoint is configured."""


@dataclass(frozen=True)
class AgentContext:
    """Passed to every tool call. Tools act as ``principal`` and must check its permissions."""

    principal: Principal
    sessions: sessionmaker[Session]


@dataclass(frozen=True)
class AgentReply:
    output: str


class AppAgent(Protocol):
    name: str
    description: str

    @property
    def configured(self) -> bool: ...

    async def run(self, context: AgentContext, message: str) -> AgentReply: ...
