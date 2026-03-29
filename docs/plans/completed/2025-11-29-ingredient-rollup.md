# Ingredient Rollup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add ingredient rollup functions to barcart package and implement EM-based cocktail space calculation with rollup applied.

**Architecture:** Two-phase implementation. Phase 1 adds rollup functions to barcart package (tested in isolation). Phase 2 integrates into analytics pipeline to generate EM-based cocktail space alongside existing Manhattan distance approach.

**Tech Stack:** Python 3.x, pandas, barcart package, pytest, AWS Lambda, boto3

---

## Task 1: Create Rollup Module Structure

**Files:**
- Create: `packages/barcart/barcart/rollup.py`
- Modify: `packages/barcart/barcart/__init__.py`
- Create: `packages/barcart/tests/test_rollup.py`

**Step 1: Create empty rollup module with docstring**

Create `packages/barcart/barcart/rollup.py`:

```python
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
```

**Step 2: Export functions from __init__.py**

Add to `packages/barcart/barcart/__init__.py`:

```python
from .rollup import create_rollup_mapping, apply_rollup_to_recipes
```

Find the `__all__` list and add:

```python
__all__ = [
    # ... existing exports ...
    "create_rollup_mapping",
    "apply_rollup_to_recipes",
]
```

**Step 3: Create test file structure**

Create `packages/barcart/tests/test_rollup.py`:

```python
"""Tests for ingredient rollup functionality."""

import pandas as pd
import pytest
from barcart.rollup import create_rollup_mapping, apply_rollup_to_recipes


class TestCreateRollupMapping:
    """Tests for create_rollup_mapping function."""

    pass


class TestApplyRollupToRecipes:
    """Tests for apply_rollup_to_recipes function."""

    pass
```

**Step 4: Verify structure**

Run: `python -c "from barcart.rollup import create_rollup_mapping, apply_rollup_to_recipes; print('Imports successful')"`

Expected: "Imports successful"

**Step 5: Commit**

```bash
git add packages/barcart/barcart/rollup.py packages/barcart/barcart/__init__.py packages/barcart/tests/test_rollup.py
git commit -m "feat(barcart): add rollup module structure with stubs"
```

---

## Task 2: Implement create_rollup_mapping with TDD

**Files:**
- Modify: `packages/barcart/tests/test_rollup.py`
- Modify: `packages/barcart/barcart/rollup.py`

**Step 1: Write failing test for basic mapping**

Add to `packages/barcart/tests/test_rollup.py` in `TestCreateRollupMapping`:

```python
def test_basic_leaf_to_parent_mapping(self):
    """Test basic rollup mapping creation."""
    # Tanqueray (id=2, substitutable leaf) -> London Dry Gin (id=1, parent)
    ingredients = pd.DataFrame({
        'id': [1, 2],
        'name': ['London Dry Gin', 'Tanqueray'],
        'allow_substitution': [0, 1]
    })

    parent_map = {
        '2': ('1', 0.1)  # Tanqueray -> London Dry Gin
    }

    rollup_map = create_rollup_mapping(ingredients, parent_map)

    assert rollup_map == {2: 1}
    assert len(rollup_map) == 1
```

**Step 2: Run test to verify it fails**

Run: `cd packages/barcart && pytest tests/test_rollup.py::TestCreateRollupMapping::test_basic_leaf_to_parent_mapping -v`

Expected: FAIL (function returns None, not dict)

**Step 3: Implement minimal create_rollup_mapping**

Update `packages/barcart/barcart/rollup.py`:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `cd packages/barcart && pytest tests/test_rollup.py::TestCreateRollupMapping::test_basic_leaf_to_parent_mapping -v`

Expected: PASS

**Step 5: Commit**

```bash
git add packages/barcart/barcart/rollup.py packages/barcart/tests/test_rollup.py
git commit -m "feat(barcart): implement create_rollup_mapping basic functionality"
```

---

## Task 3: Add Edge Case Tests for create_rollup_mapping

**Files:**
- Modify: `packages/barcart/tests/test_rollup.py`

**Step 1: Write test for non-substitutable ingredients**

Add to `TestCreateRollupMapping`:

