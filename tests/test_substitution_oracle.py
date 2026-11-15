"""Inventory matching agrees with a plain-Python statement of the substitution rule.

A seeded random ingredient tree, recipe set and group inventories are checked
against `_matches`, a direct transcription of INGREDIENT_SUBSTITUTION_MATCH.
This pins the rule's semantics so the SQL can be restructured for speed.
"""

import random

import psycopg2
import pytest

SEEDS = [1, 2, 3]
UNIT_OZ = 1  # conftest seeds 'ounce' (29.5735 ml) first
UNIT_DASH = 5  # and 'dash' (0.9 ml) fifth
ML = {UNIT_OZ: 29.5735, UNIT_DASH: 0.9}
MINOR_MAX_FRACTION = 0.02  # sql_queries.MINOR_INGREDIENT_MAX_FRACTION


def _ancestors_or_self(ing, by_id):
    """Ingredients whose path is a prefix of ing's path, nearest first."""
    chain = []
    node = ing
    while node is not None:
        chain.append(node)
        node = by_id.get(node["parent_id"])
    return chain


def _blocked(recipe_ing, top, by_id):
    """A non-substitutable ingredient lies on the path from top down to recipe_ing."""
    for node in _ancestors_or_self(recipe_ing, by_id):
        if node["id"] == top["id"]:
            return False
        if not node["allow_substitution"]:
            return True
    raise AssertionError("top is not an ancestor of recipe_ing")


def _matches(user, recipe, by_id):
    if user["id"] == recipe["id"]:
        return True
    if not recipe["allow_substitution"]:
        return False
    recipe_chain = {n["id"] for n in _ancestors_or_self(recipe, by_id)}
    if user["id"] in recipe_chain and not _blocked(recipe, user, by_id):
        return True
    if (
        recipe["parent_id"] is not None
        and recipe["parent_id"] == user["parent_id"]
        and user["allow_substitution"]
    ):
        return True
    if user["id"] == recipe["parent_id"]:
        return True
    for anc in _ancestors_or_self(user, by_id):
        if (
            anc["id"] in recipe_chain
            and anc["allow_substitution"]
            and anc["path"].count("/") <= 6
            and not _blocked(recipe, anc, by_id)
        ):
            return True
    return False


def _build_world(conn, seed):
    rng = random.Random(seed)
    cur = conn.cursor()
    ingredients = []
    by_id = {}
    for n in range(60):
        parent = rng.choice([None] + ingredients[-25:]) if ingredients else None
        if parent is not None and parent["path"].count("/") > 6:
            parent = None
        cur.execute(
            "INSERT INTO ingredients (name, parent_id, allow_substitution) "
            "VALUES (%s, %s, %s) RETURNING id",
            (f"Oracle {seed}-{n}", parent and parent["id"], rng.random() < 0.7),
        )
        new_id = cur.fetchone()[0]
        path = f"{parent['path'] if parent else '/'}{new_id}/"
        cur.execute("UPDATE ingredients SET path=%s WHERE id=%s", (path, new_id))
        cur.execute(
            "SELECT id, parent_id, path, allow_substitution FROM ingredients WHERE id=%s",
            (new_id,),
        )
        fields = ("id", "parent_id", "path", "allow_substitution")
        row = dict(zip(fields, cur.fetchone(), strict=True))
        ingredients.append(row)
        by_id[new_id] = row

    recipes = {}
    for n in range(80):
        cur.execute(
            "INSERT INTO recipes (name) VALUES (%s) RETURNING id",
            (f"Oracle R{seed}-{n}",),
        )
        recipe_id = cur.fetchone()[0]
        measures = []
        for ing in rng.sample(ingredients, rng.randint(1, 4)):
            unit, amount = rng.choice([(UNIT_DASH, 1), (UNIT_OZ, 2)])
            cur.execute(
                "INSERT INTO recipe_ingredients (recipe_id, ingredient_id, unit_id, amount) "
                "VALUES (%s, %s, %s, %s)",
                (recipe_id, ing["id"], unit, amount),
            )
            measures.append((ing, amount * ML[unit]))
        total = sum(volume for _, volume in measures)
        recipes[recipe_id] = [
            (ing, volume <= MINOR_MAX_FRACTION * total) for ing, volume in measures
        ]

    inventories = {}
    for n in range(6):
        user_id = f"oracle-{seed}-{n}"
        owned = rng.sample(ingredients, rng.randint(1, 20))
        inventories[user_id] = owned
    conn.commit()
    return by_id, recipes, inventories


@pytest.fixture
def oracle_conn(db_instance, memory_db_with_schema):
    conn = psycopg2.connect(**memory_db_with_schema)
    yield conn
    conn.close()


@pytest.mark.parametrize("seed", SEEDS)
def test_inventory_search_matches_rule(db_instance, oracle_conn, seed):
    by_id, recipes, inventories = _build_world(oracle_conn, seed)
    for user_id, owned in inventories.items():
        db_instance.add_user_ingredients_bulk(user_id, [i["id"] for i in owned])
        for ignore_minor in (False, True):
            expected = {
                recipe_id
                for recipe_id, rows in recipes.items()
                if all(
                    (ignore_minor and minor)
                    or any(_matches(u, ing, by_id) for u in owned)
                    for ing, minor in rows
                )
            }
            found = db_instance.search_recipes_paginated(
                {"inventory": True, "ignore_minor": ignore_minor},
                limit=1000,
                user_id=user_id,
            )
            assert {r["id"] for r in found} == expected, (user_id, ignore_minor)


@pytest.mark.parametrize("seed", SEEDS)
def test_recommendations_match_rule(db_instance, oracle_conn, seed):
    by_id, recipes, inventories = _build_world(oracle_conn, seed)
    for user_id, owned in inventories.items():
        db_instance.add_user_ingredients_bulk(user_id, [i["id"] for i in owned])
        expected: dict[int, int] = {}
        for rows in recipes.values():
            missing = [
                ing
                for ing, _ in rows
                if not any(_matches(u, ing, by_id) for u in owned)
            ]
            if len(missing) == 1:
                expected[missing[0]["id"]] = expected.get(missing[0]["id"], 0) + 1
        found = db_instance.get_ingredient_recommendations(user_id, limit=1000)
        assert {r["id"]: r["recipes_unlocked"] for r in found} == expected, user_id
