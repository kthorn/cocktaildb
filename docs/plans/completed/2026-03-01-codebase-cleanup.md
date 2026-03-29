# Codebase Cleanup Implementation Plan

**Status:** Refined

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove dead code, fix duplication bugs, and clean up stale files across the entire codebase.

**Architecture:** Surgical deletions and targeted edits across API, frontend, tests, and infrastructure. No new features or abstractions — pure removal and correction.

**Tech Stack:** Python/FastAPI, vanilla JavaScript, PostgreSQL, pytest

---

### Task 1: Fix duplicate analytics route handler (bug)

**Files:**
- Modify: `api/routes/analytics.py:252-277`

**Step 1: Delete the second (dead) route handler**

Remove lines 252-277 — the duplicate `@router.get("/recipe-distances-em/download")` / `download_em_recipe_distances()`. FastAPI silently ignores it since the first handler (lines 225-249) already registers this path.

**Step 2: Verify API imports cleanly**

Run: `cd api && python -c "from routes.analytics import router; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add api/routes/analytics.py
git commit -m "fix: remove duplicate /recipe-distances-em/download route handler"
```

---

### Task 2: Fix duplicate save_em_distance_matrix call and imports (bug)

**Files:**
- Modify: `api/db/db_analytics.py:435-439, 588-597`

**Step 1: Remove duplicate import at line 435**

Delete line 435 (`from utils.analytics_files import save_em_distance_matrix`) — it's redundant with the combined import at lines 436-439.

**Step 2: Remove duplicate save call at lines 593-597**

Delete lines 593-597 (the second `storage_path = os.environ.get(...)` / `save_em_distance_matrix(...)` block). Keep lines 588-592.

**Step 3: Remove unused top-level `import os` at line 4**

The function-local `import os` at line 423 is the one actually used.

**Step 4: Remove unused `emd_matrix` import at line 429**

Remove `emd_matrix,` from the `from barcart import (...)` block (lines 425-432). Only `em_fit` is called.

**Step 5: Verify**

Run: `cd api && python -c "from db.db_analytics import AnalyticsQueries; print('OK')"`
Expected: `OK`

**Step 6: Commit**

```bash
git add api/db/db_analytics.py
git commit -m "fix: remove duplicate distance matrix save call and unused imports in db_analytics"
```

---

### Task 3: Rename rollback migration to prevent auto-application

**Files:**
- Move: `migrations/08_rollback_substitution_level_to_boolean.sql` → `migrations/rollbacks/08_rollback_substitution_level_to_boolean.sql`

**Step 1: Create rollbacks directory and move file**

```bash
mkdir -p migrations/rollbacks
mv migrations/08_rollback_substitution_level_to_boolean.sql migrations/rollbacks/
```

The migration runner (`infrastructure/scripts/run-migrations.sh:54`) globs `migrations/*.sql` — the `rollbacks/` subdirectory won't be picked up.

**Step 2: Verify rollback file is excluded from migration glob**

Run: `ls migrations/*.sql | grep -c rollback`
Expected: `0` (the rollback file should not appear in the top-level glob)

**Step 3: Commit**

```bash
git add migrations/
git commit -m "fix: move rollback migration to subdirectory to prevent auto-application"
```

---

### Task 4: Remove dead Database methods

**Files:**
- Modify: `api/db/db_core.py`

**Step 1: Delete these methods not called by application code (work bottom-up to preserve line numbers)**

1. `_get_recipe_private_tags()` — lines 1840-1862
2. `_get_recipe_public_tags()` — lines 1820-1838
3. `get_recipe_ratings()` — lines 1358-1375
4. `get_unit_by_name_or_abbreviation()` — lines 1166-1171
5. `get_recipes_with_ingredients()` — lines 905-960
6. `execute_transaction()` — lines 129-152

**Step 2: Remove test code that exercises the deleted methods**

These methods are tested directly in the test suite. Remove or update the affected tests:

- `tests/test_db_units.py`: Remove the 4 `test_get_unit_by_name_or_abbreviation_*` tests
- `tests/test_db_ratings.py`: Delete `test_get_recipe_ratings` entirely. In `test_ratings_crud_full_lifecycle`, replace `db.get_recipe_ratings(recipe["id"])` with `db.get_recipe(recipe["id"])["rating_count"]` to verify ratings exist via the aggregated field
- `tests/test_db_tags.py`: Replace `db._get_recipe_public_tags(recipe_id)` calls with direct SQL queries (`SELECT t.name FROM tags t JOIN recipe_tags rt ON t.id = rt.tag_id WHERE rt.recipe_id = %s AND t.is_private = 0`). Replace `db._get_recipe_private_tags(recipe_id, user_id)` similarly (with `is_private = 1 AND t.created_by = %s`). Use `db.execute_query()` for these assertions.
- `tests/test_db_edge_cases.py`: Remove the `test_execute_transaction_*` test(s)
- `tests/test_db_integration.py`: Replace `db.get_recipe_ratings(recipe["id"])` with `db.get_recipe(recipe["id"])["rating_count"]`

**Step 3: Verify**

Run: `cd api && python -c "from db.db_core import Database; print('OK')"`
Expected: `OK`

**Step 4: Run tests**

Run: `python -m pytest tests/ -x -q`
Expected: All pass

**Step 5: Commit**

```bash
git add api/db/db_core.py tests/
git commit -m "chore: remove 6 unused Database methods and their direct test references"
```

---

### Task 5: Remove dead SQL query

**Files:**
- Modify: `api/db/sql_queries.py:127-181`

**Step 1: Delete `get_recipes_paginated_with_ingredients_sql`**

Remove the entire constant definition (lines 127-181). It's never imported or referenced.

**Step 2: Verify**

Run: `cd api && python -c "from db.sql_queries import *; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add api/db/sql_queries.py
git commit -m "chore: remove unused get_recipes_paginated_with_ingredients_sql query"
```

---

### Task 6: Remove unused API models

**Files:**
- Modify: `api/models/responses.py`
- Modify: `api/models/requests.py`

**Step 1: From `responses.py`, delete these classes:**

1. `PaginatedRecipeListResponse` — lines 229-236
2. `SearchResultsResponse` — lines 172-181
3. `RecipeListResponse` — lines 119-131

Work bottom-up. `SearchResultsResponse` references `RecipeListResponse`, so both must go. `PaginatedRecipeListResponse` also references `RecipeListResponse`.

**Step 2: From `requests.py`, delete these classes:**

1. `SearchParams` — lines 220-231
2. `RecipeListParams` — lines 211-217
3. `PaginationParams` — lines 199-208
4. `RecipeSearchRequest` — lines 160-168

Work bottom-up.

**Step 3: Verify**

Run: `cd api && python -c "from models.responses import *; from models.requests import *; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add api/models/responses.py api/models/requests.py
git commit -m "chore: remove 7 unused Pydantic request/response models"
```

---

### Task 7: Remove unused exceptions, imports, and config fields

**Files:**
- Modify: `api/core/exceptions.py:3, 37-48`
- Modify: `api/core/config.py:16, 21`
- Modify: `api/core/exception_handlers.py` (delete `http_exception_handler` function)
- Modify: `api/main.py:25`

**Step 1: In `exceptions.py`**

- Line 3: Change `from typing import Optional, Any, Dict` to `from typing import Optional`
- Delete `AuthenticationException` class (lines 37-41) and `AuthorizationException` class (lines 44-48)

**Step 2: In `config.py`**

- Delete line 16 (`aws_region: str = ...`)
- Delete line 21 (`backup_bucket: str = ...`)

**Step 3: In `main.py`**

- Delete `http_exception_handler,` from the import block at line 25

**Step 4: In `exception_handlers.py`**

- Delete the `http_exception_handler` function (the one handling `HTTPException`) — it's only imported by `main.py` which we're cleaning, and `starlette_http_exception_handler` is the one actually registered
- Also remove the now-unused `from fastapi.exceptions import HTTPException` import if it's only used by the deleted function

**Step 5: Verify**

Run: `cd api && python -c "from main import app; print('OK')"`
Expected: `OK`

**Step 6: Commit**

```bash
git add api/core/exceptions.py api/core/config.py api/core/exception_handlers.py api/main.py
git commit -m "chore: remove unused exceptions, config fields, and imports"
```

---

### Task 8: Remove unused imports in recipes.py and reduce verbose logging

**Files:**
- Modify: `api/routes/recipes.py:15-36, 307-321`

**Step 1: Remove unused imports**