```python
def test_non_substitutable_ingredients_excluded(self):
    """Non-substitutable ingredients should not be rolled up."""
    ingredients = pd.DataFrame({
        'id': [1, 2, 3],
        'name': ['Parent', 'Non-Sub Child', 'Sub Child'],
        'allow_substitution': [0, 0, 1]
    })

    parent_map = {
        '2': ('1', 0.1),  # Non-substitutable child
        '3': ('1', 0.1)   # Substitutable child
    }

    rollup_map = create_rollup_mapping(ingredients, parent_map)

    assert rollup_map == {3: 1}  # Only substitutable child included
    assert 2 not in rollup_map
```

**Step 2: Run test to verify it passes**

Run: `cd packages/barcart && pytest tests/test_rollup.py::TestCreateRollupMapping::test_non_substitutable_ingredients_excluded -v`

Expected: PASS (already implemented in previous task)

**Step 3: Write test for ingredients without parents**

Add to `TestCreateRollupMapping`:

```python
def test_ingredients_without_parents_skipped(self):
    """Ingredients not in parent_map should be skipped."""
    ingredients = pd.DataFrame({
        'id': [1, 2],
        'allow_substitution': [1, 1]
    })

    parent_map = {
        '1': ('root', 0.0)  # Has parent but it's root
    }
    # ingredient 2 not in parent_map

    rollup_map = create_rollup_mapping(ingredients, parent_map)

    assert rollup_map == {}  # Root parent excluded, 2 has no parent
```

**Step 4: Run test to verify it passes**

Run: `cd packages/barcart && pytest tests/test_rollup.py::TestCreateRollupMapping::test_ingredients_without_parents_skipped -v`

Expected: PASS (already implemented - root check exists)

**Step 5: Write test for parent ingredients not rolled up**

Add to `TestCreateRollupMapping`:

```python
def test_parent_ingredients_not_rolled_up(self):
    """Ingredients that are parents should not be rolled up."""
    ingredients = pd.DataFrame({
        'id': [1, 2, 3],
        'name': ['Grandparent', 'Parent', 'Child'],
        'allow_substitution': [0, 1, 1]  # Parent is substitutable but is also a parent
    })

    parent_map = {
        '2': ('1', 0.1),  # Parent -> Grandparent
        '3': ('2', 0.1)   # Child -> Parent
    }

    rollup_map = create_rollup_mapping(ingredients, parent_map)

    assert rollup_map == {3: 2}  # Only leaf (3) rolled up
    assert 2 not in rollup_map   # Parent not rolled up even though substitutable
```

**Step 6: Run test to verify it passes**

Run: `cd packages/barcart && pytest tests/test_rollup.py::TestCreateRollupMapping::test_parent_ingredients_not_rolled_up -v`

Expected: PASS (already implemented - parent_ids check excludes parents)

**Step 7: Commit**

```bash
git add packages/barcart/tests/test_rollup.py
git commit -m "test(barcart): add edge case tests for create_rollup_mapping"
```

---

## Task 4: Implement apply_rollup_to_recipes with TDD

**Files:**
- Modify: `packages/barcart/tests/test_rollup.py`
- Modify: `packages/barcart/barcart/rollup.py`

**Step 1: Write failing test for basic rollup application**

Add to `TestApplyRollupToRecipes`:

```python
def test_basic_rollup_application(self):
    """Test basic rollup application to recipes."""
    recipes = pd.DataFrame({
        'recipe_id': [1, 1, 2],
        'ingredient_id': [10, 20, 10],
        'volume_fraction': [0.5, 0.5, 1.0]
    })

    rollup_map = {20: 100}  # Roll 20 -> 100

    result = apply_rollup_to_recipes(recipes, rollup_map)

    # recipe 1 should have ingredients 10 and 100 (rolled from 20)
    recipe1 = result[result['recipe_id'] == 1].sort_values('ingredient_id')
    assert len(recipe1) == 2
    assert recipe1.iloc[0]['ingredient_id'] == 10
    assert recipe1.iloc[1]['ingredient_id'] == 100
    assert recipe1.iloc[0]['volume_fraction'] == 0.5
    assert recipe1.iloc[1]['volume_fraction'] == 0.5
```

**Step 2: Run test to verify it fails**

Run: `cd packages/barcart && pytest tests/test_rollup.py::TestApplyRollupToRecipes::test_basic_rollup_application -v`

Expected: FAIL (function returns None)

**Step 3: Implement apply_rollup_to_recipes**

