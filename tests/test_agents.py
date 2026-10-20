import asyncio
import json
from typing import Any, cast

import httpx2
import pytest
from databricks.sdk.core import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.agents import tools
from app.agents.assistant import AssistantAgent, load_prompt
from app.agents.base import AgentContext, AgentNotConfiguredError, AgentReply
from app.agents.llm import databricks_openai_client
from app.agents.registry import AgentRegistry, build_registry
from app.config import Settings
from app.deps import get_agent_registry
from app.permissions.roles import Role
from tests.helpers import EDITOR, VIEWER, as_user, grant, principal


class EchoAgent:
    name = "echo"
    description = "Repeats the message, prefixed with the caller's email."
    configured = True

    async def run(self, context: AgentContext, message: str) -> AgentReply:
        return AgentReply(output=f"{context.principal.email}: {message}")


def completion(*, content: str | None = None, tool_call: str | None = None) -> dict[str, Any]:
    """A minimal OpenAI chat-completions response, as Databricks Model Serving returns it."""
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_call:
        message["tool_calls"] = [
            {"id": "call_1", "type": "function", "function": {"name": tool_call, "arguments": "{}"}}
        ]
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "test-endpoint",
        "choices": [
            {"index": 0, "message": message, "finish_reason": "tool_calls" if tool_call else "stop"}
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def test_agents_are_listed(client: TestClient) -> None:
    assert client.get("/api/agents").json() == [
        {"name": "assistant", "description": AssistantAgent.description, "configured": False}
    ]


def test_an_unconfigured_agent_returns_503(client: TestClient) -> None:
    grant(client, EDITOR, Role.EDITOR)
    response = client.post(
        "/api/agents/assistant/invoke", json={"message": "hi"}, headers=as_user(EDITOR)
    )
    assert response.status_code == 503
    assert "LLM_ENDPOINT" in response.json()["detail"]


def test_invoking_agents_needs_permission(client: TestClient) -> None:
    response = client.post(
        "/api/agents/assistant/invoke", json={"message": "hi"}, headers=as_user(VIEWER)
    )
    assert response.status_code == 403


def test_unknown_agents_are_404s(client: TestClient) -> None:
    grant(client, EDITOR, Role.EDITOR)
    response = client.post(
        "/api/agents/nope/invoke", json={"message": "hi"}, headers=as_user(EDITOR)
    )
    assert response.status_code == 404


def test_agents_run_as_the_caller(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[get_agent_registry] = lambda: AgentRegistry([EchoAgent()])
    grant(client, EDITOR, Role.EDITOR)
    response = client.post(
        "/api/agents/echo/invoke", json={"message": "hello"}, headers=as_user(EDITOR)
    )
    assert response.json() == {"agent": "echo", "output": f"{EDITOR}: hello"}


def test_tools_check_the_callers_permissions(sessions: sessionmaker[Session]) -> None:
    context = AgentContext(principal=principal("nobody@example.com"), sessions=sessions)
    assert tools.recent_notes(context) == tools.PERMISSION_DENIED
    assert tools.add_note(context, title="x", body="y") == tools.PERMISSION_DENIED


def test_tools_act_as_the_caller(sessions: sessionmaker[Session]) -> None:
    context = AgentContext(principal=principal(EDITOR, Role.EDITOR), sessions=sessions)
    assert isinstance(tools.add_note(context, title="From the agent", body="Hello"), dict)

    found = tools.recent_notes(context, mine_only=True)
    assert isinstance(found, list)
    assert [(note["title"], note["owner"]) for note in found] == [("From the agent", EDITOR)]
    assert tools.describe_user(context)["roles"] == ["editor"]


def test_the_assistant_needs_an_endpoint() -> None:
    with pytest.raises(AgentNotConfiguredError):
        AssistantAgent(None).build()


def test_every_registered_agent_has_a_prompt(settings: Settings) -> None:
    for agent in build_registry(settings).all():
        assert load_prompt(agent.name).strip()


class StaticConfig:
    """Stands in for databricks.sdk Config, which would try to reach the (fake) workspace host."""

    host = "https://workspace.example.com"

    def authenticate(self) -> dict[str, str]:
        return {"Authorization": "Bearer test-token"}


def test_the_assistant_calls_tools_through_the_model_endpoint(
    sessions: sessionmaker[Session],
) -> None:
    """The real Agents SDK loop against a fake Model Serving endpoint: a tool call, then an answer."""
    calls: list[httpx2.Request] = []

    def endpoint(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        messages = json.loads(request.content)["messages"]
        if any(message["role"] == "tool" for message in messages):
            return httpx2.Response(200, json=completion(content="You are editor@example.com."))
        return httpx2.Response(200, json=completion(tool_call="whoami"))

    config = cast(Config, StaticConfig())
    agent = AssistantAgent(
        "test-endpoint",
        client_factory=lambda: databricks_openai_client(
            config, transport=httpx2.MockTransport(endpoint)
        ),
    )
    context = AgentContext(principal=principal(EDITOR, Role.EDITOR), sessions=sessions)

    reply = asyncio.run(agent.run(context, "Who am I?"))

    assert reply.output == "You are editor@example.com."
    assert [call.url.path for call in calls] == ["/serving-endpoints/chat/completions"] * 2
    assert all(call.headers["authorization"] == "Bearer test-token" for call in calls)
    first_request = json.loads(calls[0].content)
    assert first_request["model"] == "test-endpoint"
    assert {tool["function"]["name"] for tool in first_request["tools"]} == {
        "whoami",
        "list_recent_notes",
        "create_note",
    }
    tool_result = next(m for m in json.loads(calls[1].content)["messages"] if m["role"] == "tool")
    assert json.loads(tool_result["content"])["email"] == EDITOR