From the `models.requests` import block (lines 15-20), remove `RatingCreate`.
From the `models.responses` import block (lines 21-30), remove `RatingSummaryResponse` and `RatingResponse`.
Delete the entire `from .rating_handlers import (...)` block (lines 32-36).

**Step 2: Reduce verbose logging in `get_recipe()`**

Lines 307-321: Remove or downgrade the debug noise. Keep only the warning for recipe-not-found. Remove:
- `logger.info(f"Getting recipe {recipe_id}")` (line 307)
- `logger.info(f"Database instance: {db}")` (line 308)
- `logger.info(f"User info: {user}")` (line 309) — privacy concern
- `logger.info(f"Resolved user_id: {user_id}")` (line 312)
- `logger.info(f"Recipe retrieved: {recipe is not None}")` (line 315)
- `logger.info(f"Returning recipe: ...")` (line 321)

Keep: `logger.warning(f"Recipe {recipe_id} not found")` (line 318)

**Step 3: Verify**

Run: `cd api && python -c "from routes.recipes import router; print('OK')"`
Expected: `OK`

**Step 4: Run tests**

Run: `python -m pytest tests/ -x -q`
Expected: All pass

**Step 5: Commit**

```bash
git add api/routes/recipes.py
git commit -m "chore: remove unused rating imports and excessive debug logging from recipes route"
```

---

### Task 9: Remove boto3 from API requirements

**Files:**
- Modify: `api/requirements.txt:7`

**Step 1: Remove `boto3>=1.29.0`**

boto3 is not imported anywhere in `api/`. It's only used by `scripts/generate_config.py` (which runs locally, not in the API container).

**Step 2: Update `README.md` to clarify boto3 is a local script dependency**

Change the boto3 prerequisite line to clarify it's only needed for `scripts/generate_config.py`, not for running the API.

**Step 3: Commit**

```bash
git add api/requirements.txt README.md
git commit -m "chore: remove unused boto3 dependency from API requirements"
```

---

### Task 10: Frontend dead imports and exports cleanup

**Files:**
- Modify: `src/web/js/search.js:2`
- Modify: `src/web/js/recipeCard.js:588-603`
- Modify: `src/web/js/analytics.js:36, 556-563`
- Modify: `src/web/js/desktopNav.js:6, 367-415`
- Modify: `src/web/js/mobileBottomNav.js:185-233`
- Modify: `src/web/js/mobileHamburgerMenu.js:7, 392-411`
- Modify: `src/web/js/navigation.js:129, 200-208, 225-227, 292-297`

**Step 1: `search.js` — remove `createProgressiveRecipeLoader` and `createRecipeCard` from import at line 2**

`createRecipeCard` is imported but never used in `search.js` (only `displayRecipes` is called). Change line 2 from:
```js
import { displayRecipes, createProgressiveRecipeLoader, createRecipeCard } from './recipeCard.js';
```
to:
```js
import { displayRecipes } from './recipeCard.js';
```

**Step 2: `recipeCard.js` — remove `appendRecipes` and `createProgressiveRecipeLoader` exports (lines 588-603)**

First verify: `grep -rn "createProgressiveRecipeLoader\|appendRecipes" src/web/js/ --include="*.js"` — after the Step 1 edit, these should only appear in `recipeCard.js` itself. Remove both functions.

**Step 3: `analytics.js` — remove `highlightActiveNav` (lines 556-563) and its call at line 36**

The nav component system already handles active-state highlighting.

**Step 4: `desktopNav.js` — remove unused import and dead methods**

- Line 6: remove `getNavigationItems` from import
- Lines 367-415: remove `updateActiveItem()`, `findItemIdByHref()`, `destroy()`

**Step 5: `mobileBottomNav.js` — remove dead methods and resulting dead import**

- Lines 185-233: remove `destroy()`, `updateActiveItem()`, `findItemIdByHref()`
- After removing these methods, `NAV_CONFIG` (line 3) is no longer used — remove it from the import block

**Step 6: `mobileHamburgerMenu.js` — remove unused import and dead method**

- Line 7: remove `getNavigationItems` from import
- Lines 392-411: remove `destroy()`

**Step 7: `navigation.js` — remove unused exports**

- `getNavigationItemById` (lines 200-208)
- `isMobileViewport` (lines 225-227)
- `NAV_Z_INDEX` (lines 292-297)