Update `packages/barcart/barcart/rollup.py`:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `cd packages/barcart && pytest tests/test_rollup.py::TestApplyRollupToRecipes::test_basic_rollup_application -v`

Expected: PASS

**Step 5: Commit**

```bash
git add packages/barcart/barcart/rollup.py packages/barcart/tests/test_rollup.py
git commit -m "feat(barcart): implement apply_rollup_to_recipes"
```

---

## Task 5: Add Volume Aggregation Test

**Files:**
- Modify: `packages/barcart/tests/test_rollup.py`

**Step 1: Write test for volume aggregation**

Add to `TestApplyRollupToRecipes`:

```python
def test_rollup_aggregates_volumes(self):
    """Test that rollup aggregates volumes correctly when multiple ingredients map to same parent."""
    recipes = pd.DataFrame({
        'recipe_id': [1, 1, 1],
        'ingredient_id': [10, 20, 30],  # 20 and 30 both roll up to 100
        'volume_fraction': [0.5, 0.25, 0.25]
    })

    rollup_map = {20: 100, 30: 100}  # Both roll up to 100

    result = apply_rollup_to_recipes(recipes, rollup_map)

    # Should have 2 rows: ingredient 10 (0.5) and ingredient 100 (0.25+0.25=0.5)
    assert len(result) == 2

    ing_100 = result[result['ingredient_id'] == 100]
    assert len(ing_100) == 1
    assert ing_100['volume_fraction'].values[0] == 0.5

    ing_10 = result[result['ingredient_id'] == 10]
    assert len(ing_10) == 1
    assert ing_10['volume_fraction'].values[0] == 0.5
```

**Step 2: Run test to verify it passes**

Run: `cd packages/barcart && pytest tests/test_rollup.py::TestApplyRollupToRecipes::test_rollup_aggregates_volumes -v`

Expected: PASS (already implemented)

**Step 3: Write test for preserving unmapped ingredients**

Add to `TestApplyRollupToRecipes`:

```python
def test_unmapped_ingredients_preserved(self):
    """Ingredients not in rollup_map should pass through unchanged."""
    recipes = pd.DataFrame({
        'recipe_id': [1, 1],
        'ingredient_id': [10, 20],
        'volume_fraction': [0.6, 0.4]
    })

    rollup_map = {30: 100}  # Different ingredient

    result = apply_rollup_to_recipes(recipes, rollup_map)

    assert len(result) == 2
    assert set(result['ingredient_id']) == {10, 20}
    assert result['volume_fraction'].tolist() == [0.6, 0.4]
```

**Step 4: Run test to verify it passes**

Run: `cd packages/barcart && pytest tests/test_rollup.py::TestApplyRollupToRecipes::test_unmapped_ingredients_preserved -v`

Expected: PASS (already implemented)

**Step 5: Write test for multiple recipes**

Add to `TestApplyRollupToRecipes`:

```python
def test_multiple_recipes_handled_correctly(self):
    """Test that rollup works correctly across multiple recipes."""
    recipes = pd.DataFrame({
        'recipe_id': [1, 1, 2, 2],
        'ingredient_id': [10, 20, 20, 30],
        'volume_fraction': [0.5, 0.5, 0.7, 0.3]
    })

    rollup_map = {20: 100}  # Roll 20 -> 100

    result = apply_rollup_to_recipes(recipes, rollup_map)

    recipe1 = result[result['recipe_id'] == 1].sort_values('ingredient_id')
    assert len(recipe1) == 2
    assert recipe1['ingredient_id'].tolist() == [10, 100]

    recipe2 = result[result['recipe_id'] == 2].sort_values('ingredient_id')
    assert len(recipe2) == 2
    assert recipe2['ingredient_id'].tolist() == [30, 100]
```

**Step 6: Run test to verify it passes**

Run: `cd packages/barcart && pytest tests/test_rollup.py::TestApplyRollupToRecipes::test_multiple_recipes_handled_correctly -v`

Expected: PASS (already implemented)

**Step 7: Commit**

```bash
git add packages/barcart/tests/test_rollup.py
git commit -m "test(barcart): add comprehensive tests for apply_rollup_to_recipes"
```

---

## Task 6: Run Full Test Suite and Verify

**Files:**
- None (verification only)

**Step 1: Run all rollup tests**

Run: `cd packages/barcart && pytest tests/test_rollup.py -v`

