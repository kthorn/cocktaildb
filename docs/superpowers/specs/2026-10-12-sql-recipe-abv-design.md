# SQL Recipe ABV Design

**Status:** Draft for owner review
**Date:** 2026-10-12
**Supersedes (partially):** `docs/superpowers/specs/2026-09-19-recipe-abv-design.md` — the ABV *decision and math* move from Python to SQL; the response contract and all approved semantics are preserved.

## Summary

Move recipe ABV calculation from the Python module `api/recipe_abv.py` into PostgreSQL views so there is exactly one implementation of every ABV rule, and use it to add ABV filtering to recipe search. Python keeps only string formatting (display strings and notes). The API response contract (`status`, `min_percent`, `max_percent`, `display`, `notes`) does not change, so the frontend and SSR templates are untouched except for the new search filter inputs.

## Motivation

- Recipe ABV currently cannot be filtered in search: `calculate_recipe_abv()` runs in Python *after* SQL pagination, so an ABV filter would break page counts and totals.
- A future SQL re-encoding of the volume/strength rules for filtering would duplicate the Python calculator and drift (the repository DRY rule: N copies of a calculation is N surfaces for divergence).
- Postgres `numeric` is exact; Decimal semantics survive the move.

## Approved semantics (unchanged from 2026-09-19 spec)

All rules below already hold and continue to hold verbatim; they are restated here because this spec relocates them:

- Ingredient-only, **pre-dilution** ABV. No served-strength, preparation, sugar, or acid modeling.
- Known leaf values (including zero) are observations; parents' own `percent_abv` columns are never observations (the trigger from migration 16 keeps parent values cleared).
- An ingredient's strength interval is its nearest populated family's min/max observed leaf ABV; no observations anywhere up the hierarchy means **0–100%** (`source` = `unknown`).
- Strength `source`: `recorded` (self), `family` (nearest populated ancestor), `unknown` (no observations).
- Volume rules per `recipe_ingredients` row (unit name matched case-insensitively, trimmed):
  - `each` → excluded from volume; recipe is `estimated`; note discloses exclusion.
  - `to top` → 88.7205 mL per row; recipe is `estimated`.
  - `to rinse` → 1 mL per row; recipe is `estimated`.
  - otherwise → `amount × conversion_to_ml`; requires non-null unit, non-null finite amount ≥ 0, and a valid positive conversion.
  - explicit `amount = 0` contributes nothing and is valid.
  - missing unit, missing amount, negative/NaN amount, or missing/non-positive conversion makes the whole recipe `unknown`.
- Unknown-strength rows use their 0–100% interval in the weighted bounds (recipe becomes `estimated`, not unknown).
- Recipe interval: `min = Σ(volume × min_strength) / Σ(volume)`, `max` likewise with max strength.
- `status = unknown` when any row is invalid, no positive modeled volume exists, or the interval width exceeds **20 percentage points** (width exactly 20 is displayable).
- `status = calculated` when nothing was estimated; `estimated` otherwise.
- Point display: midpoint when the interval is "narrow" (width ≤ 1 percentage point); rounds half up to whole percent; `0 < x < 1` shows `<1%`; narrow results clear notes.
- Interval display (width ≤ 20): endpoints round **outward** to whole percentages (floor low, ceiling high), `N–M%`.
- Too-wide or unknown results keep raw numeric bounds in the API but display `Unknown`.
- One bulk resolution per fetched recipe collection; no per-recipe queries or caches.

## Architecture

Three layers, each concern encoded once:

### Layer 1 — SQL view `ingredient_abv_resolution` (per-ingredient strength)

Extracts the nearest-populated-family recursive walk from `RESOLVE_INGREDIENT_ABV_SQL` into a view over all ingredients:

- Columns: `ingredient_id`, `min_percent_abv`, `max_percent_abv`, `observation_count`, `family_id`, `family_name`, `source` (`recorded`/`family`/`unknown`), and `has_observations` (`observation_count > 0`).
- Same walk logic, ordering, and tie-breaking as the current `RESOLVE_INGREDIENT_ABV_SQL` (`DISTINCT ON` by requested id, smallest depth, then candidate id), but parameter-free.
- `RESOLVE_INGREDIENT_ABV_SQL` is refactored to a thin parameterized select from this view, so its consumers (bulk ABV values page, existing tests) keep their behavior and contract: same columns, same `0–100` unknown bounds via `COALESCE`.

### Layer 2 — SQL view `recipe_abv_ingredient_rows` (per-recipe contribution rows)

