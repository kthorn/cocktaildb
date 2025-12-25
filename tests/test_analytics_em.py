import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from api.db.db_analytics import AnalyticsQueries
import barcart


def test_compute_cocktail_space_umap_em_handles_sparse_volume(
    monkeypatch,
) -> None:
    class DummyDB:
        def execute_query(self, _sql, _params=None):
            return []

    ingredients_df = pd.DataFrame(
        [
            {
                "ingredient_id": 1,
                "ingredient_name": "Base",
                "ingredient_path": "/1/",
                "substitution_level": 1.0,
                "allow_substitution": 1,
            },
            {
                "ingredient_id": 2,
                "ingredient_name": "Mixer",
                "ingredient_path": "/2/",
                "substitution_level": 1.0,
                "allow_substitution": 1,
            },
        ]
    )
    recipes_df = pd.DataFrame(
        [
            {
                "recipe_id": 10,
                "recipe_name": "A",
                "ingredient_id": 1,
                "volume_fraction": 0.6,
            },
            {
                "recipe_id": 10,
                "recipe_name": "A",
                "ingredient_id": 2,
                "volume_fraction": 0.4,
            },
            {
                "recipe_id": 11,
                "recipe_name": "B",
                "ingredient_id": 1,
                "volume_fraction": 0.5,
            },
            {
                "recipe_id": 11,
                "recipe_name": "B",
                "ingredient_id": 2,
                "volume_fraction": 0.5,
            },
        ]
    )
    def fake_em_fit(volume_matrix, cost_matrix, n_ingredients, iters=1, **_kwargs):
        n_recipes = volume_matrix.shape[0]
        dist = np.zeros((n_recipes, n_recipes), dtype=np.float32)
        return dist, cost_matrix, {"delta": [0.0]}

    def fake_umap_embedding(distance_matrix, **_kwargs):
        return np.zeros((distance_matrix.shape[0], 2), dtype=np.float32)

    monkeypatch.setattr(barcart, "em_fit", fake_em_fit)
    monkeypatch.setattr(barcart, "compute_umap_embedding", fake_umap_embedding)

    analytics_queries = AnalyticsQueries(DummyDB())
    monkeypatch.setattr(
        analytics_queries, "get_ingredients_for_tree", lambda: ingredients_df
    )
    monkeypatch.setattr(
        analytics_queries, "get_recipes_for_distance_calc", lambda: recipes_df
    )
    result = analytics_queries.compute_cocktail_space_umap_em()

    assert result
    assert "x" in result[0]
    assert "y" in result[0]