Expected: All tests PASS

**Step 2: Run full barcart test suite**

Run: `cd packages/barcart && pytest tests/ -v`

Expected: All tests PASS (including existing tests)

**Step 3: Verify package installation**

Run: `cd packages/barcart && pip install -e .`

Expected: Successfully installed

**Step 4: Test imports in Python**

Run:
```bash
python -c "from barcart import create_rollup_mapping, apply_rollup_to_recipes; print('Import successful')"
```

Expected: "Import successful"

**Step 5: Commit if any changes needed**

If any fixes were needed, commit them:

```bash
git add .
git commit -m "fix(barcart): address test failures"
```

---

## Task 7: Add get_recipes_for_distance_calc Method

**Files:**
- Modify: `api/db/db_analytics.py`

**Step 1: Add method to AnalyticsQueries class**

Add to `api/db/db_analytics.py` after `get_ingredients_for_tree()`:

```python
def get_recipes_for_distance_calc(self) -> "pd.DataFrame":
    """Get recipe-ingredient data for distance calculations.

    Returns:
        DataFrame with columns: recipe_id, recipe_name, ingredient_id,
        ingredient_name, volume_fraction (normalized per recipe), ingredient_path
    """
    import pandas as pd

    try:
        # Query recipe ingredients with volume calculations
        sql = """
        SELECT
            r.id as recipe_id,
            r.name as recipe_name,
            i.id as ingredient_id,
            i.name as ingredient_name,
            i.path as ingredient_path,
            ri.amount,
            ri.unit_id,
            u.conversion_to_ml,
            CASE
                WHEN u.name = 'to top' THEN 90.0
                WHEN u.name = 'to rinse' THEN 5.0
                WHEN u.name = 'each' OR u.name = 'Each' THEN 1.0
                WHEN u.conversion_to_ml IS NOT NULL AND ri.amount IS NOT NULL
                    THEN u.conversion_to_ml * ri.amount
                WHEN ri.amount IS NOT NULL THEN ri.amount
                ELSE 1.0
            END as volume_ml
        FROM recipes r
        JOIN recipe_ingredients ri ON r.id = ri.recipe_id
        JOIN ingredients i ON ri.ingredient_id = i.id
        LEFT JOIN units u ON ri.unit_id = u.id
        ORDER BY r.id, i.id
        """

        rows = self.db.execute_query(sql)

        if not rows:
            logger.warning("No recipe data found for distance calculations")
            return pd.DataFrame()

        df = pd.DataFrame(rows)

        # Normalize volumes per recipe to sum to 1.0 (volume fractions)
        df['volume_fraction'] = df.groupby('recipe_id')['volume_ml'].transform(
            lambda x: x / x.sum()
        )

        # Drop the intermediate volume_ml and unit columns
        df = df.drop(columns=['amount', 'unit_id', 'conversion_to_ml', 'volume_ml'])

        logger.info(f"Retrieved {len(df)} recipe-ingredient pairs for {df['recipe_id'].nunique()} recipes")
        return df

    except Exception as e:
        logger.error(f"Error getting recipes for distance calc: {str(e)}")
        raise
```

**Step 2: Verify method compiles**

Run: `python -c "from api.db.db_analytics import AnalyticsQueries; print('Import successful')"`

Expected: "Import successful"

**Step 3: Commit**

```bash
git add api/db/db_analytics.py
git commit -m "feat(analytics): add get_recipes_for_distance_calc query method"
```

---

## Task 8: Add compute_cocktail_space_umap_em Method (Part 1: Setup)

**Files:**
- Modify: `api/db/db_analytics.py`

**Step 1: Add import statements at top of file**

Add after existing imports in `api/db/db_analytics.py`:

```python
from barcart import (
    build_ingredient_tree,
    build_ingredient_distance_matrix,
    build_recipe_volume_matrix,
    em_fit,
    compute_umap_embedding,
    Registry
)
from barcart.rollup import create_rollup_mapping, apply_rollup_to_recipes
```

**Step 2: Add method stub to AnalyticsQueries class**

Add after `compute_cocktail_space_umap()`:

```python
def compute_cocktail_space_umap_em(self) -> list:
    """Compute UMAP using EM-learned distances with ingredient rollup.

    Returns:
        List of dicts with {recipe_id, recipe_name, x, y, ingredients: [...]}
    """
    import numpy as np

    try:
        logger.info("Starting EM-based cocktail space computation with rollup")

        # Implementation will go here

        return []

    except Exception as e:
        logger.error(f"Error computing EM-based cocktail space: {str(e)}")
        raise
```

