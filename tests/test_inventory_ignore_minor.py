import pytest


def _add_recipe(db, name, rows):
    """Create a recipe from (ingredient name, unit name, amount) rows."""
    db.execute_query(
        "INSERT INTO recipes (name, instructions) VALUES (%s, 'Mix')", (name,)
    )
    for ingredient, unit, amount in rows:
        db.execute_query(
            """
            INSERT INTO ingredients (name, path)
            VALUES (%(name)s, '/tmp/')
            ON CONFLICT (name) DO NOTHING
            """,
            {"name": ingredient},
        )
        db.execute_query(
            "UPDATE ingredients SET path = '/' || id || '/' WHERE path = '/tmp/'"
        )
        db.execute_query(
            """
            INSERT INTO recipe_ingredients (recipe_id, ingredient_id, unit_id, amount)
            SELECT r.id, i.id, u.id, %(amount)s
            FROM recipes r, ingredients i, units u
            WHERE r.name = %(recipe)s AND i.name = %(ingredient)s
            AND u.name = %(unit)s
            """,
            {"recipe": name, "ingredient": ingredient, "unit": unit, "amount": amount},
        )


@pytest.fixture
def minor_db(db_instance_with_data):
    db = db_instance_with_data
    _add_recipe(
        db,
        "Mole Daiquiri",
        [
            ("Rum", "ounce", 2),
            ("Lime Juice", "ounce", 0.75),
            ("Simple Syrup", "ounce", 0.5),
            ("Xocolatl Mole Bitters", "dash", 2),
        ],
    )
    _add_recipe(
        db,
        "Absinthe Rinse Rum",
        [("Rum", "ounce", 2), ("Absinthe", "to rinse", None)],
    )
    _add_recipe(
        db,
        "Maraschino Rum",
        [("Rum", "ounce", 2), ("Maraschino Liqueur", "ounce", 0.25)],
    )
    _add_recipe(
        db,
        "Egg White Rum",
        [("Rum", "ounce", 2), ("Egg White", "Each", 1)],
    )
    db.add_user_ingredients_bulk("alice", [2, 11, 12])
    return db


def _names(db, params, paginate):
    result = db.search_recipes_paginated(
        params, user_id="alice", return_pagination=paginate, limit=100
    )
    recipes = result["recipes"] if paginate else result
    return {r["name"] for r in recipes}


@pytest.mark.parametrize("paginate", [False, True])
def test_ignore_minor_surfaces_recipes_missing_only_small_amounts(minor_db, paginate):
    strict = _names(minor_db, {"inventory": True}, paginate)
    relaxed = _names(minor_db, {"inventory": True, "ignore_minor": True}, paginate)

    assert "Mole Daiquiri" not in strict
    assert "Absinthe Rinse Rum" not in strict
    assert {"Mole Daiquiri", "Absinthe Rinse Rum", "Test Daiquiri"} <= relaxed


@pytest.mark.parametrize("paginate", [False, True])
def test_ignore_minor_still_requires_larger_and_unmeasured_ingredients(
    minor_db, paginate
):
    relaxed = _names(minor_db, {"inventory": True, "ignore_minor": True}, paginate)

    assert "Maraschino Rum" not in relaxed
    assert "Egg White Rum" not in relaxed


def test_ignore_minor_without_inventory_does_not_filter(minor_db):
    everything = _names(minor_db, {}, False)
    assert _names(minor_db, {"ignore_minor": True}, False) == everything


@pytest.mark.asyncio
async def test_authenticated_search_accepts_ignore_minor(
    minor_db, editor_client_with_data
):
    minor_db.add_user_ingredients_bulk("editor-user-123", [2, 11, 12])
    client = editor_client_with_data

    async def names(query):
        response = await client.get(f"/recipes/search/authenticated?{query}")
        assert response.status_code == 200
        return {r["name"] for r in response.json()["recipes"]}

    assert "Mole Daiquiri" not in await names("inventory=true")
    assert "Mole Daiquiri" in await names("inventory=true&ignore_minor=true")
