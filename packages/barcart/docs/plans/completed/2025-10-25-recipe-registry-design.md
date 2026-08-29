# Recipe Registry and Generic Registry Refactoring

**Date:** 2025-10-25
**Status:** Approved for implementation

## Problem Statement

The codebase currently has an `IngredientRegistry` class that provides a clean, centralized way to manage ingredient metadata (matrix indices, IDs, names). However:

1. **No equivalent for recipes**: Recipe metadata is managed via raw dicts (`recipe_id_to_index`), inconsistent with ingredient pattern
2. **Asymmetric APIs**: Ingredients use Registry, recipes use dict - forces users to remember two different patterns
3. **Code duplication**: `report_ingredient_neighbors` exists but no recipe equivalent, yet the logic would be identical
4. **Missed opportunity**: The registry pattern is inherently generic but implemented as ingredient-specific

## Solution: Generic Registry + Recipe Support

Refactor to a fully generic `Registry` class that works for any entity type (ingredients, recipes, etc.), then use it consistently throughout the codebase.

### Core Design Principles

- **Single generic implementation**: One `Registry` class for all entity types
- **Symmetric APIs**: Ingredients and recipes use identical patterns
- **Maximize code reuse**: Generic functions (like `report_neighbors`) work for any entity type
- **Minimal breaking changes**: Since code is new, acceptable to rename for clarity
- **Column naming**: Use generic, minimal column names (`id`, `name` vs `ingredient_id`, `recipe_id`)

## Architecture

### Component 1: Rename IngredientRegistry → Registry

**Change:**
```python
# Before
class IngredientRegistry:
    """Central registry mapping matrix indices ↔ ingredient IDs ↔ names."""

# After
class Registry:
    """Central registry mapping matrix indices ↔ entity IDs ↔ names.

    Generic registry for any entity type (ingredients, recipes, etc.).
    """
```

**Rationale:**
- Code is new (no external users to break)
- `IngredientRegistry` name implies specialization that doesn't exist
- Makes generic nature explicit

**Implementation:**
- Rename class in `barcart/registry.py`
- Update all docstrings to reflect generic usage
- Internal implementation unchanged (already generic)

### Component 2: Update build_recipe_volume_matrix

**Current signature:**
```python
def build_recipe_volume_matrix(
    recipes_df: pd.DataFrame,
    registry: "IngredientRegistry",  # ingredient registry
    recipe_id_col: str = "recipe_id",
    ingredient_id_col: str = "ingredient_id",
    volume_col: str = "volume_fraction",
    volume_error_tolerance: float = 1e-6,
) -> tuple[np.ndarray, dict[str, int]]:  # returns dict
```

**Updated signature:**
```python
def build_recipe_volume_matrix(
    recipes_df: pd.DataFrame,
    ingredient_registry: Registry,  # renamed for clarity
    recipe_id_col: str = "recipe_id",
    recipe_name_col: str = "recipe_name",  # NEW PARAMETER
    ingredient_id_col: str = "ingredient_id",
    volume_col: str = "volume_fraction",
    volume_error_tolerance: float = 1e-6,
) -> tuple[np.ndarray, Registry]:  # now returns Registry
```

**Changes:**
1. Add `recipe_name_col` parameter (default `"recipe_name"`)
2. Construct recipe Registry from unique recipes in DataFrame
3. Return `(volume_matrix, recipe_registry)` instead of `(volume_matrix, recipe_id_to_index)`

**Construction logic:**
```python
# Extract unique recipe IDs (sorted for deterministic ordering)
recipe_ids = sorted(recipes_df[recipe_id_col].unique())
recipe_id_to_index = {str(rid): i for i, rid in enumerate(recipe_ids)}

# Extract recipe names (take first occurrence per recipe ID)
recipe_names = {}
for _, row in recipes_df[[recipe_id_col, recipe_name_col]].iterrows():
    rid = str(row[recipe_id_col])
    if rid not in recipe_names:
        recipe_names[rid] = str(row[recipe_name_col])

# Build registry
recipes = [
    (idx, rid, recipe_names.get(rid, f"Recipe {rid}"))
    for rid, idx in recipe_id_to_index.items()
]
recipe_registry = Registry(recipes)

# Build volume matrix (logic unchanged)
volume_matrix = np.zeros((len(recipe_ids), len(ingredient_registry)))
# ... populate matrix ...

return volume_matrix, recipe_registry
```