**Step 3: Verify method compiles**

Run: `python -c "from api.db.db_analytics import AnalyticsQueries; print('Import successful')"`

Expected: "Import successful"

**Step 4: Commit**

```bash
git add api/db/db_analytics.py
git commit -m "feat(analytics): add compute_cocktail_space_umap_em stub"
```

---

## Task 9: Implement compute_cocktail_space_umap_em (Part 2: Data Loading)

**Files:**
- Modify: `api/db/db_analytics.py`

**Step 1: Add data loading code**

Replace the comment `# Implementation will go here` in `compute_cocktail_space_umap_em()` with:

```python
        # Step 1: Load data
        logger.info("Loading ingredients and recipes data")
        ingredients_df = self.get_ingredients_for_tree()
        recipes_df = self.get_recipes_for_distance_calc()

        if ingredients_df.empty or recipes_df.empty:
            logger.warning("Empty data, returning empty UMAP")
            return []

        logger.info(f"Loaded {len(ingredients_df)} ingredients and {len(recipes_df)} recipe-ingredient pairs")
```

**Step 2: Verify code compiles**

Run: `python -c "from api.db.db_analytics import AnalyticsQueries; print('Import successful')"`

Expected: "Import successful"

**Step 3: Commit**

```bash
git add api/db/db_analytics.py
git commit -m "feat(analytics): add data loading to EM cocktail space"
```

---

## Task 10: Implement compute_cocktail_space_umap_em (Part 3: Tree Building and Rollup)

**Files:**
- Modify: `api/db/db_analytics.py`

**Step 1: Add tree building and rollup code**

Add after the data loading code in `compute_cocktail_space_umap_em()`:

```python
        # Step 2: Build ingredient tree
        logger.info("Building ingredient tree")
        tree_dict, parent_map = build_ingredient_tree(
            ingredients_df,
            id_col='ingredient_id',
            name_col='ingredient_name',
            path_col='ingredient_path',
            weight_col='substitution_level',
            root_id='root',
            root_name='All Ingredients',
            default_edge_weight=1.0
        )

        # Step 3: Create rollup mapping and apply to recipes
        logger.info("Creating rollup mapping")
        # Add allow_substitution column (1 for all - will be filtered by create_rollup_mapping)
        # In practice, this should come from DB, but for now we assume all leaves are substitutable
        ingredients_df['allow_substitution'] = 1
        ingredients_df = ingredients_df.rename(columns={'ingredient_id': 'id'})

        rollup_map = create_rollup_mapping(ingredients_df, parent_map, allow_substitution_col='allow_substitution')
        logger.info(f"Created rollup mapping with {len(rollup_map)} substitutable leaves")

        logger.info("Applying rollup to recipes")
        recipes_rolled_df = apply_rollup_to_recipes(
            recipes_df,
            rollup_map,
            ingredient_id_col='ingredient_id',
            volume_col='volume_fraction'
        )
        logger.info(f"Recipes rolled up: {len(recipes_df)} -> {len(recipes_rolled_df)} rows")
```

**Step 2: Verify code compiles**

Run: `python -c "from api.db.db_analytics import AnalyticsQueries; print('Import successful')"`

Expected: "Import successful"

**Step 3: Commit**

```bash
git add api/db/db_analytics.py
git commit -m "feat(analytics): add tree building and rollup to EM cocktail space"
```

---

## Task 11: Implement compute_cocktail_space_umap_em (Part 4: Matrix Building)

**Files:**
- Modify: `api/db/db_analytics.py`

**Step 1: Add matrix building code**

Add after the rollup code in `compute_cocktail_space_umap_em()`:

```python
        # Step 4: Build ingredient distance matrix
        logger.info("Building ingredient distance matrix")
        id_to_name = dict(zip(
            ingredients_df['id'].astype(str),
            ingredients_df['ingredient_name']
        ))
        cost_matrix, ingredient_registry = build_ingredient_distance_matrix(
            parent_map, id_to_name
        )
        logger.info(f"Cost matrix shape: {cost_matrix.shape}")

        # Step 5: Build recipe volume matrix with rolled-up ingredients
        logger.info("Building recipe volume matrix")
        volume_matrix, recipe_registry = build_recipe_volume_matrix(
            recipes_rolled_df,
            ingredient_registry,
            recipe_id_col='recipe_id',
            ingredient_id_col='ingredient_id',
            volume_col='volume_fraction'
        )
        logger.info(f"Volume matrix shape: {volume_matrix.shape}")
```

