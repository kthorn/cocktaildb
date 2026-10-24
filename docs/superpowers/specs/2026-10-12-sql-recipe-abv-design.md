# SQL Recipe ABV Design

**Status:** Draft for owner review
**Date:** 2026-10-12
**Supersedes (partially):** `docs/superpowers/specs/2026-09-19-recipe-abv-design.md` — the ABV *decision and math* move from Python to SQL; the response contract and all approved semantics are preserved.

## Summary

Move recipe ABV calculation from the Python module `api/recipe_abv.py` into PostgreSQL views so there is exactly one implementation of every ABV rule, and use it to add ABV filtering to recipe search. Python keeps only string formatting (display strings and notes). The API response contract (`status`, `min_percent`, `max_percent`, `display`, `notes`) does not change, so the frontend and SSR templates are untouched except for the new search filter inputs.

## Motivation

- Recipe ABV currently cannot be filtered in search: `calculate_recipe_abv()` runs in Python *after* SQL pagination, so an ABV filter would break page counts and totals.
- A SQL re-encoding of the volume/strength rules for filtering would duplicate the Python calculator and drift (the repository DRY rule: N copies of a calculation is N surfaces for divergence). This is no longer hypothetical: the in-progress ignore-minor inventory filter adds `_recipe_ingredient_volume_ml` in `api/db/sql_queries.py`, a second SQL copy of the volume rules that already disagrees with Python on non-finite amounts. This spec makes one SQL view the only encoding and folds that helper onto it (see "Shared volume consumers").
- Postgres `numeric` is exact; Decimal semantics survive the move.

## Approved semantics (unchanged from 2026-09-19 spec)

All rules below already hold and continue to hold verbatim; they are restated here because this spec relocates them:

- Ingredient-only, **pre-dilution** ABV. No served-strength, preparation, sugar, or acid modeling.
- Known leaf values (including zero) are observations; parents' own `percent_abv` columns are never observations. Parents do carry values: migration 14's statement-level `roll_up_ingredient_values` trigger rewrites every parent's `percent_abv` to the average of its children on each ingredient write, and migration 16's trigger clears a former parent's stale value when it loses its last child. The observation walk counts only leaves, so rollup averages never enter an interval.
- An ingredient's strength interval is its nearest populated family's min/max observed leaf ABV; no observations anywhere up the hierarchy means **0–100%** (`source` = `unknown`).
- Strength `source`: `recorded` (self, but only when the ingredient is a leaf with a non-`NaN` `percent_abv` in 0–100), `family` (nearest populated ancestor — a category resolving to its own subtree is still `family`, never `recorded`), `unknown` (no observations).
- Volume rules per `recipe_ingredients` row (unit name trimmed of surrounding whitespace and matched case-insensitively; a blank name counts as no unit). Evaluation order matters and mirrors the Python calculator: an invalid provided amount is rejected before unit handling, and `amount = 0` short-circuits before unit handling:
  - provided amount that is non-finite (PostgreSQL `REAL` permits `NaN` and `±Infinity` besides ordinary values) or negative → invalid (`non_finite_amount` / `negative_amount`).
  - explicit `amount = 0` → zero-volume row, valid, contributes nothing, is not estimated, and is ignored for strength-source determination and notes **whatever its unit**.
  - `each` → excluded from volume; recipe is `estimated`; note discloses exclusion.
  - `to top` → 88.7205 mL per row; recipe is `estimated` (a missing amount does not invalidate the row).
  - `to rinse` → 1 mL per row; recipe is `estimated` (same).
  - otherwise → `amount × conversion_to_ml`; requires non-null unit, non-null amount, and a finite positive conversion; missing unit, missing amount, or a missing/non-finite/non-positive conversion makes the whole recipe `unknown`.
