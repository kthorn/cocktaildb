# SQL Recipe ABV Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move recipe ABV volume rules, interval math, status, and display rounding into PostgreSQL views, and add a min/max ABV search filter that matches the displayed values.

**Architecture:** Four views (`ingredient_abv_resolution` → `recipe_ingredient_volumes` → `recipe_abv_ingredient_rows` → `recipe_abv`) carry every rule once. `api/recipe_abv.py` shrinks to text formatting from view columns. Search joins `recipe_abv` only when an ABV bound is given; ignore-minor reads volumes from `recipe_ingredient_volumes`.

**Tech Stack:** PostgreSQL 15/16 views, psycopg2, FastAPI, vanilla JS, pytest with the testcontainers Postgres fixture, Node contract tests.

**Spec:** `docs/superpowers/specs/2026-10-12-sql-recipe-abv-design.md`

## Global Constraints

- `REAL` columns (`recipe_ingredients.amount`, `units.conversion_to_ml`) convert with `value::text::numeric`, never `::float8::text::numeric`.
- Top-up volume literal `88.7205`, rinse literal `1` (not `1.0`).
- Width cutoff `20` percentage points (exactly 20 is displayable); narrow when width ≤ `1`; both division-free.
- Display values are division-free using `div`/`mod` on `L = Σ(v·low)`, `H = Σ(v·high)`, `V = Σv`.
- Response contract (`status`, `min_percent`, `max_percent`, `display`, `notes`) is unchanged; bulk create still returns `abv = None`.
- Note text stays byte-identical to today's sentences in `api/recipe_abv.py`.
- Every view definition appears identically in the migration and in `infrastructure/postgres/schema.sql`.
- Focused pytest runs use `-o addopts=''`; interpreter `/home/kurtt/miniforge3/envs/cocktaildb/bin/python`.

## Review Focus

- A recipe whose only rows are `each` garnishes or zero amounts → `Unknown` with "No positive modeled liquid volume was available." (Task 2 test `test_all_excluded_recipe_is_no_volume`).
- Unit names with odd casing/whitespace (`" TO TOP "`, `"\tEach\n"`) → classified like the clean names (Task 1 test `test_unit_names_are_trimmed_and_case_folded`).
- A `to top` row with null amount ordered among measured rows → notes keep today's order (Task 3 test `test_note_order_matches_ingredient_query`).
- A signed-in user filtering by ABV → filter applies on `/search/authenticated` too (Task 5 test `test_authenticated_search_forwards_abv_bounds`).
- `min_abv=0` from the UI → sent, and hides unknown-ABV recipes (Task 6 node test plus Task 5 `test_min_abv_zero_excludes_unknown`).

---

### Task 1: Strength and volume views (Layers 1 and 2a)

**Files:**
- Create: `migrations/19_migration_add_recipe_abv_views.sql`, `migrations/rollbacks/19_rollback_recipe_abv_views.sql`
- Modify: `infrastructure/postgres/schema.sql` (after `ingredient_abv_ranges`), `api/db/sql_queries.py` (`RESOLVE_INGREDIENT_ABV_SQL`)
- Test: `tests/test_recipe_abv_views.py` (new)

**Interfaces:**
- Produces view `ingredient_abv_resolution(ingredient_id, min_percent_abv, max_percent_abv, observation_count, family_id, family_name, source, has_observations)`. Unknown rows already carry `0`, `100`, `0`.
- Produces view `recipe_ingredient_volumes(recipe_ingredient_id, recipe_id, ingredient_id, unit_name, volume_rule, invalid_reason, volume_ml, is_estimated, sort_volume)`.
- `RESOLVE_INGREDIENT_ABV_SQL` becomes `SELECT ingredient_id, min_percent_abv, max_percent_abv, observation_count, family_id, family_name, source FROM ingredient_abv_resolution WHERE ingredient_id = ANY(%(ingredient_ids)s::integer[]) ORDER BY ingredient_id`.