**Step 2: Verify code compiles**

Run: `python -c "from api.db.db_analytics import AnalyticsQueries; print('Import successful')"`

Expected: "Import successful"

**Step 3: Commit**

```bash
git add api/db/db_analytics.py
git commit -m "feat(analytics): add matrix building to EM cocktail space"
```

---

## Task 12: Implement compute_cocktail_space_umap_em (Part 5: EM Fit and UMAP)

**Files:**
- Modify: `api/db/db_analytics.py`

**Step 1: Add EM fit and UMAP code**

Add after the matrix building code in `compute_cocktail_space_umap_em()`:

```python
        # Step 6: Run EM fit
        logger.info("Running EM fit (this may take several minutes)")
        final_dist, final_cost, log = em_fit(
            volume_matrix,
            cost_matrix,
            len(ingredient_registry),
            iters=5
        )
        logger.info(f"EM fit complete. Max distance: {np.max(final_dist):.4f}")

        # Step 7: Compute UMAP embedding
        logger.info("Computing UMAP embedding")
        embedding = compute_umap_embedding(
            final_dist,
            n_neighbors=5,
            min_dist=0.05,
            random_state=42
        )
        logger.info(f"UMAP embedding shape: {embedding.shape}")
```

**Step 2: Verify code compiles**

Run: `python -c "from api.db.db_analytics import AnalyticsQueries; print('Import successful')"`

Expected: "Import successful"

**Step 3: Commit**

```bash
git add api/db/db_analytics.py
git commit -m "feat(analytics): add EM fit and UMAP to EM cocktail space"
```

---

## Task 13: Implement compute_cocktail_space_umap_em (Part 6: Format Results)

**Files:**
- Modify: `api/db/db_analytics.py`

**Step 1: Add result formatting code**

Add after the UMAP code in `compute_cocktail_space_umap_em()`:

```python
        # Step 8: Build result list with UMAP coordinates
        logger.info("Formatting results with ingredient lists")
        result = []
        recipe_ids = []

        for idx in range(len(embedding)):
            recipe_id = recipe_registry.get_id(index=idx)
            recipe_name = recipe_registry.get_name(index=idx)
            recipe_ids.append(int(recipe_id))

            result.append({
                'recipe_id': int(recipe_id),
                'recipe_name': recipe_name,
                'x': float(embedding[idx, 0]),
                'y': float(embedding[idx, 1]),
                'ingredients': []  # Will populate below
            })

        # Step 9: Query ingredients for all recipes in one go
        if recipe_ids:
            placeholders = ','.join(['?'] * len(recipe_ids))
            ingredient_query = f"""
                SELECT
                    ri.recipe_id,
                    i.name as ingredient_name,
                    CASE
                        WHEN u.name = 'to top' THEN 90.0
                        WHEN u.name = 'to rinse' THEN 5.0
                        WHEN u.name = 'each' OR u.name = 'Each' THEN -1.0
                        WHEN u.conversion_to_ml IS NOT NULL AND ri.amount IS NOT NULL
                            THEN u.conversion_to_ml * ri.amount
                        WHEN ri.amount IS NOT NULL THEN ri.amount
                        ELSE 0.0
                    END as volume_ml
                FROM recipe_ingredients ri
                JOIN ingredients i ON ri.ingredient_id = i.id
                LEFT JOIN units u ON ri.unit_id = u.id
                WHERE ri.recipe_id IN ({placeholders})
                ORDER BY ri.recipe_id
            """

            ingredient_rows = self.db.execute_query(ingredient_query, tuple(recipe_ids))

            # Group ingredients by recipe and sort by volume
            recipe_ingredients = {}
            for row in ingredient_rows:
                recipe_id = row['recipe_id']
                if recipe_id not in recipe_ingredients:
                    recipe_ingredients[recipe_id] = []

                recipe_ingredients[recipe_id].append({
                    'name': row['ingredient_name'],
                    'amount_ml': row['volume_ml']
                })

            # Sort ingredients by volume and add to results
            for item in result:
                recipe_id = item['recipe_id']
                if recipe_id in recipe_ingredients:
                    sorted_ings = sorted(
                        recipe_ingredients[recipe_id],
                        key=lambda x: x['amount_ml'],
                        reverse=True
                    )
                    item['ingredients'] = [ing['name'] for ing in sorted_ings]

        logger.info(f"EM-based UMAP computation complete: {len(result)} recipes")
        return result
```

