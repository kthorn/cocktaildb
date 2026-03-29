# Fix created_by Field Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the `created_by` field so it is properly saved when creating recipes and ingredients, and returned in API responses.

**Architecture:** The route handlers already set `created_by` from user context, but the database layer ignores it. We need to update INSERT statements and SELECT queries to include `created_by`, then update response models to expose it.

**Tech Stack:** Python, FastAPI, PostgreSQL, Pydantic, pytest

---

## Summary of Issues

| Operation | Route Sets created_by | Database Saves | API Returns |
|-----------|----------------------|----------------|-------------|
| Create Recipe (single) | Yes | **No** | No |
| Create Recipe (bulk) | Yes | Yes | No |
| Create Ingredient (single) | Yes | **No** | No |
| Create Ingredient (bulk) | Yes | **No** | No |
| Get Recipe | - | - | **No** |
| Get Ingredient | - | - | **No** |

---

### Task 1: Add created_by to IngredientResponse Model

**Files:**
- Modify: `api/models/responses.py:6-18`
- Test: `tests/test_created_by.py` (new)

**Step 1: Write the failing test**

Create `tests/test_created_by.py`:

```python
"""Tests for created_by field on recipes and ingredients"""

import pytest
from api.models.responses import IngredientResponse


class TestIngredientCreatedByField:
    """Test created_by field on ingredient responses"""

    def test_ingredient_response_has_created_by_field(self):
        """IngredientResponse model should accept created_by field"""
        ingredient = IngredientResponse(
            id=1,
            name="Test Ingredient",
            allow_substitution=False,
            created_by="user-123"
        )
        assert ingredient.created_by == "user-123"

    def test_ingredient_response_created_by_optional(self):
        """created_by should be optional (None for legacy data)"""
        ingredient = IngredientResponse(
            id=1,
            name="Test Ingredient",
            allow_substitution=False
        )
        assert ingredient.created_by is None
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_created_by.py::TestIngredientCreatedByField -v`
Expected: FAIL with "unexpected keyword argument 'created_by'"

**Step 3: Write minimal implementation**

In `api/models/responses.py`, add to `IngredientResponse` class (after line 14):

```python
    created_by: Optional[str] = Field(None, description="User ID who created this ingredient")
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_created_by.py::TestIngredientCreatedByField -v`
Expected: PASS

**Step 5: Commit**

```bash
git add api/models/responses.py tests/test_created_by.py
git commit -m "feat: add created_by field to IngredientResponse model"
```

---

### Task 2: Add created_by to RecipeResponse Model

**Files:**
- Modify: `api/models/responses.py:85-109`
- Test: `tests/test_created_by.py`

**Step 1: Write the failing test**

Add to `tests/test_created_by.py`:

```python
from api.models.responses import RecipeResponse


class TestRecipeCreatedByField:
    """Test created_by field on recipe responses"""

    def test_recipe_response_has_created_by_field(self):
        """RecipeResponse model should accept created_by field"""
        recipe = RecipeResponse(
            id=1,
            name="Test Recipe",
            created_by="user-456"
        )
        assert recipe.created_by == "user-456"

    def test_recipe_response_created_by_optional(self):
        """created_by should be optional (None for legacy data)"""
        recipe = RecipeResponse(
            id=1,
            name="Test Recipe"
        )
        assert recipe.created_by is None
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_created_by.py::TestRecipeCreatedByField -v`
Expected: FAIL with "unexpected keyword argument 'created_by'"

**Step 3: Write minimal implementation**

In `api/models/responses.py`, add to `RecipeResponse` class (after line 96, before `user_rating`):

```python
    created_by: Optional[str] = Field(None, description="User ID who created this recipe")
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_created_by.py::TestRecipeCreatedByField -v`
Expected: PASS

**Step 5: Commit**

```bash
git add api/models/responses.py tests/test_created_by.py
git commit -m "feat: add created_by field to RecipeResponse model"
```

---

### Task 3: Save created_by When Creating Ingredients

**Files:**
- Modify: `api/db/db_core.py:201-212`
- Test: `tests/test_created_by.py`

**Step 1: Write the failing test**

Add to `tests/test_created_by.py`:

```python
class TestIngredientCreatedByDatabase:
    """Test created_by is saved to database for ingredients"""

    def test_create_ingredient_saves_created_by(self, test_client_with_data, mock_user, mocker):
        """Creating an ingredient should save created_by to database"""
        from api.dependencies.auth import UserInfo

        client, app = test_client_with_data

        # Mock authentication
        mock_auth = mocker.patch("api.dependencies.auth.get_user_from_jwt")
        mock_auth.return_value = UserInfo(
            user_id=mock_user["user_id"],
            username=mock_user.get("username"),
            email=mock_user.get("email"),
            groups=mock_user.get("cognito:groups", []),
            claims=mock_user,
        )

        # Create ingredient
        response = client.post("/ingredients", json={
            "name": "Test Created By Ingredient",
            "description": "Testing created_by field"
        })

        assert response.status_code == 201
        data = response.json()
        assert data.get("created_by") == mock_user["user_id"]
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_created_by.py::TestIngredientCreatedByDatabase -v`
Expected: FAIL - `created_by` is None or missing

**Step 3: Write minimal implementation**

In `api/db/db_core.py`, modify the `create_ingredient` method INSERT statement (lines 201-212):

Change:
```python
cursor.execute(
    """
    INSERT INTO ingredients (name, description, parent_id, allow_substitution)
    VALUES (%s, %s, %s, %s)
    RETURNING id
    """,
    (
        data.get("name"),
        data.get("description"),
        data.get("parent_id"),
        data.get("allow_substitution", False),
    ),
)
```

To:
```python
cursor.execute(
    """
    INSERT INTO ingredients (name, description, parent_id, allow_substitution, created_by)
    VALUES (%s, %s, %s, %s, %s)
    RETURNING id
    """,
    (
        data.get("name"),
        data.get("description"),
        data.get("parent_id"),
        data.get("allow_substitution", False),
        data.get("created_by"),
    ),
)
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_created_by.py::TestIngredientCreatedByDatabase -v`
Expected: Still FAIL (need to also return created_by in SELECT - see Task 4)

**Step 5: Commit partial progress**

```bash
git add api/db/db_core.py
git commit -m "fix: save created_by field when creating ingredients"
```

---

### Task 4: Return created_by When Fetching Ingredients

**Files:**
- Modify: `api/db/db_core.py:237` (create_ingredient SELECT)
- Modify: `api/db/db_core.py:455-470` (get_ingredients SELECT)
- Modify: `api/db/db_core.py:586-590` (get_ingredient SELECT)
- Test: `tests/test_created_by.py`

**Step 1: Complete the failing test from Task 3**

The test from Task 3 should now pass after these changes.

**Step 2: Write minimal implementation**

In `api/db/db_core.py`, update the SELECT in `create_ingredient` (line 237):

Change:
```python
"SELECT id, name, description, parent_id, path, allow_substitution FROM ingredients WHERE id = %(id)s",
```

To:
```python
"SELECT id, name, description, parent_id, path, allow_substitution, created_by FROM ingredients WHERE id = %(id)s",
```

In `api/db/db_core.py`, find `get_ingredient` method and update its SELECT to include `created_by`:

Change:
```python
"SELECT id, name, description, parent_id, path, allow_substitution FROM ingredients"
```

To:
```python
"SELECT id, name, description, parent_id, path, allow_substitution, created_by FROM ingredients"
```

In `api/db/db_core.py`, find `get_ingredients` method and update its SELECT similarly.

**Step 3: Run test to verify it passes**

Run: `python -m pytest tests/test_created_by.py::TestIngredientCreatedByDatabase -v`
Expected: PASS

**Step 4: Commit**

```bash
git add api/db/db_core.py
git commit -m "fix: return created_by field when fetching ingredients"
```

---

### Task 5: Save created_by When Creating Recipes (Single)

**Files:**
- Modify: `api/db/db_core.py:751-764`
- Test: `tests/test_created_by.py`

**Step 1: Write the failing test**

Add to `tests/test_created_by.py`:

```python
class TestRecipeCreatedByDatabase:
    """Test created_by is saved to database for recipes"""

    def test_create_recipe_saves_created_by(self, test_client_with_data, mock_user, mocker):
        """Creating a recipe should save created_by to database"""
        from api.dependencies.auth import UserInfo

        client, app = test_client_with_data

        # Mock authentication
        mock_auth = mocker.patch("api.dependencies.auth.get_user_from_jwt")
        mock_auth.return_value = UserInfo(
            user_id=mock_user["user_id"],
            username=mock_user.get("username"),
            email=mock_user.get("email"),
            groups=mock_user.get("cognito:groups", []),
            claims=mock_user,
        )

        # Create recipe
        response = client.post("/recipes", json={
            "name": "Test Created By Recipe",
            "instructions": "Test instructions"
        })

        assert response.status_code == 201
        data = response.json()
        assert data.get("created_by") == mock_user["user_id"]
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_created_by.py::TestRecipeCreatedByDatabase::test_create_recipe_saves_created_by -v`
Expected: FAIL - `created_by` is None or missing

