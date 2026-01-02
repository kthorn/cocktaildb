import psycopg2


def _fetch_column_types(cursor, table_name):
    cursor.execute(
        """
        SELECT column_name, data_type, udt_name
        FROM information_schema.columns
        WHERE table_name = %s
        """,
        (table_name,),
    )
    return {row[0]: (row[1], row[2]) for row in cursor.fetchall()}


def _fetch_indexes(cursor, table_name):
    cursor.execute(
        """
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename = %s
        """,
        (table_name,),
    )
    return {row[0]: row[1] for row in cursor.fetchall()}


def test_schema_adds_citext_and_ingredient_metadata(pg_db_with_schema):
    conn = psycopg2.connect(**pg_db_with_schema)
    conn.autocommit = True
    cursor = conn.cursor()

    columns = _fetch_column_types(cursor, "ingredients")
    assert "percent_abv" in columns
    assert "sugar_g_per_l" in columns
    assert "titratable_acidity_g_per_l" in columns
    assert "url" in columns

    recipe_cols = _fetch_column_types(cursor, "recipes")
    ingredient_cols = _fetch_column_types(cursor, "ingredients")
    assert recipe_cols["name"][1] == "citext"
    assert ingredient_cols["name"][1] == "citext"

    cursor.close()
    conn.close()


def test_schema_adds_ordering_indexes(pg_db_with_schema):
    conn = psycopg2.connect(**pg_db_with_schema)
    conn.autocommit = True
    cursor = conn.cursor()

    indexes = _fetch_indexes(cursor, "recipes")
    expected = {
        "idx_recipes_name_id",
        "idx_recipes_avg_rating_id",
        "idx_recipes_created_at_id",
        "idx_recipes_rating_count_id",
    }
    assert expected.issubset(set(indexes.keys()))

    cursor.close()
    conn.close()