**Step 2: Verify code compiles**

Run: `python -c "from api.db.db_analytics import AnalyticsQueries; print('Import successful')"`

Expected: "Import successful"

**Step 3: Commit**

```bash
git add api/db/db_analytics.py
git commit -m "feat(analytics): complete EM cocktail space with result formatting"
```

---

## Task 14: Update analytics_refresh Lambda to Generate Both Spaces

**Files:**
- Modify: `api/analytics/analytics_refresh.py`

**Step 1: Update cocktail space generation**

Find the line:
```python
cocktail_space = analytics_queries.compute_cocktail_space_umap()
```

Replace with:
```python
# Generate both cocktail space variants for comparison
logger.info("Generating Manhattan-based cocktail space")
cocktail_space_manhattan = analytics_queries.compute_cocktail_space_umap()

logger.info("Generating EM-based cocktail space with rollup")
cocktail_space_em = analytics_queries.compute_cocktail_space_umap_em()
```

**Step 2: Update storage calls**

Find the line:
```python
storage.put_analytics('cocktail-space', cocktail_space)
```

Replace with:
```python
storage.put_analytics('cocktail-space', cocktail_space_manhattan)
storage.put_analytics('cocktail-space-em', cocktail_space_em)
```

**Step 3: Update response body**

Find the return statement in `lambda_handler()` and update the body to include:

```python
"cocktail_space_count": len(cocktail_space_manhattan),
"cocktail_space_em_count": len(cocktail_space_em),
```

(Replace the existing `"cocktail_space_count": len(cocktail_space)` line)

**Step 4: Verify code compiles**

Run: `python -c "import api.analytics.analytics_refresh; print('Import successful')"`

Expected: "Import successful"

**Step 5: Commit**

```bash
git add api/analytics/analytics_refresh.py
git commit -m "feat(analytics): generate both Manhattan and EM cocktail spaces"
```

---

## Task 15: Update Lambda Configuration

**Files:**
- Modify: `template.yaml`

**Step 1: Update AnalyticsRefreshFunction timeout**

Find `AnalyticsRefreshFunction` in `template.yaml` and update the `Timeout` property:

```yaml
AnalyticsRefreshFunction:
  Type: AWS::Serverless::Function
  Properties:
    # ... existing properties ...
    Timeout: 600  # 10 minutes (up from 180)
```

**Step 2: Update AnalyticsRefreshFunction memory**

Add or update the `MemorySize` property in `AnalyticsRefreshFunction`:

```yaml
AnalyticsRefreshFunction:
  Type: AWS::Serverless::Function
  Properties:
    # ... existing properties ...
    MemorySize: 2048  # 2GB (up from default 512)
    Timeout: 600
```

**Step 3: Validate template**

Run: `sam validate --template-file template.yaml`

Expected: "template.yaml is a valid SAM Template"

**Step 4: Commit**

```bash
git add template.yaml
git commit -m "feat(infra): increase analytics Lambda timeout to 10min and memory to 2GB"
```

---

## Task 16: Add allow_substitution Column to Database Query

**Files:**
- Modify: `api/db/db_analytics.py`

**Step 1: Update get_ingredients_for_tree query**

In `get_ingredients_for_tree()` method, find the comment that calls `get_ingredient_usage_stats()` and note that we need to add `allow_substitution` to the query.

Update `get_ingredient_usage_stats()` SQL to include `allow_substitution`:

Find this line in `get_ingredient_usage_stats()`:
```python
            SELECT
              i.id as ingredient_id,
              i.name as ingredient_name,
              i.path,
              i.parent_id,
```

Add `i.allow_substitution` to the SELECT:
```python
            SELECT
              i.id as ingredient_id,
              i.name as ingredient_name,
              i.path,
              i.parent_id,
              i.allow_substitution,
```

**Step 2: Update compute_cocktail_space_umap_em to use real allow_substitution**

