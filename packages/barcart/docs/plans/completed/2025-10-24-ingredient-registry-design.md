# Ingredient Registry Design

**Date:** 2025-10-24
**Status:** Implemented and refactored to generic `Registry` class

**Note:** This design was implemented as `IngredientRegistry` and later refactored to the generic `Registry` class. See [2025-10-25-recipe-registry-design.md](2025-10-25-recipe-registry-design.md) for the refactoring design that made the registry generic and added recipe support.

## Problem Statement

The current approach to tracking ingredient metadata (IDs, names, matrix indices) has several issues:

1. **Multiple objects to manage**: Three separate data structures (`id_to_index`, `index_to_id`, `id_to_name`) must be kept in sync
2. **Multi-step lookups**: Common operations like "matrix index → name" require chaining lookups
3. **Type inconsistency**: `id_to_name` accepts both `str` and `int` keys, requiring normalization helpers
4. **Hard to inspect and debug**: No single view of the complete mapping
5. **Error-prone**: Easy to pass incompatible objects or get them out of sync

## Solution: IngredientRegistry Class

A single, dedicated class that centralizes all ingredient metadata and provides a clean, type-safe API.

### Core Design Principles

- **Single source of truth**: One object containing all ingredient metadata
- **Immutable after construction**: Ingredients don't change during matrix operations
- **Type safety**: All IDs stored as strings internally, strong typing on all methods
- **Fast common paths**: Index → name/id lookups are O(1) array accesses
- **Built-in validation**: Catch data quality issues at construction time
- **Extensible**: Easy to add features (caching, derived properties, etc.) later

### Architecture

#### Internal Storage

```python
class IngredientRegistry:
    """Central registry mapping matrix indices ↔ ingredient IDs ↔ names."""

    def __init__(self, ingredients: list[tuple[int, str, str]]):
        """
        Parameters
        ----------
        ingredients : list of (matrix_index, ingredient_id, ingredient_name)
        """
        self._indices: np.ndarray    # [0, 1, 2, ...] - matrix positions
        self._ids: np.ndarray         # ['123', '456', ...] - ingredient IDs
        self._names: np.ndarray       # ['Gin', 'Vodka', ...] - display names
        self._id_to_idx: dict[str, int]      # Reverse lookup: id → index
        self._name_to_idx: dict[str, int]    # Reverse lookup: name → index (lazy)
```

**Design rationale:**
- Parallel numpy arrays for fast indexing (common case: index → name/id)
- Single dict for reverse lookups (less common, acceptable O(1) dict overhead)
- All IDs normalized to strings at construction (eliminates type mixing)

#### Public API

**Flexible accessors** (keyword-only for clarity):

```python
def get_name(self, *, index: int | None = None, id: str | None = None) -> str:
    """Get ingredient name from either index or id."""

def get_id(self, *, index: int | None = None, name: str | None = None) -> str:
    """Get ingredient ID from either index or name."""

def get_index(self, *, id: str | None = None, name: str | None = None) -> int:
    """Get matrix index from either id or name."""
```

**Convenience methods:**

```python
def __len__(self) -> int:
    """Number of ingredients."""

def __getitem__(self, index: int) -> tuple[str, str]:
    """registry[i] returns (id, name) for matrix index i."""

def validate_matrix(self, matrix: np.ndarray) -> None:
    """Validate matrix dimensions match ingredient count."""
```

**Legacy compatibility:**

```python
def to_id_to_index(self) -> dict[str, int]:
    """Export as {ingredient_id: matrix_index} dict if needed."""
```

### Validation Strategy

Validation occurs at construction to fail fast:

```python
def _validate_ingredients(self, ingredients):
    """Check for common data quality issues."""

    # 1. Matrix indices must be contiguous 0..N-1
    indices = [idx for idx, _, _ in ingredients]
    if sorted(indices) != list(range(len(indices))):
        raise ValueError("Matrix indices must be contiguous 0..N-1")

    # 2. IDs must be unique
    ids = [id for _, id, _ in ingredients]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate ingredient IDs found")

    # 3. Names should be unique (warn if not, don't fail)
    names = [name for _, _, name in ingredients]
    if len(names) != len(set(names)):
        warnings.warn("Duplicate ingredient names found")
```

Accessor methods validate arguments:

```python
def get_name(self, *, index=None, id=None) -> str:
    # Exactly one argument must be provided
    if (index is None) == (id is None):
        raise ValueError("Exactly one of 'index' or 'id' must be provided")

    # Range checking
    if index is not None and not 0 <= index < len(self):
        raise IndexError(f"Index {index} out of range")

    # Key existence checking
    if id is not None and id not in self._id_to_idx:
        raise KeyError(f"Ingredient ID '{id}' not found")
```

### Integration with Existing Code

#### Construction Pattern

**Updated `build_ingredient_distance_matrix` signature:**

```python
def build_ingredient_distance_matrix(
    parent_map: dict[str, tuple[str | None, float]],
    id_to_name: dict[str | int, str],
    root_id: str = "root",
) -> tuple[np.ndarray, IngredientRegistry]:
    """
    Build distance matrix and registry together (always in sync).

    The root node is excluded from the matrix as it is an implicit structural
    node, not an actual ingredient that appears in recipes.

    Returns
    -------
    distance_matrix : np.ndarray
        Pairwise distances, shape (n, n) where n = len(parent_map) - 1 (root excluded)
    registry : IngredientRegistry
        Metadata for n ingredients (excluding root), guaranteed to match matrix dimensions
    """
```

