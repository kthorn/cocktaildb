"""Client errors raised below the routes must reach clients as 4xx responses.

Route handlers used to wrap everything in ``except Exception`` and re-raise a
500 ``DatabaseException`` carrying ``str(e)``, which turned conflicts and
invalid input into server errors and leaked database error text.
"""

import httpx
import psycopg2
import pytest
from db.db_core import Database


async def _create_ingredient(client, name, parent_id=None):
    response = await client.post(
        "/ingredients", json={"name": name, "parent_id": parent_id}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _create_recipe(client, name, ingredient_id):
    return await client.post(
        "/recipes",
        json={
            "name": name,
            "instructions": "Stir.",
            "ingredients": [
                {"ingredient_id": ingredient_id, "amount": 2, "unit_id": 1}
            ],
        },
    )


@pytest.mark.asyncio
async def test_duplicate_recipe_name_is_conflict(editor_client):
    gin = await _create_ingredient(editor_client, "Gin")
    first = await _create_recipe(editor_client, "Martinez", gin)
    assert first.status_code == 201, first.text

    response = await _create_recipe(editor_client, "Martinez", gin)

    assert response.status_code == 409
    assert "already exists" in response.json()["error"]


@pytest.mark.asyncio
async def test_recipe_with_unknown_ingredient_is_bad_request(editor_client):
    response = await _create_recipe(editor_client, "Mystery", 987654)

    assert response.status_code == 400
    assert "987654" in response.json()["error"]


@pytest.mark.asyncio
async def test_ingredient_cycle_is_bad_request(editor_client):
    spirit = await _create_ingredient(editor_client, "Spirit")
    gin = await _create_ingredient(editor_client, "Gin", parent_id=spirit)

    response = await editor_client.put(
        f"/ingredients/{spirit}", json={"parent_id": gin}
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_deleting_ingredient_with_children_is_bad_request(editor_client):
    spirit = await _create_ingredient(editor_client, "Spirit")
    await _create_ingredient(editor_client, "Gin", parent_id=spirit)

    response = await editor_client.delete(f"/ingredients/{spirit}")

    assert response.status_code == 400
    assert "child" in response.json()["error"]


async def _recipe_and_tag(client, tag_kind):
    gin = await _create_ingredient(client, "Gin")
    recipe = await _create_recipe(client, "Gibson", gin)
    assert recipe.status_code == 201, recipe.text
    tag = await client.post(f"/tags/{tag_kind}", json={"name": "favorite"})
    assert tag.status_code == 201, tag.text
    return recipe.json()["id"], tag.json()["id"]


@pytest.mark.asyncio
async def test_private_tag_added_as_public_is_bad_request(editor_client):
    recipe_id, tag_id = await _recipe_and_tag(editor_client, "private")

    response = await editor_client.post(
        f"/recipes/{recipe_id}/public_tags", json={"tag_id": tag_id}
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_public_tag_added_as_private_is_bad_request(editor_client):
    recipe_id, tag_id = await _recipe_and_tag(editor_client, "public")

    response = await editor_client.post(
        f"/recipes/{recipe_id}/private_tags", json={"tag_id": tag_id}
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_other_users_private_tag_is_not_found(editor_client, pg_db_with_schema):
    gin = await _create_ingredient(editor_client, "Gin")
    recipe = await _create_recipe(editor_client, "Gibson", gin)
    conn = psycopg2.connect(**pg_db_with_schema)
    conn.autocommit = True
    with conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO tags (name, created_by) VALUES ('secret', 'someone-else') "
            "RETURNING id"
        )
        tag_id = cursor.fetchone()[0]
    conn.close()

    response = await editor_client.post(
        f"/recipes/{recipe.json()['id']}/private_tags", json={"tag_id": tag_id}
    )

    assert response.status_code == 404


async def _get_without_raising(app, path):
    """Request through the full middleware stack, returning 500s as responses."""
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


@pytest.mark.asyncio
async def test_unexpected_database_error_does_not_leak_details(
    test_client_memory_with_app, monkeypatch
):
    def fail(self):
        raise psycopg2.OperationalError(
            'connection to server at "10.0.0.5", port 5432 failed'
        )

    monkeypatch.setattr(Database, "get_units", fail)

    _, app = test_client_memory_with_app
    response = await _get_without_raising(app, "/units")

    assert response.status_code == 500
    assert "10.0.0.5" not in response.text


@pytest.mark.asyncio
async def test_invalid_response_data_is_server_error(
    test_client_memory_with_app, monkeypatch
):
    # pydantic's ValidationError subclasses ValueError; a malformed row is a
    # server bug, not a client error.
    monkeypatch.setattr(Database, "get_units", lambda self: [{"name": None}])

    _, app = test_client_memory_with_app
    response = await _get_without_raising(app, "/units")

    assert response.status_code == 500
