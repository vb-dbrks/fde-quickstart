import httpx

from tests.conftest import create_brief
from tests.helpers import EDITOR, OTHER_EDITOR, VIEWER, as_user


async def share(
    client: httpx.AsyncClient, document_id: str, email: str, access: str, by: str = EDITOR
) -> int:
    response = await client.put(
        f"/api/documents/{document_id}/access",
        json={"email": email, "access": access},
        headers=as_user(by),
    )
    return response.status_code


async def test_view_access_reads_but_cannot_edit(client: httpx.AsyncClient, editor: str) -> None:
    document = await create_brief(client)
    assert await share(client, document["id"], VIEWER, "view") == 200

    viewer = as_user(VIEWER)
    fetched = (await client.get(f"/api/documents/{document['id']}", headers=viewer)).json()
    assert fetched["my_access"] == "view"
    edit = await client.patch(
        f"/api/documents/{document['id']}/fields/brief.goal", json={"value": "x"}, headers=viewer
    )
    assert edit.status_code == 403


async def test_edit_access_allows_editing(client: httpx.AsyncClient, editor: str) -> None:
    document = await create_brief(client)
    await share(client, document["id"], OTHER_EDITOR, "edit")
    edit = await client.patch(
        f"/api/documents/{document['id']}/fields/brief.goal",
        json={"value": "Sharper goal"},
        headers=as_user(OTHER_EDITOR),
    )
    assert edit.status_code == 200


async def test_only_owners_share(client: httpx.AsyncClient, editor: str) -> None:
    document = await create_brief(client)
    await share(client, document["id"], OTHER_EDITOR, "edit")
    assert await share(client, document["id"], VIEWER, "view", by=OTHER_EDITOR) == 403
    access = (
        await client.get(f"/api/documents/{document['id']}/access", headers=as_user(EDITOR))
    ).json()
    assert {(a["principal"], a["access"]) for a in access} == {
        (EDITOR, "owner"),
        (OTHER_EDITOR, "edit"),
    }


async def test_the_last_owner_cannot_be_removed(client: httpx.AsyncClient, editor: str) -> None:
    document = await create_brief(client)
    url = f"/api/documents/{document['id']}/access"
    assert (await client.delete(f"{url}/{EDITOR}", headers=as_user(EDITOR))).status_code == 409
    await share(client, document["id"], VIEWER, "view")
    assert (await client.delete(f"{url}/{VIEWER}", headers=as_user(EDITOR))).status_code == 204
    assert (await client.delete(f"{url}/{VIEWER}", headers=as_user(EDITOR))).status_code == 404
    assert (
        await client.get(f"/api/documents/{document['id']}", headers=as_user(VIEWER))
    ).status_code == 404
