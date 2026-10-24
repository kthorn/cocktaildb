# ruff: noqa: FURB157
"""SQL views that own the recipe ABV rules (migration 19)."""

import itertools
from decimal import Decimal
from pathlib import Path

import pytest

from api.db.sql_queries import RESOLVE_INGREDIENT_ABV_SQL

_names = itertools.count(1)


def _select_id(db, table, name):
    return db.execute_query(
        f"SELECT id FROM {table} WHERE name = %(name)s",  # noqa: S608
        {"name": name},
    )[0]["id"]


def _unit(db, name, conversion):
    db.execute_query(
        """
        INSERT INTO units (name, conversion_to_ml) VALUES (%(name)s, %(conversion)s)
        ON CONFLICT (name) DO UPDATE SET conversion_to_ml = EXCLUDED.conversion_to_ml
        """,
        {"name": name, "conversion": conversion},
    )
    return _select_id(db, "units", name)


def _ingredient(db, percent=None, parent_id=None, name=None):
    name = name or f"View ingredient {next(_names)}"
    db.execute_query(
        """
        INSERT INTO ingredients (name, parent_id, percent_abv)
        VALUES (%(name)s, %(parent_id)s, %(percent)s)
        """,
        {"name": name, "parent_id": parent_id, "percent": percent},
    )
    return _select_id(db, "ingredients", name)


def _recipe(db, rows, name=None):
    """Create a recipe from (ingredient_id, unit_id_or_None, amount) rows."""
    name = name or f"View recipe {next(_names)}"
    db.execute_query(
        "INSERT INTO recipes (name, instructions) VALUES (%(name)s, 'Mix')",
        {"name": name},
    )
    recipe_id = _select_id(db, "recipes", name)
    for ingredient_id, unit_id, amount in rows:
        db.execute_query(
            """
            INSERT INTO recipe_ingredients (recipe_id, ingredient_id, unit_id, amount)
            VALUES (%(recipe_id)s, %(ingredient_id)s, %(unit_id)s, %(amount)s)
            """,
            {
                "recipe_id": recipe_id,
                "ingredient_id": ingredient_id,
                "unit_id": unit_id,
                "amount": amount,
            },
        )
    return recipe_id


def _volume_rows(db, recipe_id):
    return db.execute_query(
        """
        SELECT * FROM recipe_ingredient_volumes
        WHERE recipe_id = %(recipe_id)s ORDER BY recipe_ingredient_id
        """,
        {"recipe_id": recipe_id},
    )


def _single_volume_row(db, unit, conversion, amount):
    unit_id = None if unit is None else _unit(db, unit, conversion)
    recipe_id = _recipe(db, [(_ingredient(db, 40), unit_id, amount)])
    (row,) = _volume_rows(db, recipe_id)
    return row


@pytest.mark.parametrize(
    ("unit", "conversion", "amount", "rule", "reason", "volume"),
    [
        ("ml", 1, "NaN", "invalid", "non_finite_amount", None),
        ("ml", 1, "Infinity", "invalid", "non_finite_amount", None),
        ("ml", 1, "-Infinity", "invalid", "non_finite_amount", None),
        ("ml", 1, -1, "invalid", "negative_amount", None),
        ("each", None, -1, "invalid", "negative_amount", None),
        ("to top", None, "NaN", "invalid", "non_finite_amount", None),
        ("to top", None, 0, "zero", None, Decimal("0")),
        ("each", None, 0, "zero", None, Decimal("0")),
        ("ml", None, 0, "zero", None, Decimal("0")),
        ("each", None, None, "counted", None, None),
        ("each", None, 2, "counted", None, None),
        ("to top", None, None, "top", None, Decimal("88.7205")),
        ("to top", None, 99, "top", None, Decimal("88.7205")),
        ("to rinse", None, None, "rinse", None, Decimal("1")),
        ("to rinse", None, 99, "rinse", None, Decimal("1")),
        (None, None, 10, "invalid", "missing_unit", None),
        ("   ", 1, 10, "invalid", "missing_unit", None),
        ("ml", 1, None, "invalid", "missing_amount", None),
        ("pinch", None, 10, "invalid", "invalid_conversion", None),
        ("ml", 0, 10, "invalid", "invalid_conversion", None),
        ("ml", -1, 10, "invalid", "invalid_conversion", None),
        ("ml", "NaN", 10, "invalid", "invalid_conversion", None),
        ("ml", "Infinity", 10, "invalid", "invalid_conversion", None),
        ("oz", 29.5735, 0.75, "measured", None, Decimal("22.180125")),
        ("ml", 1, 60, "measured", None, Decimal("60")),
    ],
)
def test_volume_rules_classify_each_row(
    db_instance, unit, conversion, amount, rule, reason, volume
):
    row = _single_volume_row(db_instance, unit, conversion, amount)
    assert row["volume_rule"] == rule
    assert row["invalid_reason"] == reason
    assert row["volume_ml"] == volume


