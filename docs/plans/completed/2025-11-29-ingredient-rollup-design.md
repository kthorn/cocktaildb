# Ingredient Rollup & EM-Based Cocktail Space Design

**Date:** 2025-11-29
**Status:** Approved

## Overview

Add ingredient rollup functionality to the barcart package and implement an EM-based cocktail space calculation alongside the existing Manhattan distance approach. This enables comparison of distance metrics and reduces dimensionality by rolling up substitutable brand ingredients to their parent categories.

## Goals

1. Add reusable rollup functions to the barcart package
2. Generate both Manhattan-based and EM-based cocktail spaces for comparison
3. Reduce ingredient dimensionality by rolling up substitutable leaf ingredients to parents
4. Maintain data-agnostic design in barcart while integrating with analytics pipeline

## Architecture

### 1. Data Layer: Rollup Functions

**New module:** `packages/barcart/barcart/rollup.py`

#### Function 1: `create_rollup_mapping`

```python
def create_rollup_mapping(
    ingredients: pd.DataFrame,
    parent_map: dict,
    allow_substitution_col: str = "allow_substitution"
) -> dict[int, int]:
    """Map substitutable leaf ingredients to their parents.

    Args:
        ingredients: DataFrame with columns [id, allow_substitution]
        parent_map: Dict from build_ingredient_tree mapping child_id -> (parent_id, cost)
        allow_substitution_col: Column name for substitution flag

    Returns:
        Dict mapping leaf_ingredient_id -> parent_ingredient_id
    """
```

**Logic:**
- Identify ingredients where `allow_substitution = 1` (substitutable brands)
- Filter to leaf nodes only (not parents of other ingredients)
- Map each leaf to its parent from `parent_map`
- Skip orphans, root nodes, and invalid mappings

#### Function 2: `apply_rollup_to_recipes`

```python
def apply_rollup_to_recipes(
    recipes: pd.DataFrame,
    rollup_map: dict[int, int],
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
```

**Logic:**
1. Map ingredient IDs using `rollup_map.get(id, id)` (unmapped IDs pass through)
2. Group by `(recipe_id, ingredient_id)`
3. Sum volumes for duplicate ingredients
4. Keep first value for non-numeric columns (recipe_name, etc.)

**Key Design Decisions:**
- Works with DataFrames (matches SQL query outputs)
- Column names are configurable
- Returns new DataFrames (immutable)
- Lives in barcart package (reusable, testable)

### 2. Analytics Pipeline Integration

**Changes to `api/db/db_analytics.py`:**

#### New Method: `get_recipes_for_distance_calc`

```python
def get_recipes_for_distance_calc(self) -> "pd.DataFrame":
    """Get recipe-ingredient data for distance calculations.

    Returns:
        DataFrame with columns: recipe_id, recipe_name, ingredient_id,
        ingredient_name, volume_fraction (normalized per recipe)
    """
```

**Implementation:**
- Query `recipe_ingredients` with volume conversions (similar to existing queries)
- Normalize volumes per recipe to sum to 1.0
- Return as DataFrame ready for barcart functions

#### New Method: `compute_cocktail_space_umap_em`

```python
def compute_cocktail_space_umap_em(self) -> dict:
    """Compute UMAP using EM-learned distances with ingredient rollup.

    Returns:
        Same format as compute_cocktail_space_umap(): list of dicts with
        {recipe_id, recipe_name, x, y, ingredients: [...]}
    """
```

**Pipeline:**
1. Load data: `get_ingredients_for_tree()` and `get_recipes_for_distance_calc()`
2. Build ingredient tree: `build_ingredient_tree()` → `tree, parent_map`
3. Apply rollup: `create_rollup_mapping()` → `rollup_map`
4. Roll up recipes: `apply_rollup_to_recipes()` → `recipes_rolled`
5. Build matrices: `build_ingredient_distance_matrix()`, `build_recipe_volume_matrix()`
6. EM fit: `em_fit()` → `final_dist, final_cost`
7. UMAP: `compute_umap_embedding()` → `embedding`
8. Format results with ingredient lists (same as existing method)

**Changes to `api/analytics/analytics_refresh.py`:**

```python
# Generate both cocktail space variants
logger.info("Generating Manhattan-based cocktail space")
cocktail_space_manhattan = analytics_queries.compute_cocktail_space_umap()

logger.info("Generating EM-based cocktail space with rollup")
cocktail_space_em = analytics_queries.compute_cocktail_space_umap_em()

# Store both in S3
storage.put_analytics('cocktail-space', cocktail_space_manhattan)
storage.put_analytics('cocktail-space-em', cocktail_space_em)
```

### 3. Infrastructure Changes

**Update `template.yaml`:**

```yaml
AnalyticsRefreshFunction:
  Type: AWS::Serverless::Function
  Properties:
    Timeout: 600        # 10 minutes (up from 180)
    MemorySize: 2048    # 2GB (up from 512)
```

**Rationale:**
- EM fitting is computationally intensive (observed 3-4 minutes in notebook)
- Matrix operations require more memory
- Need buffer for UMAP and data loading

