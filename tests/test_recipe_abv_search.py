# ruff: noqa: FURB157
"""Recipe search filtered by the displayed ABV."""

import re
from decimal import Decimal

import pytest

from api.db.sql_queries import (
    build_search_recipes_keyset_sql,
    build_search_recipes_paginated_sql,
)


def _id(db, table, name):
    return db.execute_query(
        f"SELECT id FROM {table} WHERE name = %(name)s",  # noqa: S608
        {"name": name},
    )[0]["id"]


def _ingredient(db, name, percent=None, parent=None):
    db.execute_query(
        """
        INSERT INTO ingredients (name, percent_abv, parent_id)
        VALUES (%(name)s, %(percent)s, %(parent)s)
        """,
        {"name": name, "percent": percent, "parent": parent},
    )
    return _id(db, "ingredients", name)


def _family_member(db, name, lo, hi):
    parent = _ingredient(db, f"{name} family")
    _ingredient(db, f"{name} low", Decimal(lo), parent)
    _ingredient(db, f"{name} high", Decimal(hi), parent)
    return _ingredient(db, name, parent=parent)


def _recipe(db, name, rows):
    db.execute_query(
        "INSERT INTO recipes (name, instructions) VALUES (%(name)s, 'Mix')",
        {"name": name},
    )
    recipe_id = _id(db, "recipes", name)
    ml = _id(db, "units", "milliliter")
    for ingredient_id, amount in rows:
        db.execute_query(
            """
            INSERT INTO recipe_ingredients (recipe_id, ingredient_id, unit_id, amount)
            VALUES (%(recipe)s, %(ingredient)s, %(unit)s, %(amount)s)
            """,
            {
                "recipe": recipe_id,
                "ingredient": ingredient_id,
                "unit": ml,
                "amount": amount,
            },
        )


@pytest.fixture
def abv_db(db_instance):
    db = db_instance
    _recipe(db, "Range", [(_family_member(db, "Ranged", "10.4", "14.2"), 10)])
    _recipe(db, "Point", [(_family_member(db, "Pointed", "14.1", "15.1"), 10)])
    _recipe(db, "Tiny", [(_ingredient(db, "Tiny spirit", Decimal("0.4")), 10)])
    _recipe(db, "Strong", [(_ingredient(db, "Strong spirit", 40), 10)])
    _recipe(
        db,
        "Too wide",
        [(_ingredient(db, "Mystery"), 30), (_ingredient(db, "Water", 0), 30)],
    )
    _recipe(db, "Empty", [])
    return db


def _parse_display(display):
    if display == "<1%":
        return 0, 0
    numbers = [int(n) for n in re.findall(r"\d+", display)]
    return numbers[0], numbers[-1]


PATHS = [("name", False), ("name", True), ("random", True)]


def _search(db, params, sort_by="name", paginate=True):
    result = db.search_recipes_paginated(
        params, limit=100, sort_by=sort_by, return_pagination=paginate
    )
    return result["recipes"] if paginate else result


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"min_abv": 15}, {"Range", "Point", "Strong"}),
        ({"max_abv": 15}, {"Range", "Point", "Tiny"}),
        ({"min_abv": 15, "max_abv": 15}, {"Range", "Point"}),
        ({"max_abv": 0}, {"Tiny"}),
        ({"min_abv": 1}, {"Range", "Point", "Strong"}),
        ({"min_abv": 41}, set()),
    ],
)
@pytest.mark.parametrize(("sort_by", "paginate"), PATHS)
def test_abv_filter_matches_displayed_range(
    abv_db, params, expected, sort_by, paginate
):
    recipes = _search(abv_db, params, sort_by, paginate)

    assert {r["name"] for r in recipes} == expected
    low_bound = params.get("min_abv", 0)
    high_bound = params.get("max_abv", 100)
    for recipe in recipes:
        low, high = _parse_display(recipe["abv"]["display"])
        assert high >= low_bound and low <= high_bound


