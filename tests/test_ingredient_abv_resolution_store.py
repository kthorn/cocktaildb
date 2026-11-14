"""The stored ingredient ABV resolution stays identical to its defining view."""

import threading
from pathlib import Path

import psycopg2
import pytest

ROOT = Path(__file__).resolve().parent.parent
MIGRATION = ROOT / "migrations/20_migration_store_ingredient_abv_resolution.sql"
ROLLBACK = ROOT / "migrations/rollbacks/20_rollback_store_ingredient_abv_resolution.sql"

STORED = "SELECT * FROM ingredient_abv_resolution_store ORDER BY ingredient_id"
COMPUTED = "SELECT * FROM ingredient_abv_resolution ORDER BY ingredient_id"


def _assert_in_sync(db):
    assert db.execute_query(STORED) == db.execute_query(COMPUTED)


def _seed(db):
    db.execute_query(
        """
        INSERT INTO ingredients (id, name, parent_id, percent_abv) VALUES
        (1001, 'Spirits', NULL, NULL), (1002, 'Gin', 1001, NULL),
        (1003, 'Gin A', 1002, 40), (1004, 'Gin B', 1002, 50),
        (1005, 'Unknown gin', 1002, NULL), (1006, 'Vodka', 1001, 35),
        (1007, 'Lonely', NULL, NULL)
        """
    )


@pytest.mark.parametrize(
    "change",
    [
        "UPDATE ingredients SET percent_abv = 47 WHERE id = 1003",
        "UPDATE ingredients SET parent_id = 1001 WHERE id = 1005",
        "UPDATE ingredients SET parent_id = NULL WHERE id = 1006",
        "UPDATE ingredients SET name = 'Genever' WHERE id = 1002",
        "DELETE FROM ingredients WHERE id = 1004",
        "INSERT INTO ingredients (id, name, parent_id, percent_abv) "
        "VALUES (1008, 'Gin C', 1002, 60)",
    ],
)
def test_store_follows_ingredient_changes(db_instance, change):
    db = db_instance
    _seed(db)
    _assert_in_sync(db)
    db.execute_query(change)
    _assert_in_sync(db)


def test_recipe_rows_read_the_store(db_instance):
    (row,) = db_instance.execute_query(
        "SELECT pg_get_viewdef('recipe_abv_ingredient_rows') AS sql"
    )
    assert "ingredient_abv_resolution_store" in row["sql"]


def test_concurrent_ingredient_writers_keep_store_in_sync(
    db_instance, memory_db_with_schema
):
    db = db_instance
    _seed(db)
    first = psycopg2.connect(**memory_db_with_schema)
    second = psycopg2.connect(**memory_db_with_schema)
    errors = []
    try:
        with first.cursor() as cursor:
            cursor.execute("UPDATE ingredients SET percent_abv = 41 WHERE id = 1003")

        def write_second():
            try:
                with second.cursor() as cursor:
                    cursor.execute(
                        "UPDATE ingredients SET percent_abv = 51 WHERE id = 1004"
                    )
                second.commit()
            except Exception as error:  # noqa: BLE001 - reported below
                errors.append(error)

        writer = threading.Thread(target=write_second)
        writer.start()
        writer.join(0.3)  # the second writer waits on the first
        first.commit()
        writer.join(10)
        assert not writer.is_alive()
    finally:
        first.close()
        second.close()

    assert errors == []
    _assert_in_sync(db)


def test_schema_contains_the_migration():
    schema = (ROOT / "infrastructure/postgres/schema.sql").read_text()
    body = MIGRATION.read_text().split("BEGIN;\n", 1)[1].rsplit("COMMIT;", 1)[0]
    assert body.strip() in schema


def test_rollback_then_migration_round_trips(db_instance):
    db = db_instance
    _seed(db)
    store = "SELECT to_regclass('ingredient_abv_resolution_store') IS NOT NULL AS ok"

    db.execute_query(ROLLBACK.read_text())
    assert not db.execute_query(store)[0]["ok"]
    (row,) = db.execute_query(
        "SELECT pg_get_viewdef('recipe_abv_ingredient_rows') AS sql"
    )
    assert "ingredient_abv_resolution_store" not in row["sql"]

    db.execute_query(MIGRATION.read_text())
    assert db.execute_query(store)[0]["ok"]
    _assert_in_sync(db)


def test_mixed_ingredient_writers_do_not_deadlock(db_instance, memory_db_with_schema):
    """A roll-up-only write, then a store-only write, then a write needing both."""
    db = db_instance
    _seed(db)
    first = psycopg2.connect(**memory_db_with_schema)
    second = psycopg2.connect(**memory_db_with_schema)
    errors = []
    try:
        with first.cursor() as cursor:
            cursor.execute("SET deadlock_timeout = '100ms'")
            cursor.execute("UPDATE ingredients SET sugar_g_per_l = 5 WHERE id = 1003")

        def rename():
            try:
                with second.cursor() as cursor:
                    cursor.execute("SET deadlock_timeout = '100ms'")
                    cursor.execute(
                        "UPDATE ingredients SET name = 'Gin X' WHERE id = 1004"
                    )
                second.commit()
            except psycopg2.Error as error:
                errors.append(error)
                second.rollback()

        writer = threading.Thread(target=rename)
        writer.start()
        writer.join(0.3)
        try:
            with first.cursor() as cursor:
                cursor.execute(
                    "UPDATE ingredients SET percent_abv = 42 WHERE id = 1003"
                )
            first.commit()
        except psycopg2.Error as error:
            errors.append(error)
            first.rollback()
        writer.join(10)
        assert not writer.is_alive()
    finally:
        first.close()
        second.close()

    assert errors == []
    _assert_in_sync(db)
