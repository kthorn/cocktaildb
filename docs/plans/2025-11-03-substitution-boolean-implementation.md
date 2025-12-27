# Boolean Substitution System Implementation Plan

> **LEGACY DOCUMENT**: This plan was implemented in November 2025 when the codebase used SQLite. The substitution system now runs on PostgreSQL. SQLite references here are historical.

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace 3-level integer substitution system with boolean `allow_substitution` field

**Architecture:** Database schema migration, update CRUD operations and matching queries, simplify API models, replace frontend dropdown with checkbox

**Tech Stack:** SQLite, Python/FastAPI, Pydantic, Vanilla JavaScript

**Related:** bd-53, fixes bd-65 (ingredient recommendations bug)

---

## Task 1: Create Database Migration Script

**Files:**
- Create: `migrations/08_migration_substitution_level_to_boolean.sql`

**Step 1: Write migration SQL file**

Create file `migrations/08_migration_substitution_level_to_boolean.sql`:

```sql
-- Migration: Convert substitution_level (INTEGER) to allow_substitution (BOOLEAN)
-- Date: 2025-11-03
-- Issue: bd-53

BEGIN TRANSACTION;

-- Add new column with default false
ALTER TABLE ingredients ADD COLUMN allow_substitution BOOLEAN NOT NULL DEFAULT 0;

-- Populate: Conservative mapping (only explicit 1 or 2 → true)
UPDATE ingredients
SET allow_substitution = CASE
  WHEN substitution_level IN (1, 2) THEN 1
  ELSE 0
END;

-- Drop old column
ALTER TABLE ingredients DROP COLUMN substitution_level;

COMMIT;
```

**Step 2: Create rollback script**

Create file `migrations/08_rollback_substitution_level_to_boolean.sql`:

```sql
-- Rollback: Revert allow_substitution (BOOLEAN) back to substitution_level (INTEGER)
-- Date: 2025-11-03
-- Issue: bd-53

BEGIN TRANSACTION;

ALTER TABLE ingredients ADD COLUMN substitution_level INTEGER DEFAULT 0;

UPDATE ingredients
SET substitution_level = CASE
  WHEN allow_substitution = 1 THEN 1
  ELSE 0
END;

ALTER TABLE ingredients DROP COLUMN allow_substitution;

COMMIT;
```

**Step 3: Commit migration scripts**

```bash
git add migrations/08_migration_substitution_level_to_boolean.sql migrations/08_rollback_substitution_level_to_boolean.sql
git commit -m "feat: add migration script for boolean substitution system

- Conservative mapping: level 1,2 → true, rest → false
- Includes rollback script for safety
- Part of bd-53

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: Update Database CRUD Operations (db_core.py)

**Files:**
- Modify: `api/db/db_core.py:274-281` (create_ingredient)
- Modify: `api/db/db_core.py:306-308` (create_ingredient SELECT)
- Modify: `api/db/db_core.py:407-410` (update_ingredient substitution handling)
- Modify: `api/db/db_core.py:445-448` (update_ingredient substitution handling)
- Modify: `api/db/db_core.py:463-464` (update_ingredient SELECT)
- Modify: `api/db/db_core.py:524` (get_all_ingredients SELECT)
- Modify: `api/db/db_core.py:555` (search_ingredients exact SELECT)
- Modify: `api/db/db_core.py:568` (search_ingredients partial SELECT)
- Modify: `api/db/db_core.py:596` (search_ingredients_by_names SELECT)
- Modify: `api/db/db_core.py:655` (get_ingredient SELECT)

**Step 1: Update create_ingredient INSERT statement**

In `api/db/db_core.py` around line 274, change:

```python
# OLD
cursor.execute(
    """
    INSERT INTO ingredients (name, description, parent_id, substitution_level)
    VALUES (:name, :description, :parent_id, :substitution_level)
    """,
    {
        "name": data.get("name"),
        "description": data.get("description"),
        "parent_id": data.get("parent_id"),
        "substitution_level": data.get("substitution_level"),
    },
)

