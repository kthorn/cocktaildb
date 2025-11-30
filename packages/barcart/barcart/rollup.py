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
    # Validate inputs
    assert "id" in ingredients.columns, "ingredients must have 'id' column"
    assert allow_substitution_col in ingredients.columns, f"ingredients must have '{allow_substitution_col}' column"

    # Get all ingredient IDs that have children (i.e., they are parents)
    parent_ids = set()
    for child_id, (parent_id, cost) in parent_map.items():
        if parent_id is not None:
            parent_ids.add(parent_id)

    # Find substitutable leaves: allow_substitution=1 AND not a parent
    substitutable_leaves = ingredients[
        (ingredients[allow_substitution_col] == 1) &
        (~ingredients["id"].astype(str).isin(parent_ids))
    ]

    # Map each leaf to its parent
    rollup_map = {}
    for leaf_id in substitutable_leaves["id"]:
        leaf_id_str = str(leaf_id)
        if leaf_id_str in parent_map:
            parent_id, _ = parent_map[leaf_id_str]
            if parent_id is not None and parent_id != "root":
                # Convert parent_id to int
                try:
                    rollup_map[leaf_id] = int(parent_id)
                except (ValueError, TypeError):
                    # Skip if parent_id can't be converted to int
                    pass

    return rollup_map


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
    # Validate inputs
    assert ingredient_id_col in recipes.columns, f"recipes must have '{ingredient_id_col}' column"
    assert volume_col in recipes.columns, f"recipes must have '{volume_col}' column"

    # Create a copy to avoid modifying original
    recipes_rolled = recipes.copy()

    # Apply rollup mapping (unmapped IDs pass through)
    recipes_rolled[ingredient_id_col] = recipes_rolled[ingredient_id_col].map(
        lambda x: rollup_map.get(x, x)
    )

    # After rollup, we may have duplicate ingredients in the same recipe
    # Aggregate by summing volumes and keeping first value for other columns
    agg_dict = {volume_col: 'sum'}

    # Add 'first' aggregation for non-numeric columns
    for col in recipes_rolled.columns:
        if col not in ['recipe_id', ingredient_id_col, volume_col]:
            agg_dict[col] = 'first'

    recipes_rolled = recipes_rolled.groupby(
        ['recipe_id', ingredient_id_col], as_index=False
    ).agg(agg_dict)

    return recipes_rolled
