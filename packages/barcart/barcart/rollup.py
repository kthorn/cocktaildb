"""Ingredient rollup functionality for reducing dimensionality.

This module provides functions to roll up substitutable leaf ingredients
to their parent categories, reducing the ingredient space while preserving
recipe semantics.
"""

from typing import Dict
import pandas as pd


def create_rollup_mapping(
    ingredients: pd.DataFrame,
    parent_map: Dict[str, tuple],
    allow_substitution_col: str = "allow_substitution"
) -> Dict[int, int]:
    """Map substitutable leaf ingredients to their parents.

    Args:
        ingredients: DataFrame with columns [id, allow_substitution]
        parent_map: Dict from build_ingredient_tree mapping child_id -> (parent_id, cost)
        allow_substitution_col: Column name for substitution flag

    Returns:
        Dict mapping leaf_ingredient_id -> parent_ingredient_id
    """
    pass


def apply_rollup_to_recipes(
    recipes: pd.DataFrame,
    rollup_map: Dict[int, int],
    ingredient_id_col: str = "ingredient_id",
    volume_col: str = "volume_fraction"
) -> pd.DataFrame:
    """Apply rollup mapping and aggregate duplicate ingredients.

    Args:
        recipes: DataFrame with columns [recipe_id, ingredient_id, volume_fraction, ...]
        rollup_map: Dict mapping ingredient_id -> parent_id
        ingredient_id_col: Column name for ingredient IDs
        volume_col: Column name for volumes to aggregate

    Returns:
        New DataFrame with rolled-up ingredients and aggregated volumes
    """
    pass