# NEW
cursor.execute(
    """
    INSERT INTO ingredients (name, description, parent_id, allow_substitution)
    VALUES (:name, :description, :parent_id, :allow_substitution)
    """,
    {
        "name": data.get("name"),
        "description": data.get("description"),
        "parent_id": data.get("parent_id"),
        "allow_substitution": data.get("allow_substitution", False),
    },
)
```

**Step 2: Update all SELECT statements to use allow_substitution**

Find and replace all occurrences in `db_core.py`:

```python
# OLD pattern
"SELECT id, name, description, parent_id, path, substitution_level FROM ingredients"

# NEW pattern
"SELECT id, name, description, parent_id, path, allow_substitution FROM ingredients"
```

Specific lines to update:
- Line 306: `create_ingredient` fetch
- Line 463: `update_ingredient` fetch
- Line 524: `get_all_ingredients`
- Line 555: `search_ingredients` exact match
- Line 568: `search_ingredients` partial match
- Line 596: `search_ingredients_by_names`
- Line 655: `get_ingredient`

**Step 3: Update update_ingredient substitution handling**

Around lines 407-410 and 445-448, change:

```python
# OLD
# Handle substitution_level explicitly to allow None values
if "substitution_level" in data:
    set_clauses.append("substitution_level = :substitution_level")
    query_params["substitution_level"] = data.get("substitution_level")

# NEW
# Handle allow_substitution explicitly
if "allow_substitution" in data:
    set_clauses.append("allow_substitution = :allow_substitution")
    query_params["allow_substitution"] = data.get("allow_substitution")
```

**Step 4: Run existing tests to verify breakage**

```bash
python -m pytest tests/test_db.py -v -k ingredient
```

Expected: FAIL - tests will fail because schema doesn't match yet (migration not applied)

**Step 5: Commit db_core.py changes**

```bash
git add api/db/db_core.py
git commit -m "refactor: update db_core.py for boolean substitution

- Replace substitution_level with allow_substitution
- Update all SELECT statements
- Update INSERT/UPDATE operations
- Default to False if not provided
- Part of bd-53

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: Update API Request Models

**Files:**
- Modify: `api/models/requests.py:13-15` (IngredientCreate)
- Modify: `api/models/requests.py:26-28` (IngredientUpdate)
- Modify: `api/models/requests.py:168-170` (BulkIngredientCreate)

**Step 1: Update IngredientCreate model**

In `api/models/requests.py` around line 13:

```python
# OLD
substitution_level: Optional[int] = Field(
    None, description="Substitution level: 0=no substitution, 1=parent-level, 2=grandparent-level, null=inherit"
)

# NEW
allow_substitution: bool = Field(
    default=False,
    description="Whether this ingredient can be substituted with siblings/ancestors"
)
```

**Step 2: Update IngredientUpdate model**

Around line 26:

```python
# OLD
substitution_level: Optional[int] = Field(
    None, description="Substitution level: 0=no substitution, 1=parent-level, 2=grandparent-level, null=inherit"
)

# NEW
allow_substitution: Optional[bool] = Field(
    None,
    description="Whether this ingredient can be substituted with siblings/ancestors"
)
```

**Step 3: Update BulkIngredientCreate model**

Around line 168:

```python
# OLD
substitution_level: Optional[int] = Field(
    None, description="Substitution level: 0=no substitution, 1=parent-level, 2=grandparent-level, null=inherit"
)

# NEW
allow_substitution: Optional[bool] = Field(
    default=False,
    description="Whether this ingredient can be substituted with siblings/ancestors"
)
```

**Step 4: Commit request model changes**

```bash
git add api/models/requests.py
git commit -m "refactor: update request models for boolean substitution

- Replace substitution_level with allow_substitution in all models
- Change from Optional[int] to bool/Optional[bool]
- Update field descriptions
- Part of bd-53

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: Update API Response Models

**Files:**
- Modify: `api/models/responses.py:14` (IngredientResponse)
- Modify: `api/models/responses.py:344` (IngredientRecommendationResponse)

**Step 1: Update IngredientResponse model**

In `api/models/responses.py` around line 14:

```python
# OLD
substitution_level: Optional[int] = Field(None, description="Substitution level: 0=no substitution, 1=parent-level, 2=grandparent-level, null=inherit")

