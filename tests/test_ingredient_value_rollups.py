import queue
import threading
from pathlib import Path

import psycopg2
from psycopg2 import sql


def test_ingredient_values_roll_up_recursively(db_instance):
    db_instance.execute_query(
        """
        INSERT INTO ingredients
            (id, name, parent_id, path, percent_abv, sugar_g_per_l,
             titratable_acidity_g_per_l)
        VALUES
            (1, 'Spirits', NULL, '/1/', 99, 99, 99),
            (2, 'Gin', 1, '/1/2/', 99, 99, 99),
            (3, 'Dry Gin', 2, '/1/2/3/', 40, NULL, 2),
            (4, 'Old Tom Gin', 2, '/1/2/4/', 50, 100, NULL),
            (5, 'Vodka', 1, '/1/5/', 35, 20, 4),
            (6, 'Mixers', NULL, '/6/', 99, 99, 99),
            (7, 'Soda', 6, '/6/7/', NULL, NULL, NULL)
        """
    )

    ingredients = {
        row["name"]: row
        for row in db_instance.execute_query(
            """
            SELECT name::text, percent_abv, sugar_g_per_l,
                   titratable_acidity_g_per_l
            FROM ingredients
            """
        )
    }

    assert ingredients["Gin"]["percent_abv"] == 45
    assert ingredients["Gin"]["sugar_g_per_l"] == 100
    assert ingredients["Gin"]["titratable_acidity_g_per_l"] == 2
    assert ingredients["Spirits"]["percent_abv"] == 40
    assert ingredients["Spirits"]["sugar_g_per_l"] == 60
    assert ingredients["Spirits"]["titratable_acidity_g_per_l"] == 3
    assert ingredients["Mixers"]["percent_abv"] is None
    assert ingredients["Mixers"]["sugar_g_per_l"] is None
    assert ingredients["Mixers"]["titratable_acidity_g_per_l"] is None


def test_ingredient_rollups_follow_add_edit_and_reparent(db_instance):
    db_instance.execute_query(
        """
        INSERT INTO ingredients (id, name, parent_id, path, percent_abv) VALUES
            (1, 'Brown Spirits', NULL, '/1/', NULL),
            (2, 'Clear Spirits', NULL, '/2/', NULL),
            (3, 'Bourbon', 1, '/1/3/', 40)
        """
    )

    db_instance.execute_query("UPDATE ingredients SET percent_abv = 50 WHERE id = 3")
    assert db_instance.get_ingredient(1)["percent_abv"] == 50

    db_instance.execute_query(
        """
        INSERT INTO ingredients (id, name, parent_id, path, percent_abv)
        VALUES (4, 'Rye', 1, '/1/4/', 40)
        """
    )
    assert db_instance.get_ingredient(1)["percent_abv"] == 45

    db_instance.execute_query(
        "UPDATE ingredients SET parent_id = 2, path = '/2/4/' WHERE id = 4"
    )
    assert db_instance.get_ingredient(1)["percent_abv"] == 50
    assert db_instance.get_ingredient(2)["percent_abv"] == 40


def test_rollup_lock_precedes_ingredient_row_locks(pg_db_with_schema):
    setup = psycopg2.connect(**pg_db_with_schema)
    setup.autocommit = True
    with setup.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO ingredients (id, name, parent_id, path, percent_abv) VALUES
                (1, 'Whiskey', NULL, '/1/', NULL),
                (2, 'Bourbon', 1, '/1/2/', 40)
            """
        )
    setup.close()

    lock_owner = psycopg2.connect(**pg_db_with_schema)
    editor = psycopg2.connect(**pg_db_with_schema)
    errors = queue.SimpleQueue()
    editor_pid = editor.get_backend_pid()

    with lock_owner.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtext('roll_up_ingredient_values'))"
        )

    def edit_parent():
        try:
            with editor.cursor() as cursor:
                cursor.execute("SET deadlock_timeout = '100ms'")
                cursor.execute("UPDATE ingredients SET percent_abv = 60 WHERE id = 1")
            editor.commit()
        except psycopg2.Error as error:
            errors.put(error)
            editor.rollback()

    thread = threading.Thread(target=edit_parent)
    thread.start()

    waiting = False
    with lock_owner.cursor() as cursor:
        for _ in range(100):
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM pg_locks
                    WHERE pid = %s AND locktype = 'advisory' AND NOT granted
                )
                """,
                (editor_pid,),
            )
            if cursor.fetchone()[0]:
                waiting = True
                break
            threading.Event().wait(0.01)

        assert waiting, "concurrent edit never waited for the rollup lock"
        try:
            cursor.execute("UPDATE ingredients SET percent_abv = 50 WHERE id = 2")
        except psycopg2.Error as error:
            errors.put(error)

    lock_owner.commit()
    thread.join(timeout=2)
    lock_owner.close()
    editor.close()

    assert not thread.is_alive()
    assert errors.empty()

    check = psycopg2.connect(**pg_db_with_schema)
    with check.cursor() as cursor:
        cursor.execute("SELECT percent_abv FROM ingredients WHERE id = 1")
        assert cursor.fetchone()[0] == 50
    check.close()


def test_rollup_migration_backfills_and_can_be_retried(pg_db_with_schema):
    connection = psycopg2.connect(**pg_db_with_schema)
    connection.autocommit = True
    migration = (
        Path(__file__).parents[1]
        / "migrations"
        / "14_migration_roll_up_ingredient_values.sql"
    ).read_text()

    with connection.cursor() as cursor:
        cursor.execute(
            """
            DROP TRIGGER lock_ingredient_value_rollup_before_change ON ingredients;
            DROP TRIGGER roll_up_ingredient_values_after_change ON ingredients;
            DROP FUNCTION roll_up_ingredient_values();
            INSERT INTO ingredients
                (id, name, parent_id, path, percent_abv, sugar_g_per_l)
            VALUES
                (1, 'Rum', NULL, '/1/', 99, 99),
                (2, 'White Rum', 1, '/1/2/', 40, NULL),
                (3, 'Dark Rum', 1, '/1/3/', 50, 100);
            """
        )
        cursor.execute(sql.SQL(migration))
        cursor.execute(sql.SQL(migration))
        cursor.execute(
            "SELECT percent_abv, sugar_g_per_l FROM ingredients WHERE id = 1"
        )
        assert cursor.fetchone() == (45, 100)

    connection.close()
