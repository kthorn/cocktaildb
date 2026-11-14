"""API tests for ratings and the personal ingredient inventory."""

import psycopg2
import pytest
import pytest_asyncio

USER_ID = "rating-inventory-user"


def _rows(params, sql, args=()):
    conn = psycopg2.connect(**params)
    conn.autocommit = True
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, args)
            return cursor.fetchall() if cursor.description else []
    finally:
        conn.close()


@pytest_asyncio.fixture
async def signed_in(test_client_with_data):
    """Client whose requests are authenticated as USER_ID."""
    from dependencies.auth import (
        UserInfo,
        get_current_user_optional,
        require_authentication,
    )

    client, app = test_client_with_data
    user = UserInfo(user_id=USER_ID, username="rater", groups=[], claims={})
    app.dependency_overrides[require_authentication] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def recipe_id(test_db_with_data):
    """A seeded recipe nobody has rated, so counts and averages are exact."""
    return _rows(
        test_db_with_data,
        "SELECT min(id) FROM recipes WHERE id NOT IN (SELECT recipe_id FROM ratings)",
    )[0][0]


# ---------------------------------------------------------------- ratings


@pytest.mark.asyncio
async def test_rating_is_created_then_updated_in_place(signed_in, recipe_id):
    created = await signed_in.post(f"/ratings/{recipe_id}", json={"rating": 4})
    assert created.status_code == 201, created.text
    assert created.json()["user_id"] == USER_ID
    assert created.json()["rating"] == 4

    updated = await signed_in.post(f"/ratings/{recipe_id}", json={"rating": 2})
    assert updated.status_code == 201, updated.text

    summary = (await signed_in.get(f"/ratings/{recipe_id}")).json()
    assert summary["rating_count"] == 1
    assert summary["avg_rating"] == 2
    assert summary["user_rating"]["rating"] == 2
    assert summary["user_rating"]["user_id"] == USER_ID


@pytest.mark.asyncio
async def test_anonymous_summary_has_no_user_rating(
    test_client_with_data, signed_in, recipe_id
):
    await signed_in.post(f"/ratings/{recipe_id}", json={"rating": 5})
    _, app = test_client_with_data
    app.dependency_overrides.clear()

    summary = (await signed_in.get(f"/ratings/{recipe_id}")).json()

    assert summary["rating_count"] == 1
    assert summary["user_rating"] is None


@pytest.mark.asyncio
async def test_ratings_for_missing_recipe_are_not_found(signed_in):
    assert (await signed_in.get("/ratings/987654")).status_code == 404
    response = await signed_in.post("/ratings/987654", json={"rating": 3})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_rating_outside_one_to_five_is_rejected(signed_in, recipe_id):
    response = await signed_in.post(f"/ratings/{recipe_id}", json={"rating": 6})
    assert response.status_code == 422


# ---------------------------------------------------------------- inventory


async def _inventory_ids(client):
    response = await client.get("/user-ingredients")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_count"] == len(body["ingredients"])
    return {item["ingredient_id"] for item in body["ingredients"]}


@pytest.fixture
def child_ingredient(test_db_with_data):
    """(child_id, parent_id) for a seeded ingredient with a parent."""
    return _rows(
        test_db_with_data,
        "SELECT id, parent_id FROM ingredients WHERE parent_id IS NOT NULL "
        "ORDER BY id LIMIT 1",
    )[0]


@pytest.mark.asyncio
async def test_add_list_and_remove_single_ingredient(signed_in, child_ingredient):
    child_id, parent_id = child_ingredient

    added = await signed_in.post("/user-ingredients", json={"ingredient_id": child_id})
    assert added.status_code == 201, added.text
    assert added.json()["ingredient_id"] == child_id
    # Adding a child also adds its ancestors.
    assert {child_id, parent_id} <= await _inventory_ids(signed_in)

    removed = await signed_in.delete(f"/user-ingredients/{child_id}")
    assert removed.status_code == 200, removed.text
    assert child_id not in await _inventory_ids(signed_in)

    again = await signed_in.delete(f"/user-ingredients/{child_id}")
    assert again.status_code == 404


@pytest.mark.asyncio
async def test_adding_unknown_or_duplicate_ingredient_fails(
    signed_in, child_ingredient
):
    missing = await signed_in.post("/user-ingredients", json={"ingredient_id": 987654})
    assert missing.status_code == 404

    child_id, _ = child_ingredient
    await signed_in.post("/user-ingredients", json={"ingredient_id": child_id})
    duplicate = await signed_in.post(
        "/user-ingredients", json={"ingredient_id": child_id}
    )
    assert duplicate.status_code == 400


@pytest.mark.asyncio
async def test_bulk_remove_reports_counts(signed_in, child_ingredient):
    child_id, parent_id = child_ingredient
    await signed_in.post("/user-ingredients", json={"ingredient_id": child_id})

    response = await signed_in.request(
        "DELETE",
        "/user-ingredients/bulk",
        json={"ingredient_ids": [child_id, parent_id, 987654]},
    )

    assert response.status_code == 200, response.text
    assert response.json()["removed_count"] == 2
    assert response.json()["not_found_count"] == 1
    assert {child_id, parent_id}.isdisjoint(await _inventory_ids(signed_in))


@pytest.mark.asyncio
async def test_bulk_remove_refuses_to_orphan_a_child(signed_in, child_ingredient):
    child_id, parent_id = child_ingredient
    await signed_in.post("/user-ingredients", json={"ingredient_id": child_id})

    response = await signed_in.request(
        "DELETE", "/user-ingredients/bulk", json={"ingredient_ids": [parent_id]}
    )

    assert response.status_code == 400
    assert {child_id, parent_id} <= await _inventory_ids(signed_in)


@pytest.mark.asyncio
async def test_recommendations_name_the_missing_ingredient(
    signed_in, test_db_with_data
):
    have, need = (
        row[0]
        for row in _rows(
            test_db_with_data,
            "INSERT INTO ingredients (name, path) VALUES "
            "('Coverage Base', '/tmp/'), ('Coverage Modifier', '/tmp/') RETURNING id",
        )
    )
    for ingredient_id in (have, need):
        _rows(
            test_db_with_data,
            "UPDATE ingredients SET path = %s WHERE id = %s",
            (f"/{ingredient_id}/", ingredient_id),
        )
    recipe = _rows(
        test_db_with_data,
        "INSERT INTO recipes (name) VALUES ('Coverage Sour') RETURNING id",
    )[0][0]
    _rows(
        test_db_with_data,
        "INSERT INTO recipe_ingredients (recipe_id, ingredient_id, amount, unit_id) "
        "VALUES (%s, %s, 1, 1), (%s, %s, 1, 1)",
        (recipe, have, recipe, need),
    )
    await signed_in.post("/user-ingredients", json={"ingredient_id": have})

    response = await signed_in.get("/user-ingredients/recommendations?limit=50")

    assert response.status_code == 200, response.text
    by_id = {rec["id"]: rec for rec in response.json()["recommendations"]}
    assert "Coverage Sour" in by_id[need]["recipe_names"]
    assert have not in by_id


@pytest.mark.asyncio
async def test_bulk_add_counts_new_duplicate_and_unknown(signed_in, child_ingredient):
    child_id, _ = child_ingredient

    response = await signed_in.post(
        "/user-ingredients/bulk", json={"ingredient_ids": [child_id, child_id, 987654]}
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert (
        body["added_count"],
        body["already_exists_count"],
        body["failed_count"],
    ) == (
        1,
        1,
        1,
    )
    assert any("987654" in error for error in body["errors"])
    assert child_id in await _inventory_ids(signed_in)
