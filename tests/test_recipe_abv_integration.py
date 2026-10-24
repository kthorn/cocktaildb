# ruff: noqa: FURB157

import logging
from decimal import Decimal
from unittest.mock import Mock, call

import pytest

from api.db.db_core import Database
from api.db.sql_queries import RECIPE_ABV_BOUNDS_SQL, RECIPE_ABV_ROWS_SQL
from api.models.responses import RecipeABVResponse, RecipeResponse


def bounds_row(recipe_id, percent="40"):
    return {
        "recipe_id": recipe_id,
        "status": "calculated",
        "unknown_reason": None,
        "min_percent": Decimal(percent),
        "max_percent": Decimal(percent),
        "narrow": True,
        "display_low": int(percent),
        "display_high": int(percent),
        "display_below_one": False,
    }


def contribution_row(recipe_id):
    return {
        "recipe_id": recipe_id,
        "ingredient_id": 1,
        "ingredient_name": "Spirit",
        "volume_rule": "measured",
        "invalid_reason": None,
        "volume_ml": Decimal("10"),
        "strength_source": "recorded",
        "contributes": True,
        "strength_display_low": 40,
        "strength_display_high": 40,
        "strength_display_below_one": False,
    }


def test_enrichment_uses_two_bulk_queries_for_all_recipes():
    recipes = [{"id": 1, "ingredients": []}, {"id": 2, "ingredients": []}]
    execute = Mock(
        side_effect=[
            [bounds_row(2, "0"), bounds_row(1)],
            [contribution_row(1), contribution_row(2)],
        ]
    )
    db = Database.__new__(Database)

    db._add_recipe_abv(recipes, execute)

    assert execute.call_args_list == [
        call(RECIPE_ABV_BOUNDS_SQL, {"recipe_ids": [1, 2]}),
        call(RECIPE_ABV_ROWS_SQL, {"recipe_ids": [1, 2]}),
    ]
    assert recipes[0]["abv"]["display"] == "40%"
    assert recipes[1]["abv"]["display"] == "0%"


def test_enrichment_propagates_sql_failures():
    error = RuntimeError("database unavailable")
    execute = Mock(side_effect=error)
    db = Database.__new__(Database)

    with pytest.raises(RuntimeError) as raised:
        db._add_recipe_abv([{"id": 1, "ingredients": []}], execute)

    assert raised.value is error


def test_recipe_missing_from_view_gets_null_abv_and_warning(caplog):
    recipes = [{"id": 1, "ingredients": []}, {"id": 2, "ingredients": []}]
    execute = Mock(side_effect=[[bounds_row(1)], [contribution_row(1)]])
    db = Database.__new__(Database)

    with caplog.at_level(logging.WARNING):
        db._add_recipe_abv(recipes, execute)

    assert recipes[0]["abv"]["display"] == "40%"
    assert recipes[1]["abv"] is None
    assert any("2" in record.getMessage() for record in caplog.records)


def test_empty_recipe_collection_skips_lookup():
    execute = Mock(side_effect=AssertionError("lookup should not run"))
    db = Database.__new__(Database)

    db._add_recipe_abv([], execute)

    execute.assert_not_called()


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


def test_note_order_matches_ingredient_query(db_instance):
    db = db_instance
    db.execute_query(
        """
        INSERT INTO ingredients (id, name, parent_id, percent_abv) VALUES
        (101, 'Family A', NULL, NULL), (102, 'A low', 101, 10),
        (103, 'A high', 101, 20), (104, 'A', 101, NULL),
        (111, 'Family B', NULL, NULL), (112, 'B low', 111, 12),
        (113, 'B high', 111, 18), (114, 'B', 111, NULL),
        (121, 'Family C', NULL, NULL), (122, 'C low', 121, 11),
        (123, 'C high', 121, 19), (124, 'C', 121, NULL)
        """
    )
    db.execute_query(
        "INSERT INTO recipes (id, name, instructions) VALUES (1, 'Ordered', 'Mix')"
    )
    db.execute_query(
        """
        INSERT INTO recipe_ingredients (recipe_id, ingredient_id, unit_id, amount)
        SELECT 1, v.ingredient_id, u.id, v.amount
        FROM (VALUES (1, 104, 'to top', NULL::real), (2, 114, 'milliliter', 10),
                     (3, 124, 'milliliter', 30)) AS v(position, ingredient_id, unit, amount)
        JOIN units u ON u.name = v.unit
        ORDER BY v.position
        """
    )

    notes = db.get_recipe(1)["abv"]["notes"]

    assert notes == [
        "C: 11–19%",
        "B: 12–18%",
        "Assumed 88.7205 mL for to top ingredient A.",
        "A: 10–20%",
    ]
