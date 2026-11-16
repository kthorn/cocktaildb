"""Pure unit tests for MCP output shaping"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from mcp_tools.shaping import (
    hierarchy_names,
    ingredient_url,
    path_ids,
    recipe_url,
    to_detail,
    to_similar,
    to_summary,
)

BASE = "https://mixology.tools"


def test_urls_strip_trailing_slash():
    assert recipe_url(BASE + "/", 12) == "https://mixology.tools/recipe/12"
    assert ingredient_url(BASE, 8) == "https://mixology.tools/ingredient/8"


def test_detail_drops_private_fields_and_keeps_public_tags():
    recipe = {
        "id": 1,
        "name": "Negroni",
        "instructions": "Stir.",
        "description": None,
        "source": "Book",
        "source_url": None,
        "avg_rating": 4.5,
        "rating_count": 2,
        "created_by": "cognito-sub-123",
        "user_rating": 5,
        "abv": {"status": "calculated", "display": "24%", "notes": ["n"]},
        "ingredients": [
            {
                "ingredient_id": 4,
                "ingredient_name": "Gin",
                "amount": 1.0,
                "unit_name": "ounce",
                "unit_abbreviation": "oz",
            }
        ],
        "tags": [
            {"id": 1, "name": "bitter", "type": "public"},
            {"id": 2, "name": "mine", "type": "private"},
        ],
    }
    d = to_detail(recipe, BASE)
    dumped = d.model_dump()
    assert "created_by" not in dumped and "user_rating" not in dumped
    assert d.tags == ["bitter"]
    assert d.url == "https://mixology.tools/recipe/1"
    assert d.ingredients[0].unit == "oz"
    assert d.ingredients[0].url == "https://mixology.tools/ingredient/4"
    assert d.abv == "24%" and d.abv_notes == ["n"]


def test_summary_lists_ingredient_names_and_handles_missing_rating():
    s = to_summary(
        {
            "id": 3,
            "name": "X",
            "avg_rating": None,
            "rating_count": None,
            "ingredients": [{"ingredient_id": 1, "ingredient_name": "Rum"}],
            "tags": [],
            "abv": None,
        },
        BASE,
    )
    assert s.ingredients == ["Rum"] and s.rating_count == 0 and s.abv is None


def test_similar_sorted_by_distance_and_limited_with_swaps_by_weight():
    row = {
        "recipe_id": 1,
        "recipe_name": "Negroni",
        "neighbors": [
            {
                "neighbor_recipe_id": 3,
                "neighbor_name": "Far",
                "distance": 0.9,
                "transport_plan": [],
            },
            {
                "neighbor_recipe_id": 2,
                "neighbor_name": "Near",
                "distance": 0.1,
                "transport_plan": [
                    {
                        "from_ingredient_name": "Gin",
                        "to_ingredient_name": "Bourbon",
                        "mass": 0.2,
                    },
                    {
                        "from_ingredient_name": "Campari",
                        "to_ingredient_name": "Aperol",
                        "mass": 0.5,
                    },
                ],
            },
        ],
    }
    r = to_similar(row, BASE, limit=1)
    assert [s.name for s in r.similar] == ["Near"]
    assert r.similar[0].swaps[0].from_ingredient == "Campari"
    assert r.similar[0].url == "https://mixology.tools/recipe/2"


def test_hierarchy_names_from_path():
    assert path_ids("/1/8/") == [1, 8]
    assert hierarchy_names("/1/8/", {1: "Whiskey", 8: "Bourbon"}) == [
        "Whiskey",
        "Bourbon",
    ]
    assert hierarchy_names(None, {}) == []


def _neighbor(neighbor_id, name, distance, plan):
    return {
        "neighbor_recipe_id": neighbor_id,
        "neighbor_name": name,
        "distance": distance,
        "transport_plan": [
            {"from_ingredient_name": a, "to_ingredient_name": b, "mass": m}
            for a, b, m in plan
        ],
    }


def test_similar_drops_small_and_self_swaps():
    row = {
        "recipe_id": 1,
        "recipe_name": "Negroni",
        "neighbors": [
            _neighbor(
                2,
                "Variant",
                0.02,
                [
                    ("Gin", "Sweet Vermouth", 0.008),
                    ("Gin", "Gin", 0.3),
                    ("Campari", "Aperol", 0.05),
                ],
            ),
            _neighbor(3, "Ratio Tweak", 0.03, [("Gin", "Campari", 0.01)]),
        ],
    }
    r = to_similar(row, BASE, limit=5)
    assert [(s.from_ingredient, s.to_ingredient) for s in r.similar[0].swaps] == [
        ("Campari", "Aperol")
    ]
    # A neighbour whose differences are all small stays listed, with no swaps.
    assert r.similar[1].name == "Ratio Tweak"
    assert r.similar[1].swaps == []