## Implementation Details

### Edge Cases

**1. Rollup Mapping:**
- Ingredients with no parent → skip in rollup_map
- Root-level ingredients → never rolled up
- `allow_substitution = 0` → never rolled up
- Multiple hierarchy levels → only map leaf-to-parent (not leaf-to-grandparent)

**2. Recipe Aggregation:**
- Multiple ingredients mapping to same parent → sum volumes
- Validate recipe volumes sum to ~1.0 after aggregation
- Preserve metadata using `first()` aggregation

**3. Type Handling:**
- `parent_map` keys are strings (e.g., `'123'`)
- Ingredient IDs in DataFrame are integers
- Convert types when looking up: `str(leaf_id)` → `int(parent_id)`
- Skip special values: `'root'`, `None`

### Data Validation

```python
# In create_rollup_mapping:
assert "id" in ingredients.columns
assert allow_substitution_col in ingredients.columns
logger.info(f"Rollup mapping created: {len(rollup_map)} substitutable leaves")

# In apply_rollup_to_recipes:
assert ingredient_id_col in recipes.columns
assert volume_col in recipes.columns
logger.info(f"Recipes reduced from {len(recipes)} to {len(recipes_rolled)} rows")
```

## Testing Strategy

### Unit Tests: `packages/barcart/tests/test_rollup.py`

**Test Cases:**
1. `test_create_rollup_mapping_basic` - Basic leaf-to-parent mapping
2. `test_create_rollup_mapping_non_substitutable` - Non-substitutable ingredients excluded
3. `test_create_rollup_mapping_no_parent` - Ingredients without parents skipped
4. `test_apply_rollup_aggregates_volumes` - Volume aggregation correctness
5. `test_apply_rollup_preserves_unmapped` - Unmapped ingredients pass through
6. `test_apply_rollup_multiple_recipes` - Multiple recipes handled correctly

### Integration Test

```python
def test_rollup_integration_with_barcart_pipeline():
    """Test rollup integrates correctly with build_recipe_volume_matrix"""
    # Load test data
    ingredients = load_test_ingredients()
    recipes = load_test_recipes()

    # Apply rollup
    tree, parent_map = build_ingredient_tree(ingredients, ...)
    rollup_map = create_rollup_mapping(ingredients, parent_map)
    recipes_rolled = apply_rollup_to_recipes(recipes, rollup_map)

    # Build matrices
    volume_matrix, recipe_registry = build_recipe_volume_matrix(recipes_rolled, ...)

    # Verify dimensions reduced
    unique_before = recipes['ingredient_id'].nunique()
    unique_after = recipes_rolled['ingredient_id'].nunique()
    assert unique_after < unique_before
```

### Manual Verification

After deployment to dev:
1. Trigger analytics refresh: `./scripts/trigger-analytics-refresh.sh dev`
2. Verify both `cocktail-space` and `cocktail-space-em` exist in S3
3. Check both have same number of recipes
4. Spot-check similar cocktails are near each other in both spaces
5. Expect differences (that's the point of comparison)

## Implementation Order

### Phase 1: Barcart Package (Isolated)

1. Create `packages/barcart/barcart/rollup.py`
2. Implement `create_rollup_mapping()` and `apply_rollup_to_recipes()`
3. Write unit tests in `packages/barcart/tests/test_rollup.py`
4. Test locally with notebook data
5. Update `packages/barcart/barcart/__init__.py` to export functions
6. Run tests: `pytest packages/barcart/tests/`

### Phase 2: Analytics Queries

1. Add `get_recipes_for_distance_calc()` to `api/db/db_analytics.py`
2. Add `compute_cocktail_space_umap_em()` to `api/db/db_analytics.py`
3. Test locally if possible (may need test database)

### Phase 3: Lambda Function

1. Update `api/analytics/analytics_refresh.py` to generate both spaces
2. Update `template.yaml`:
   - Timeout: 600
   - MemorySize: 2048
3. Deploy to dev: `sam build && sam deploy --config-env dev`

### Phase 4: Validation

1. Trigger refresh: `./scripts/trigger-analytics-refresh.sh dev`
2. Monitor CloudWatch logs for errors
3. Check S3 for both analytics files
4. Download and compare results
5. If successful, deploy to prod

## Benefits

✅ **Reusable:** Rollup logic in barcart package, usable in notebooks and production
✅ **Comparable:** Both distance metrics available for analysis
✅ **Non-breaking:** Additive changes, existing cocktail-space unchanged
✅ **Testable:** Unit and integration tests before deployment
✅ **Maintainable:** Clear separation of concerns (data, analytics, infrastructure)
✅ **Dimensional reduction:** 608 ingredients → ~350 ingredients (43% reduction observed in notebook)

## Open Questions

None - design approved.

## References

- Original notebook: `/home/kurtt/cocktail-research/notebooks/cocktailspace/test_learner.ipynb`
- Barcart package: `/home/kurtt/cocktaildb/packages/barcart/`
- Analytics code: `/home/kurtt/cocktaildb/api/analytics/analytics_refresh.py`