**Benefits:**
- Mirrors `build_ingredient_distance_matrix` pattern (returns matrix + registry atomically)
- Recipes and ingredients now have symmetric APIs
- Registry and matrix guaranteed to stay in sync

### Component 3: Generic report_neighbors Function

**New function (replaces report_ingredient_neighbors):**

```python
def report_neighbors(
    distance_matrix: np.ndarray,
    registry: Registry,
    k: int,
) -> pd.DataFrame:
    """
    Report k nearest neighbors for each entity in the registry.

    Works for any entity type (ingredients, recipes, etc.) - the registry
    determines what entities are being compared.

    Parameters
    ----------
    distance_matrix : np.ndarray
        Pairwise distance matrix (n, n) where n = len(registry).
        For ingredients: typically tree-based cost matrix.
        For recipes: typically EMD-based distance matrix.
    registry : Registry
        Entity metadata registry with IDs and names.
    k : int
        Number of neighbors to report per entity (excluding self).

    Returns
    -------
    pd.DataFrame
        Columns: id, name, neighbor_id, neighbor_name, distance

        - id, name: The entity whose neighbors are being reported
        - neighbor_id, neighbor_name: The neighbor entity
        - distance: Distance value from the input matrix

    Examples
    --------
    >>> # Ingredient neighbors
    >>> ingredient_neighbors = report_neighbors(cost_matrix, ingredient_registry, k=5)

    >>> # Recipe neighbors
    >>> recipe_neighbors = report_neighbors(emd_matrix, recipe_registry, k=10)
    """
    registry.validate_matrix(distance_matrix)
    nn_idx, nn_dist = knn_matrix(distance_matrix, k)

    records = []
    for idx in range(len(registry)):
        entity_id = registry.get_id(index=idx)
        entity_name = registry.get_name(index=idx)

        for neighbor_idx, dist in zip(nn_idx[idx], nn_dist[idx], strict=False):
            n_idx = int(neighbor_idx)
            neighbor_id = registry.get_id(index=n_idx)
            neighbor_name = registry.get_name(index=n_idx)

            records.append({
                "id": entity_id,
                "name": entity_name,
                "neighbor_id": neighbor_id,
                "neighbor_name": neighbor_name,
                "distance": float(dist),
            })

    return pd.DataFrame.from_records(records)
```

**Changes from report_ingredient_neighbors:**
- Rename function: `report_ingredient_neighbors` → `report_neighbors`
- Column names: `ingredient_id/ingredient_name` → `id/name`
- Column name: `cost` → `distance` (more generic)
- Docstring updated to reflect generic usage

**Code reuse:**
- Same implementation works for ingredients AND recipes
- Zero duplication
- Users choose entity type by passing appropriate registry + distance matrix

### Component 4: Usage Patterns

**Before (asymmetric):**
```python
# Ingredients: use Registry
cost_matrix, ingredient_registry = build_ingredient_distance_matrix(parent_map, id_to_name)
ingredient_neighbors = report_ingredient_neighbors(cost_matrix, ingredient_registry, k=5)
# → ingredient_id, ingredient_name, neighbor_id, neighbor_name, cost

# Recipes: use dict
volume_matrix, recipe_id_to_index = build_recipe_volume_matrix(recipes_df, ingredient_registry)
# Manual neighbor logic, no standard function
```