Keep `getNavigationItems` (line 129) — it IS imported by `mobileBottomNav.js`.

**Step 8: Commit**

```bash
git add src/web/js/
git commit -m "chore: remove dead JS imports, exports, and unused nav methods"
```

---

### Task 11: Remove dead exclude_unrated feature

**Files:**
- Modify: `src/web/js/search.js:403-407`
- Modify: `src/web/search.html:41-46`
- Modify: `src/web/styles.css` (remove `.unrated-filter` rules)

**Step 1: Remove query-building code in `search.js`**

Delete lines 403-407 (the `exclude_unrated` block in `buildSearchQuery()`).

**Step 2: Remove checkbox HTML in `search.html`**

Delete lines 41-46 (the `.unrated-filter` div with the checkbox).

**Step 3: Remove `.unrated-filter` CSS in `styles.css`**

Delete the `.unrated-filter` and `.unrated-filter label` rules (lines 2152-2159) — the HTML they style is being removed in Step 2.

**Step 4: Commit**

```bash
git add src/web/js/search.js src/web/search.html src/web/styles.css
git commit -m "chore: remove dead exclude_unrated feature (never wired to API)"
```

---

### Task 12: Remove redundant script tags and fix CSS class mismatch

**Files:**
- Modify: `src/web/index.html:40-41`
- Modify: `src/web/search.html:125-126`
- Modify: `src/web/recipe.html:30-31`
- Modify: `src/web/js/user-ingredients.js:577, 580`

**Step 1: Remove redundant `<script>` tags**

From each HTML file, remove the top-level `<script type="module" src="js/api.js">` and `<script type="module" src="js/recipeCard.js">` tags. These modules are already imported by the page-specific JS modules.

**Step 2: ~~Remove dead `.modal-footer` CSS rules~~ — KEEP these**

`.modal-footer` is still used by `analytics.html:279`. Do NOT delete these CSS rules.

**Step 3: Fix `btn-sm` → `btn-small` in `user-ingredients.js`**

Lines 577, 580: Change `btn-sm` to `btn-small` to match the existing CSS class.

**Step 4: Commit**

```bash
git add src/web/index.html src/web/search.html src/web/recipe.html src/web/js/user-ingredients.js
git commit -m "chore: remove redundant script tags, fix btn-sm class mismatch"
```

---

### Task 13: Test cleanup

**Files:**
- Delete: `tests/test_analytics_routes.py`
- Modify: `tests/conftest.py:34`
- Modify: `tests/test_fastapi.py:73-81`

**Step 1: Delete `tests/test_analytics_routes.py`**

The file has zero test functions — only a comment about disabled tests with an outdated reason.

**Step 2: In `conftest.py`, remove or update `PROD_BACKUP_PATH`**

Line 34: `PROD_BACKUP_PATH = Path("/home/kurtt/cocktaildb/backup-2025-12-25_08-08-15.sql.gz")` — hardcoded absolute path. Change to use an environment variable with `None` default (NOT empty string, since `Path("")` resolves to `Path(".")` which always exists and would break the skip logic):

```python
_backup_env = os.environ.get("PROD_BACKUP_PATH")
PROD_BACKUP_PATH = Path(_backup_env) if _backup_env else None
```

Update the fixture that uses it (line 170) to check `if PROD_BACKUP_PATH is None or not PROD_BACKUP_PATH.is_file():` before skipping.

**Step 3: In `test_fastapi.py`, remove local `test_settings` fixture (lines 73-81)**

It shadows the conftest version and contains stale SQLite `:memory:` reference.

**Step 4: Run tests**

Run: `python -m pytest tests/ -x -q`
Expected: All pass

**Step 5: Commit**

```bash
git add tests/
git commit -m "chore: remove empty test file, stale fixture, and hardcoded path in tests"
```

---

### Task 14: Remove stale root-level and infrastructure files

**Files:**
- Delete: `test_emd_speedup.py`, `test_pot_parallelization.py`
- Delete: `known_abv.json`, `leaf_ingredients.csv`, `leaf_ingredients_with_abv.csv`, `need_abv_search.csv`, `spirits_to_search.csv`
- Delete: `schema-deploy/` directory
- Delete: `infrastructure/scripts/migrate-sqlite-to-postgres.py`
- Delete: `infrastructure/ansible/playbooks/migrate-data.yml`

