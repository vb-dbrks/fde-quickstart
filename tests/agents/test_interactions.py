"""Offline execution-v2 fixtures: real/fake parity, chunks, parse retries and boundaries."""

import json
from collections.abc import Iterator
from typing import Any

import pytest
from langchain_core.messages import AIMessageChunk
from langchain_core.runnables import Runnable, RunnableGenerator

from backend.agents.config import AgentSettings
from backend.agents.example_registry import definitions
from backend.agents.interaction import InteractionRuntime
from backend.agents.runtime import InlineExecutor
from backend.contracts.examples import ChatResult, GenerationResult
from backend.contracts.execution import ExecutionRequest
from tests.agents.test_real_runners import ScriptedModel


@pytest.mark.parametrize("agent_id", ["chat", "generation"])
@pytest.mark.parametrize("real", [False, True])
def test_fake_and_scripted_real_share_the_event_contract(
    monkeypatch: pytest.MonkeyPatch, agent_id: str, real: bool
) -> None:
    result = (
        ChatResult(content="Hello")
        if agent_id == "chat"
        else GenerationResult(title="Title", summary="Summary", key_points=["Point"])
    )
    model = ScriptedModel().queue(result)
    monkeypatch.setattr(
        "backend.agents.example_registry.chat_model_factory", lambda *args, **kwargs: lambda: model
    )
    settings = AgentSettings(
        _env_file=None,
        agent_runner="real" if real else "fake",
        llm_endpoint="scripted",
        fake_agent_step_seconds=0,
    )
    runtime = InteractionRuntime(definitions(settings), InlineExecutor())
    request = ExecutionRequest(
        run_id="test",
        agent_id=agent_id,
        thread_id="session",
        initiator="fde",
        input={"message": "Hello"} if agent_id == "chat" else {"topic": "AG-UI"},
    )
    first = runtime.submit(request)
    again = runtime.submit(request)
    assert first == again
    assert first.status == "succeeded"
    assert first.result is not None
    assert all(event["type"] not in ("RUN_STARTED", "RUN_FINISHED") for event in first.events)
    assert any(event["type"] == "STATE_SNAPSHOT" for event in first.events)
    assert len(model.prompts) == int(real)


class ChunkedModel(ScriptedModel):
    def bind_tools(
        self, tools: Any, *, tool_choice: Any = None, **kwargs: Any
    ) -> Runnable[Any, Any]:
        attempts = iter(
            [
                json.dumps({"content": "discard this", "invalid": True}),
                json.dumps({"content": "replacement"}),
            ]
        )

        def chunks(inputs: Iterator[Any]) -> Iterator[AIMessageChunk]:
            list(inputs)
            for char in next(attempts):
                yield AIMessageChunk(content=char)

        return RunnableGenerator(chunks)


def test_stream_retry_replaces_provisional_state_and_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "backend.agents.example_registry.chat_model_factory",
        lambda *args, **kwargs: lambda: ChunkedModel(),
    )
    runtime = InteractionRuntime(
        definitions(AgentSettings(_env_file=None, agent_runner="real", llm_endpoint="scripted")),
        InlineExecutor(),
    )
    status = runtime.submit(
        ExecutionRequest(
            run_id="retry",
            agent_id="chat",
            thread_id="thread",
            initiator="fde",
            input={"message": "Hello"},
        )
    )
    assert status.status == "succeeded"
    assert status.result == {"content": "replacement"}
    snapshots = [e["snapshot"] for e in status.events if e["type"] == "STATE_SNAPSHOT"]
    assert {"preview": {}, "provisional": True} in snapshots
    assert any(e["type"] == "MESSAGES_SNAPSHOT" for e in status.events)
    assert snapshots[-1]["preview"] == {"content": "replacement"}