# NEW
allow_substitution: bool = Field(..., description="Whether this ingredient can be substituted with siblings/ancestors")
```

**Step 2: Update IngredientRecommendationResponse model**

Around line 344:

```python
# OLD
substitution_level: Optional[int] = Field(None, description="Substitution level")

# NEW
allow_substitution: bool = Field(..., description="Whether this ingredient can be substituted with siblings/ancestors")
```

**Step 3: Commit response model changes**

```bash
git add api/models/responses.py
git commit -m "refactor: update response models for boolean substitution

- Replace substitution_level with allow_substitution
- Change from Optional[int] to bool
- Update field descriptions
- Part of bd-53

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: Update Route Handlers

**Files:**
- Modify: `api/routes/ingredients.py:329` (create_ingredient data mapping)
- Modify: `api/routes/user_ingredients.py:186` (recommendations response mapping)

**Step 1: Update ingredients route handler**

In `api/routes/ingredients.py` around line 329:

```python
# OLD
{
    "name": ingredient_data.name,
    "description": ingredient_data.description,
    "parent_id": parent_id,
    "substitution_level": ingredient_data.substitution_level,
    "created_by": user.user_id,
}

# NEW
{
    "name": ingredient_data.name,
    "description": ingredient_data.description,
    "parent_id": parent_id,
    "allow_substitution": ingredient_data.allow_substitution,
    "created_by": user.user_id,
}
```

**Step 2: Update user_ingredients route handler**

In `api/routes/user_ingredients.py` around line 186:

```python
# OLD
substitution_level=rec.get("substitution_level"),

# NEW
allow_substitution=rec.get("allow_substitution", False),
```

**Step 3: Commit route handler changes**

```bash
git add api/routes/ingredients.py api/routes/user_ingredients.py
git commit -m "refactor: update route handlers for boolean substitution

- Update data mapping in ingredient creation
- Update recommendation response mapping
- Part of bd-53

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: Rewrite Inventory Matching Query (sql_queries.py)

**Files:**
- Modify: `api/db/sql_queries.py:199-268` (SEARCH_RECIPES_BY_USER_INGREDIENTS_QUERY - matching logic)

**Step 1: Understand the new matching logic**

The new algorithm:
1. Direct match: `user.id = recipe.id`
2. User has parent: `user.id IN (recipe.path ancestors)`
3. Sibling match: Same parent AND both have `allow_substitution=true`
4. Recursive upward: Walk up recipe ingredient's parent chain checking allow_substitution

**Step 2: Write new matching query**

Replace the complex COALESCE logic (lines 199-268) with simpler recursive matching:

```sql
-- New matching logic using allow_substitution boolean
AND (
    -- Direct match
    i_user.id = i_recipe.id
    OR
    -- User has ancestor of recipe ingredient (user has "Whiskey", recipe needs "Bourbon")
    i_recipe.path LIKE i_user.path || '%'
    OR
    -- Recipe allows substitution AND user ingredient can substitute
    (i_recipe.allow_substitution = 1 AND (
        -- Sibling match: same parent, both allow substitution
        (i_recipe.parent_id = i_user.parent_id
         AND i_recipe.parent_id IS NOT NULL
         AND i_user.allow_substitution = 1)
        OR
        -- User has parent of recipe ingredient
        (i_user.id = i_recipe.parent_id)
        OR
        -- Recursive: user has ancestor, check path up to 5 levels
        EXISTS (
            SELECT 1 FROM ingredients anc
            WHERE i_user.path LIKE anc.path || '%'
            AND i_recipe.path LIKE anc.path || '%'
            AND anc.allow_substitution = 1
            AND LENGTH(anc.path) - LENGTH(REPLACE(anc.path, '/', '')) <= 6
        )
    ))
)
```

**Step 3: Update the full query in sql_queries.py**

Around line 199-268, replace the entire WHERE clause section:

```python
# In sql_queries.py, update SEARCH_RECIPES_BY_USER_INGREDIENTS_QUERY

