"""Request and response models for the REST API. The frontend's TypeScript types are generated from
these (`make api-types`), so changes here show up as type errors in the UI."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.auth.roles import Permission, Role
from backend.domain.enums import Access, FieldSource, RunStatus
from backend.domain.models import EMAIL_LENGTH

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "error"]
    agent: dict[str, Any] | None = None


class MeOut(BaseModel):
    email: str
    display_name: str
    roles: list[Role]
    permissions: list[Permission]


# ---- documents ----------------------------------------------------------------------------------


class FieldSpecOut(BaseModel):
    field_path: str
    label: str
    type: Literal["text", "list"]
    agent_generates: bool
    required: bool
    description: str


class DocumentTypeOut(BaseModel):
    name: str
    label: str
    description: str
    fields: list[FieldSpecOut]


class DocumentCreate(BaseModel):
    document_type: str
    # Values of user fields keyed by field path, e.g. {"brief.title": "...", "brief.goal": "..."}.
    fields: dict[str, Any]


class CitationOut(BaseModel):
    source_document_id: str
    snippet: str | None = None


class FieldOut(BaseModel):
    field_path: str
    label: str
    type: Literal["text", "list"]
    agent_generates: bool
    value: Any = None
    source: FieldSource | None = None
    confidence: str | None = None
    confidence_reason: str | None = None
    reasoning: str | None = None
    citations: list[CitationOut] = Field(default_factory=list)
    agent_run_id: str | None = None
    updated_by: str | None = None
    updated_at: datetime | None = None


class DocumentSummary(BaseModel):
    id: str
    document_type: str
    title: str
    my_access: Access
    current_version: int
    created_by: str
    updated_at: datetime


class StepOut(BaseModel):
    name: str
    status: Literal["pending", "running", "completed", "failed"]
    started_at: str | None = None
    completed_at: str | None = None


class SuggestionOut(BaseModel):
    field_path: str
    value: Any
    confidence: str
    confidence_reason: str
    reasoning: str
    citations: list[CitationOut] = Field(default_factory=list)


class AgentRunOut(BaseModel):
    id: str
    document_id: str
    thread_id: str | None
    run_kind: Literal["generate", "enhance_field", "assistant_turn"]
    # enhance_field: the field being revised (known before the run finishes).
    field_path: str | None = None
    status: RunStatus
    step_history: list[StepOut]
    # enhance_field: the suggestion to accept or dismiss.
    suggestion: SuggestionOut | None = None
    # assistant_turn: the reply (also stored as a message in the thread).
    answer: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    trace_id: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class DocumentOut(DocumentSummary):
    fields: list[FieldOut]
    # Runs still in progress, so the UI can resume watching them after a reload.
    active_runs: list[AgentRunOut]


class FieldUpdate(BaseModel):
    value: Any
    # Set when accepting an enhance_field suggestion; records the agent's provenance on the field.
    accepted_from_run_id: str | None = None


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: int
    snapshot: dict[str, Any]
    agent_run_id: str | None
    created_by: str
    created_at: datetime


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    field_path: str | None
    action: str
    value_before: Any
    value_after: Any
    actor: str
    agent_run_id: str | None
    trace_id: str | None
    created_at: datetime


class AccessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    principal: str
    access: Access
    granted_by: str
    granted_at: datetime


class AccessGrant(BaseModel):
    email: str = Field(max_length=EMAIL_LENGTH, pattern=EMAIL_PATTERN)
    access: Access


# ---- agent runs and conversations ---------------------------------------------------------------


class AgentRunCreate(BaseModel):
    run_kind: Literal["generate", "enhance_field", "assistant_turn"]
    instruction: str | None = Field(default=None, max_length=2_000)
    # generate: a subset of agent fields to (re)generate; omitted means all.
    scope: list[str] | None = None
    # enhance_field: the field to revise.
    field_path: str | None = None
    # assistant_turn: the conversation and the user's message.
    thread_id: str | None = None
    message: str | None = Field(default=None, max_length=4_000)
    # Other documents (that the user can see) the agent may use and cite.
    source_document_ids: list[str] = Field(default_factory=list, max_length=5)


class ThreadCreate(BaseModel):
    title: str = Field(default="Conversation", max_length=200)


class ThreadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    title: str
    created_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    citations: list[CitationOut]
    agent_run_id: str | None
    created_at: datetime


# ---- notifications and roles --------------------------------------------------------------------


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    title: str
    body: str | None
    link: str | None
    created_at: datetime
    read_at: datetime | None


class NotificationList(BaseModel):
    items: list[NotificationOut]
    unread_count: int


class MarkedRead(BaseModel):
    updated: int


class RoleInfo(BaseModel):
    role: Role
    permissions: list[Permission]


class RoleAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    principal: str
    role: Role
    granted_by: str
    granted_at: datetime


class RoleGrantIn(BaseModel):
    email: str = Field(max_length=EMAIL_LENGTH, pattern=EMAIL_PATTERN)
    role: Role
