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
        {"from_ingredient_id": 10, "to_ingredient_id": 11, "mass": 0.5},
        {"from_ingredient_id": 11, "to_ingredient_id": 12, "mass": 0.3},
        {"from_ingredient_id": 12, "to_ingredient_id": 10, "mass": 0.2},
    ]
    assert neighbors[0]["transport_plan"] == expected_plan
