# ruff: noqa: FURB157

from decimal import Decimal
from pathlib import Path

import psycopg2
from psycopg2 import sql

from api.db.sql_queries import RESOLVE_INGREDIENT_ABV_SQL


def _ranges(db_instance):
    return {
        row["ingredient_id"]: row
        for row in db_instance.execute_query(
            "SELECT * FROM ingredient_abv_ranges ORDER BY ingredient_id"
        )
    }


def test_unknown_gin_uses_nearest_observed_leaf_range(db_instance):
    db_instance.execute_query(
        """
        INSERT INTO ingredients (id, name, parent_id, percent_abv) VALUES
        (1, 'Spirits', NULL, NULL), (2, 'Gin', 1, NULL),
        (3, 'Gin A', 2, 40), (4, 'Gin B', 2, 50),
        (5, 'Unknown gin', 2, NULL), (6, 'Vodka', 1, 35)
        """
    )
    rows = db_instance.execute_query(
        RESOLVE_INGREDIENT_ABV_SQL, {"ingredient_ids": [5]}
    )
    assert rows[0]["min_percent_abv"] == Decimal("40")
    assert rows[0]["max_percent_abv"] == Decimal("50")
    assert rows[0]["family_id"] == 2
    assert rows[0]["observation_count"] == 2
    assert rows[0]["source"] == "family"


def test_ranges_include_recorded_zero_and_ignore_rollup_values(db_instance):
    db_instance.execute_query(
        """
        INSERT INTO ingredients (id, name, parent_id, percent_abv) VALUES
        (1, 'Root', NULL, NULL),
        (2, 'Category', 1, NULL),
        (3, 'Zero', 2, 0),
        (4, 'Spirit', 2, 40)
        """
    )

    rows = _ranges(db_instance)
    assert rows[1]["min_percent_abv"] == Decimal("0")
    assert rows[1]["max_percent_abv"] == Decimal("40")
    assert rows[1]["observation_count"] == 2
    assert rows[2]["min_percent_abv"] == Decimal("0")
    assert rows[2]["max_percent_abv"] == Decimal("40")
    assert rows[2]["observation_count"] == 2
    assert rows[3]["min_percent_abv"] == Decimal("0")
    assert rows[3]["max_percent_abv"] == Decimal("0")
    assert rows[3]["observation_count"] == 1


def test_ranges_follow_deep_uneven_branches_and_count_each_leaf_once(db_instance):
    db_instance.execute_query(
        """
        INSERT INTO ingredients (id, name, parent_id, percent_abv) VALUES
        (1, 'Root', NULL, NULL),
        (2, 'Left', 1, NULL),
        (3, 'Left branch', 2, NULL),
        (4, 'Left low', 3, 10),
        (5, 'Left high', 3, 30),
        (6, 'Right', 1, NULL),
        (7, 'Right leaf', 6, 70),
        (8, 'Root leaf', 1, 90)
        """
    )

    rows = _ranges(db_instance)
    assert (rows[1]["min_percent_abv"], rows[1]["max_percent_abv"]) == (
        Decimal("10"),
        Decimal("90"),
    )
    assert rows[1]["observation_count"] == 4
    assert rows[2]["observation_count"] == 2
    assert rows[3]["observation_count"] == 2
    assert rows[6]["observation_count"] == 1


def test_empty_root_resolves_to_explicit_unknown_and_single_leaf_is_recorded(
    db_instance,
):
    db_instance.execute_query(
        """
        INSERT INTO ingredients (id, name, parent_id, percent_abv) VALUES
        (1, 'Empty root', NULL, NULL),
        (2, 'Measured root', NULL, 35)
        """
    )

    rows = {
        row["ingredient_id"]: row
        for row in db_instance.execute_query(
            RESOLVE_INGREDIENT_ABV_SQL, {"ingredient_ids": [1, 2]}
        )
    }
    assert rows[1]["min_percent_abv"] == Decimal("0")
    assert rows[1]["max_percent_abv"] == Decimal("100")
    assert rows[1]["family_id"] is None
    assert rows[1]["observation_count"] == 0
    assert rows[1]["source"] == "unknown"
    assert rows[2]["min_percent_abv"] == Decimal("35")
    assert rows[2]["max_percent_abv"] == Decimal("35")
    assert rows[2]["family_id"] == 2
    assert rows[2]["source"] == "recorded"