@pytest.mark.parametrize(
    ("unit", "rule"),
    [(" TO TOP ", "top"), ("\tEach\n", "counted"), (" tO rInSe ", "rinse")],
)
def test_unit_names_are_trimmed_and_case_folded(db_instance, unit, rule):
    row = _single_volume_row(db_instance, unit, None, 1)
    assert row["volume_rule"] == rule
    assert row["unit_name"] == unit


@pytest.mark.parametrize(("unit", "text"), [("to top", "88.7205"), ("to rinse", "1")])
def test_special_volume_literals_keep_scale(db_instance, unit, text):
    row = _single_volume_row(db_instance, unit, None, None)
    assert str(row["volume_ml"]) == text


@pytest.mark.parametrize(
    ("unit", "conversion", "amount", "estimated"),
    [
        ("each", None, 1, True),
        ("to top", None, None, True),
        ("to rinse", None, None, True),
        ("to top", None, 0, False),
        ("ml", 1, 10, False),
        ("ml", 1, -1, False),
    ],
)
def test_is_estimated_only_for_counted_top_rinse(
    db_instance, unit, conversion, amount, estimated
):
    row = _single_volume_row(db_instance, unit, conversion, amount)
    assert row["is_estimated"] is estimated


def test_sort_volume_matches_ingredient_query_ordering_expression(db_instance):
    db = db_instance
    oz = _unit(db, "oz", 29.5735)
    top = _unit(db, "to top", None)
    recipe_id = _recipe(
        db, [(_ingredient(db, 40), oz, 2), (_ingredient(db, 0), top, None)]
    )
    rows = _volume_rows(db, recipe_id)
    assert rows[0]["sort_volume"] == pytest.approx(59.147)
    assert rows[1]["sort_volume"] == 0


@pytest.mark.parametrize(
    ("ingredient_id", "expected"),
    [
        (1001, (35, 50, 3, 1001, "family")),
        (1002, (40, 50, 2, 1002, "family")),
        (1003, (40, 40, 1, 1003, "recorded")),
        (1005, (40, 50, 2, 1002, "family")),
        (1006, (35, 35, 1, 1006, "recorded")),
        (1007, (0, 100, 0, None, "unknown")),
        (1008, (30, 30, 1, 1008, "family")),
        (1009, (30, 30, 1, 1009, "recorded")),
    ],
)
def test_resolution_view_covers_every_ingredient(db_instance, ingredient_id, expected):
    db = db_instance
    db.execute_query(
        """
        INSERT INTO ingredients (id, name, parent_id, percent_abv) VALUES
        (1001, 'Spirits', NULL, NULL), (1002, 'Gin', 1001, NULL),
        (1003, 'Gin A', 1002, 40), (1004, 'Gin B', 1002, 50),
        (1005, 'Unknown gin', 1002, NULL), (1006, 'Vodka', 1001, 35),
        (1007, 'Lonely', NULL, NULL), (1008, 'Category', NULL, 20),
        (1009, 'Category child', 1008, 30)
        """
    )
    (row,) = db.execute_query(
        "SELECT * FROM ingredient_abv_resolution WHERE ingredient_id = %(id)s",
        {"id": ingredient_id},
    )
    assert (
        row["min_percent_abv"],
        row["max_percent_abv"],
        row["observation_count"],
        row["family_id"],
        row["source"],
    ) == expected
    assert row["has_observations"] is (expected[2] > 0)


def test_resolver_reads_the_view(db_instance):
    db = db_instance
    db.execute_query("INSERT INTO ingredients (id, name) VALUES (1, 'Lonely')")
    (row,) = db.execute_query(RESOLVE_INGREDIENT_ABV_SQL, {"ingredient_ids": [1, 1]})
    assert (row["min_percent_abv"], row["max_percent_abv"], row["source"]) == (
        0,
        100,
        "unknown",
    )
    assert "ingredient_abv_resolution" in RESOLVE_INGREDIENT_ABV_SQL


def test_schema_and_migration_define_identical_views():
    root = Path(__file__).resolve().parent.parent
    migration = (root / "migrations/19_migration_add_recipe_abv_views.sql").read_text()
    schema = (root / "infrastructure/postgres/schema.sql").read_text()
    body = migration.split("BEGIN;\n", 1)[1].rsplit("COMMIT;", 1)[0].strip()
    assert body in schema