For each `(recipe_id, recipe_ingredients.id)` row of every recipe:

- `recipe_id`, `ingredient_id`, `ingredient_name`, `unit_name`
- `volume_ml numeric` — the modeled volume from the rules above (null when excluded, zero, or invalid)
- `is_estimated boolean` — true for `each`, `to top`, and `to rinse` rows (zero-amount rows are NOT estimated)
- `is_invalid boolean` plus `invalid_reason text` (code, not prose): one of `'missing_unit'`, `'missing_amount'`, `'negative_amount'`, `'non_finite_amount'`, `'invalid_conversion'`
- `min_percent_abv`, `max_percent_abv` — from `ingredient_abv_resolution`, `COALESCE(…, 0)` / `COALESCE(…, 100)` (unknown rows carry 0–100)
- `strength_source` — `recorded`/`family`/`unknown`

No strings are composed here beyond the fixed reason codes; no aggregation.

### Layer 3 — SQL view `recipe_abv` (per-recipe interval; the math)

Aggregates Layer 2 by `recipe_id`:

- `min_percent`, `max_percent` — the volume-weighted interval (null when no positive modeled volume or when invalid rows exist)
- `status` — `unknown` if any invalid row / no positive volume / width > 20; `calculated` if no row has `is_estimated` and every strength source is `recorded`; else `estimated`
- `narrow boolean` — interval width ≤ 1 percentage point (drives point-vs-interval display)
- `display` is **not** in this view; display and notes are Python's job.

### Python — `api/recipe_abv.py` (formatting only)

Slimmed to a pure presentation module, roughly:

- `format_recipe_abv(bounds: dict, rows: list[dict]) -> dict` where `bounds` is a Layer-3 row (`status`, `min_percent`, `max_percent`, `narrow`) and `rows` are the recipe's Layer-2 rows.
- Builds `display` (point/interval/`Unknown` rounding rules above) and `notes` (first-occurrence dedup via the existing `_append_note` pattern) from Layer-2 fields: exclusion/invalid codes → disclosure sentences, `to top`/`to rinse`/`each` assumptions, family-strength disclosures like `Vodka: 40–40%`, unknown-strength disclosure. Note *text* stays in Python; note *decisions* come from SQL flags.
- Deletes all arithmetic: `TOP_UP_VOLUME_ML`, `RINSE_VOLUME_ML`, width/interval computation, status determination move to SQL. Python never invents numbers.

### Enrichment — `api/db/db_core.py`

`_add_recipe_abv(recipes, execute_query)` keeps its signature and call sites (get recipe, search batches, bulk create) but becomes:

1. One query: Layer-3 rows for the batch's recipe ids (`WHERE recipe_id = ANY(%(recipe_ids)s)`).
2. One query: Layer-2 rows for those ids.
3. Per recipe: `recipe["abv"] = format_recipe_abv(bounds, rows)`; recipes missing from the views get a Python-built `unknown` result (no ingredients).

### Search filtering — `api/db/sql_queries.py`

Both `build_search_recipes_paginated_sql` and `build_search_recipes_keyset_sql` add inside the `search_results` CTE:

```sql
LEFT JOIN recipe_abv rab ON rab.recipe_id = r.id
```

and the filter condition:

```sql
(%(min_abv)s IS NULL OR (rab.max_percent >= %(min_abv)s))
AND
(%(max_abv)s IS NULL OR (rab.min_percent <= %(max_abv)s))
```

- Interval-overlap semantics: a recipe matches when its ABV interval intersects `[min_abv, max_abv]`.
- `status = unknown` rows have null bounds → both comparisons are null → row excluded whenever either filter is active. Unknown-ABV recipes are never returned under an ABV filter.
- The join happens **before** `LIMIT/OFFSET` (or keyset `LIMIT limit+1`), so pagination, ordering, and counts stay exact.
- `GROUP BY` needs no change: the view's columns are functionally dependent on `r.id`; select `rab.min_percent`/`rab.max_percent` only if needed (they are not; the CTE does not select them).

### API — `api/routes/recipes.py`

`GET /api/recipes/search` gains two optional query parameters:

- `min_abv: float | None = Query(None, ge=0, le=100, description="Minimum estimated ABV percent")`
- `max_abv: float | None = Query(None, ge=0, le=100, description="Maximum estimated ABV percent")`

