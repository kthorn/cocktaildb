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


# --- Layers 2b and 3: contribution rows and recipe ABV -----------------------


def _ml(db):
    return _unit(db, "milliliter", 1)


def _unknown(db):
    return _ingredient(db)


def _family_member(db, lo, hi):
    """An unrecorded ingredient whose family interval is lo-hi."""
    parent = _ingredient(db)
    _ingredient(db, lo, parent_id=parent)
    if hi != lo:
        _ingredient(db, hi, parent_id=parent)
    return _ingredient(db, parent_id=parent)


def _abv(db, recipe_id):
    (row,) = db.execute_query(
        "SELECT * FROM recipe_abv WHERE recipe_id = %(recipe_id)s",
        {"recipe_id": recipe_id},
    )
    return row


def _contribution_rows(db, recipe_id):
    return db.execute_query(
        """
        SELECT * FROM recipe_abv_ingredient_rows
        WHERE recipe_id = %(recipe_id)s ORDER BY recipe_ingredient_id
        """,
        {"recipe_id": recipe_id},
    )


def _display(row):
    return (row["display_low"], row["display_high"], row["display_below_one"])


def test_small_unknown_contribution_gives_useful_range(db_instance):
    db = db_instance
    ml = _ml(db)
    recipe = _recipe(db, [(_ingredient(db, 40), ml, 60), (_unknown(db), ml, 5)])
    row = _abv(db, recipe)
    assert row["status"] == "estimated"
    assert row["unknown_reason"] is None
    assert float(row["min_percent"]) == pytest.approx(36.9230769231)
    assert float(row["max_percent"]) == pytest.approx(44.6153846154)
    assert row["narrow"] is False
    assert _display(row) == (36, 45, False)


def test_exactly_twenty_points_is_displayable(db_instance):
    db = db_instance
    ml = _ml(db)
    recipe = _recipe(db, [(_ingredient(db, 0), ml, 80), (_unknown(db), ml, 20)])
    row = _abv(db, recipe)
    assert row["status"] == "estimated"
    assert _display(row) == (0, 20, False)


@pytest.mark.parametrize(
    ("width", "status", "reason"),
    [("19.9999", "estimated", None), ("20.0001", "unknown", "too_wide")],
)
def test_width_cutoff_is_division_free(db_instance, width, status, reason):
    db = db_instance
    member = _family_member(db, 0, Decimal(width))
    row = _abv(db, _recipe(db, [(member, _ml(db), 100)]))
    assert row["status"] == status
    assert row["unknown_reason"] == reason
    assert row["max_percent"] == Decimal(width)


def test_to_top_uses_the_approved_per_row_volume(db_instance):
    db = db_instance
    top = _unit(db, "to top", None)
    recipe = _recipe(
        db, [(_ingredient(db, 40), top, 99), (_ingredient(db, 0), _ml(db), 10)]
    )
    row = _abv(db, recipe)
    expected = Decimal("88.7205") * 40 / (Decimal("88.7205") + 10)
    assert float(row["min_percent"]) == pytest.approx(float(expected))
    assert float(row["max_percent"]) == pytest.approx(float(expected))
    assert row["status"] == "estimated"


def test_rinse_uses_one_ml_without_multiplying_amount(db_instance):
    db = db_instance
    rinse = _unit(db, "to rinse", None)
    recipe = _recipe(
        db, [(_ingredient(db, 40), rinse, 99), (_ingredient(db, 0), _ml(db), 10)]
    )
    row = _abv(db, recipe)
    assert float(row["min_percent"]) == pytest.approx(40 / 11)


def test_too_wide_keeps_raw_bounds_without_display(db_instance):
    db = db_instance
    ml = _ml(db)
    recipe = _recipe(db, [(_unknown(db), ml, 30), (_ingredient(db, 0), ml, 30)])
    row = _abv(db, recipe)
    assert row["status"] == "unknown"
    assert row["unknown_reason"] == "too_wide"
    assert row["min_percent"] == 0
    assert float(row["max_percent"]) == pytest.approx(50)
    assert row["narrow"] is None
    assert _display(row) == (None, None, None)


def test_each_garnish_makes_recorded_recipe_estimated(db_instance):
    db = db_instance
    each = _unit(db, "each", None)
    recipe = _recipe(db, [(_ingredient(db, 40), _ml(db), 10), (_unknown(db), each, 1)])
    row = _abv(db, recipe)
    assert row["status"] == "estimated"
    assert _display(row) == (40, 40, False)


def test_zero_amount_unknown_row_does_not_make_recipe_estimated(db_instance):
    db = db_instance
    ml = _ml(db)
    recipe = _recipe(db, [(_ingredient(db, 40), ml, 10), (_unknown(db), ml, 0)])
    assert _abv(db, recipe)["status"] == "calculated"


@pytest.mark.parametrize("kind", ["no rows", "zero rows", "each rows"])
def test_all_excluded_recipe_is_no_volume(db_instance, kind):
    db = db_instance
    rows = {
        "no rows": [],
        "zero rows": [(_ingredient(db, 40), _ml(db), 0)],
        "each rows": [(_ingredient(db, 40), _unit(db, "each", None), 1)],
    }[kind]
    row = _abv(db, _recipe(db, rows))
    assert row["status"] == "unknown"
    assert row["unknown_reason"] == "no_volume"
    assert (row["min_percent"], row["max_percent"], row["narrow"]) == (None,) * 3
    assert _display(row) == (None, None, None)