**After (symmetric):**
```python
# Ingredients: use Registry
cost_matrix, ingredient_registry = build_ingredient_distance_matrix(parent_map, id_to_name)
ingredient_neighbors = report_neighbors(cost_matrix, ingredient_registry, k=5)
# → id, name, neighbor_id, neighbor_name, distance

# Recipes: use Registry (same pattern!)
volume_matrix, recipe_registry = build_recipe_volume_matrix(
    recipes_df,
    ingredient_registry,
    recipe_name_col="recipe_name"
)
emd_dist = emd_matrix(volume_matrix, cost_matrix)
recipe_neighbors = report_neighbors(emd_dist, recipe_registry, k=10)
# → id, name, neighbor_id, neighbor_name, distance
```

**Benefits:**
- Consistent API for all entity types
- Same function for all neighbor reports
- Registry + matrix returned together (always in sync)

## Implementation Plan

### Phase 1: Rename to Generic Registry
1. Rename `IngredientRegistry` → `Registry` in `barcart/registry.py`
2. Update docstrings to reflect generic usage
3. Update all imports and type hints across codebase:
   - `barcart/distance.py`
   - `tests/test_registry.py`
   - `tests/test_registry_integration.py`
   - `tests/test_distance.py`
4. Run tests to verify no breakage

### Phase 2: Update build_recipe_volume_matrix
1. Add `recipe_name_col` parameter with default `"recipe_name"`
2. Implement recipe Registry construction logic
3. Update return type from `dict[str, int]` to `Registry`
4. Update function docstring and examples
5. Add unit tests for recipe registry construction
6. Update integration tests

### Phase 3: Create Generic report_neighbors
1. Rename `report_ingredient_neighbors` → `report_neighbors`
2. Update column names in output DataFrame:
   - `ingredient_id` → `id`
   - `ingredient_name` → `name`
   - `cost` → `distance`
3. Update docstring to reflect generic usage with examples
4. Update all call sites in tests
5. Add tests for recipe neighbor reporting

### Phase 4: Documentation Updates
1. Update `docs/plans/2025-10-24-ingredient-registry-design.md`
   - Add note about rename to generic `Registry`
   - Reference this design doc for recipe extension
2. Update README if it references the old names
3. Update any example notebooks or scripts

## Files Modified

1. **barcart/registry.py**
   - Rename class `IngredientRegistry` → `Registry`
   - Update docstrings

2. **barcart/distance.py**
   - Update imports: `IngredientRegistry` → `Registry`
   - Update `build_ingredient_distance_matrix` return type hint
   - Update `build_recipe_volume_matrix`:
     - Add `recipe_name_col` parameter
     - Build recipe Registry
     - Change return type
   - Rename `report_ingredient_neighbors` → `report_neighbors`
   - Update column names in `report_neighbors`

3. **tests/test_registry.py**
   - Rename test class
   - Update all `IngredientRegistry` → `Registry`

4. **tests/test_registry_integration.py**
   - Update imports

5. **tests/test_distance.py**
   - Update imports
   - Update function names
   - Update column name assertions

6. **docs/plans/2025-10-24-ingredient-registry-design.md**
   - Add note about rename to `Registry`

## Benefits Summary

1. **Consistency**: Same patterns for all entity types (ingredients, recipes, etc.)
2. **Code reuse**: One `report_neighbors` function instead of duplicates per entity type
3. **Cleaner API**: Generic column names (`id`, `name`) work everywhere
4. **Maintainability**: Changes to registry logic only needed in one place
5. **Extensibility**: Easy to add new entity types (cocktail categories, bars, etc.) using same pattern
6. **Simplicity**: Users learn one pattern that works for everything

## Breaking Changes

Since the code is new (no external users), these breaking changes are acceptable:

1. `IngredientRegistry` → `Registry` (class name)
2. `report_ingredient_neighbors` → `report_neighbors` (function name)
3. `build_recipe_volume_matrix` return type changes from `dict` to `Registry`
4. Column names in neighbor reports change to generic names

All changes improve consistency and reduce future maintenance burden.

## Future Enhancements

- Additional entity types (user-defined categories, bars, glassware, etc.)
- Generic distance matrix computation functions
- Registry serialization/deserialization
- Multi-registry operations (joins, merges)

## Open Questions

None - design approved for implementation.
