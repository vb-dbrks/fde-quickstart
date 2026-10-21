import httpx

from backend.auth.roles import Role
from tests.conftest import create_brief, grant
from tests.helpers import ADMIN, EDITOR, OTHER_EDITOR, VIEWER, as_user


async def test_document_types_come_from_the_field_catalog(client: httpx.AsyncClient) -> None:
    [brief] = (await client.get("/api/document-types")).json()
    assert brief["name"] == "brief"
    agent_fields = [f["field_path"] for f in brief["fields"] if f["agent_generates"]]
    assert agent_fields == ["brief.summary", "brief.key_points", "brief.risks", "brief.next_steps"]


async def test_editors_create_documents_they_own(client: httpx.AsyncClient, editor: str) -> None:
    document = await create_brief(client)
    assert document["title"] == "Onboarding refresh"
    assert document["my_access"] == "owner"
    fields = {f["field_path"]: f for f in document["fields"]}
    assert fields["brief.goal"]["value"] == "Reach first value in three days."
    assert fields["brief.goal"]["source"] == "user"
    assert fields["brief.summary"]["value"] is None

    audit = (
        await client.get(f"/api/documents/{document['id']}/audit", headers=as_user(editor))
    ).json()
    assert {(a["action"], a["field_path"]) for a in audit} == {
        ("create", "brief.title"),
        ("create", "brief.goal"),
    }


async def test_viewers_cannot_create_documents(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/documents",
        json={"document_type": "brief", "fields": {"brief.title": "x", "brief.goal": "y"}},
        headers=as_user(VIEWER),
    )
    assert response.status_code == 403


async def test_creating_validates_against_the_catalog(
    client: httpx.AsyncClient, editor: str
) -> None:
    async def create(body: dict[str, object]) -> int:
        response = await client.post("/api/documents", json=body, headers=as_user(editor))
        return response.status_code

    assert await create({"document_type": "memo", "fields": {}}) == 422
    assert (
        await create({"document_type": "brief", "fields": {"brief.title": "only a title"}}) == 422
    )
    assert await create({"document_type": "brief", "fields": {"brief.nope": "x"}}) == 422


async def test_documents_are_invisible_without_access(
    client: httpx.AsyncClient, editor: str
) -> None:
    document = await create_brief(client)
    await grant(client, OTHER_EDITOR, Role.EDITOR)
    other = as_user(OTHER_EDITOR)
    assert (await client.get(f"/api/documents/{document['id']}", headers=other)).status_code == 404
    assert (await client.get("/api/documents", headers=other)).json() == []
    # Admins see everything.
    listed = (await client.get("/api/documents", headers=as_user(ADMIN))).json()
    assert [d["id"] for d in listed] == [document["id"]]


async def test_editing_a_field_is_audited(client: httpx.AsyncClient, editor: str) -> None:
    document = await create_brief(client)
    url = f"/api/documents/{document['id']}/fields/brief.title"
    response = await client.patch(url, json={"value": "New title"}, headers=as_user(editor))
    assert response.status_code == 200
    assert response.json()["value"] == "New title"
    fresh = (await client.get(f"/api/documents/{document['id']}", headers=as_user(editor))).json()
    assert fresh["title"] == "New title"
    audit = (
        await client.get(f"/api/documents/{document['id']}/audit", headers=as_user(editor))
    ).json()
    assert audit[0]["action"] == "update"
    assert (audit[0]["value_before"], audit[0]["value_after"]) == (
        "Onboarding refresh",
        "New title",
    )


async def test_field_values_must_match_their_type(client: httpx.AsyncClient, editor: str) -> None:
    document = await create_brief(client)
    url = f"/api/documents/{document['id']}/fields/brief.risks"
    assert (
        await client.patch(url, json={"value": "not a list"}, headers=as_user(editor))
    ).status_code == 422
    assert (
        await client.patch(url, json={"value": ["ok"]}, headers=as_user(editor))
    ).status_code == 200
    title = f"/api/documents/{document['id']}/fields/brief.title"
    assert (
        await client.patch(title, json={"value": ""}, headers=as_user(editor))
    ).status_code == 422
    unknown = f"/api/documents/{document['id']}/fields/brief.nope"
    assert (
        await client.patch(unknown, json={"value": "x"}, headers=as_user(editor))
    ).status_code == 404


async def test_only_owners_delete(client: httpx.AsyncClient, editor: str) -> None:
    document = await create_brief(client)
    share = {"email": OTHER_EDITOR, "access": "edit"}
    await client.put(f"/api/documents/{document['id']}/access", json=share, headers=as_user(editor))
    url = f"/api/documents/{document['id']}"
    assert (await client.delete(url, headers=as_user(OTHER_EDITOR))).status_code == 403
    assert (await client.delete(url, headers=as_user(EDITOR))).status_code == 204
    assert (await client.get(url, headers=as_user(EDITOR))).status_code == 404
