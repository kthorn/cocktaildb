"""Search returns each of a recipe's tags once, however many ingredients it has."""

import pytest


@pytest.mark.parametrize(
    "sort_by,paginate", [("name", True), ("name", False), ("random", True)]
)
def test_search_lists_each_tag_once(db_instance, sort_by, paginate):
    db = db_instance
    ingredient_ids = [
        db.create_ingredient({"name": f"Tag Test Spirit {n}"})["id"] for n in range(3)
    ]
    recipe = db.create_recipe(
        {
            "name": "Three Ingredient Sour",
            "ingredients": [
                {"ingredient_id": ingredient_id, "unit_id": 1, "amount": 1}
                for ingredient_id in ingredient_ids
            ],
        }
    )
    public = db.create_public_tag("sour")
    private = db.create_private_tag("weeknight", "tag-user")
    db.add_public_tag_to_recipe(recipe["id"], public["id"])
    db.add_private_tag_to_recipe(recipe["id"], private["id"])

    result = db.search_recipes_paginated(
        {"q": "Three Ingredient Sour"},
        sort_by=sort_by,
        user_id="tag-user",
        return_pagination=paginate,
    )
    recipes = result["recipes"] if paginate else result

    assert len(recipes) == 1
    assert len(recipes[0]["ingredients"]) == 3
    assert sorted((t["name"], t["type"]) for t in recipes[0]["tags"]) == [
        ("sour", "public"),
        ("weeknight", "private"),
    ]