- Unknown-strength rows use their 0–100% interval in the weighted bounds (recipe becomes `estimated`, not unknown).
- Recipe interval: `min = Σ(volume × min_strength) / Σ(volume)`, `max` likewise with max strength, over positive modeled volumes only.
- `status = unknown` when any row is invalid, no positive modeled volume exists (including a recipe with no ingredients), or the interval width exceeds **20 percentage points** (width exactly 20 is displayable). Width decisions must be evaluated division-free exactly as the Python calculator does — compare `Σ(volume × (high − low))` against `20 × Σv` for the cutoff and against `Σv` for `narrow` — because Postgres `numeric` division rounds, and a divided comparison could flip the exactly-20 and exactly-1 boundaries that the 2026-09-19 spec explicitly protected.
- `status = calculated` when nothing was estimated; `estimated` otherwise. A recipe is estimated when **any** row is an `each`, `to top`, or `to rinse` row (zero-amount rows never are, whatever their unit, because they short-circuit first), **or** any positive-volume row has a non-`recorded` strength source. Strength sources of zero-volume, `each`, and invalid rows are never consulted: a zero-amount unknown-strength ingredient does not make a recorded recipe `estimated`, but an `each` garnish does — because of its unit, not its strength. (This is `estimated = estimated or row_estimated` applied to every row in `api/recipe_abv.py`.)
- Point display: midpoint when the interval is "narrow" (width ≤ 1 percentage point); rounds half up to whole percent; `0 < x < 1` shows `<1%`; narrow results clear notes.
- Interval display (width ≤ 20): endpoints round **outward** to whole percentages (floor low, ceiling high), `N–M%`.
- New in this spec: these whole-percent display values are computed once, in SQL, and the search ABV filter matches against them, so a search returns exactly the recipes whose displayed ABV falls in the requested range.
- Too-wide or unknown results keep raw numeric bounds in the API but display `Unknown`. (The predecessor spec also required an `Estimated` prefix on estimated display strings; the owner deliberately removed that prefix in `fe6733f` — display is a bare percentage and `status` conveys estimated-ness — so the prefix requirement does not carry forward.)
- One bulk resolution per fetched recipe collection; no per-recipe queries or caches.

## Architecture

Four views in three layers, each concern encoded once. Volume rules are their own view (Layer 2a) because the ignore-minor inventory filter needs volumes without paying for the strength walk.

### Layer 1 — SQL view `ingredient_abv_resolution` (per-ingredient strength)

Extracts the nearest-populated-family recursive walk from `RESOLVE_INGREDIENT_ABV_SQL` into a view over all ingredients:

- Columns: `ingredient_id`, `min_percent_abv`, `max_percent_abv`, `observation_count`, `family_id`, `family_name`, `source` (`recorded`/`family`/`unknown`), and `has_observations` (`observation_count > 0`).
- `source` preserves the resolver's full `CASE` verbatim, not just the family walk: `recorded` requires depth 0 **and** a valid non-`NaN` `percent_abv` between 0 and 100 **and** no children; every other observed resolution is `family`.
- Same walk logic, ordering, and tie-breaking as the current `RESOLVE_INGREDIENT_ABV_SQL` (`DISTINCT ON` by requested id, smallest depth, then candidate id), but parameter-free.
- Unknown rows already carry `min_percent_abv = 0`, `max_percent_abv = 100`, and `observation_count = 0`; the `COALESCE`s live in this view.
- `RESOLVE_INGREDIENT_ABV_SQL` is refactored to a thin parameterized select from this view, so its consumers (bulk ABV values page, existing tests) keep their behavior and contract: same columns, same `0–100` unknown bounds via `COALESCE`.

### Layer 2a — SQL view `recipe_ingredient_volumes` (volume rules; the only encoding)

One row per `recipe_ingredients` row. No strength data, no aggregation, no prose.

- `recipe_ingredient_id`, `recipe_id`, `ingredient_id`, `unit_name`
- `volume_rule text` — exactly one of `'invalid'`, `'zero'`, `'counted'` (`each`), `'top'`, `'rinse'`, `'measured'`. This is what lets Python choose notes without re-parsing unit names.
- `invalid_reason text` — non-null only when `volume_rule = 'invalid'`: one of `'non_finite_amount'`, `'negative_amount'`, `'missing_unit'`, `'missing_amount'`, `'invalid_conversion'`.
- `volume_ml numeric` — `0` for `zero`; `88.7205` for `top`; `1` for `rinse`; the product for `measured`; null for `counted` and `invalid`. The constant literals must be written exactly `88.7205` and `1` (not `1.0`): Python renders them into note text via `str(Decimal)`, which preserves scale.
- `is_estimated boolean` — `volume_rule IN ('counted', 'top', 'rinse')`.
- `sort_volume real` — `COALESCE(ri.amount * u.conversion_to_ml, 0)`, computed in `REAL` exactly as the existing ingredient queries order rows (`_get_recipe_ingredients` and both search builders). It exists only for ordering.

