from typing import Any

from fastapi.testclient import TestClient

from app.permissions.roles import Role
from tests.helpers import ADMIN, EDITOR, OTHER_EDITOR, VIEWER, as_user, grant


def create_note(client: TestClient, email: str, title: str = "Kick-off") -> dict[str, Any]:
    response = client.post(
        "/api/notes", json={"title": title, "body": "Monday 10:00"}, headers=as_user(email)
    )
    assert response.status_code == 201, response.text
    note: dict[str, Any] = response.json()
    return note


def test_viewers_cannot_create_notes(client: TestClient) -> None:
    response = client.post("/api/notes", json={"title": "Nope"}, headers=as_user(VIEWER))
    assert response.status_code == 403


def test_editors_create_notes_and_everyone_reads_them(client: TestClient) -> None:
    grant(client, EDITOR, Role.EDITOR)
    note = create_note(client, EDITOR)
    assert note["owner"] == EDITOR
    assert note["can_delete"] is True

    listed = client.get("/api/notes", headers=as_user(VIEWER)).json()
    assert [item["id"] for item in listed] == [note["id"]]
    assert listed[0]["can_delete"] is False


def test_only_owners_and_admins_delete_notes(client: TestClient) -> None:
    grant(client, EDITOR, Role.EDITOR)
    grant(client, OTHER_EDITOR, Role.EDITOR)
    first = create_note(client, EDITOR, "first")
    second = create_note(client, EDITOR, "second")

    assert (
        client.delete(f"/api/notes/{first['id']}", headers=as_user(OTHER_EDITOR)).status_code == 403
    )
    assert client.delete(f"/api/notes/{first['id']}", headers=as_user(EDITOR)).status_code == 204
    assert client.delete(f"/api/notes/{second['id']}", headers=as_user(ADMIN)).status_code == 204
    assert client.delete(f"/api/notes/{second['id']}", headers=as_user(ADMIN)).status_code == 404


def test_mine_filters_to_the_callers_notes(client: TestClient) -> None:
    grant(client, EDITOR, Role.EDITOR)
    grant(client, OTHER_EDITOR, Role.EDITOR)
    create_note(client, EDITOR, "mine")
    create_note(client, OTHER_EDITOR, "theirs")

    listed = client.get("/api/notes?mine=true", headers=as_user(EDITOR)).json()
    assert [item["title"] for item in listed] == ["mine"]


def test_note_titles_are_required(client: TestClient) -> None:
    grant(client, EDITOR, Role.EDITOR)
    response = client.post("/api/notes", json={"title": ""}, headers=as_user(EDITOR))
    assert response.status_code == 422