def test_resolver_prefers_category_subtree_over_higher_ancestor(db_instance):
    db_instance.execute_query(
        """
        INSERT INTO ingredients (id, name, parent_id, percent_abv) VALUES
        (1, 'Root', NULL, NULL),
        (2, 'Category', 1, NULL),
        (3, 'Known child', 2, 40),
        (4, 'Root sibling', 1, 80),
        (5, 'Unknown child', 2, NULL)
        """
    )

    rows = db_instance.execute_query(
        RESOLVE_INGREDIENT_ABV_SQL, {"ingredient_ids": [2, 5]}
    )
    by_id = {row["ingredient_id"]: row for row in rows}
    assert by_id[2]["family_id"] == 2
    assert by_id[2]["min_percent_abv"] == Decimal("40")
    assert by_id[2]["max_percent_abv"] == Decimal("40")
    assert by_id[5]["family_id"] == 2
    assert by_id[5]["min_percent_abv"] == Decimal("40")
    assert by_id[5]["max_percent_abv"] == Decimal("40")


def test_noop_parent_update_preserves_parent_abv(db_instance):
    db_instance.execute_query(
        """
        INSERT INTO ingredients (id, name, parent_id, percent_abv) VALUES
        (1, 'Root', NULL, NULL), (2, 'Category', 1, NULL),
        (3, 'Leaf', 2, 40)
        """
    )
    assert db_instance.get_ingredient(2)["percent_abv"] == 40

    db_instance.execute_query(
        "UPDATE ingredients SET parent_id = 2, path = '/1/2/3/' WHERE id = 3"
    )
    assert db_instance.get_ingredient(2)["percent_abv"] == 40


def test_last_child_delete_clears_parent_and_recomputes_higher_ancestor(
    db_instance,
):
    db_instance.execute_query(
        """
        INSERT INTO ingredients (id, name, parent_id, percent_abv) VALUES
        (1, 'Root', NULL, NULL),
        (2, 'Category', 1, NULL),
        (3, 'Category leaf', 2, 40),
        (4, 'Remaining root branch', 1, 60),
        (5, 'Other root', NULL, NULL),
        (6, 'Unrelated leaf', 5, 25)
        """
    )
    db_instance.execute_query("DELETE FROM ingredients WHERE id = 3")

    values = {
        row["id"]: row["percent_abv"]
        for row in db_instance.execute_query(
            "SELECT id, percent_abv FROM ingredients ORDER BY id"
        )
    }
    assert values[2] is None
    assert values[1] == 60
    assert values[4] == 60
    assert values[6] == 25
    rows = _ranges(db_instance)
    assert rows[2]["observation_count"] == 0
    assert rows[1]["min_percent_abv"] == Decimal("60")
    assert rows[1]["max_percent_abv"] == Decimal("60")
    assert rows[1]["observation_count"] == 1


def test_last_child_reparent_clears_old_family_and_updates_both_roots(db_instance):
    db_instance.execute_query(
        """
        INSERT INTO ingredients (id, name, parent_id, percent_abv) VALUES
        (1, 'Old root', NULL, NULL),
        (2, 'Old category', 1, NULL),
        (3, 'Moved leaf', 2, 40),
        (4, 'Old remaining leaf', 1, 60),
        (5, 'New root', NULL, NULL),
        (6, 'New remaining leaf', 5, 20)
        """
    )
    db_instance.execute_query(
        "UPDATE ingredients SET parent_id = 5, path = '/5/3/' WHERE id = 3"
    )

    values = {
        row["id"]: row["percent_abv"]
        for row in db_instance.execute_query(
            "SELECT id, percent_abv FROM ingredients ORDER BY id"
        )
    }
    assert values[2] is None
    assert values[1] == 60
    assert values[5] == 30
    assert values[6] == 20
    assert values[3] == 40


def test_multirow_last_child_deletion_keeps_unrelated_leaves(db_instance):
    db_instance.execute_query(
        """
        INSERT INTO ingredients (id, name, parent_id, percent_abv) VALUES
        (1, 'Root', NULL, NULL),
        (2, 'Category', 1, NULL),
        (3, 'First leaf', 2, 40),
        (4, 'Second leaf', 2, 50),
        (5, 'Remaining root leaf', 1, 70),
        (6, 'Other root', NULL, NULL),
        (7, 'Unrelated leaf', 6, 15)
        """
    )
    db_instance.execute_query("DELETE FROM ingredients WHERE id IN (3, 4)")

    values = {
        row["id"]: row["percent_abv"]
        for row in db_instance.execute_query(
            "SELECT id, percent_abv FROM ingredients ORDER BY id"
        )
    }
    assert values[2] is None
    assert values[1] == 70
    assert values[5] == 70
    assert values[7] == 15