In `compute_cocktail_space_umap_em()`, find these lines:
```python
        # Add allow_substitution column (1 for all - will be filtered by create_rollup_mapping)
        # In practice, this should come from DB, but for now we assume all leaves are substitutable
        ingredients_df['allow_substitution'] = 1
```

Replace with:
```python
        # allow_substitution column now comes from DB query
        # No need to add it - it's already in ingredients_df from get_ingredients_for_tree()
```

**Step 3: Verify code compiles**

Run: `python -c "from api.db.db_analytics import AnalyticsQueries; print('Import successful')"`

Expected: "Import successful"

**Step 4: Commit**

```bash
git add api/db/db_analytics.py
git commit -m "feat(analytics): use real allow_substitution from database"
```

---

## Task 17: Local Testing and Validation

**Files:**
- None (testing only)

**Step 1: Install barcart package locally**

Run: `cd packages/barcart && pip install -e .`

Expected: Successfully installed

**Step 2: Run barcart tests**

Run: `cd packages/barcart && pytest tests/test_rollup.py -v`

Expected: All tests PASS

**Step 3: Test analytics query imports**

Run:
```bash
python -c "from api.db.db_analytics import AnalyticsQueries; from barcart.rollup import create_rollup_mapping, apply_rollup_to_recipes; print('All imports successful')"
```

Expected: "All imports successful"

**Step 4: Validate SAM template**

Run: `sam validate --template-file template.yaml`

Expected: Valid template

**Step 5: Build SAM application**

Run: `sam build --template-file template.yaml`

Expected: Build successful

**Step 6: Commit if any fixes needed**

If any issues found and fixed:
```bash
git add .
git commit -m "fix: address testing issues"
```

---

## Task 18: Create Pull Request

**Files:**
- None (git operations only)

**Step 1: Push branch to remote**

Run: `git push -u origin feature/ingredient-rollup`

Expected: Branch pushed successfully

**Step 2: Create pull request**

Run:
```bash
gh pr create --title "Add ingredient rollup and EM-based cocktail space" --body "$(cat <<'EOF'
## Summary
- Add `create_rollup_mapping()` and `apply_rollup_to_recipes()` to barcart package
- Implement EM-based cocktail space calculation with ingredient rollup
- Generate both Manhattan and EM cocktail spaces for comparison
- Increase analytics Lambda timeout to 10min and memory to 2GB

## Changes
### Barcart Package
- New module: `barcart/rollup.py` with rollup functions
- Comprehensive test coverage in `tests/test_rollup.py`

### Analytics Pipeline
- New method: `get_recipes_for_distance_calc()` for loading recipe data
- New method: `compute_cocktail_space_umap_em()` for EM-based distances
- Updated `analytics_refresh.py` to generate both cocktail spaces
- Store both `cocktail-space` (Manhattan) and `cocktail-space-em` (EM) in S3

### Infrastructure
- Lambda timeout: 180s → 600s (10 minutes)
- Lambda memory: 512MB → 2048MB (2GB)

## Testing
- ✅ All barcart unit tests passing
- ✅ SAM template validates
- ✅ SAM build successful
- 🔲 Ready for dev deployment and validation

## Deployment Plan
1. Deploy to dev environment
2. Trigger analytics refresh
3. Verify both cocktail spaces in S3
4. Compare results
5. Deploy to prod if successful

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR created with URL

**Step 3: Record PR URL**

Output the PR URL for reference.

---

## Summary

This plan implements ingredient rollup functionality in the barcart package and integrates it into the analytics pipeline to generate an EM-based cocktail space alongside the existing Manhattan distance approach.

**Key Deliverables:**
1. ✅ `barcart/rollup.py` with `create_rollup_mapping()` and `apply_rollup_to_recipes()`
2. ✅ Comprehensive unit tests for rollup functions
3. ✅ `compute_cocktail_space_umap_em()` method using EM-learned distances
4. ✅ Both cocktail spaces generated and stored in S3
5. ✅ Lambda timeout and memory increased for EM computation

**Post-Implementation:**
- Deploy to dev: `sam build && sam deploy --config-env dev`
- Trigger refresh: `./scripts/trigger-analytics-refresh.sh dev`
- Monitor CloudWatch logs
- Verify S3 files: `cocktail-space` and `cocktail-space-em`
- Compare results between the two approaches
