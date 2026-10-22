"""Execution v2: domain-independent submit/poll, carrying official AG-UI events."""

from typing import Any, Literal

from ag_ui.core import Event, Message, Tool
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

AGUI_EVENT = TypeAdapter(Event)


class ExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal["v2"] = "v2"
    run_id: str
    agent_id: str
    thread_id: str
    initiator: str
    input: dict[str, Any]
    context: dict[str, Any] = Field(default_factory=dict)
    messages: list[Message] = Field(default_factory=list)


class ExecutionStatus(BaseModel):
    version: Literal["v2"] = "v2"
    run_id: str
    status: Literal["accepted", "running", "succeeded", "failed"]
    events: list[dict[str, Any]] = Field(default_factory=list)
    cursor: int = 0
    result: dict[str, Any] | None = None
    error: str | None = None
    trace_id: str | None = None

    @field_validator("events")
    @classmethod
    def validate_events(cls, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            AGUI_EVENT.validate_python(event).model_dump(
                mode="json", by_alias=True, exclude_none=True
            )
            for event in value
        ]


class AgentDescriptor(BaseModel):
    id: str
    example: str
    description: str
    input_schema: dict[str, Any]
    result_schema: dict[str, Any]
    capabilities: list[str] = Field(default_factory=list)
    tools: list[Tool] = Field(default_factory=list)