Validation: when both are provided, `min_abv ≤ max_abv` (422 otherwise). Plumbed into `search_params` as `min_abv`/`max_abv` and forwarded to the db layer as query parameters on both SQL builders.

### Frontend — `src/web/search.html`, `src/web/js/search.js`

Two numeric inputs (Min ABV / Max ABV, 0–100, step 0.5) in the existing filter panel beside the rating filter; both serialize into the search request when set and clear independently. No changes to `recipeCard.js`, `recipe.html`, or any ABV display code: the contract is identical.

### What is deleted

- `api/recipe_abv.py`: `calculate_recipe_abv`, `_volume_for_ingredient`, `_interval_display`, `_point_display`'s math inputs, `TOP_UP_VOLUME_ML`/`RINSE_VOLUME_ML`/width constants — replaced by Layer 2/3. Python keeps only rounding/label helpers and note composition.
- The Python side of `RESOLVE_INGREDIENT_ABV_SQL` consumers' per-id resolution shape (the SQL text itself shrinks to a view select).

## Data flow

```
search/detail request
  → db query (Layer-3 filtered join for search; plain fetch for detail)
  → _add_recipe_abv: Layer-3 bounds + Layer-2 rows for the page's recipe ids
  → format_recipe_abv (Python formatting)
  → RecipeABVResponse (unchanged shape)
  → recipeCard.js / recipe.html (unchanged rendering)
```

## Migration

`migrations/19_migration_add_recipe_abv_views.sql` (+ rollback):

1. `CREATE OR REPLACE VIEW ingredient_abv_resolution` (recursive walk).
2. `CREATE OR REPLACE VIEW recipe_abv_ingredient_rows`.
3. `CREATE OR REPLACE VIEW recipe_abv`.
4. No tables, columns, or existing views are altered; migration 16's `ingredient_abv_ranges` view and trigger remain as-is.
5. Rollback drops the three new views. Code rollback is out of SQL scope (matches the existing 16 rollback convention); views are additive so older code keeps working with them present.

Deployment ordering: apply the migration before deploying the API version that uses the views.

## Error handling

- Recipes with invalid rows or unresolvable volume: `status = unknown`, null bounds, display `Unknown`, notes disclose the reason codes (Python renders prose).
- ABV filter with no parameters: behavior identical to today (no join filter, join is a no-op LEFT JOIN).
- Malformed `min_abv > max_abv`: 422 at the API boundary.
- View absent (unmigrated DB): search raises; enrichment raises — fails loudly rather than silently returning wrong data, consistent with the repository's no-silent-fallback rule.

## Testing

- **View tests** (`tests/test_recipe_abv_ranges.py` style, Postgres fixture): extend with Layer 1/2/3 assertions — volume rules per special unit, exclusion, invalid codes, unknown 0–100 strength, width cutoff at exactly 20, `narrow` boundary at exactly 1 point.
- **Ported calculator tests**: existing `tests/test_recipe_abv.py` cases move to DB-backed equivalents asserting Layer-3 `min_percent`/`max_percent`/`status` for the same scenarios (same expected numbers).
- **Python formatting unit tests**: remain pure and fast — rounding, `<1%`, outward interval rounding, `Estimated` prefix, note ordering/dedup, narrow clears notes.
- **Search integration tests** (`tests/test_recipe_abv_integration.py`): `min_abv`/`max_abv` filtering on offset and keyset paths, interval-overlap edge cases (recipe at exactly the bound matches), unknown-ABV exclusion, pagination correctness (no off-by-one, no skipped/duplicated recipes across pages).
- **Contract tests**: `tests/test_recipe_abv_display.mjs` and SSR template tests pass unchanged (proof the response contract held).
- **Search SQL parity**: the two builders get the same filter; a test asserts both SQL strings contain the ABV join/condition.
- Coverage gate (80%) retains; focused pytest uses `-o addopts=''`.

## Performance

- Views are plain (non-materialized): per-request computation, matching the current on-the-fly Python cost. Group-key pushdown applies the page's recipe ids into the aggregates.
- Scale is hundreds of recipes and shallow hierarchies; no index changes anticipated. If profiling ever disagrees, the upgrade path is materializing `recipe_abv` with a refresh hook — deliberately out of scope.

## Out of scope

- Sorting by ABV (falls out of Layer 3 later; `build_recipe_sort_spec` extension is a trivial follow-up).
- A persisted/materialized recipe-ABV column.
- Dilution/served-strength modeling.
- Changes to `ingredient_abv_ranges`, the bulk ABV values feature, or the notes API shape.