**Step 1: Delete ad-hoc experiment scripts**

```bash
rm test_emd_speedup.py test_pot_parallelization.py
```

**Step 2: Delete research data artifacts**

```bash
rm known_abv.json leaf_ingredients.csv leaf_ingredients_with_abv.csv need_abv_search.csv spirits_to_search.csv
```

**Step 3: Delete old SQLite schema directory**

```bash
rm -rf schema-deploy/
```

**Step 4: Delete historical one-time migration scripts**

```bash
rm infrastructure/scripts/migrate-sqlite-to-postgres.py
rm infrastructure/ansible/playbooks/migrate-data.yml
```

**Step 5: Clean stale `__pycache__` directories**

```bash
rm -rf __pycache__/
rm -rf api/__pycache__/
```

**Step 6: Update documentation references to deleted files**

- `docs/operations-runbook.md:142`: Remove or update the line referencing `playbooks/migrate-data.yml` (the migration is complete and the playbook is being deleted)
- `TESTING.md:122`: Update the reference to `schema-deploy/schema.sql` — change to `infrastructure/postgres/schema.sql` (the current PostgreSQL schema location)
- `docs/substitution-logic.md:295`: Update the reference to `schema-deploy/schema.sql` — change to `infrastructure/postgres/schema.sql`

**Step 7: Commit**

Stage explicit paths only (avoid `git add -A` which can pick up unrelated files):

```bash
git rm test_emd_speedup.py test_pot_parallelization.py
git rm known_abv.json leaf_ingredients.csv leaf_ingredients_with_abv.csv need_abv_search.csv spirits_to_search.csv
git rm -rf schema-deploy/
git rm infrastructure/scripts/migrate-sqlite-to-postgres.py
git rm infrastructure/ansible/playbooks/migrate-data.yml
git add docs/operations-runbook.md TESTING.md docs/substitution-logic.md
git commit -m "chore: remove stale experiment scripts, research artifacts, and historical migration tooling"
```

---

### Task 15: Barcart package cleanup

**Files:**
- Modify: `packages/barcart/barcart/distance.py:558-572, 1082-1083`

**Step 1: Remove joblib ImportError fallback**

In the `emd_matrix` function, the `try/except ImportError` block for joblib (lines 558-572) has a fallback that duplicates the sequential path. Since joblib is a required dependency, remove the try/except wrapper and just import joblib directly.

Change from:
```python
try:
    from joblib import Parallel, delayed
except ImportError:
    # sequential fallback (duplicate of above)
    ...
```
to:
```python
from joblib import Parallel, delayed
```

(keeping only the parallel path)

**Step 2: Remove commented-out code at lines 1082-1083**

Delete the two commented-out lines referencing non-existent variables (`C_out`, `prior_blend`, `cost_matrix`).

**Step 3: Run barcart tests**

Run: `cd packages/barcart && pytest tests/ -x -q`
Expected: All pass

**Step 4: Commit**

```bash
git add packages/barcart/
git commit -m "chore: remove dead joblib fallback and commented-out code in barcart distance"
```

---

### Task 16: Final verification

**Step 1: Run full test suite**

Run: `python -m pytest tests/ -x -q`
Expected: All pass

**Step 2: Run barcart tests**

Run: `cd packages/barcart && pytest tests/ -x -q`
Expected: All pass

**Step 3: Verify API starts cleanly**

Run: `cd api && python -c "from main import app; print('OK')"`
Expected: `OK`

**Step 4: Grep for dangling references**

```bash
# Check for references to deleted functions
grep -r "execute_transaction\|get_recipes_with_ingredients\|get_recipe_ratings\|get_unit_by_name_or_abbreviation\|_get_recipe_public_tags\|_get_recipe_private_tags" api/ --include="*.py" | grep -v __pycache__
grep -r "AuthenticationException\|AuthorizationException" api/ --include="*.py" | grep -v __pycache__
grep -r "RecipeListResponse\|SearchResultsResponse\|PaginatedRecipeListResponse\|RecipeSearchRequest\|PaginationParams\|RecipeListParams\|SearchParams" api/ --include="*.py" | grep -v __pycache__
```
Expected: No matches (or only the deletion diffs)
