"""Schemas owned by the bundled examples, not requirements of the execution protocol."""

from pydantic import BaseModel, ConfigDict, Field


class ChatInput(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    context: str = Field(default="", max_length=12000)


class ChatResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1)


class GenerationInput(BaseModel):
    topic: str = Field(min_length=1, max_length=2000)
    audience: str = Field(default="General audience", max_length=2000)
    constraints: str = Field(default="", max_length=4000)


class GenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    key_points: list[str] = Field(min_length=1)
