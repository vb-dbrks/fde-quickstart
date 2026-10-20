"""Test users and request helpers."""

from fastapi.testclient import TestClient
from pydantic_settings import SettingsConfigDict

from app.config import Settings
from app.permissions.roles import Role, permissions_for
from app.permissions.service import Principal

ADMIN = "admin@example.com"
EDITOR = "editor@example.com"
OTHER_EDITOR = "other.editor@example.com"
VIEWER = "viewer@example.com"
DEV_USER = "dev.user@example.com"


class IsolatedSettings(Settings):
    """Settings that ignore any local .env file."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")


def as_user(email: str) -> dict[str, str]:
    """Headers the Databricks Apps proxy would send for ``email``."""
    return {"X-Forwarded-Email": email}


def grant(client: TestClient, email: str, role: Role) -> None:
    response = client.post(
        "/api/admin/role-assignments", json={"email": email, "role": role}, headers=as_user(ADMIN)
    )
    assert response.status_code in (200, 201), response.text


def principal(email: str, *roles: Role) -> Principal:
    return Principal(
        email=email, display_name=email, roles=frozenset(roles), permissions=permissions_for(roles)
    )
