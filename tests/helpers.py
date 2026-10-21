"""Test users, settings and agent runtimes."""

from collections.abc import Callable
from concurrent.futures import Executor, Future
from typing import Any, ParamSpec, TypeVar

import httpx
from fastapi import FastAPI
from pydantic_settings import SettingsConfigDict

from backend.agents.config import AgentSettings
from backend.agents.runtime import AgentRuntime
from backend.agents.server import build_runtime, create_agent_app
from backend.auth.principal import Principal
from backend.auth.roles import Role, permissions_for
from backend.services.agent_client import AgentClient
from backend.settings import Settings

ADMIN = "admin@example.com"
EDITOR = "editor@example.com"
OTHER_EDITOR = "other.editor@example.com"
VIEWER = "viewer@example.com"
DEV_USER = "dev.user@example.com"

P = ParamSpec("P")
T = TypeVar("T")


class IsolatedSettings(Settings):
    """App settings that ignore any local .env file."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")


class IsolatedAgentSettings(AgentSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")


class InlineExecutor(Executor):
    """Runs submitted work immediately, so agent runs finish before submit returns."""

    def submit(self, fn: Callable[P, T], /, *args: P.args, **kwargs: P.kwargs) -> Future[T]:
        future: Future[T] = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:
            future.set_exception(exc)
        return future


def fake_runtime(**overrides: Any) -> AgentRuntime:
    """The fake agent with no step delays, executing inline."""
    settings = IsolatedAgentSettings(
        agent_runner="fake",
        llm_endpoint=None,
        fake_agent_step_seconds=0,
        mlflow_experiment_id=None,
        **overrides,
    )
    return build_runtime(settings, executor=InlineExecutor())


def use_runtime(app: FastAPI, runtime: AgentRuntime) -> AgentClient:
    """Point the app at ``runtime`` (in-process). Restore with ``app.state.agent_client = ...``."""
    client = AgentClient.in_process(create_agent_app(runtime), timeout=5)
    app.state.agent_client = client
    return client


def broken_agent_client() -> AgentClient:
    """A client whose agent is unreachable."""

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(refuse), base_url="http://agent.test")
    return AgentClient(http, retries=1)


def as_user(email: str) -> dict[str, str]:
    """Headers the Databricks Apps proxy would send for ``email``."""
    return {"X-Forwarded-Email": email}


def principal(email: str, *roles: Role) -> Principal:
    return Principal(
        email=email, display_name=email, roles=frozenset(roles), permissions=permissions_for(roles)
    )


BRIEF = {"brief.title": "Onboarding refresh", "brief.goal": "Reach first value in three days."}
