"""PUT /ingredients/{id} must persist URL changes."""

import pytest

URL = "https://example.com/gin"


async def _create(client, name, **fields):
    response = await client.post("/ingredients", json={"name": name, **fields})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _url_of(client, ingredient_id):
    response = await client.get(f"/ingredients/{ingredient_id}")
    assert response.status_code == 200, response.text
    return response.json()["url"]


@pytest.mark.asyncio
async def test_update_sets_url(editor_client):
    gin = await _create(editor_client, "Gin")

    response = await editor_client.put(f"/ingredients/{gin}", json={"url": URL})

    assert response.status_code == 200, response.text
    assert await _url_of(editor_client, gin) == URL


@pytest.mark.asyncio
async def test_update_sets_url_while_changing_parent(editor_client):
    spirit = await _create(editor_client, "Spirit")
    gin = await _create(editor_client, "Gin")

    response = await editor_client.put(
        f"/ingredients/{gin}", json={"parent_id": spirit, "url": URL}
    )

    assert response.status_code == 200, response.text
    assert await _url_of(editor_client, gin) == URL


@pytest.mark.asyncio
async def test_update_with_null_url_clears_it(editor_client):
    gin = await _create(editor_client, "Gin", url=URL)

    response = await editor_client.put(f"/ingredients/{gin}", json={"url": None})

    assert response.status_code == 200, response.text
    assert await _url_of(editor_client, gin) is None


@pytest.mark.asyncio
async def test_update_without_url_keeps_it(editor_client):
    gin = await _create(editor_client, "Gin", url=URL)

    response = await editor_client.put(
        f"/ingredients/{gin}", json={"description": "London dry"}
    )

    assert response.status_code == 200, response.text
    assert await _url_of(editor_client, gin) == URL
