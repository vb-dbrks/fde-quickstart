"""Explicit registrations: remove an example here without changing the execution engine."""

import time
from typing import Any

from ag_ui.core import (
    AssistantMessage,
    EventType,
    MessagesSnapshotEvent,
    StateSnapshotEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from backend.agents.config import AgentSettings
from backend.agents.interaction import AgentDefinition, EventEmitter, Runner
from backend.agents.llm import chat_model_factory
from backend.agents.runners._common import stream_structured
from backend.contracts.examples import ChatInput, ChatResult, GenerationInput, GenerationResult
from backend.contracts.execution import ExecutionRequest


def definitions(settings: AgentSettings) -> dict[str, AgentDefinition]:
    def runner(schema: type[BaseModel], fake: bool) -> Runner:
        def run(request: ExecutionRequest, emit: EventEmitter) -> BaseModel:
            message_id = f"{request.run_id}:answer"
            previous = ""
            chat = schema is ChatResult
            if chat:
                emit.emit(
                    TextMessageStartEvent(
                        type=EventType.TEXT_MESSAGE_START, message_id=message_id, role="assistant"
                    )
                )

            def preview(value: dict[str, Any], reset: bool = False) -> None:
                nonlocal previous
                emit.emit(
                    StateSnapshotEvent(
                        type=EventType.STATE_SNAPSHOT,
                        snapshot={"preview": value, "provisional": True},
                    )
                )
                if reset and chat:
                    previous = ""
                    emit.emit(
                        MessagesSnapshotEvent(
                            type=EventType.MESSAGES_SNAPSHOT,
                            messages=[
                                *request.messages,
                                AssistantMessage(id=message_id, content=""),
                            ],
                        )
                    )
                content = value.get("content", "")
                if chat and isinstance(content, str) and content.startswith(previous):
                    delta = content[len(previous) :]
                    if delta:
                        emit.emit(
                            TextMessageContentEvent(
                                type=EventType.TEXT_MESSAGE_CONTENT,
                                message_id=message_id,
                                delta=delta,
                            )
                        )
                    previous = content
                if reset:
                    # A retry's draft replaces the old attempt; the UI reads preview state.
                    previous = ""

            if fake:
                if chat:
                    prompt = ChatInput.model_validate(request.input)
                    result: BaseModel = ChatResult(
                        content=f"(Fake agent) You asked: {prompt.message}. I can see {len(request.messages)} earlier messages. {prompt.context}"
                    )
                    text = result.model_dump()["content"]
                    for end in range(12, len(text) + 12, 12):
                        preview({"content": text[:end]})
                        if settings.fake_agent_step_seconds:
                            time.sleep(settings.fake_agent_step_seconds / 10)
                else:
                    data = GenerationInput.model_validate(request.input)
                    result = GenerationResult(
                        title=data.topic,
                        summary=f"An introduction to {data.topic} for {data.audience}.",
                        key_points=[
                            f"Understand {data.topic}",
                            f"Consider {data.constraints or 'the practical tradeoffs'}",
                            "Choose the next step",
                        ],
                    )
                    partial: dict[str, Any] = {}
                    for key, value in result.model_dump().items():
                        partial[key] = value
                        preview(dict(partial))
                        if settings.fake_agent_step_seconds:
                            time.sleep(settings.fake_agent_step_seconds)
                if settings.fake_agent_fail_at:
                    raise ValueError("Injected fake failure")
            else:
                import json

                model = chat_model_factory(
                    settings.llm_endpoint or "", temperature=settings.llm_temperature
                )()
                history = [
                    HumanMessage(str(m.content)) if m.role == "user" else AIMessage(m.content or "")
                    for m in request.messages
                    if m.role in ("user", "assistant")
                ]
                template = ChatPromptTemplate.from_messages(
                    [
                        (
                            "system",
                            "Answer the user's request using their supplied context. "
                            + (
                                "Write a helpful conversational answer."
                                if chat
                                else "Generate a title, summary and key points for the topic, audience and constraints."
                            )
                            + " Answer by calling the provided tool once.",
                        ),
                        *history,
                        HumanMessage(json.dumps(request.input)),
                    ]
                )
                result = stream_structured(model, template.invoke({}), schema, preview)
            preview(result.model_dump(mode="json"))
            if chat:
                emit.emit(
                    TextMessageEndEvent(type=EventType.TEXT_MESSAGE_END, message_id=message_id)
                )
            return result

        return run

    return {
        "chat": AgentDefinition(
            "chat",
            "chat",
            "A standalone conversational assistant",
            ChatInput,
            ChatResult,
            runner(ChatResult, settings.runner_for("chat") == "fake"),
            ("messages", "state"),
        ),
        "generation": AgentDefinition(
            "generation",
            "generation",
            "Generate and review structured content",
            GenerationInput,
            GenerationResult,
            runner(GenerationResult, settings.runner_for("generation") == "fake"),
        ),
    }