**Step 3: Write minimal implementation**

In `api/db/db_core.py`, modify the `create_recipe` INSERT statement (lines 751-764):

Change:
```python
cursor.execute(
    """
    INSERT INTO recipes (name, instructions, description, image_url, source, source_url)
    VALUES (%s, %s, %s, %s, %s, %s)
    RETURNING id
    """,
    (
        data["name"] if data["name"] else None,
        data.get("instructions"),
        data.get("description"),
        data.get("image_url"),
        data.get("source"),
        data.get("source_url"),
    ),
)
```

To:
```python
cursor.execute(
    """
    INSERT INTO recipes (name, instructions, description, image_url, source, source_url, created_by)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    RETURNING id
    """,
    (
        data["name"] if data["name"] else None,
        data.get("instructions"),
        data.get("description"),
        data.get("image_url"),
        data.get("source"),
        data.get("source_url"),
        data.get("created_by"),
    ),
)
```

**Step 4: Run test to verify progress**

Run: `python -m pytest tests/test_created_by.py::TestRecipeCreatedByDatabase::test_create_recipe_saves_created_by -v`
Expected: Still FAIL (need to also return created_by - see Task 6)

**Step 5: Commit partial progress**

```bash
git add api/db/db_core.py
git commit -m "fix: save created_by field when creating recipes"
```

---

### Task 6: Return created_by When Fetching Recipes

**Files:**
- Modify: `api/db/sql_queries.py:62-80` (get_recipe_by_id_sql)
- Modify: `api/db/sql_queries.py:84-97` (get_all_recipes_sql)
- Modify: `api/db/db_core.py:969-982` (get_recipe dict construction)
- Test: `tests/test_created_by.py`

**Step 1: The test from Task 5 should pass after these changes**

**Step 2: Write minimal implementation**

In `api/db/sql_queries.py`, modify `get_recipe_by_id_sql` (lines 62-80):

Change line 63:
```python
        r.id, r.name, r.instructions, r.description, r.image_url,
```

To:
```python
        r.id, r.name, r.instructions, r.description, r.image_url, r.created_by,
```

Add `r.created_by` to GROUP BY clause (line 78):
```python
        r.id, r.name, r.instructions, r.description, r.image_url, r.created_by,
```

In `api/db/sql_queries.py`, modify `get_all_recipes_sql` similarly (lines 84-97).

In `api/db/db_core.py`, modify `get_recipe` method dict construction (around line 969):

Add after `"source_url"`:
```python
"created_by": recipe_data["created_by"],
```

**Step 3: Run test to verify it passes**

Run: `python -m pytest tests/test_created_by.py::TestRecipeCreatedByDatabase -v`
Expected: PASS

**Step 4: Commit**

```bash
git add api/db/sql_queries.py api/db/db_core.py
git commit -m "fix: return created_by field when fetching recipes"
```

---

### Task 7: Run Full Test Suite and Verify

**Step 1: Run all created_by tests**

Run: `python -m pytest tests/test_created_by.py -v`
Expected: All tests PASS

**Step 2: Run related existing tests**

Run: `python -m pytest tests/test_crud_operations.py tests/test_db_recipes.py tests/test_db_ingredients.py -v`
Expected: All tests PASS (no regressions)

**Step 3: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

**Step 4: Final commit**

```bash
git add -A
git commit -m "test: add comprehensive tests for created_by field"
```

---

### Task 8: Close Issue

**Step 1: Update beads issue status**

Run: `bd update bd-21 --status closed`

**Step 2: Final commit with issue reference**

```bash
git commit --allow-empty -m "fix(bd-21): created_by field now saved and returned for recipes and ingredients"
```

---

## Files Changed Summary

| File | Changes |
|------|---------|
| `api/models/responses.py` | Add `created_by` field to `IngredientResponse` and `RecipeResponse` |
| `api/db/db_core.py` | Update INSERT and SELECT statements for ingredients and recipes |
| `api/db/sql_queries.py` | Add `r.created_by` to recipe SELECT and GROUP BY clauses |
| `tests/test_created_by.py` | New test file for created_by functionality |
