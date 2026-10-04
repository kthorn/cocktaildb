# ruff: noqa: FURB157

from decimal import Decimal
from unittest.mock import Mock

import pytest

from api.db.db_core import Database
from api.db.sql_queries import RESOLVE_INGREDIENT_ABV_SQL
from api.models.responses import RecipeABVResponse, RecipeResponse


def ingredient(ingredient_id, amount=10, name=None):
    return {
        "ingredient_id": ingredient_id,
        "ingredient_name": name or f"Ingredient {ingredient_id}",
        "amount": amount,
        "unit_name": "ml",
        "conversion_to_ml": Decimal("1"),
    }


def resolved(ingredient_id, lo=40, hi=40, source="recorded"):
    return {
        "ingredient_id": ingredient_id,
        "min_percent_abv": Decimal(str(lo)),
        "max_percent_abv": Decimal(str(hi)),
        "observation_count": 1,
        "family_id": ingredient_id,
        "family_name": f"Family {ingredient_id}",
        "source": source,
    }


def test_enrichment_uses_one_bulk_lookup_and_indexes_all_recipes():
    recipes = [
        {"id": 1, "ingredients": [ingredient(2), ingredient(1)]},
        {"id": 2, "ingredients": [ingredient(2)]},
    ]
    execute = Mock(return_value=[resolved(1), resolved(2, 0, 0)])
    db = Database.__new__(Database)

    db._add_recipe_abv(recipes, execute)

    execute.assert_called_once_with(
        RESOLVE_INGREDIENT_ABV_SQL, {"ingredient_ids": [1, 2]}
    )
    assert recipes[0]["abv"]["display"] == "20%"
    assert recipes[1]["abv"]["display"] == "0%"


def test_enrichment_uses_the_passed_cursor_executor_without_opening_a_connection():
    recipes = [{"id": 1, "ingredients": [ingredient(1)]}]
    cursor_execute = Mock(return_value=[resolved(1)])
    db = Database.__new__(Database)

    db._add_recipe_abv(recipes, cursor_execute)

    cursor_execute.assert_called_once()
    assert recipes[0]["abv"]["status"] == "calculated"


def test_enrichment_propagates_sql_failures():
    error = RuntimeError("database unavailable")
    execute = Mock(side_effect=error)
    db = Database.__new__(Database)

    with pytest.raises(RuntimeError) as raised:
        db._add_recipe_abv([{"id": 1, "ingredients": [ingredient(1)]}], execute)

    assert raised.value is error


def test_missing_returned_ingredient_id_becomes_explicit_unknown():
    recipes = [{"id": 1, "ingredients": [ingredient(1), ingredient(2)]}]
    execute = Mock(return_value=[resolved(1)])
    db = Database.__new__(Database)

    db._add_recipe_abv(recipes, execute)

    assert recipes[0]["abv"]["status"] == "unknown"
    assert recipes[0]["abv"]["min_percent"] is None
    assert any("Ingredient 2" in note for note in recipes[0]["abv"]["notes"])


def test_empty_recipe_collection_and_empty_ingredients_skip_lookup():
    execute = Mock(side_effect=AssertionError("lookup should not run"))
    db = Database.__new__(Database)
    recipes = [{"id": 1, "ingredients": []}]

    db._add_recipe_abv(recipes, execute)

    execute.assert_not_called()
    assert recipes[0]["abv"]["status"] == "unknown"


def test_recipe_abv_response_serializes_additive_contract():
    abv = RecipeABVResponse(
        status="estimated",
        min_percent=Decimal("36.9"),
        max_percent=44.6,
        display="36–45%",
        notes=["Unknown strength for Ingredient 2"],
    )
    response = RecipeResponse(id=1, name="Test", abv=abv)

    payload = response.model_dump()

    assert payload["abv"] == {
        "status": "estimated",
        "min_percent": pytest.approx(36.9),
        "max_percent": pytest.approx(44.6),
        "display": "36–45%",
        "notes": ["Unknown strength for Ingredient 2"],
    }


def test_recipe_response_keeps_abv_optional_for_legacy_payloads():
    response = RecipeResponse(id=1, name="Legacy")

    assert response.abv is None


def _set_recorded_abv(db, ingredient_name, percent):
    row = db.execute_query(
        "SELECT id FROM ingredients WHERE name = %(name)s", {"name": ingredient_name}
    )[0]
    db.execute_query(
        "UPDATE ingredients SET percent_abv = %(percent)s WHERE id = %(id)s",
        {"percent": percent, "id": row["id"]},
    )
    return row["id"]


