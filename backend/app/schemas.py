"""Request and response models for the REST API. The frontend's TypeScript types are generated from
these (`make api-types`), so changes here show up as type errors in the UI."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import EMAIL_LENGTH
from app.permissions.roles import Permission, Role

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "error"]


class MeOut(BaseModel):
    email: str
    display_name: str
    roles: list[Role]
    permissions: list[Permission]


class NoteIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=10_000)


class NoteOut(BaseModel):
    id: int
    title: str
    body: str
    owner: str
    created_at: datetime
    can_delete: bool


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


class AgentInfo(BaseModel):
    name: str
    description: str
    configured: bool


class AgentInvokeIn(BaseModel):
    message: str = Field(min_length=1, max_length=4_000)


class AgentInvokeOut(BaseModel):
    agent: str
    output: str