The `CASE` is evaluated in the order of the Approved semantics bullets:

1. `amount IS NOT NULL AND amount IN ('NaN', 'Infinity', '-Infinity')` → `non_finite_amount`. Test on the `REAL` value, before any numeric conversion: Postgres float `NaN` compares greater than every number, so `amount < 0` alone would let it through.
2. `amount < 0` → `negative_amount`.
3. `amount = 0` → `zero`.
4. unit = `each` → `counted`; `to top` → `top`; `to rinse` → `rinse`.
5. no unit row, or blank name after trimming → `missing_unit`.
6. `amount IS NULL` → `missing_amount`.
7. `conversion_to_ml` null, non-finite, or ≤ 0 → `invalid_conversion`.
8. otherwise `measured`, `volume_ml = amount::text::numeric * conversion_to_ml::text::numeric`.

**`REAL` normalization:** `amount` and `conversion_to_ml` are `REAL` columns. Convert them with `value::text::numeric`, **not** `value::float8::text::numeric`. psycopg2 receives `REAL` values as Postgres's shortest float4 text, so Python's current `Decimal(str(value))` sees `29.5735`. `::text::numeric` reproduces that, but `::float8::text::numeric` widens first and yields `29.57349967956543` (verified on `postgres:15`). The wrong cast would shift every ounce-based volume and could flip the exactly-20 / exactly-1 boundary tests.

Trimming: Python uses `str.strip()`, so trim the whitespace characters unit names can realistically contain (space, tab, CR, LF) with `btrim`, not a bare `TRIM` that strips only spaces. `LOWER` stands in for `casefold()`, which is equivalent for the ASCII unit names in use.

### Layer 2b — SQL view `recipe_abv_ingredient_rows` (per-recipe contribution rows)

Layer 2a joined to Layer 1 on `ingredient_id`, plus `ingredients.name`:

- every Layer 2a column, plus `ingredient_name`
- `min_percent_abv`, `max_percent_abv` — from `ingredient_abv_resolution` (unknown rows carry 0–100)
- `strength_source` — `recorded`/`family`/`unknown`
- `contributes boolean` — `volume_ml > 0`, i.e. `volume_rule IN ('top', 'rinse', 'measured')`. Only contributing rows enter the interval, the strength-source part of the status decision, and strength notes.
- `strength_display_low`, `strength_display_high integer`, `strength_display_below_one boolean` — the whole-percent display of the ingredient's own strength interval, used by family notes. When `min_percent_abv = max_percent_abv` it is a point: both columns are `round(min_percent_abv)` (half up; values are never negative), except that a point with `0 < min_percent_abv < 1` sets `strength_display_below_one` and both columns to `0`, as in Layer 3. Otherwise `floor(min_percent_abv)` / `ceil(max_percent_abv)`. No division is involved, because ingredient bounds are stored values.

No strings are composed here beyond the fixed codes; no aggregation.

### Layer 3 — SQL view `recipe_abv` (per-recipe interval; the math)

Built from `recipes LEFT JOIN recipe_abv_ingredient_rows`, grouped by recipe id, so **every recipe has exactly one row**, including recipes with no ingredients. That removes any Python special case and makes the search filter's treatment of ingredientless recipes explicit.