# OLD: Complex COALESCE with 3-level hierarchy resolution (lines 199-268)
# Replace with simpler boolean logic:

                    WHERE ui_check.cognito_user_id = :cognito_user_id
                    AND (
                        -- Direct match
                        i_user.id = i_recipe.id
                        OR
                        -- User has ancestor of recipe ingredient
                        i_recipe.path LIKE i_user.path || '%'
                        OR
                        -- Recipe allows substitution
                        (i_recipe.allow_substitution = 1 AND (
                            -- Sibling match: same parent, both allow substitution
                            (i_recipe.parent_id = i_user.parent_id
                             AND i_recipe.parent_id IS NOT NULL
                             AND i_user.allow_substitution = 1)
                            OR
                            -- User has parent
                            (i_user.id = i_recipe.parent_id)
                            OR
                            -- Recursive match through common ancestor
                            EXISTS (
                                SELECT 1 FROM ingredients anc
                                WHERE i_user.path LIKE anc.path || '%'
                                AND i_recipe.path LIKE anc.path || '%'
                                AND anc.allow_substitution = 1
                                AND LENGTH(anc.path) - LENGTH(REPLACE(anc.path, '/', '')) <= 6
                            )
                        ))
                    )
```

**Step 4: Commit query changes**

```bash
git add api/db/sql_queries.py
git commit -m "refactor: simplify inventory matching query for boolean substitution

- Remove complex COALESCE inheritance resolution
- Implement simpler recursive matching with allow_substitution
- Check siblings, parents, and common ancestors
- Part of bd-53

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 7: Update Ingredient Recommendations Logic (db_core.py)

**Files:**
- Modify: `api/db/db_core.py:2613-2690` (get_ingredient_recommendations matching logic)

**Step 1: Update recommendation query**

Around line 2630-2690, replace the COALESCE logic with simpler boolean checks:

```python
# In get_ingredient_recommendations method

# OLD: Complex COALESCE with effective_substitution_level (lines 2631-2690)
# Replace with:

                    COALESCE(i.allow_substitution, 0) as user_allow_substitution
                FROM user_ingredients ui
                JOIN ingredients i ON ui.ingredient_id = i.id
                WHERE ui.cognito_user_id = :cognito_user_id
            ),
            required_ingredients AS (
                SELECT
                    ri.recipe_id,
                    i.id as required_ingredient_id,
                    i.path as required_ingredient_path,
                    i.parent_id as required_parent_id,
                    COALESCE(i.allow_substitution, 0) as required_allow_substitution
                FROM recipe_ingredients ri
                JOIN ingredients i ON ri.ingredient_id = i.id
            ),
            matched_ingredients AS (
                SELECT DISTINCT
                    rr.recipe_id,
                    rr.required_ingredient_id
                FROM required_ingredients rr
                WHERE EXISTS (
                    SELECT 1 FROM user_inventory ui
                    WHERE
                        -- Direct match
                        (rr.required_ingredient_id = ui.ingredient_id)
                        OR
                        -- User has ancestor
                        (rr.required_ingredient_path LIKE ui.path || '%')
                        OR
                        -- Substitution match
                        (rr.required_allow_substitution = 1 AND (
                            -- Sibling match
                            (rr.required_parent_id = ui.parent_id
                             AND rr.required_parent_id IS NOT NULL
                             AND ui.user_allow_substitution = 1)
                            OR
                            -- Parent match
                            (ui.ingredient_id = rr.required_parent_id)
                            OR
                            -- Common ancestor match
                            EXISTS (
                                SELECT 1 FROM ingredients anc
                                WHERE ui.path LIKE anc.path || '%'
                                AND rr.required_ingredient_path LIKE anc.path || '%'
                                AND anc.allow_substitution = 1
                            )
                        ))
                )
            ),
```

**Step 2: Update substitution_level field reference**

Around line 2750, change:

```python
# OLD
i.substitution_level,

# NEW
i.allow_substitution,
```

**Step 3: Commit recommendation changes**

```bash
git add api/db/db_core.py
git commit -m "refactor: update ingredient recommendations for boolean substitution

- Simplify matching logic in get_ingredient_recommendations
- Remove COALESCE inheritance resolution
- Use allow_substitution boolean for matching
- Fixes bd-65 (recommendations not considering substitutability)
- Part of bd-53

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 8: Update Frontend HTML Forms

**Files:**
- Modify: `src/web/ingredients.html` (ingredient form substitution field)
- Modify: `src/web/admin.html` (admin ingredient form substitution field)

**Step 1: Update ingredients.html form**

Find the substitution level dropdown (search for "substitution-level" or "substitution_level") and replace with checkbox:

```html
<!-- OLD -->
<div class="form-group">
  <label for="substitution-level">Substitution Level</label>
  <select id="substitution-level" name="substitution_level">
    <option value="">Inherit from parent</option>
    <option value="0">No substitution</option>
    <option value="1">Parent-level</option>
    <option value="2">Grandparent-level</option>
  </select>