def test_view_cycle_terminates_without_borrowing_another_root(db_instance):
    db_instance.execute_query(
        """
        INSERT INTO ingredients (id, name, parent_id, percent_abv) VALUES
        (1, 'Cycle one', NULL, NULL),
        (2, 'Cycle two', 1, NULL),
        (3, 'Cycle leaf', 2, 40),
        (4, 'Other root', NULL, NULL),
        (5, 'Other leaf', 4, 80)
        """
    )
    db_instance.execute_query("ALTER TABLE ingredients DISABLE TRIGGER USER")
    db_instance.execute_query("UPDATE ingredients SET parent_id = 2 WHERE id = 1")

    rows = _ranges(db_instance)
    assert rows[1]["min_percent_abv"] == Decimal("40")
    assert rows[1]["max_percent_abv"] == Decimal("40")
    assert rows[1]["observation_count"] == 1
    assert rows[2]["min_percent_abv"] == Decimal("40")
    assert rows[2]["max_percent_abv"] == Decimal("40")
    assert rows[2]["observation_count"] == 1
    assert rows[4]["min_percent_abv"] == Decimal("80")
    assert rows[4]["observation_count"] == 1


def test_resolver_cycle_terminates_with_cycle_family_only(db_instance):
    db_instance.execute_query(
        """
        INSERT INTO ingredients (id, name, parent_id, percent_abv) VALUES
        (1, 'Cycle one', NULL, NULL),
        (2, 'Cycle two', 1, NULL),
        (3, 'Cycle leaf', 2, 40),
        (4, 'Other root', NULL, NULL),
        (5, 'Other leaf', 4, 80)
        """
    )
    db_instance.execute_query("ALTER TABLE ingredients DISABLE TRIGGER USER")
    db_instance.execute_query("UPDATE ingredients SET parent_id = 2 WHERE id = 1")

    rows = db_instance.execute_query(
        RESOLVE_INGREDIENT_ABV_SQL, {"ingredient_ids": [1, 2]}
    )
    by_id = {row["ingredient_id"]: row for row in rows}
    assert by_id[1]["family_id"] == 1
    assert by_id[1]["min_percent_abv"] == Decimal("40")
    assert by_id[1]["max_percent_abv"] == Decimal("40")
    assert by_id[2]["family_id"] == 2
    assert by_id[2]["min_percent_abv"] == Decimal("40")
    assert by_id[2]["max_percent_abv"] == Decimal("40")


def test_recipe_abv_migration_is_idempotent_and_preserves_leaf_measurements(
    pg_db_with_schema,
):
    connection = psycopg2.connect(**pg_db_with_schema)
    connection.autocommit = True
    migration = (
        Path(__file__).parents[1]
        / "migrations"
        / "16_migration_add_recipe_abv_ranges.sql"
    ).read_text()

    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO ingredients (id, name, parent_id, percent_abv) VALUES
            (1, 'Rum', NULL, NULL),
            (2, 'White Rum', 1, 40),
            (3, 'Dark Rum', 1, 50)
            """
        )
        cursor.execute("SELECT id, percent_abv FROM ingredients WHERE id IN (2, 3)")
        before = cursor.fetchall()
        cursor.execute(sql.SQL(migration))
        cursor.execute(sql.SQL(migration))
        cursor.execute("SELECT id, percent_abv FROM ingredients WHERE id IN (2, 3)")
        assert cursor.fetchall() == before
        cursor.execute(
            """
            SELECT min_percent_abv, max_percent_abv, observation_count
            FROM ingredient_abv_ranges
            WHERE ingredient_id = 1
            """
        )
        assert cursor.fetchone() == (40, 50, 2)

    connection.close()


def test_bulk_resolver_explain_on_representative_fixture(pg_db_with_schema):
    connection = psycopg2.connect(**pg_db_with_schema)
    connection.autocommit = True
    requested_ids = list(range(1, 101))
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO ingredients (id, name, parent_id, percent_abv)
            SELECT id, 'Ingredient ' || id, NULL, CASE WHEN id % 2 = 0 THEN 40 ELSE NULL END
            FROM generate_series(1, 100) AS ids(id)
            """
        )
        cursor.execute(
            "EXPLAIN (ANALYZE, BUFFERS) " + RESOLVE_INGREDIENT_ABV_SQL,
            {"ingredient_ids": requested_ids},
        )
        plan = "\n".join(row[0] for row in cursor.fetchall())

    connection.close()
    print(f"EXPLAIN_DATASET_SIZE={len(requested_ids)}")
    print(plan)
    assert "Execution Time" in plan
    assert "Buffers" in plan