- `recipe_id`
- `unknown_reason text` — `'invalid_row'` (any `volume_rule = 'invalid'`), else `'no_volume'` (no contributing row, including no rows at all), else `'too_wide'` (division-free width > 20), else null. Python chooses the aggregate disclosure from this, not by inferring from null bounds.
- `min_percent`, `max_percent` — the volume-weighted interval over contributing rows; null for `invalid_row` and `no_volume`, real values for `too_wide` and for displayable results.
- `status` — `unknown` when `unknown_reason` is non-null; otherwise `estimated` if any row `is_estimated` or any contributing row has `strength_source <> 'recorded'`; otherwise `calculated`.
- `narrow boolean` — interval width ≤ 1 percentage point, evaluated division-free (drives point-vs-interval display). Null when status is `unknown`.
- `display_low`, `display_high integer`, `display_below_one boolean` — the whole-percent values the recipe displays, and the values search filters on. All null when `status = 'unknown'`, including too-wide rows, which display `Unknown`.
  - Narrow: a point. Both columns hold the midpoint rounded half up, and `display_below_one` is true when `0 < midpoint < 1` (displayed `<1%`; both columns are then `0`).
  - Otherwise: `display_low` = floor of `min_percent`, `display_high` = ceiling of `max_percent`. A non-narrow interval can never have `display_low = display_high`.
- The display string itself is **not** in this view; turning these integers into text, and composing notes, are Python's job.

**Display values are computed division-free**, for the same reason as the width decisions: a rounded quotient could tip a value that sits exactly on a rounding boundary. With `L = Σ(v × low)`, `H = Σ(v × high)`, and `V = Σv`, all exact `numeric`, use Postgres's exact integer `div` and `mod` (operands are never negative, so truncation is floor):
- midpoint rounded half up = `div(L + H + V, 2V)`;
- `display_below_one` = `0 < L + H AND L + H < 2V`;
- floor of `min_percent` = `div(L, V)`;
- ceiling of `max_percent` = `div(H, V) + (mod(H, V) > 0)::int`.

Every expression that divides by `V` sits inside a `CASE`, so `V = 0` or null never reaches `div`, `mod`, or `/`. The display columns are computed only when `unknown_reason` is null. The raw bounds are computed whenever there is no invalid row and `V > 0`, so too-wide rows keep them.

**Division precision of the raw bounds:** `min_percent`/`max_percent` are still the quotients `L / V` and `H / V`. Postgres picks the quotient's scale itself (at least 16 significant digits, typically 18–20), while Python used 50-digit precision, so after conversion to `float` they can differ from today's values in the last unit of precision. That only affects the raw numbers in the API response. Every decision (status, narrow, display, filtering) is division-free. Ported tests compare floats with `pytest.approx`, as most of the current ones already do.

### Python — `api/recipe_abv.py` (formatting only)

Python is still the final numeric frontier: Layer-3 `numeric` values arrive as `Decimal` and are converted to finite JSON floats at the format boundary (the existing `_json_number` discipline: reject/`None` non-finite, emit floats otherwise). Note text keeps the current wording, including equal-endpoint family collapses (`Vodka: 40%`, not `Vodka: 40–40%`) and the aggregate disclosures.

Slimmed to a pure presentation module, roughly:

- `format_recipe_abv(bounds: dict, rows: list[dict]) -> dict`, where `bounds` is a Layer-3 row and `rows` are the recipe's Layer-2b rows in note order (below).
- `display`: one text helper turns SQL's display integers into a string, with no rounding: `Unknown` when `status = 'unknown'`; `<1%` when `display_below_one`; `N%` when `display_low = display_high`; otherwise `N–M%`. Family notes reuse the same helper on Layer 2b's `strength_display_*` columns.
- `notes`, per row in order, with first-occurrence dedup via the existing `_append_note` pattern. Every decision comes from a SQL column:
  - `volume_rule = 'invalid'` → the existing sentence for its `invalid_reason` (`non_finite_amount` and `negative_amount` both map to "Invalid quantity for …"; `missing_unit`, `missing_amount`, `invalid_conversion` to their current "Unknown volume for …" sentences).
  - `counted` → "Excluded counted ingredient …".
  - `top` / `rinse` → "Assumed {volume_ml} mL for to top/to rinse ingredient …", with the number taken from Layer 2a's `volume_ml`.
  - `contributes` and `strength_source = 'unknown'` → "Unknown strength for …; assuming 0–100%."
  - `contributes` and `strength_source = 'family'` → "{label}: {display}", formatted from `strength_display_*`, so equal endpoints collapse to a point (`Vodka: 40%`).
  - then the aggregate note from `unknown_reason`: `no_volume` → "No positive modeled liquid volume was available.", `too_wide` → "The ABV interval is wider than 20 percentage points.", `invalid_row` → none.
  - `narrow` results clear notes.
