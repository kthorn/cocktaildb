"""End-to-end CRUD workflows for ingredients and recipes through the API."""

import pytest

pytestmark = pytest.mark.asyncio


async def _create_ingredient(client, name, parent_id=None):
    response = await client.post(
        "/ingredients", json={"name": name, "parent_id": parent_id}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_recipe(client, name, ingredient_ids):
    response = await client.post(
        "/recipes",
        json={
            "name": name,
            "instructions": "Stir with ice and strain",
            "ingredients": [
                {"ingredient_id": ingredient_id, "amount": 1.5, "unit_id": 1}
                for ingredient_id in ingredient_ids
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_ingredient_hierarchy_crud_workflow(editor_client):
    parent = await _create_ingredient(editor_client, "Test Spirits")
    child = await _create_ingredient(editor_client, "Test Gin", parent_id=parent["id"])
    assert child["parent_id"] == parent["id"]
    assert child["path"] == f"/{parent['id']}/{child['id']}/"

    update = await editor_client.put(
        f"/ingredients/{child['id']}", json={"description": "Juniper-forward"}
    )
    assert update.status_code == 200, update.text
    assert update.json()["description"] == "Juniper-forward"
    assert update.json()["parent_id"] == parent["id"]

    assert (
        await editor_client.delete(f"/ingredients/{child['id']}")
    ).status_code == 200
    assert (
        await editor_client.delete(f"/ingredients/{parent['id']}")
    ).status_code == 200
    assert (await editor_client.get(f"/ingredients/{parent['id']}")).status_code == 404


async def test_recipe_with_ingredients_crud_workflow(editor_client):
    gin = await _create_ingredient(editor_client, "Gin")
    vermouth = await _create_ingredient(editor_client, "Dry Vermouth")
    created = await _create_recipe(
        editor_client, "Test Complex Martini", [gin["id"], vermouth["id"]]
    )

    read = await editor_client.get(f"/recipes/{created['id']}")
    assert read.status_code == 200, read.text
    assert {i["ingredient_id"] for i in read.json()["ingredients"]} == {
        gin["id"],
        vermouth["id"],
    }

    update = await editor_client.put(
        f"/recipes/{created['id']}",
        json={"instructions": "Stir gently, double strain, express lemon peel"},
    )
    assert update.status_code == 200, update.text
    assert update.json()["instructions"] == (
        "Stir gently, double strain, express lemon peel"
    )
    assert len(update.json()["ingredients"]) == 2

    assert (await editor_client.delete(f"/recipes/{created['id']}")).status_code == 200
    assert (await editor_client.get(f"/recipes/{created['id']}")).status_code == 404


async def test_successive_recipe_updates_keep_the_last_write(editor_client):
    gin = await _create_ingredient(editor_client, "Gin")
    created = await _create_recipe(editor_client, "Update Order Recipe", [gin["id"]])

    for instructions in ("First update", "Second update"):
        response = await editor_client.put(
            f"/recipes/{created['id']}", json={"instructions": instructions}
        )
        assert response.status_code == 200, response.text

    final = await editor_client.get(f"/recipes/{created['id']}")
    assert final.json()["instructions"] == "Second update"


async def test_deep_ingredient_hierarchy_paths(editor_client):
    spirit = await _create_ingredient(editor_client, "Spirit")
    whiskey = await _create_ingredient(editor_client, "Whiskey", spirit["id"])
    bourbon = await _create_ingredient(editor_client, "Bourbon", whiskey["id"])

    response = await editor_client.get(f"/ingredients/{bourbon['id']}")

    assert response.status_code == 200, response.text
    assert response.json()["path"] == (
        f"/{spirit['id']}/{whiskey['id']}/{bourbon['id']}/"
    )