- [ ] **Step 1: Write failing view tests** in `tests/test_recipe_abv_views.py` using `db_instance`. A helper `_recipe(db, rows)` inserts its own units (`name`, `conversion_to_ml`) and ingredients, then a recipe, and returns the recipe id; `rows` are `(ingredient_id, unit_name_or_None, amount)`. Tests:
  - `test_volume_rules_classify_each_row`: parametrized over `(unit, conversion, amount) → (volume_rule, invalid_reason, volume_ml)`: `("ml",1,"NaN")→invalid/non_finite_amount/None`; `("ml",1,"-Infinity")→non_finite_amount`; `("ml",1,-1)→negative_amount`; `("each",None,-1)→negative_amount`; `("to top",None,0)→zero/None/Decimal("0")`; `("each",None,None)→counted/None/None`; `("to top",None,None)→top/None/Decimal("88.7205")`; `("to rinse",None,99)→rinse/None/Decimal("1")`; `(None,…,10)→missing_unit`; `("   ",1,10)→missing_unit`; `("ml",1,None)→missing_amount`; conversions `None`, `0`, `-1`, `"NaN"`, `"Infinity"` → `invalid_conversion`; `("oz",29.5735,0.75)→measured/None/Decimal("22.180125")`.
  - `test_unit_names_are_trimmed_and_case_folded`: `" TO TOP "`, `"\tEach\n"`, `" tO rInSe "` → `top`, `counted`, `rinse`.
  - `test_special_volume_literals_keep_scale`: `str(volume_ml)` is `"88.7205"` and `"1"`.
  - `test_is_estimated_only_for_counted_top_rinse`.
  - `test_resolution_view_matches_resolver_for_all_ingredients`: for the fixtures in `tests/test_recipe_abv_ranges.py`, `SELECT * FROM ingredient_abv_resolution` agrees with `RESOLVE_INGREDIENT_ABV_SQL` for every id, and unknown rows have `0`/`100`/`0`/`source='unknown'`.
- [ ] **Step 2: Run** `pytest tests/test_recipe_abv_views.py -o addopts='' -q`. Expected: FAIL, relation does not exist.
- [ ] **Step 3: Write the two views** in the migration (inside `BEGIN; … COMMIT;`) and in `schema.sql`. Layer 1 is the current resolver with `requested` replaced by all ingredients and the `COALESCE`s moved inside. Layer 2a follows the spec's eight-step `CASE`. The unit key is `NULLIF(LOWER(BTRIM(u.name, E' \t\r\n')), '')`. `amount IN ('NaN','Infinity','-Infinity')` is tested on the `REAL` value before any cast. Measured `volume_ml = ri.amount::text::numeric * u.conversion_to_ml::text::numeric`. `sort_volume = COALESCE(ri.amount * u.conversion_to_ml, 0)`. The rollback drops views in reverse order without `CASCADE` (Task 2 adds its two views to the top of the drop list). Point `RESOLVE_INGREDIENT_ABV_SQL` at the view.
- [ ] **Step 4: Run** the new tests plus `tests/test_recipe_abv_ranges.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: add SQL ingredient strength and recipe volume views`.

### Task 2: Contribution rows and recipe ABV views (Layers 2b and 3)

**Files:**
- Modify: both migration files, `infrastructure/postgres/schema.sql`
- Test: `tests/test_recipe_abv_views.py`

**Interfaces:**
- Produces `recipe_abv_ingredient_rows`: every Layer 2a column plus `ingredient_name, min_percent_abv, max_percent_abv, strength_source, contributes, strength_display_low, strength_display_high, strength_display_below_one`.
- Produces `recipe_abv(recipe_id, unknown_reason, status, min_percent, max_percent, narrow, display_low, display_high, display_below_one)`, one row per recipe. `display_*` are `integer`.