- Notes that become unreachable are dropped intentionally: "Missing strength data …" and "Invalid strength data …" (Layer 1 covers every ingredient with bounds inside 0–100 by construction), "its modeled volume is invalid" (a positive finite amount times a positive finite conversion is always positive in `numeric`), and the two non-finite-bounds sentences (weighted averages of values in 0–100 are always finite).
- **Note order:** the Layer-2b fetch orders by `recipe_id, sort_volume DESC, recipe_ingredient_id ASC`. `sort_volume` is the exact `COALESCE(ri.amount * u.conversion_to_ml, 0)` expression used by the ingredient queries. The `COALESCE` matters: without it Postgres sorts NULLs first under `DESC`, moving `to top`/`to rinse` rows with no amount ahead of measured ones and changing first-occurrence dedup.
- Deletes all arithmetic and rounding: `TOP_UP_VOLUME_ML`, `RINSE_VOLUME_ML`, the width constant, interval/midpoint computation, display rounding, and status determination all move to SQL.

### Enrichment — `api/db/db_core.py`

`_add_recipe_abv(recipes, execute_query)` keeps its signature and its existing call sites — get recipe, search batch (offset), and search batch (keyset). Bulk create is **not** a call site: it deliberately returns minimal recipe metadata without ABV (`tests/test_recipe_abv_integration.py` asserts that null-ABV contract), and it stays that way. The enrichment becomes:

1. One query: Layer-3 rows for the batch's recipe ids (`WHERE recipe_id = ANY(%(recipe_ids)s)`).
2. One query: Layer-2b rows for those ids, in note order.
3. Per recipe: `recipe["abv"] = format_recipe_abv(bounds, rows)`.

Because Layer 3 has a row for every recipe, a missing row can only mean the recipe was deleted between the batch query and the enrichment query. That recipe gets `abv = None` (the response model already allows null for bulk create), and a warning is logged naming the id. It is not given an invented `unknown` result.

### Shared volume consumers — `api/db/sql_queries.py`