@pytest.mark.parametrize(
    ("sort_by", "return_pagination"),
    [("name", False), ("name", True), ("random", True)],
)
def test_get_and_search_paths_include_matching_abv_payload(
    db_instance, sort_by, return_pagination
):
    db = db_instance
    known = db.create_ingredient({"name": "Recorded spirit", "percent_abv": 40})
    unknown = db.create_ingredient({"name": "Unobserved ingredient"})
    unit_id = db.execute_query("SELECT id FROM units WHERE name = 'milliliter'")[0][
        "id"
    ]
    created = db.create_recipe(
        {
            "name": "Small unknown contribution",
            "ingredients": [
                {"ingredient_id": known["id"], "unit_id": unit_id, "amount": 60},
                {"ingredient_id": unknown["id"], "unit_id": unit_id, "amount": 5},
            ],
        }
    )
    recipes = db.search_recipes_paginated(
        {},
        limit=100,
        offset=0,
        sort_by=sort_by,
        return_pagination=return_pagination,
    )
    listed = recipes["recipes"] if return_pagination else recipes
    assert len(listed) == 1
    target = db.get_recipe(created["id"])
    for recipe in (created, target, listed[0]):
        assert recipe["abv"]["status"] == "estimated"
        assert recipe["abv"]["display"] == "36–45%"
        assert recipe["abv"]["min_percent"] == pytest.approx(36.9230769231)
        assert recipe["abv"]["max_percent"] == pytest.approx(44.6153846154)
        assert any("Unobserved ingredient" in note for note in recipe["abv"]["notes"])
    assert listed[0]["abv"] == target["abv"]


def test_keyset_and_offset_searches_enrich_after_trimming(db_instance_with_data):
    db = db_instance_with_data
    _set_recorded_abv(db, "Bourbon", 40)
    first = db.search_recipes_paginated({}, limit=1, return_pagination=True)
    keyset = db.search_recipes_paginated(
        {}, limit=1, cursor=first["next_cursor"], return_pagination=True
    )
    offset = db.search_recipes_paginated({}, limit=1, offset=1, return_pagination=True)
    assert first["recipes"][0]["abv"] is not None
    assert keyset["recipes"][0]["abv"] is not None
    assert offset["recipes"][0]["abv"] is not None


def test_inventory_search_uses_transaction_cursor_for_abv_lookup(db_instance_with_data):
    db = db_instance_with_data
    _set_recorded_abv(db, "Bourbon", 40)
    db.add_user_ingredients_bulk("abv-user", list(range(1, 14)))

    result = db.search_recipes_paginated(
        {"inventory": True},
        user_id="abv-user",
        limit=2,
        return_pagination=True,
    )

    assert result["recipes"]
    assert all(recipe["abv"] is not None for recipe in result["recipes"])


def test_abv_is_fresh_after_leaf_edit_and_create_update_reads(db_instance):
    db = db_instance
    bourbon_id = db.create_ingredient({"name": "ABV Bourbon", "percent_abv": 40})["id"]
    unit_id = db.execute_query("SELECT id FROM units WHERE name = 'milliliter'")[0][
        "id"
    ]
    created = db.create_recipe(
        {
            "name": "ABV Fresh Recipe",
            "ingredients": [
                {"ingredient_id": bourbon_id, "unit_id": unit_id, "amount": 10}
            ],
        }
    )
    assert created["abv"]["display"] == "40%"

    db.execute_query(
        "UPDATE ingredients SET percent_abv = 60 WHERE id = %(id)s",
        {"id": bourbon_id},
    )
    assert db.get_recipe(created["id"])["abv"]["display"] == "60%"

    updated = db.update_recipe(
        created["id"],
        {
            "ingredients": [
                {"ingredient_id": bourbon_id, "unit_id": unit_id, "amount": 5}
            ]
        },
    )
    assert updated["abv"]["display"] == "60%"


def test_bulk_create_stays_minimal_then_normal_get_enriches(db_instance):
    db = db_instance
    bourbon_id = db.create_ingredient({"name": "Bulk ABV Bourbon", "percent_abv": 40})[
        "id"
    ]
    unit_id = db.execute_query("SELECT id FROM units WHERE name = 'milliliter'")[0][
        "id"
    ]
    created = db.bulk_create_recipes(
        [
            {
                "name": "Bulk ABV Recipe",
                "ingredients": [
                    {"ingredient_id": bourbon_id, "unit_id": unit_id, "amount": 10}
                ],
            }
        ],
        "bulk-user",
    )

    assert RecipeResponse(**created[0]).abv is None
    assert db.get_recipe(created[0]["id"])["abv"]["display"] == "40%"
