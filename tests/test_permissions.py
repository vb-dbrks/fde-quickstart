from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

from app.config import Settings
from app.identity import identity_from_request
from app.models import RoleAssignment
from app.permissions.roles import Permission, Role, permissions_for
from tests.helpers import ADMIN, DEV_USER, EDITOR, VIEWER, as_user, grant

ASSIGNMENTS = "/api/admin/role-assignments"


def make_request(headers: dict[str, str]) -> Request:
    raw = [(name.lower().encode(), value.encode()) for name, value in headers.items()]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": raw})


def test_roles_bundle_permissions() -> None:
    assert permissions_for([Role.VIEWER]) == {Permission.NOTES_READ}
    assert Permission.NOTES_WRITE in permissions_for([Role.EDITOR])
    assert Permission.ROLES_MANAGE not in permissions_for([Role.EDITOR])
    assert permissions_for([Role.ADMIN]) == frozenset(Permission)
    assert permissions_for([]) == frozenset()


def test_header_identity_is_normalised(settings: Settings) -> None:
    request = make_request({"X-Forwarded-Email": "  Alice@Example.COM "})
    assert identity_from_request(request, settings).email == "alice@example.com"


def test_off_platform_requests_fall_back_to_the_dev_user(settings: Settings) -> None:
    assert identity_from_request(make_request({}), settings).email == DEV_USER


def test_on_databricks_the_identity_header_is_required(settings: Settings) -> None:
    on_platform = settings.model_copy(update={"databricks_app_name": "my-app"})
    with pytest.raises(HTTPException) as excinfo:
        identity_from_request(make_request({}), on_platform)
    assert excinfo.value.status_code == 401


def test_new_users_get_the_default_role(client: TestClient) -> None:
    assert client.get("/api/me").json() == {
        "email": DEV_USER,
        "display_name": "Local developer",
        "roles": ["viewer"],
        "permissions": ["notes:read"],
    }


def test_bootstrap_admins_have_every_permission(client: TestClient) -> None:
    body = client.get("/api/me", headers=as_user(ADMIN)).json()
    assert "admin" in body["roles"]
    assert set(body["permissions"]) == set(Permission)


def test_admins_grant_and_revoke_roles(client: TestClient) -> None:
    payload = {"email": "Editor@Example.com", "role": "editor"}
    created = client.post(ASSIGNMENTS, json=payload, headers=as_user(ADMIN))
    assert created.status_code == 201
    assert created.json()["principal"] == EDITOR
    assert created.json()["granted_by"] == ADMIN
    assert client.post(ASSIGNMENTS, json=payload, headers=as_user(ADMIN)).status_code == 200

    assert "editor" in client.get("/api/me", headers=as_user(EDITOR)).json()["roles"]
    listed = client.get(ASSIGNMENTS, headers=as_user(ADMIN)).json()
    assert [(item["principal"], item["role"]) for item in listed] == [(EDITOR, "editor")]

    assert (
        client.delete(f"{ASSIGNMENTS}/{EDITOR}/editor", headers=as_user(ADMIN)).status_code == 204
    )
    assert (
        client.delete(f"{ASSIGNMENTS}/{EDITOR}/editor", headers=as_user(ADMIN)).status_code == 404
    )
    assert client.get("/api/me", headers=as_user(EDITOR)).json()["roles"] == ["viewer"]


def test_only_role_managers_use_admin_endpoints(client: TestClient) -> None:
    grant(client, EDITOR, Role.EDITOR)
    for email in (VIEWER, EDITOR):
        headers = as_user(email)
        assert client.get("/api/admin/roles", headers=headers).status_code == 403
        assert client.get(ASSIGNMENTS, headers=headers).status_code == 403
        payload = {"email": email, "role": "admin"}
        assert client.post(ASSIGNMENTS, json=payload, headers=headers).status_code == 403


def test_role_catalog_lists_every_role(client: TestClient) -> None:
    body = client.get("/api/admin/roles", headers=as_user(ADMIN)).json()
    assert {item["role"] for item in body} == set(Role)
    viewer = next(item for item in body if item["role"] == "viewer")
    assert viewer["permissions"] == ["notes:read"]


@pytest.mark.parametrize(
    "payload",
    [{"email": "not-an-email", "role": "editor"}, {"email": EDITOR, "role": "superuser"}],
)
def test_invalid_grants_are_rejected(client: TestClient, payload: dict[str, Any]) -> None:
    assert client.post(ASSIGNMENTS, json=payload, headers=as_user(ADMIN)).status_code == 422


def test_unknown_stored_roles_are_ignored(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    with sessions() as session:
        session.add(RoleAssignment(principal=VIEWER, role="retired-role", granted_by=ADMIN))
        session.commit()
    assert client.get("/api/me", headers=as_user(VIEWER)).json()["roles"] == ["viewer"]
