from api.db.db_core import Database


def test_search_sort_by_rating_count_uses_id_tiebreaker(set_pg_env):
    db = Database()

    db.execute_query(
        """
        INSERT INTO recipes (id, name, rating_count)
        VALUES (100, 'Tie A', 5), (101, 'Tie B', 5)
        """
    )

    results = db.search_recipes_paginated(
        search_params={},
        limit=10,
        offset=0,
        sort_by="rating_count",
        sort_order="asc",
        return_pagination=False,
    )

    ids = [recipe["id"] for recipe in results]
    assert ids[:2] == [100, 101]