def test_invalid_row_nulls_bounds(db_instance):
    db = db_instance
    ml = _ml(db)
    recipe = _recipe(
        db, [(_ingredient(db, 40), ml, 10), (_ingredient(db, 0), ml, "NaN")]
    )
    row = _abv(db, recipe)
    assert row["status"] == "unknown"
    assert row["unknown_reason"] == "invalid_row"
    assert (row["min_percent"], row["max_percent"]) == (None, None)


@pytest.mark.parametrize(
    ("percent", "display", "status"),
    [
        ("26.5", (27, 27, False), "calculated"),
        ("0", (0, 0, False), "calculated"),
        ("0.4", (0, 0, True), "calculated"),
        ("0.6", (0, 0, True), "calculated"),
        ("14.4999999999999999999999999999", (14, 14, False), "calculated"),
    ],
)
def test_point_display_rounds_half_up(db_instance, percent, display, status):
    db = db_instance
    recipe = _recipe(db, [(_ingredient(db, Decimal(percent)), _ml(db), 10)])
    row = _abv(db, recipe)
    assert row["narrow"] is True
    assert row["status"] == status
    assert _display(row) == display


@pytest.mark.parametrize(
    ("lo", "hi", "display", "narrow"),
    [
        ("10.1", "20.1", (10, 21, False), False),
        ("30", "30.9999", (30, 30, False), True),
        ("30", "31", (31, 31, False), True),
        ("30", "31.0001", (30, 32, False), False),
        ("15", "17", (15, 17, False), False),
    ],
)
def test_family_interval_display(db_instance, lo, hi, display, narrow):
    db = db_instance
    member = _family_member(db, Decimal(lo), Decimal(hi))
    row = _abv(db, _recipe(db, [(member, _ml(db), 10)]))
    assert row["status"] == "estimated"
    assert row["narrow"] is narrow
    assert _display(row) == display
    assert row["min_percent"] == Decimal(lo)
    assert row["max_percent"] == Decimal(hi)


def test_narrow_uses_volume_weighted_width(db_instance):
    db = db_instance
    ml = _ml(db)
    recipe = _recipe(db, [(_ingredient(db, 30), ml, 99), (_unknown(db), ml, 1)])
    row = _abv(db, recipe)
    assert row["narrow"] is True
    assert float(row["min_percent"]) == pytest.approx(29.7)
    assert float(row["max_percent"]) == pytest.approx(30.7)
    assert _display(row) == (30, 30, False)


def test_contribution_rows_carry_strength_and_display(db_instance):
    db = db_instance
    ml = _ml(db)
    point = _family_member(db, 40, 40)
    interval = _family_member(db, 15, 16)
    tiny = _ingredient(db, Decimal("0.4"), name="Tiny")
    unknown = _unknown(db)
    recipe = _recipe(
        db,
        [
            (point, ml, 10),
            (interval, ml, 10),
            (tiny, ml, 10),
            (unknown, ml, 0),
            (unknown, _unit(db, "each", None), 1),
        ],
    )
    rows = _contribution_rows(db, recipe)
    summary = [
        (
            r["strength_source"],
            r["contributes"],
            r["strength_display_low"],
            r["strength_display_high"],
            r["strength_display_below_one"],
        )
        for r in rows
    ]
    assert summary == [
        ("family", True, 40, 40, False),
        ("family", True, 15, 16, False),
        ("recorded", True, 0, 0, True),
        ("unknown", False, 0, 100, False),
        ("unknown", False, 0, 100, False),
    ]
    assert rows[2]["ingredient_name"] == "Tiny"
    assert (rows[3]["min_percent_abv"], rows[3]["max_percent_abv"]) == (0, 100)


def test_category_resolving_to_its_own_subtree_is_family(db_instance):
    db = db_instance
    category = _ingredient(db, 20)
    _ingredient(db, 30, parent_id=category)
    recipe = _recipe(db, [(category, _ml(db), 10)])
    (row,) = _contribution_rows(db, recipe)
    assert row["strength_source"] == "family"
    assert _abv(db, recipe)["status"] == "estimated"


def test_rollback_then_migration_round_trips(db_instance):
    db = db_instance
    root = Path(__file__).resolve().parent.parent
    views = (
        "SELECT count(*) AS n FROM pg_views WHERE viewname IN "
        "('ingredient_abv_resolution', 'recipe_ingredient_volumes', "
        "'recipe_abv_ingredient_rows', 'recipe_abv')"
    )
    db.execute_query(
        (root / "migrations/rollbacks/19_rollback_recipe_abv_views.sql").read_text()
    )
    assert db.execute_query(views)[0]["n"] == 0
    assert db.execute_query("SELECT count(*) AS n FROM ingredient_abv_ranges")
    db.execute_query(
        (root / "migrations/19_migration_add_recipe_abv_views.sql").read_text()
    )
    assert db.execute_query(views)[0]["n"] == 4