`build_inventory_filter_sql(ignore_minor=True)` stops using `_recipe_ingredient_volume_ml` and reads `volume_ml` from `recipe_ingredient_volumes` instead (joined on `recipe_ingredient_id` for the row under test, and summed over the recipe's rows for the total). Then `_recipe_ingredient_volume_ml` is deleted, along with the `from recipe_abv import RINSE_VOLUME_ML, TOP_UP_VOLUME_ML` import, which would otherwise break once those constants are removed.

It reads Layer 2a, not 2b, so the inventory subquery never runs the recursive strength walk.

Behavior compared with the current helper is unchanged except at the edges where the helper was wrong:

- `NaN`/`±Infinity` amounts now yield null (never minor) instead of `NaN` products or the top/rinse constants.
- `each` rows are null whatever their unit's conversion.
- Measured volumes use the text-normalized `numeric` product rather than the `REAL` product, which can only matter for an ingredient sitting exactly at the 2% threshold.

`tests/test_inventory_ignore_minor.py` must pass unchanged.

**Sequencing:** ignore-minor is PR #116 (`feat/ignore-minor-ingredients`). This spec is implemented on `feat/sql-recipe-abv`, stacked on that branch, and performs the fold above; merge #116 first.

### Search filtering — `api/db/sql_queries.py`

Both `build_search_recipes_paginated_sql` and `build_search_recipes_keyset_sql` take `abv_filter: bool = False`, following the existing `inventory_filter` pattern. Only when it is true (either bound given) do they add inside the `search_results` CTE:

```sql
LEFT JOIN recipe_abv rab ON rab.recipe_id = r.id
```

and the filter condition:

```sql
rab.status <> 'unknown'
AND (%(min_abv)s IS NULL OR rab.display_high >= %(min_abv)s)
AND (%(max_abv)s IS NULL OR rab.display_low <= %(max_abv)s)
```

- **The filter matches what the user sees.** A recipe matches when its displayed whole-percent range `[display_low, display_high]` intersects `[min_abv, max_abv]`:
  - A recipe displayed `10–15%` (raw 10.4–14.2) matches `min_abv = 15`.
  - A recipe displayed `15%` (narrow, midpoint 14.6) matches `min_abv = 15` and `max_abv = 15`.
  - A recipe displayed `<1%` counts as 0: it matches `max_abv = 0` and does not match `min_abv = 1`.
- `status = 'unknown'` recipes are never returned while either ABV filter is active. That includes too-wide rows and ingredientless recipes; both display `Unknown` and have null display columns. The explicit status guard states the intent rather than relying on null comparisons.
- **Any provided value activates the filter, including `min_abv = 0`.** `min_abv=0` is therefore not a no-op: it means "recipes with a known ABV". The frontend sends it only when the user has entered a value.
- The join happens **before** `LIMIT/OFFSET` (or keyset `LIMIT limit+1`), so pagination and ordering behavior are unchanged. (Search reports the fetched page length as `total_count` today; this change does not introduce a new exact-total contract.)
- `GROUP BY` needs no change — but for the correct reason: no `rab` column is selected in the CTE (PostgreSQL does not infer functional dependency from `r.id` across a joined view, so selecting `rab.min_percent`/`rab.max_percent` would require grouping/aggregating those columns; don't).

### API — `api/routes/recipes.py`

`GET /api/recipes/search` gains two optional query parameters:

- `min_abv: int | None = Query(None, ge=0, le=100, description="Minimum displayed ABV percent")`
- `max_abv: int | None = Query(None, ge=0, le=100, description="Maximum displayed ABV percent")`

They are integers because every displayed ABV is a whole percentage; a fractional bound would invite questions about where `14.5` falls against a displayed `15%`. FastAPI rejects a non-integer or out-of-range value with 422. When both are provided and `min_abv > max_abv`, the route raises `ValidationException` (400), like its other cross-field checks (`sort_by`, `rating_type`). Plumbed into `search_params` as `min_abv`/`max_abv` and forwarded to the db layer as query parameters on both SQL builders.

`GET /api/recipes/search/authenticated` **must** declare and forward the same two parameters. Logged-in users always call this endpoint (`CocktailAPI.searchRecipes` in `api.js`), so dropping them there would silently disable the filter for every signed-in user. It calls `search_recipes` with explicit keyword arguments, so pass the values explicitly; the `Query(...)` defaults must not leak into the db call.

### Frontend — `src/web/search.html`, `src/web/js/search.js`, `src/web/js/api.js`

- `search.html`: two numeric inputs (Min ABV / Max ABV, 0–100, step 1) in their own group of the filter panel, after the inventory checkboxes, with short help text saying they match the ABV shown on each recipe and hide recipes whose ABV is unknown.
- `search.js`: the query builder sets `query.min_abv` / `query.max_abv` when the input's value is non-empty (`input.value !== ''`), so an entered `0` is kept. The existing reset handler clears both inputs.
- `api.js`: `searchRecipes` appends `min_abv` / `max_abv` when they are not `null`/`undefined`. Use an explicit null check, not the truthiness pattern used for `rating`, which would drop `0`. The anonymous-user branch already forwards every parameter except `inventory`/`ignore_minor`, so both endpoints receive the filter.
- No changes to `recipeCard.js`, `recipe.html`, or any ABV display code: the contract is identical.

### What is deleted

- `api/recipe_abv.py`: `calculate_recipe_abv`, `_volume_for_ingredient`, `_point_display`, `_interval_display`, `TOP_UP_VOLUME_ML`/`RINSE_VOLUME_ML`/width constants, and all interval, midpoint, rounding, and status logic — replaced by Layers 2a/2b/3. The unreachable notes listed above go with them. Python keeps only the display-text helper, the label helper, `_json_number`, and note composition.
- `api/db/sql_queries.py`: `_recipe_ingredient_volume_ml` and its import of the Python volume constants.
- The Python side of `RESOLVE_INGREDIENT_ABV_SQL` consumers' per-id resolution shape (the SQL text itself shrinks to a view select).

## Data flow

```
search/detail request
  → db query (Layer-3 filtered join for search; plain fetch for detail)
  → _add_recipe_abv: Layer-3 bounds + Layer-2b rows (note order) for the page's recipe ids
  → format_recipe_abv (Python formatting)
  → RecipeABVResponse (unchanged shape)
  → recipeCard.js / recipe.html (unchanged rendering)

inventory search with ignore_minor
  → build_inventory_filter_sql reads Layer-2a volume_ml
```

## Migration

`migrations/19_migration_add_recipe_abv_views.sql` (+ rollback). There is no migration 17 in history; 19 follows the existing 18.

1. `CREATE OR REPLACE VIEW ingredient_abv_resolution` (recursive walk).
2. `CREATE OR REPLACE VIEW recipe_ingredient_volumes`.
3. `CREATE OR REPLACE VIEW recipe_abv_ingredient_rows`.
4. `CREATE OR REPLACE VIEW recipe_abv`.
5. No tables, columns, or existing views are altered; migration 16's `ingredient_abv_ranges` view and trigger remain as-is.
6. The same four definitions are also added to `infrastructure/postgres/schema.sql`: fresh databases (including the py.test fixture DB) build from the canonical schema, not from migrations, so enrichment, the search join, and ignore-minor would fail there without it. Watch for definition drift the way the predecessor spec required.
7. Rollback drops the four new views in dependency order — `recipe_abv`, `recipe_abv_ingredient_rows`, `recipe_ingredient_volumes`, `ingredient_abv_resolution` — without `CASCADE`; `ingredient_abv_ranges` stays. Code rollback is out of SQL scope (matches the existing 16 rollback convention) and happens first, so older code keeps working with the views present.

Deployment ordering: apply the migration before deploying the API version that uses the views.

## Error handling

- Recipes with invalid rows or no modeled volume: `status = unknown`, null bounds, display `Unknown`, notes disclose the reason (Python renders prose from the codes).
- ABV filter with no parameters: the SQL is exactly today's; the join is not emitted.
- Malformed `min_abv > max_abv`: 400 at the API boundary; non-integer or out-of-range bounds: 422.
- View absent (unmigrated DB): search, enrichment, and ignore-minor raise — fails loudly rather than silently returning wrong data, consistent with the repository's no-silent-fallback rule.

## Testing

- **View tests** (`tests/test_recipe_abv_ranges.py` style, Postgres fixture): extend with Layer 1/2a/2b/3 assertions:
  - volume rules: each `volume_rule` and `invalid_reason` code, including a blank or whitespace-only unit name and `NaN`/`±Infinity` amounts and conversions stored in `REAL`;
  - evaluation precedence: `each`/`to top` with a missing amount stays valid, a provided non-finite amount is invalid, `amount = 0` with `to top` is a zero row rather than an assumption;
  - `REAL` normalization: `0.75` of a unit with `conversion_to_ml = 29.5735` gives `volume_ml = 22.180125` exactly;
  - constant scale: `top`/`rinse` `volume_ml` render as `88.7205` and `1`;
  - status: an `each` garnish makes an otherwise recorded recipe `estimated`; a zero-amount unknown-strength row does not;
  - an ingredientless recipe has a Layer-3 row with `unknown_reason = 'no_volume'`;
  - width cutoff at exactly 20, `narrow` boundary at exactly 1 point;
  - display columns: a midpoint of exactly `x.5` rounds up; a midpoint just below `x.5` rounds down, where a rounded quotient would have tipped it up; outward floor/ceiling including integer-valued bounds (`ceil` of exactly 15 stays 15); `<1%` sets `display_below_one` with both columns `0`; a midpoint of exactly 0 is `0%`, not `<1%`; all display columns null for every `unknown` reason;
  - `strength_display_*` for point and interval family strengths, including a sub-1% point;
  - unknown 0–100 strength; `recorded` vs `family` for a category resolving to its own subtree.
- **Ported calculator tests**: existing `tests/test_recipe_abv.py` cases move to DB-backed equivalents asserting Layer-3 `min_percent`/`max_percent`/`status` for the same scenarios, compared with `pytest.approx`.
- **Python formatting unit tests**: remain pure and fast:
  - display: the text helper's four forms (`Unknown`, `<1%`, `N%`, `N–M%`) from given integers, Decimal→finite-float conversion, no `Estimated` prefix (bare display, per `fe6733f`). The rounding cases move to the view tests, since rounding is now SQL's job;
  - notes: one note per `volume_rule`/`invalid_reason`, `Assumed … mL` text taken from `volume_ml`, every `unknown_reason` disclosure, equal-endpoint family notes (`Vodka: 40%`), first-occurrence dedup, narrow clears notes.
- **Note-order parity**: a DB-backed test with a `to top` row whose amount is null, plus measured rows, asserts the notes match the order produced by the existing ingredient query.
- **Search integration tests** (`tests/test_recipe_abv_integration.py`):
  - filtering: `min_abv`/`max_abv` on offset and keyset paths, on both `/search` and `/search/authenticated`; interval-overlap edge cases (a recipe at exactly the bound matches); display-matching cases from the filtering section (`10–15%` with raw max 14.2 matches `min_abv = 15`; narrow `15%` from midpoint 14.6 matches both bounds at 15; `<1%` matches `max_abv = 0` but not `min_abv = 1`); every returned recipe's `abv.display` falls inside the requested range; a fractional `min_abv` is rejected with 422;
  - exclusion: unknown-ABV recipes, including width>20 rows and ingredientless recipes; `min_abv = 0` excludes unknown recipes;
  - pagination correctness (no off-by-one, no skipped/duplicated recipes across pages);
  - bulk create's unchanged null-ABV response.
- **Ignore-minor**: `tests/test_inventory_ignore_minor.py` passes unchanged after the fold; add one case asserting a `NaN`-amount row is never treated as minor.
- **Frontend**: a Node test that `searchRecipes` sends `min_abv=0` when given `0` and omits both parameters when null.
- **Contract tests**: `tests/test_recipe_abv_display.mjs` and SSR template tests pass unchanged (proof the response contract held).
- **Search SQL parity**: the two builders get the same filter; a test asserts both SQL strings contain the ABV join/condition.
- Coverage gate (80%) retains; focused pytest uses `-o addopts=''`.

## Performance

- Views are plain (non-materialized) and computed per request. The planner limits how much of that work can be narrowed:
  - Layer 1's recursive CTE is always materialized, so it is computed over **all** ingredients whenever Layer 2b or 3 is read. The refactored `RESOLVE_INGREDIENT_ABV_SQL` likewise walks all ingredients instead of only the requested ids.
  - Enrichment's `recipe_id = ANY(...)` filters on a grouping column, so it narrows Layers 2a/2b/3 to the page's recipes; only Layer 1 is still computed in full.
  - With an ABV filter active, the search join cannot push `r.id` into the aggregate view, so `recipe_abv` is computed for every recipe on each filtered search.
  - Without an ABV filter, the join is not emitted at all. (Relying on the planner's join removal would not work: `recipe_abv` stacks CTEs over its `GROUP BY`, which hides the uniqueness the planner needs.)
  - Ignore-minor reads only Layer 2a and never touches the recursive walk.
- Scale is hundreds of recipes and shallow hierarchies, so these full computations are cheap; no index changes anticipated. The implementation plan includes one `EXPLAIN ANALYZE` of a filtered search and an enrichment batch against the `pg_db_with_prod_data` fixture as a sanity check, not a gate. If profiling ever disagrees, the upgrade path is materializing `recipe_abv` with a refresh hook — deliberately out of scope.

## Out of scope

- Sorting by ABV (falls out of Layer 3 later; `build_recipe_sort_spec` extension is a trivial follow-up).
- A persisted/materialized recipe-ABV column.
- Dilution/served-strength modeling.
- Changes to `ingredient_abv_ranges`, the bulk ABV values feature, or the notes API shape.