</div>

<!-- NEW -->
<div class="form-group checkbox-group">
  <input type="checkbox" id="allow-substitution" name="allow_substitution">
  <label for="allow-substitution">
    Allow substitution with siblings/ancestors
    <span class="tooltip" title="When enabled, this ingredient can be substituted with similar ingredients that share the same parent in recipes">ⓘ</span>
  </label>
</div>
```

**Step 2: Update admin.html form**

Make the same change in `admin.html` for the admin ingredient form. Find and replace the substitution dropdown with the checkbox.

**Step 3: Add checkbox styling (if needed)**

If checkbox-group class doesn't exist, add to `src/web/css/styles.css`:

```css
.checkbox-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.checkbox-group input[type="checkbox"] {
  margin: 0;
}

.checkbox-group .tooltip {
  cursor: help;
  color: var(--text-secondary, #666);
  margin-left: 4px;
}
```

**Step 4: Commit HTML changes**

```bash
git add src/web/ingredients.html src/web/admin.html
git commit -m "refactor: replace substitution dropdown with checkbox in forms

- Replace 4-option dropdown with simple checkbox
- Add tooltip explaining substitution behavior
- Simpler UX for users
- Part of bd-53

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 9: Update Frontend JavaScript

**Files:**
- Modify: `src/web/js/ingredients.js` (form data collection)
- Modify: `src/web/js/admin.js` (admin form data collection)

**Step 1: Update ingredients.js form data collection**

Find where ingredient data is collected from the form (search for "substitution_level") and update:

```javascript
// OLD
const data = {
  name: form.name.value,
  description: form.description.value,
  parent_id: form.parent_id.value || null,
  substitution_level: parseInt(form.substitution_level.value) || null
};

// NEW
const data = {
  name: form.name.value,
  description: form.description.value,
  parent_id: form.parent_id.value || null,
  allow_substitution: form.allow_substitution.checked
};
```

**Step 2: Update ingredient display logic**

Find where ingredients are displayed (search for "substitution" in display functions) and update:

```javascript
// OLD
if (ingredient.substitution_level !== null) {
  html += `<p>Substitution Level: ${ingredient.substitution_level}</p>`;
}

// NEW
html += `<p>Substitutable: ${ingredient.allow_substitution ? 'Yes' : 'No'}</p>`;
```

**Step 3: Update form population for editing**

Find where the edit form is populated and update:

```javascript
// OLD
if (ingredient.substitution_level !== null) {
  form.substitution_level.value = ingredient.substitution_level;
}

// NEW
form.allow_substitution.checked = ingredient.allow_substitution || false;
```

**Step 4: Make same changes in admin.js**

Repeat steps 1-3 for `src/web/js/admin.js` file.

**Step 5: Commit JavaScript changes**

```bash
git add src/web/js/ingredients.js src/web/js/admin.js
git commit -m "refactor: update JavaScript for boolean substitution field

- Change form data collection to use checkbox value
- Update display to show Yes/No instead of level number
- Update form population for editing
- Part of bd-53

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 10: Update Backend Tests

**Files:**
- Modify: `tests/test_substitution_api.py` (update all test data)
- Modify: `tests/test_substitution_system.py` (update all test data)
- Modify: `tests/test_substitution_integration.py` (update all test data)
- Modify: `tests/test_ingredient_recommendations.py` (update test data and expectations)

**Step 1: Update test_substitution_api.py**

Find all references to `substitution_level` and replace with `allow_substitution`:

```python
# OLD test data
payload = {
    "name": "Test Whiskey",
    "description": "Test description",
    "parent_id": 1,
    "substitution_level": 1
}

# NEW test data
payload = {
    "name": "Test Whiskey",
    "description": "Test description",
    "parent_id": 1,
    "allow_substitution": True
}

# OLD assertion
assert response.json()["substitution_level"] == 1

# NEW assertion
assert response.json()["allow_substitution"] is True
```

Update all test functions in the file following this pattern.

**Step 2: Update test_substitution_system.py**

Replace all test data and assertions:
- Change `substitution_level=0` → `allow_substitution=False`
- Change `substitution_level=1` → `allow_substitution=True`
- Change `substitution_level=2` → `allow_substitution=True`
- Change `substitution_level=None` → `allow_substitution=False`

**Step 3: Update test_substitution_integration.py**

Update end-to-end test scenarios:

```python
# OLD: Test level 1 substitution
ingredient = create_ingredient(
    name="Bourbon",
    parent_id=whiskey_id,
    substitution_level=1
)

# NEW: Test allow_substitution=True
ingredient = create_ingredient(
    name="Bourbon",
    parent_id=whiskey_id,
    allow_substitution=True
)
```

**Step 4: Update test_ingredient_recommendations.py**

This is critical for fixing bd-65. Update test data and add new test cases for the recursive matching:

```python
def test_recommendations_respect_allow_substitution(db, user_id):
    """Test that recommendations correctly consider allow_substitution flag"""
    # Setup hierarchy
    spirit_id = db.create_ingredient({"name": "Spirit", "allow_substitution": True})
    whiskey_id = db.create_ingredient({"name": "Whiskey", "parent_id": spirit_id, "allow_substitution": True})
    bourbon_id = db.create_ingredient({"name": "Bourbon", "parent_id": whiskey_id, "allow_substitution": True})
    rye_id = db.create_ingredient({"name": "Rye", "parent_id": whiskey_id, "allow_substitution": True})
    rum_id = db.create_ingredient({"name": "Rum", "parent_id": spirit_id, "allow_substitution": False})
    dark_rum_id = db.create_ingredient({"name": "Dark Rum", "parent_id": rum_id, "allow_substitution": True})

    # User has Bourbon
    db.add_user_ingredient(user_id, bourbon_id)

    # Create recipe with Rye (sibling, both allow substitution)
    recipe_id = db.create_recipe({"name": "Manhattan", "ingredients": [{"ingredient_id": rye_id}]})

    # User should be able to make it (sibling substitution)
    makeable = db.search_recipes_by_user_ingredients(user_id)
    assert recipe_id in [r["id"] for r in makeable]

    # Create recipe with Dark Rum (not substitutable due to Rum blocking)
    recipe_id2 = db.create_recipe({"name": "Daiquiri", "ingredients": [{"ingredient_id": dark_rum_id}]})

    # User should NOT be able to make it
    makeable = db.search_recipes_by_user_ingredients(user_id)
    assert recipe_id2 not in [r["id"] for r in makeable]
```

**Step 5: Run all tests to see current failures**

```bash
python -m pytest tests/test_substitution*.py tests/test_ingredient_recommendations.py -v
```

Expected: Many FAIL - tests reference old schema that doesn't exist yet

**Step 6: Commit test updates**

```bash
git add tests/test_substitution_api.py tests/test_substitution_system.py tests/test_substitution_integration.py tests/test_ingredient_recommendations.py
git commit -m "test: update all substitution tests for boolean field

- Replace substitution_level with allow_substitution
- Update test data: 0→False, 1/2→True, null→False
- Add tests for recursive matching logic
- Add tests for bd-65 fix (recommendation bugs)
- Part of bd-53

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 11: Apply Migration to Dev Database

**Files:**
- Execute: `migrations/08_migration_substitution_level_to_boolean.sql`

**Step 1: Backup dev database**

```bash
./scripts/restore-backup.sh -t dev --dry-run
# Review backup location, then create manual backup if needed
cp /path/to/dev/cocktaildb.db /path/to/dev/cocktaildb.db.pre-bd53-backup
```

**Step 2: Apply migration to dev**

```bash
./scripts/apply-migration.sh -f migrations/08_migration_substitution_level_to_boolean.sql -e dev
```

Expected output: `Migration applied successfully`

**Step 3: Verify migration success**

```bash
# Check schema
sqlite3 /path/to/dev/cocktaildb.db ".schema ingredients"
```

Expected output should show:
- `allow_substitution BOOLEAN NOT NULL DEFAULT 0`
- NO `substitution_level` column

**Step 4: Verify data migration**

```bash
# Check that data migrated correctly
sqlite3 /path/to/dev/cocktaildb.db "SELECT name, allow_substitution FROM ingredients LIMIT 10;"
```

Expected: See ingredient names with 0 or 1 values (boolean represented as integer in SQLite)

**Step 5: Run tests against dev database**

```bash
python -m pytest tests/test_substitution*.py tests/test_ingredient_recommendations.py -v
```

Expected: PASS - all tests should now pass with new schema

**Step 6: Document migration completion**

Add note to deployment log or create tracking file:

```bash
echo "Dev migration completed: $(date)" >> docs/deployment-log.txt
git add docs/deployment-log.txt
git commit -m "docs: record dev database migration completion

Applied migration 08_migration_substitution_level_to_boolean.sql
to dev environment successfully.

Part of bd-53

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 12: Manual Testing in Dev Environment

**Prerequisites:** Migration applied, code deployed to dev

**Step 1: Test ingredient creation via UI**

1. Navigate to dev frontend: `http://[dev-url]/ingredients.html`
2. Click "Add New Ingredient"
3. Fill in name, description, select parent
4. Check the "Allow substitution" checkbox
5. Submit form
6. Verify ingredient appears with "Substitutable: Yes"

**Step 2: Test ingredient editing**

1. Click edit on an existing ingredient
2. Verify checkbox state matches ingredient's allow_substitution value
3. Toggle checkbox
4. Save
5. Verify updated value displays correctly

**Step 3: Test recipe search with substitution**

1. Add Bourbon to your inventory (user ingredients)
2. Search for recipes that require Rye (sibling of Bourbon)
3. If both Bourbon and Rye have allow_substitution=True, recipe should appear
4. Verify recipe shows up in search results

**Step 4: Test ingredient recommendations**

1. Navigate to recommendations page
2. Verify recommendations show ingredients that would unlock recipes
3. Check that substitutability is considered (bd-65 fix)
4. Verify no errors in browser console

**Step 5: Test admin interface**

1. Navigate to admin page
2. Create ingredient via admin form
3. Verify checkbox works correctly
4. Verify bulk operations still work

**Step 6: Document test results**

Create test results file:

```bash
cat > docs/test-results-bd53-dev.txt << EOF
Dev Testing Results - BD-53 Boolean Substitution
Date: $(date)

✅ Ingredient creation with checkbox
✅ Ingredient editing preserves checkbox state
✅ Recipe search respects substitution rules
✅ Ingredient recommendations working (bd-65 fix)
✅ Admin interface functional
✅ No console errors
✅ No API errors in logs

Ready for production deployment.
EOF

git add docs/test-results-bd53-dev.txt
git commit -m "docs: record successful dev testing for bd-53

All functionality verified in dev environment.
Ready for production deployment.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 13: Production Deployment

**Prerequisites:** All dev testing passed, code reviewed and approved

**IMPORTANT:** Coordinate deployment timing. Migration + code deployment must happen together.

**Step 1: Backup production database**

```bash
# Verify automatic backup exists
./scripts/restore-backup.sh -s prod --dry-run

# Create manual pre-migration backup
aws s3 cp s3://[prod-backup-bucket]/latest/cocktaildb.db s3://[prod-backup-bucket]/pre-bd53-backup/cocktaildb.db
```

**Step 2: Announce maintenance (if desired)**

Since only 2 users, this is optional. If doing maintenance window:
- Post message to users
- Wait for confirmation they're not actively using site

**Step 3: Apply migration to prod**

```bash
./scripts/apply-migration.sh -f migrations/08_migration_substitution_level_to_boolean.sql -e prod
```

Expected: `Migration applied successfully`

**Step 4: Deploy new code immediately**

```bash
# Deploy backend (Lambda functions)
sam build --template-file template.yaml
sam deploy --config-env prod --no-confirm-changeset

# Deploy frontend (S3 + CloudFront)
python scripts/generate_config.py --env prod
aws s3 sync src/web/ s3://[prod-website-bucket]/ --delete
aws cloudfront create-invalidation --distribution-id [DIST_ID] --paths "/*"
```

**Step 5: Smoke test production**

1. Visit production site
2. Test ingredient creation
3. Test recipe search
4. Check browser console for errors
5. Check CloudWatch logs for API errors

**Step 6: Verify with users**

Since there are only 2 users, reach out and ask them to verify:
- Ingredient forms work correctly
- Recipe search still works
- No unexpected errors

**Step 7: Document production deployment**

```bash
cat > docs/deployment-bd53-prod.txt << EOF
Production Deployment - BD-53 Boolean Substitution
Date: $(date)

Migration: 08_migration_substitution_level_to_boolean.sql
Backup: s3://[prod-backup-bucket]/pre-bd53-backup/cocktaildb.db

Deployment Steps:
1. ✅ Backed up production database
2. ✅ Applied migration successfully
3. ✅ Deployed new backend code
4. ✅ Deployed new frontend code
5. ✅ Smoke tested production
6. ✅ User verification complete

Issues: None

Closes: bd-53, bd-54, bd-55, bd-56, bd-57, bd-58, bd-59, bd-65
EOF

git add docs/deployment-bd53-prod.txt
git commit -m "docs: record successful production deployment for bd-53

Boolean substitution system live in production.
All related issues resolved.

Closes: bd-53
Fixes: bd-65

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 14: Close Related Issues

**Step 1: Update issue status in beads**

```bash
bd update 53 --status closed
bd update 54 --status closed
bd update 55 --status closed
bd update 56 --status closed
bd update 57 --status closed
bd update 58 --status closed
bd update 59 --status closed
bd update 65 --status closed
```

**Step 2: Verify all issues closed**

```bash
bd list | grep -E "(bd-53|bd-54|bd-55|bd-56|bd-57|bd-58|bd-59|bd-65)"
```

Expected: All should show status "closed"

**Step 3: Final commit**

```bash
git commit --allow-empty -m "chore: close bd-53 epic and related issues

Boolean substitution system complete:
- bd-53: Overhaul substitution system ✅
- bd-54: Database migration ✅
- bd-55: Remove inheritance logic ✅
- bd-56: Update API models ✅
- bd-57: Update frontend forms ✅
- bd-58: Update tests ✅
- bd-59: Create migration script ✅
- bd-65: Fix recommendation bugs ✅

All changes deployed to production successfully.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Rollback Procedure (If Needed)

**If issues discovered in production:**

**Step 1: Restore database backup**

```bash
./scripts/restore-backup.sh -t prod -f pre-bd53-backup/cocktaildb.db
```

**Step 2: Revert code deployment**

```bash
# Checkout previous commit
git log --oneline -20
git checkout [previous-commit-hash]

# Redeploy old code
sam build && sam deploy --config-env prod
python scripts/generate_config.py --env prod
aws s3 sync src/web/ s3://[prod-website-bucket]/ --delete
```

**Step 3: OR apply rollback migration**

```bash
./scripts/apply-migration.sh -f migrations/08_rollback_substitution_level_to_boolean.sql -e prod
```

**Step 4: Return to main branch**

```bash
git checkout main
```

**Step 5: Document rollback**

```bash
echo "ROLLED BACK bd-53 at $(date): [reason]" >> docs/deployment-log.txt
```

---

## Success Criteria

✅ Migration applied successfully in dev and prod
✅ All tests passing
✅ Ingredient forms display checkbox instead of dropdown
✅ Recipe search correctly uses substitution logic
✅ Ingredient recommendations working (bd-65 fixed)
✅ No 500 errors in production logs
✅ Users confirm improved UX
✅ All related issues closed

## Related Documentation

- Design doc: `docs/plans/2025-11-03-substitution-system-boolean-overhaul.md`
- Test results: `docs/test-results-bd53-dev.txt`
- Deployment record: `docs/deployment-bd53-prod.txt`

## Estimated Time

- Tasks 1-10: 3-4 hours (development)
- Task 11: 30 minutes (dev migration + testing)
- Task 12: 45 minutes (manual testing)
- Task 13: 45 minutes (prod deployment)
- Task 14: 15 minutes (cleanup)

**Total: ~5-6 hours**