- [ ] **Step 1: Write failing tests**, with a helper `_abv(db, recipe_id)` returning the `recipe_abv` row:
  - Ported calculator scenarios, compared with `pytest.approx`: 60 ml at 40% + 5 ml unknown → `estimated`, `display_low/high = 36/45`, `min_percent ≈ 36.9230769231`. 80 ml at 0% + 20 ml unknown → `0/20`, `estimated`. Unknown with width `19.9999` → estimated, `20.0001` → `unknown`/`too_wide` with real bounds. `to top` (amount 99) at 40% + 10 ml at 0% → `min_percent ≈ 88.7205·40/98.7205`. `to rinse` → `40/11`. 30 ml unknown + 30 ml at 0% → `too_wide`, `min_percent == 0`, `max_percent ≈ 50`, display columns null.
  - `test_each_garnish_makes_recorded_recipe_estimated` and `test_zero_amount_unknown_row_does_not`.
  - `test_all_excluded_recipe_is_no_volume`: no rows, only zero rows, only `each` rows → `unknown_reason='no_volume'`, null bounds.
  - `test_invalid_row_nulls_bounds`: `unknown_reason='invalid_row'`.
  - `test_display_columns`: points `26.5→27`, `0→0` (not below one), `0.4→below_one` with both columns `0`, `14.4999999999999999999999999999→14`. Family intervals `10.1–20.1 → 10/21`, `30–30.9999 → 30/30` (narrow), `30–31 → 31/31` (narrow, midpoint 30.5 rounds up), `30–31.0001 → 30/32`, an integer bound `15–17 → 15/17`.
  - `test_narrow_uses_volume_weighted_width`: 99 ml at 30% + 1 ml unknown → narrow, `30/30`.
  - `test_strength_display_columns`: family point 40–40 → `40/40`; family 15–16 → `15/16`; point 0.4 → below one.
  - `test_category_resolving_to_own_subtree_is_family`.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Write the views.**
  - Layer 2b joins 2a to Layer 1 and `ingredients`. `contributes = volume_rule IN ('top','rinse','measured')`. The strength display rule is in the spec.
  - Layer 3 aggregates `recipes r LEFT JOIN recipe_abv_ingredient_rows` with `GROUP BY r.id`:
    - `V`, `L`, `H` are `SUM(...) FILTER (WHERE contributes)`; `has_invalid = COALESCE(bool_or(volume_rule='invalid'), false)`.
    - `unknown_reason` is `invalid_row` if `has_invalid`, else `no_volume` if `V IS NULL`, else `too_wide` if `H − L > 20·V`.
    - `status` is `unknown`, else `estimated` when `bool_or(is_estimated)` or `bool_or(contributes AND strength_source <> 'recorded')`, else `calculated`.
    - Raw bounds `L/V`, `H/V` unless `invalid_row`/`no_volume`. `narrow = H − L <= V`.
    - Display: narrow → `div(L+H+V, 2V)` for both, or `0` for both when below one (`0 < L+H AND L+H < 2V`); otherwise `div(L,V)` and `div(H,V) + (mod(H,V) > 0)::int`. Everything is cast `::integer` and null unless `unknown_reason IS NULL`.
  - Write each derived column once by stacking non-recursive CTEs inside the view.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat: compute recipe ABV interval, status, and display in SQL`.

### Task 3: Python formatting and enrichment

**Files:**
- Modify: `api/recipe_abv.py` (rewrite), `api/db/db_core.py` (`_add_recipe_abv`, imports), `api/db/sql_queries.py` (two fetch constants)
- Test: `tests/test_recipe_abv.py` (rewrite as formatting tests), `tests/test_recipe_abv_integration.py` (replace the mock-based enrichment tests), `tests/test_recipe_abv_views.py`

**Interfaces:**
- Consumes the Task 2 views.
- Produces `RECIPE_ABV_BOUNDS_SQL = "SELECT * FROM recipe_abv WHERE recipe_id = ANY(%(recipe_ids)s)"` and `RECIPE_ABV_ROWS_SQL` (the same filter on `recipe_abv_ingredient_rows`, `ORDER BY recipe_id, sort_volume DESC, recipe_ingredient_id`).
- Produces `display_text(low: int | None, high: int | None, below_one: bool | None) -> str` and `format_recipe_abv(bounds: dict, rows: list[dict]) -> dict` in `api/recipe_abv.py`.

- [ ] **Step 1: Write failing formatting tests** in `tests/test_recipe_abv.py`, built from plain dicts:
  - `display_text`: `(None,None,None)→"Unknown"`, `(0,0,True)→"<1%"`, `(27,27,False)→"27%"`, `(36,45,False)→"36–45%"`.
  - `format_recipe_abv` notes: one test per `invalid_reason` sentence; `counted` → "Excluded counted ingredient X; no liquid volume was modeled."; `top` → "Assumed 88.7205 mL for to top ingredient X."; `rinse` → "Assumed 1 mL …"; unknown strength → "Unknown strength for X; assuming 0–100%."; family → `"Blanc Vermouth: 15–16%"` and `"Vodka: 40%"`; `no_volume` and `too_wide` aggregate sentences; dedup of repeated notes; narrow clears notes; non-contributing rows give no strength notes.
  - Numbers: `min_percent`/`max_percent` come back as floats from `Decimal` input, and the zero `Decimal` becomes `0.0`.
  - Wide unknown keeps raw bounds; `invalid_row` has `None` bounds.
- [ ] **Step 2: Write failing DB-backed tests**:
  - `test_note_order_matches_ingredient_query`: a recipe with a null-amount `to top` family row plus two measured family rows; the notes follow `sort_volume DESC, id`.
  - In `tests/test_recipe_abv_integration.py`, replace the four mock tests that assume `RESOLVE_INGREDIENT_ABV_SQL`:
    - one bulk pair of queries for many recipes (`execute` called twice with the two constants);
    - SQL failures propagate;
    - a missing Layer-3 row gives `abv = None` and logs a warning;
    - an empty collection runs no query.
- [ ] **Step 3: Run** them. Expected: FAIL.
- [ ] **Step 4: Implement.**
  - `format_recipe_abv` follows the spec's Python section.
  - Delete the volume constants, `calculate_recipe_abv`, `_volume_for_ingredient`, `_point_display`, `_interval_display`, and `_as_decimal` if unused.
  - `_add_recipe_abv` collects `recipe_ids`, returns early when there are none, runs the two queries, groups rows by `recipe_id`, and sets each `recipe["abv"]`.
  - Drop the `calculate_recipe_abv` import and the `RESOLVE_INGREDIENT_ABV_SQL` import from `db_core.py`.
- [ ] **Step 5: Run** `tests/test_recipe_abv*.py tests/test_page_route_contracts.py tests/test_frontend_node.py`. Expected: PASS, with `test_get_and_search_paths_include_matching_abv_payload` unchanged.
- [ ] **Step 6: Commit** `refactor: format recipe ABV from SQL views`.

### Task 4: Fold ignore-minor onto the volume view

**Files:**
- Modify: `api/db/sql_queries.py` (`build_inventory_filter_sql`; delete `_recipe_ingredient_volume_ml` and the `recipe_abv` import)
- Test: `tests/test_inventory_ignore_minor.py`

**Interfaces:** consumes `recipe_ingredient_volumes.volume_ml` and `recipe_ingredient_id`.

- [ ] **Step 1: Add the failing test** `test_non_finite_amount_is_never_minor`: a recipe with Rum 2 oz plus an unowned ingredient at `'NaN'` ounces is absent under `ignore_minor`.
- [ ] **Step 2: Run** it. Expected: FAIL, because the helper treats the NaN product as comparable.
- [ ] **Step 3: Implement.** In `minor_skip`, compare `(SELECT v.volume_ml FROM recipe_ingredient_volumes v WHERE v.recipe_ingredient_id = ri_missing.id)` against `MINOR_INGREDIENT_MAX_FRACTION * (SELECT SUM(v.volume_ml) FROM recipe_ingredient_volumes v WHERE v.recipe_id = r_inv.id)`, keeping the `COALESCE(…, FALSE)` wrapper. Remove the `u_missing` join if nothing else uses it.
- [ ] **Step 4: Run** `tests/test_inventory_ignore_minor.py`. Expected: all PASS.
- [ ] **Step 5: Commit** `refactor: read ignore-minor volumes from the SQL volume view`.

### Task 5: Search filter, db plumbing, and routes

**Files:**
- Modify: `api/db/sql_queries.py` (both builders gain `abv_filter: bool = False`), `api/db/db_core.py` (query params and builder calls), `api/routes/recipes.py` (both endpoints)
- Test: `tests/test_recipe_abv_integration.py`

**Interfaces:**
- `build_search_recipes_paginated_sql(..., ignore_minor=False, abv_filter=False)`, and the same for `build_search_recipes_keyset_sql`.
- `search_params["min_abv"]` / `["max_abv"]` are `int`; `query_params` always carries both keys.

- [ ] **Step 1: Write failing tests:**
  - `test_both_builders_emit_abv_join_only_when_filtering`: the string `recipe_abv rab` is present with `abv_filter=True` and absent by default, for both builders.
  - `test_abv_filter_matches_displayed_range`, parametrized over offset/keyset/random. Recipes display `10–15%` (raw 10.4–14.2), `15%` (narrow, midpoint 14.6), `<1%`, `40%`, a too-wide `Unknown`, and an ingredientless recipe. Expected matches:

    | Bounds | Matches |
    |---|---|
    | `min=15` | `10–15%`, `15%`, `40%` |
    | `max=15` | `10–15%`, `15%`, `<1%` |
    | `min=15,max=15` | `10–15%`, `15%` |
    | `max=0` | `<1%` |
    | `min=1` | excludes `<1%` |

    Every returned recipe's `abv.display` is in range.
  - `test_min_abv_zero_excludes_unknown`.
  - `test_abv_filter_paginates_without_gaps`: walk keyset pages with `limit=1`; the union equals the unpaged result with no duplicates.
  - API: `/recipes/search?min_abv=20&max_abv=10` → 400; `min_abv=12.5` → 422; `min_abv=101` → 422.
  - `test_authenticated_search_forwards_abv_bounds`, using `editor_client_with_data`.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - When `abv_filter` is set, the builders append `LEFT JOIN recipe_abv rab ON rab.recipe_id = r.id` after the existing joins, plus the spec's three conditions on `display_low`/`display_high`.
  - `_search_recipes_paginated` adds `min_abv`/`max_abv` to `query_params` and passes `abv_filter=search_params.get("min_abv") is not None or search_params.get("max_abv") is not None`.
  - Routes declare `min_abv: int | None = Query(None, ge=0, le=100, description="Minimum displayed ABV percent")` (same for max), raise `ValidationException("min_abv must be less than or equal to max_abv")` when both are set and out of order, and add them to `search_params` when not `None`. `/search/authenticated` declares and forwards both.
- [ ] **Step 4: Run** the new tests plus `tests/test_recipe_abv_integration.py tests/test_inventory_ignore_minor.py tests/test_fastapi.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: filter recipe search by displayed ABV`.

### Task 6: Frontend filter inputs

**Files:**
- Modify: `src/web/search.html` (inputs in the rating filter row), `src/web/js/search.js` (`buildSearchQuery`, reset handler), `src/web/js/api.js` (`searchRecipes`), `tests/test_frontend_node.py` (register the new script)
- Test: `tests/test_search_abv_params.mjs` (new; follows the `tests/test_groups.mjs` config/localStorage setup and stubs `globalThis.fetch` to capture the URL)

- [ ] **Step 1: Write the failing node test.**
  - `searchRecipes({min_abv: 0, max_abv: 15})` puts `min_abv=0&max_abv=15` in the URL, for both the signed-in (`/recipes/search/authenticated`) and anonymous (`/recipes/search`) paths.
  - `searchRecipes({min_abv: null})` sends neither parameter.
- [ ] **Step 2: Run** `node tests/test_search_abv_params.mjs`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Inputs `#min-abv-search` / `#max-abv-search`: `type="number" min="0" max="100" step="1"`, with help text "Matches the ABV shown on each recipe; recipes with unknown ABV are hidden."
  - `buildSearchQuery` sets `query.min_abv = Number(input.value)` when `input.value !== ''`. The reset handler clears both inputs.
  - `api.js` appends each parameter when it is `!= null`.
- [ ] **Step 4: Run** the node test, `pytest tests/test_frontend_node.py -o addopts=''`, and `npm run build && npm run test:build`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: add ABV range inputs to recipe search`.

### Task 7: Verification and docs

- [ ] **Step 1:** Update the spec where implementation settled details:
  - `min_abv > max_abv` returns 400 via `ValidationException`, matching the route's other cross-field checks;
  - the join is emitted only when filtering;
  - Layer 1 carries the `COALESCE`d bounds;
  - sequencing is a PR stacked on #116.
- [ ] **Step 2:** Run `EXPLAIN ANALYZE` on a filtered search and an enrichment batch against `pg_db_with_prod_data` if `PROD_BACKUP_PATH` is available, and record the timings in the PR. This is a sanity check, not a gate.
- [ ] **Step 3:** Run the full suite (`pytest -q`), the README release gate, and `pre_commit run --all-files`. Compare against the baseline; only the known rating aggregation failure may remain.
- [ ] **Step 4: Commit** `docs: align SQL recipe ABV spec with implementation`.