**Workflow:**

```python
# Step 1: Build tree
tree, parent_map = build_ingredient_tree(df)

# Step 2: Extract id_to_name mapping
id_to_name = dict(zip(df['ingredient_id'], df['ingredient_name']))

# Step 3: Build matrix and registry atomically (guaranteed consistent)
cost_matrix, registry = build_ingredient_distance_matrix(parent_map, id_to_name)

# Step 4: Use registry throughout
neighbors_df = report_ingredient_neighbors(cost_matrix, k=5, registry)
```

#### Refactored Function Signatures

**Before:**
```python
report_ingredient_neighbors(
    cost_matrix: np.ndarray,
    k: int,
    id_to_name: dict[str | int, str],
    index_to_id: list[str],
) -> pd.DataFrame
```

**After:**
```python
report_ingredient_neighbors(
    cost_matrix: np.ndarray,
    k: int,
    registry: IngredientRegistry,
) -> pd.DataFrame
```

Functions that need updating:
- `report_ingredient_neighbors` - replace `id_to_name` + `index_to_id` with `registry`
- `build_recipe_volume_matrix` - can accept `registry` instead of `ingredient_id_to_index`
- Any custom analysis/reporting code using ingredient metadata

### Relationship to Cost Matrix

**Design decision: Keep cost matrix separate from registry.**

Rationale:
- Cost matrix has different lifecycle (updated iteratively via EM algorithm)
- Registry is immutable ingredient metadata
- Same registry used across multiple cost matrix iterations
- Cleaner separation of concerns (metadata vs. computation)

Pattern:
```python
# Registry built once
cost_matrix_0, registry = build_ingredient_distance_matrix(parent_map, id_to_name)

# Cost matrix evolves, registry stays fixed
T_sum, _ = expected_ingredient_match_matrix(volume_matrix, cost_matrix_0, k, beta)
cost_matrix_1 = m_step_blosum(cost_matrix_0, T_sum, alpha, blend)

# Both matrices reference same registry
report_0 = report_ingredient_neighbors(cost_matrix_0, k=5, registry)
report_1 = report_ingredient_neighbors(cost_matrix_1, k=5, registry)
```

### Example: Refactored Code

**Before:**
```python
def report_ingredient_neighbors(cost_matrix, k, id_to_name, index_to_id):
    if cost_matrix.shape[0] != len(index_to_id):
        raise ValueError("Dimension mismatch")

    id_to_name_str = _normalize_id_to_name_keys(id_to_name)
    nn_idx, nn_dist = knn_matrix(cost_matrix, k)

    records = []
    for ing_idx in range(cost_matrix.shape[0]):
        ing_id = index_to_id[int(ing_idx)]
        ing_name = id_to_name_str.get(ing_id, f"id:{ing_id}")

        for neighbor_idx, cost in zip(nn_idx[ing_idx], nn_dist[ing_idx]):
            n_idx = int(neighbor_idx)
            neighbor_id = index_to_id[n_idx]
            neighbor_name = id_to_name_str.get(neighbor_id, f"id:{neighbor_id}")
            records.append({...})

    return pd.DataFrame.from_records(records)
```

**After:**
```python
def report_ingredient_neighbors(cost_matrix, k, registry):
    registry.validate_matrix(cost_matrix)
    nn_idx, nn_dist = knn_matrix(cost_matrix, k)

    records = []
    for ing_idx in range(len(registry)):
        ing_id = registry.get_id(index=ing_idx)
        ing_name = registry.get_name(index=ing_idx)

        for neighbor_idx, cost in zip(nn_idx[ing_idx], nn_dist[ing_idx]):
            neighbor_id = registry.get_id(index=int(neighbor_idx))
            neighbor_name = registry.get_name(index=int(neighbor_idx))
            records.append({...})

    return pd.DataFrame.from_records(records)
```

**Improvements:**
- 3 parameters → 2 parameters
- No manual type normalization
- Validation centralized
- Clearer lookup intent

## Implementation Plan

### Phase 1: Core Registry Class
1. Implement `IngredientRegistry.__init__` with validation
2. Implement accessor methods (`get_name`, `get_id`, `get_index`)
3. Implement convenience methods (`__len__`, `__getitem__`)
4. Add comprehensive unit tests

### Phase 2: Integration
1. Update `build_ingredient_distance_matrix` signature
2. Add `from_parent_map` classmethod
3. Update `report_ingredient_neighbors` signature
4. Update `build_recipe_volume_matrix` to accept registry (optional)
5. Add integration tests

### Phase 3: Migration
1. Update all existing code using old pattern
2. Remove deprecated helpers (`build_index_to_id`, `_normalize_id_to_name_keys`)
3. Update documentation and examples

## Benefits Summary

1. **Simpler API**: One object instead of three, fewer parameters to pass
2. **Type safety**: No more str/int mixing, strong typing throughout
3. **Guaranteed consistency**: Matrix and metadata built atomically
4. **Better error messages**: Validation at construction, clear accessor errors
5. **Easier debugging**: Single object to inspect
6. **Extensibility**: Clean place to add features (serialization, caching, validation hooks, etc.)
7. **Cleaner code**: Lookup intent is explicit (`get_name(index=i)` vs. `index_to_id[i]`)

## Future Enhancements

- Serialization (to_dict/from_dict, to_dataframe/from_dataframe)
- Performance optimizations (caching, vectorized lookups)
- Additional validation hooks
- Support for ingredient hierarchies

## Open Questions

None - design approved for implementation.
