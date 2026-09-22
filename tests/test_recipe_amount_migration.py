from pathlib import Path

import psycopg2
import pytest

MIGRATION = Path("migrations/17_migration_require_convertible_recipe_amounts.sql")


def apply_migration(db):
    db.execute_query(MIGRATION.read_text())


def test_recipe_905_gets_amount_for_barspoon(db_instance):
    db = db_instance
    db.execute_query(
        "INSERT INTO recipes (id, name) VALUES (905, %s)", ("The Perfect BQE",)
    )
    db.execute_query(
        "INSERT INTO ingredients (name) VALUES (%s)", ("Maraschino Liqueur",)
    )
    ingredient_id = db.execute_query(
        "SELECT id FROM ingredients WHERE name = %s", ("Maraschino Liqueur",)
    )[0]["id"]
    db.execute_query(
        "INSERT INTO units (name, abbreviation, conversion_to_ml) VALUES (%s, %s, %s)",
        ("Barspoon", "bsp", 2.46446),
    )
    unit_id = db.execute_query("SELECT id FROM units WHERE name = %s", ("Barspoon",))[
        0
    ]["id"]
    # Simulate the legacy row before the new schema trigger existed.
    db.execute_query(
        "DROP TRIGGER require_convertible_recipe_ingredient_amount ON recipe_ingredients"
    )
    db.execute_query(
        "INSERT INTO recipe_ingredients (recipe_id, ingredient_id, unit_id, amount) VALUES (%s, %s, %s, NULL)",
        (905, ingredient_id, unit_id),
    )

    apply_migration(db)

    row = db.execute_query(
        "SELECT amount FROM recipe_ingredients WHERE recipe_id = 905"
    )[0]
    assert row["amount"] == 1


def test_schema_rejects_new_null_amount_for_convertible_unit(db_instance):
    db = db_instance
    db.execute_query("INSERT INTO recipes (name) VALUES (%s)", ("Schema Recipe",))
    recipe_id = db.execute_query(
        "SELECT id FROM recipes WHERE name = %s", ("Schema Recipe",)
    )[0]["id"]
    db.execute_query("INSERT INTO ingredients (name) VALUES (%s)", ("Schema Gin",))
    ingredient_id = db.execute_query(
        "SELECT id FROM ingredients WHERE name = %s", ("Schema Gin",)
    )[0]["id"]
    db.execute_query(
        "INSERT INTO units (name, abbreviation, conversion_to_ml) VALUES (%s, %s, %s)",
        ("Schema Barspoon", "sbsp", 2.46446),
    )
    unit_id = db.execute_query(
        "SELECT id FROM units WHERE name = %s", ("Schema Barspoon",)
    )[0]["id"]

    with pytest.raises(psycopg2.Error, match="requires an amount"):
        db.execute_query(
            "INSERT INTO recipe_ingredients (recipe_id, ingredient_id, unit_id, amount) VALUES (%s, %s, %s, NULL)",
            (recipe_id, ingredient_id, unit_id),
        )


def test_migration_rejects_new_null_amount_for_convertible_unit(db_instance):
    db = db_instance
    db.execute_query("INSERT INTO recipes (name) VALUES (%s)", ("Trigger Recipe",))
    recipe_id = db.execute_query(
        "SELECT id FROM recipes WHERE name = %s", ("Trigger Recipe",)
    )[0]["id"]
    db.execute_query("INSERT INTO ingredients (name) VALUES (%s)", ("Trigger Gin",))
    ingredient_id = db.execute_query(
        "SELECT id FROM ingredients WHERE name = %s", ("Trigger Gin",)
    )[0]["id"]
    db.execute_query(
        "INSERT INTO units (name, abbreviation, conversion_to_ml) VALUES (%s, %s, %s)",
        ("Trigger Barspoon", "tbspn", 2.46446),
    )
    unit_id = db.execute_query(
        "SELECT id FROM units WHERE name = %s", ("Trigger Barspoon",)
    )[0]["id"]
    apply_migration(db)

    with pytest.raises(psycopg2.Error, match="requires an amount"):
        db.execute_query(
            "INSERT INTO recipe_ingredients (recipe_id, ingredient_id, unit_id, amount) VALUES (%s, %s, %s, NULL)",
            (recipe_id, ingredient_id, unit_id),
        )
