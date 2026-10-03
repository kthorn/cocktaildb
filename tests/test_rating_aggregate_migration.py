"""Migration 18: repair recipe rating aggregates left short by the concurrency race.

See issue #86. The trigger recompute is serialized by the CREATE OR REPLACE in
this migration; the UPDATE repairs the rows the race already corrupted, because
they never self-heal until the next rating arrives on the affected recipe.
"""

from pathlib import Path

MIGRATION = Path("migrations/18_migration_fix_recipe_rating_aggregate_race.sql")
SCHEMA = Path("infrastructure/postgres/schema.sql")
FUNCTION_HEADER = "CREATE OR REPLACE FUNCTION update_recipe_avg_rating()"


def _function_definition(path):
    text = path.read_text()
    start = text.index(FUNCTION_HEADER)
    return text[start : text.index("$$ LANGUAGE plpgsql;", start)]


def _create_recipe(db, name):
    db.execute_query("INSERT INTO recipes (name) VALUES (%s)", (name,))
    return db.execute_query("SELECT id FROM recipes WHERE name = %s", (name,))[0]["id"]


def _add_ratings(db, recipe_id, ratings):
    for index, rating in enumerate(ratings):
        db.execute_query(
            "INSERT INTO ratings (cognito_user_id, recipe_id, rating) VALUES (%s, %s, %s)",
            (f"user{index}", recipe_id, rating),
        )


def _aggregates(db, recipe_id):
    return db.execute_query(
        "SELECT rating_count, avg_rating FROM recipes WHERE id = %s", (recipe_id,)
    )[0]


def test_migration_repairs_aggregates_left_short_by_the_race(db_instance):
    db = db_instance
    recipe_id = _create_recipe(db, "Race Victim")
    _add_ratings(db, recipe_id, (5, 4, 3, 2, 1))
    # Simulate the aftermath: the last writer recomputed from a partial snapshot.
    db.execute_query(
        "UPDATE recipes SET avg_rating = 5.0, rating_count = 1 WHERE id = %s",
        (recipe_id,),
    )

    db.execute_query(MIGRATION.read_text())

    row = _aggregates(db, recipe_id)
    assert row["rating_count"] == 5
    assert row["avg_rating"] == 3.0


def test_migration_zeroes_aggregates_for_recipes_with_no_ratings(db_instance):
    db = db_instance
    recipe_id = _create_recipe(db, "Never Rated")
    db.execute_query(
        "UPDATE recipes SET avg_rating = NULL, rating_count = NULL WHERE id = %s",
        (recipe_id,),
    )

    db.execute_query(MIGRATION.read_text())

    row = _aggregates(db, recipe_id)
    assert row["rating_count"] == 0
    assert row["avg_rating"] == 0


def test_migration_serializes_the_trigger_recompute(db_instance):
    """FOR NO KEY UPDATE, never FOR UPDATE: see the deadlock note in the migration."""
    db = db_instance

    db.execute_query(MIGRATION.read_text())

    definition = db.execute_query(
        "SELECT pg_get_functiondef('update_recipe_avg_rating()'::regprocedure) AS definition"
    )[0]["definition"]
    assert "FOR NO KEY UPDATE" in definition
    assert "FOR UPDATE;" not in definition


def test_migration_matches_the_fresh_install_schema():
    """Upgraded databases and fresh installs must get the same trigger function."""
    assert _function_definition(MIGRATION) == _function_definition(SCHEMA)
