"""Tests for recipe similarity reporting."""

import numpy as np
import pytest

from barcart.registry import Registry
from barcart.reporting import build_recipe_similarity


def test_build_recipe_similarity_selects_top_neighbors_and_plans():
    distance_matrix = np.array(
        [
            [0.0, 0.0, 0.5, 0.2, 0.3],
            [0.0, 0.0, 0.4, 0.1, 0.2],
            [0.5, 0.4, 0.0, 0.6, 0.7],
            [0.2, 0.1, 0.6, 0.0, 0.9],
            [0.3, 0.2, 0.7, 0.9, 0.0],
        ],
        dtype=np.float32,
    )

    recipe_registry = Registry(
        [
            (0, 1, "One"),
            (1, 2, "Two"),
            (2, 3, "Three"),
            (3, 4, "Four"),
            (4, 5, "Five"),
        ]
    )
    ingredient_registry = Registry(
        [
            (0, 10, "Ing A"),
            (1, 11, "Ing B"),
            (2, 12, "Ing C"),
        ]
    )

    plans = {
        (0, 1): [
            (0, 1, 0.5, 0.1),
            (1, 2, 0.3, 0.2),
            (2, 0, 0.2, 0.3),
            (0, 2, 0.1, 0.4),
        ]
    }

    result = build_recipe_similarity(
        distance_matrix,
        plans,
        recipe_registry,
        ingredient_registry,
        k=4,
        plan_topk=3,
    )

    entry = next(item for item in result if item["recipe_id"] == 1)
    neighbors = entry["neighbors"]

    assert [neighbor["neighbor_recipe_id"] for neighbor in neighbors] == [2, 4, 5, 3]
    assert all(neighbor["neighbor_recipe_id"] != 1 for neighbor in neighbors)
    assert neighbors[0]["distance"] == pytest.approx(0.0)

    expected_plan = [
        {"from_ingredient_id": 10, "from_ingredient_name": "Ing A", "to_ingredient_id": 11, "to_ingredient_name": "Ing B", "mass": 0.5},
        {"from_ingredient_id": 11, "from_ingredient_name": "Ing B", "to_ingredient_id": 12, "to_ingredient_name": "Ing C", "mass": 0.3},
        {"from_ingredient_id": 12, "from_ingredient_name": "Ing C", "to_ingredient_id": 10, "to_ingredient_name": "Ing A", "mass": 0.2},
    ]
    assert neighbors[0]["transport_plan"] == expected_plan


def test_build_recipe_similarity_filters_self_transport():
    """Self-transport entries (same ingredient to same ingredient) should be filtered out."""
    distance_matrix = np.array(
        [
            [0.0, 0.2],
            [0.2, 0.0],
        ],
        dtype=np.float32,
    )

    recipe_registry = Registry([(0, 1, "One"), (1, 2, "Two")])
    ingredient_registry = Registry(
        [
            (0, 10, "Lemon Juice"),
            (1, 11, "Gin"),
        ]
    )

    # Include a self-transport entry (0, 0) which should be filtered out
    plans = {
        (0, 1): [
            (0, 0, 0.25, 0.0),  # Self-transport: lemon -> lemon (should be filtered)
            (0, 1, 0.15, 0.1),  # Real transport: lemon -> gin
            (1, 1, 0.20, 0.0),  # Self-transport: gin -> gin (should be filtered)
        ]
    }

    result = build_recipe_similarity(
        distance_matrix,
        plans,
        recipe_registry,
        ingredient_registry,
        k=1,
        plan_topk=3,
    )

    transport_plan = result[0]["neighbors"][0]["transport_plan"]

    # Only the real transport should remain
    assert len(transport_plan) == 1
    assert transport_plan[0]["from_ingredient_id"] == 10
    assert transport_plan[0]["to_ingredient_id"] == 11


def test_build_recipe_similarity_swaps_direction_for_higher_index_recipe():
    """Transport plan direction should be relative to the current recipe, not storage order."""
    distance_matrix = np.array(
        [
            [0.0, 0.2],
            [0.2, 0.0],
        ],
        dtype=np.float32,
    )

    recipe_registry = Registry([(0, 1, "One"), (1, 2, "Two")])
    ingredient_registry = Registry(
        [
            (0, 10, "Maraschino"),
            (1, 11, "Cynar"),
        ]
    )

    # Plan stored for (0, 1): from recipe 0's ingredient to recipe 1's ingredient
    # idx=0 has Maraschino (ing 0), idx=1 has Cynar (ing 1)
    plans = {(0, 1): [(0, 1, 0.25, 0.1)]}  # Maraschino -> Cynar

    result = build_recipe_similarity(
        distance_matrix,
        plans,
        recipe_registry,
        ingredient_registry,
        k=1,
        plan_topk=1,
    )

    # For recipe 1 (One), neighbor is recipe 2 (Two)
    # idx=0 < neighbor_idx=1, so no swap needed
    # Should show: Maraschino -> Cynar (One's ingredient -> Two's ingredient)
    recipe_one = next(r for r in result if r["recipe_id"] == 1)
    plan_one = recipe_one["neighbors"][0]["transport_plan"][0]
    assert plan_one["from_ingredient_name"] == "Maraschino"
    assert plan_one["to_ingredient_name"] == "Cynar"

    # For recipe 2 (Two), neighbor is recipe 1 (One)
    # idx=1 > neighbor_idx=0, so swap IS needed
    # Should show: Cynar -> Maraschino (Two's ingredient -> One's ingredient)
    recipe_two = next(r for r in result if r["recipe_id"] == 2)
    plan_two = recipe_two["neighbors"][0]["transport_plan"][0]
    assert plan_two["from_ingredient_name"] == "Cynar"
    assert plan_two["to_ingredient_name"] == "Maraschino"


def test_build_recipe_similarity_includes_transport_names():
    distance_matrix = np.array(
        [
            [0.0, 0.2],
            [0.2, 0.0],
        ],
        dtype=np.float32,
    )

    recipe_registry = Registry([(0, 1, "One"), (1, 2, "Two")])
    ingredient_registry = Registry(
        [
            (0, 10, "Lillet"),
            (1, 11, "Cocchi Americano"),
        ]
    )

    plans = {(0, 1): [(0, 1, 0.4, 0.1)]}

    result = build_recipe_similarity(
        distance_matrix,
        plans,
        recipe_registry,
        ingredient_registry,
        k=1,
        plan_topk=1,
    )

    transport = result[0]["neighbors"][0]["transport_plan"][0]
    assert transport["from_ingredient_name"] == "Lillet"
    assert transport["to_ingredient_name"] == "Cocchi Americano"