def test_displays_match_the_fixture_story(abv_db):
    displays = {r["name"]: r["abv"]["display"] for r in _search(abv_db, {})}
    assert displays == {
        "Range": "10–15%",
        "Point": "15%",
        "Tiny": "<1%",
        "Strong": "40%",
        "Too wide": "Unknown",
        "Empty": "Unknown",
    }


@pytest.mark.parametrize(("sort_by", "paginate"), PATHS)
def test_min_abv_zero_excludes_unknown(abv_db, sort_by, paginate):
    names = {r["name"] for r in _search(abv_db, {"min_abv": 0}, sort_by, paginate)}
    assert names == {"Range", "Point", "Tiny", "Strong"}


def test_no_abv_filter_returns_unknown_recipes_too(abv_db):
    assert len(_search(abv_db, {})) == 6


def test_abv_filter_paginates_without_gaps(abv_db):
    db = abv_db
    seen = []
    cursor = None
    while True:
        page = db.search_recipes_paginated(
            {"min_abv": 1}, limit=1, cursor=cursor, return_pagination=True
        )
        seen.extend(r["name"] for r in page["recipes"])
        if not page["has_next"]:
            break
        cursor = page["next_cursor"]
    assert seen == sorted(seen)
    assert set(seen) == {"Range", "Point", "Strong"}
    assert len(seen) == 3

    offset_pages = [
        db.search_recipes_paginated(
            {"min_abv": 1},
            limit=1,
            offset=offset,
            sort_by="name",
            return_pagination=False,
        )
        for offset in range(4)
    ]
    assert [r["name"] for page in offset_pages for r in page] == seen


@pytest.mark.parametrize(
    "builder", [build_search_recipes_paginated_sql, build_search_recipes_keyset_sql]
)
def test_builders_emit_abv_join_only_when_filtering(builder):
    assert "recipe_abv rab" not in builder([], [])
    filtered = builder([], [], abv_filter=True)
    assert "recipe_abv rab ON rab.recipe_id = r.id" in filtered
    assert "rab.display_high >= %(min_abv)s" in filtered
    assert "rab.display_low <= %(max_abv)s" in filtered
    assert "rab.status <> 'unknown'" in filtered


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "status"),
    [
        ("min_abv=20&max_abv=10", 400),
        ("min_abv=12.5", 422),
        ("min_abv=101", 422),
        ("max_abv=-1", 422),
        ("min_abv=10&max_abv=10", 200),
    ],
)
async def test_search_validates_abv_bounds(abv_db, test_client_memory, query, status):
    response = await test_client_memory.get(f"/recipes/search?{query}")
    assert response.status_code == status


@pytest.mark.asyncio
async def test_public_search_applies_abv_bounds(abv_db, test_client_memory):
    response = await test_client_memory.get("/recipes/search?min_abv=15&max_abv=15")
    assert response.status_code == 200
    assert {r["name"] for r in response.json()["recipes"]} == {"Range", "Point"}


@pytest.mark.asyncio
async def test_authenticated_search_forwards_abv_bounds(abv_db, editor_client):
    response = await editor_client.get(
        "/recipes/search/authenticated?min_abv=15&max_abv=15"
    )
    assert response.status_code == 200
    assert {r["name"] for r in response.json()["recipes"]} == {"Range", "Point"}


@pytest.mark.parametrize(
    ("params", "matches"),
    [
        ({"min_abv": 2}, True),
        ({"min_abv": 3}, False),
        ({"max_abv": 0}, True),
    ],
)
def test_low_wide_interval_is_filtered_by_its_displayed_range(
    db_instance, params, matches
):
    db = db_instance
    _recipe(db, "Mocktail", [(_family_member(db, "Bitters", "0", "1.5"), 10)])
    (listed,) = _search(db, {})
    assert listed["abv"]["display"] == "0–2%"
    names = {r["name"] for r in _search(db, params)}
    assert ("Mocktail" in names) is matches
