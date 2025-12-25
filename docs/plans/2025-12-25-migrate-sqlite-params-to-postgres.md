# Migrate SQLite Parameter Syntax to Native PostgreSQL

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove legacy SQLite parameter conversion layer by migrating all SQL queries to native PostgreSQL parameter format.

**Architecture:** The codebase currently uses SQLite-style parameters (`:name` and `?`) which are converted at runtime to PostgreSQL format (`%(name)s` and `%s`) via `_convert_sqlite_to_pg_params()`. This adds unnecessary overhead and complexity. We'll update all SQL queries to use native PostgreSQL format and remove the conversion function.

**Tech Stack:** Python, PostgreSQL, psycopg2

---

## Summary of Changes

| File | `:name` params | `?` params | Effort |
|------|---------------|------------|--------|
| `api/db/sql_queries.py` | ~47 | 0 | Medium |
| `api/db/db_analytics.py` | 1 | 0 | Trivial |
| `api/db/db_core.py` | ~62 | ~8 | High |

---

### Task 1: Update sql_queries.py - Part 1 (Static Queries)

**Files:**
- Modify: `api/db/sql_queries.py:61-98` (get_recipe_by_id_sql, get_all_recipes_sql)

**Step 1: Update get_recipe_by_id_sql**

Replace `:cognito_user_id` with `%(cognito_user_id)s` and `:recipe_id` with `%(recipe_id)s`:

```python
get_recipe_by_id_sql = """
    SELECT
        r.id, r.name, r.instructions, r.description, r.image_url,
        r.source, r.source_url, r.avg_rating, r.rating_count,
        STRING_AGG(CASE WHEN t.created_by IS NULL THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS public_tags_data,
        STRING_AGG(CASE WHEN t.created_by = %(cognito_user_id)s THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS private_tags_data,
        ur.rating AS user_rating
    FROM
        recipes r
    LEFT JOIN
        recipe_tags rt ON r.id = rt.recipe_id
    LEFT JOIN
        tags t ON rt.tag_id = t.id
    LEFT JOIN
        ratings ur ON r.id = ur.recipe_id AND ur.cognito_user_id = %(cognito_user_id)s
    WHERE r.id = %(recipe_id)s
    GROUP BY
        r.id, r.name, r.instructions, r.description, r.image_url,
        r.source, r.source_url, r.avg_rating, r.rating_count,
        ur.rating;
"""
```

**Step 2: Update get_all_recipes_sql**

```python
get_all_recipes_sql = """
    SELECT
        r.id, r.name, r.instructions, r.description, r.image_url,
        r.source, r.source_url, r.avg_rating, r.rating_count,
        STRING_AGG(CASE WHEN t.created_by IS NULL THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS public_tags_data,
        STRING_AGG(CASE WHEN t.created_by = %(cognito_user_id)s THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS private_tags_data
    FROM
        recipes r
    LEFT JOIN
        recipe_tags rt ON r.id = rt.recipe_id
    LEFT JOIN
        tags t ON rt.tag_id = t.id
    GROUP BY
        r.id, r.name, r.instructions, r.description, r.image_url,
        r.source, r.source_url, r.avg_rating, r.rating_count;
"""
```

**Step 3: Run tests to verify**

Run: `python -m pytest tests/test_db_recipes.py -v -x`
Expected: PASS

**Step 4: Commit**

```bash
git add api/db/sql_queries.py
git commit -m "refactor: migrate static recipe queries to native PostgreSQL params"
```

---

### Task 2: Update sql_queries.py - Part 2 (get_recipes_paginated_with_ingredients_sql)

**Files:**
- Modify: `api/db/sql_queries.py:125-175`

**Step 1: Update the paginated query**

Replace all `:param` with `%(param)s`:

```python
get_recipes_paginated_with_ingredients_sql = """
    WITH paginated_recipes AS (
        SELECT
            r.id, r.name, r.instructions, r.description, r.image_url,
            r.source, r.source_url, r.avg_rating, r.rating_count,
            STRING_AGG(CASE WHEN t.created_by IS NULL THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS public_tags_data,
            STRING_AGG(CASE WHEN t.created_by = %(cognito_user_id)s THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS private_tags_data,
            ur.rating AS user_rating
        FROM
            recipes r
        LEFT JOIN
            recipe_tags rt ON r.id = rt.recipe_id
        LEFT JOIN
            tags t ON rt.tag_id = t.id
        LEFT JOIN
            ratings ur ON r.id = ur.recipe_id AND ur.cognito_user_id = %(cognito_user_id)s
        GROUP BY
            r.id, r.name, r.instructions, r.description, r.image_url,
            r.source, r.source_url, r.avg_rating, r.rating_count,
            ur.rating
        ORDER BY
            CASE
                WHEN %(sort_by)s = 'name' AND %(sort_order)s = 'asc' THEN r.name
                WHEN %(sort_by)s = 'avg_rating' AND %(sort_order)s = 'asc' THEN CAST(COALESCE(r.avg_rating, 0) AS TEXT)
                WHEN %(sort_by)s = 'created_at' AND %(sort_order)s = 'asc' THEN CAST(r.id AS TEXT)
            END ASC,
            CASE
                WHEN %(sort_by)s = 'name' AND %(sort_order)s = 'desc' THEN r.name
                WHEN %(sort_by)s = 'avg_rating' AND %(sort_order)s = 'desc' THEN CAST(COALESCE(r.avg_rating, 0) AS TEXT)
                WHEN %(sort_by)s = 'created_at' AND %(sort_order)s = 'desc' THEN CAST(r.id AS TEXT)
            END DESC
        LIMIT %(limit)s OFFSET %(offset)s
    )
    SELECT
        pr.id, pr.name, pr.instructions, pr.description, pr.image_url,
        pr.source, pr.source_url, pr.avg_rating, pr.rating_count,
        pr.public_tags_data, pr.private_tags_data, pr.user_rating,
        {INGREDIENT_SELECT_FIELDS}
    FROM
        paginated_recipes pr
    LEFT JOIN
        recipe_ingredients ri ON pr.id = ri.recipe_id
    LEFT JOIN
        ingredients i ON ri.ingredient_id = i.id
    LEFT JOIN
        units u ON ri.unit_id = u.id
    ORDER BY
        pr.id ASC,
        COALESCE(ri.amount * u.conversion_to_ml, 0) DESC,
        ri.id ASC
"""
```

**Step 2: Run tests**

Run: `python -m pytest tests/test_pagination.py -v -x`
Expected: PASS

**Step 3: Commit**

```bash
git add api/db/sql_queries.py
git commit -m "refactor: migrate paginated recipes query to native PostgreSQL params"
```

---

### Task 3: Update sql_queries.py - Part 3 (build_search_recipes_paginated_sql)

**Files:**
- Modify: `api/db/sql_queries.py:180-331`

**Step 1: Update the search function**

This is a large function that builds dynamic SQL. Replace all `:param` with `%(param)s` in the base_sql string template.

Key replacements in base_sql:
- `:cognito_user_id` → `%(cognito_user_id)s`
- `:search_query` → `%(search_query)s`
- `:search_query_with_wildcards` → `%(search_query_with_wildcards)s`
- `:min_rating` → `%(min_rating)s`
- `:max_rating` → `%(max_rating)s`
- `:limit` → `%(limit)s`
- `:offset` → `%(offset)s`
- `:sort_by` → `%(sort_by)s`
- `:sort_order` → `%(sort_order)s`

**Step 2: Run tests**

Run: `python -m pytest tests/test_recipe_name_search.py tests/test_ingredient_search.py -v -x`
Expected: PASS

**Step 3: Commit**

```bash
git add api/db/sql_queries.py
git commit -m "refactor: migrate search recipes query builder to native PostgreSQL params"
```

---

### Task 4: Update sql_queries.py - Part 4 (build_search_recipes_keyset_sql)

**Files:**
- Modify: `api/db/sql_queries.py:334-459`

**Step 1: Update the keyset pagination function**

Replace all `:param` with `%(param)s`:
- `:cognito_user_id` → `%(cognito_user_id)s`
- `:search_query` → `%(search_query)s`
- `:search_query_with_wildcards` → `%(search_query_with_wildcards)s`
- `:min_rating` → `%(min_rating)s`
- `:max_rating` → `%(max_rating)s`
- `:cursor_sort` → `%(cursor_sort)s`
- `:cursor_id` → `%(cursor_id)s`
- `:limit_plus_one` → `%(limit_plus_one)s`

**Step 2: Run tests**

Run: `python -m pytest tests/test_infinite_scroll_coverage.py -v -x`
Expected: PASS

**Step 3: Commit**

```bash
git add api/db/sql_queries.py
git commit -m "refactor: migrate keyset pagination query to native PostgreSQL params"
```

---

### Task 5: Update sql_queries.py - Part 5 (get_ingredient_recommendations_sql)

**Files:**
- Modify: `api/db/sql_queries.py:462-581`

**Step 1: Update the recommendations function**

Replace:
- `:user_id` → `%(user_id)s`
- `:limit` → `%(limit)s`

**Step 2: Run tests**

Run: `python -m pytest tests/test_ingredient_recommendations.py -v -x`
Expected: PASS

**Step 3: Commit**

```bash
git add api/db/sql_queries.py
git commit -m "refactor: migrate ingredient recommendations query to native PostgreSQL params"
```

---

### Task 6: Update db_analytics.py

**Files:**
- Modify: `api/db/db_analytics.py:44`

**Step 1: Update the single parameter**

Change line 44 from:
```python
where_clause = "WHERE i.parent_id = :parent_id"
```

To:
```python
where_clause = "WHERE i.parent_id = %(parent_id)s"
```

**Step 2: Run tests**

Run: `python -m pytest tests/test_db_analytics.py -v -x`
Expected: PASS

**Step 3: Commit**

```bash
git add api/db/db_analytics.py
git commit -m "refactor: migrate analytics query to native PostgreSQL params"
```

---

### Task 7: Update db_core.py - Part 1 (Ingredient CRUD)

**Files:**
- Modify: `api/db/db_core.py:200-470`

**Step 1: Update ingredient-related queries**

This section contains ~15 inline SQL queries with `:param` and `?` placeholders. Key replacements:

| Old | New |
|-----|-----|
| `:parent_id` | `%(parent_id)s` |
| `:id` | `%(id)s` |
| `:name` | `%(name)s` |
| `:description` | `%(description)s` |
| `:path` | `%(path)s` |
| `:allow_substitution` | `%(allow_substitution)s` |
| `:ingredient_id` | `%(ingredient_id)s` |
| `LOWER(?)` | `LOWER(%s)` |

**Step 2: Run tests**

Run: `python -m pytest tests/test_db_ingredients.py -v -x`
Expected: PASS

**Step 3: Commit**

```bash
git add api/db/db_core.py
git commit -m "refactor: migrate ingredient CRUD queries to native PostgreSQL params"
```

---

### Task 8: Update db_core.py - Part 2 (Recipe operations and ratings)

**Files:**
- Modify: `api/db/db_core.py:1050-1550`

**Step 1: Update recipe and rating queries**

Key replacements:
- `:recipe_id` → `%(recipe_id)s`
- `:user_id` → `%(user_id)s`
- `:cognito_user_id` → `%(cognito_user_id)s`
- `:rating` → `%(rating)s`

**Step 2: Run tests**

Run: `python -m pytest tests/test_db_ratings.py tests/test_db_recipes.py -v -x`
Expected: PASS

**Step 3: Commit**

```bash
git add api/db/db_core.py
git commit -m "refactor: migrate recipe and rating queries to native PostgreSQL params"
```

---

### Task 9: Update db_core.py - Part 3 (Tags)

**Files:**
- Modify: `api/db/db_core.py:1550-1950`

**Step 1: Update tag-related queries**

Key replacements:
- `:tag_id` → `%(tag_id)s`
- `:name` → `%(name)s`
- `:cognito_user_id` → `%(cognito_user_id)s`
- `:recipe_id` → `%(recipe_id)s`

**Step 2: Run tests**

Run: `python -m pytest tests/test_db_tags.py -v -x`
Expected: PASS

**Step 3: Commit**

```bash
git add api/db/db_core.py
git commit -m "refactor: migrate tag queries to native PostgreSQL params"
```

---

### Task 10: Remove the conversion function

**Files:**
- Modify: `api/db/db_core.py:29-40, 115-116, 158-159`

**Step 1: Remove `_convert_sqlite_to_pg_params` function**

Delete lines 29-40:
```python
def _convert_sqlite_to_pg_params(sql: str) -> str:
    """Convert SQLite parameters to PostgreSQL format.

    Converts:
    - Named params: :name -> %(name)s
    - Positional params: ? -> %s
    """
    # First convert named params
    sql = re.sub(r':(\w+)', r'%(\1)s', sql)
    # Then convert positional params
    sql = sql.replace('?', '%s')
    return sql
```

**Step 2: Remove conversion calls in execute_query**

Change line ~115-116 from:
```python
# Convert SQLite named params to PostgreSQL format
pg_sql = _convert_sqlite_to_pg_params(sql)
```

To just use `sql` directly:
```python
pg_sql = sql
```

**Step 3: Remove conversion calls in execute_transaction**

Change line ~158-159 similarly.

**Step 4: Remove unused import**

Remove `import re` if no longer needed (check first).

**Step 5: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add api/db/db_core.py
git commit -m "refactor: remove SQLite parameter conversion layer

The codebase now uses native PostgreSQL parameter format throughout.
This removes unnecessary runtime regex processing on every query."
```

---

### Task 11: Final verification and cleanup

**Step 1: Verify no SQLite params remain**

Run:
```bash
grep -rn ':\w\+' api/db/*.py | grep -v "^[^:]*:[0-9]*:\s*#" | grep -v "__pycache__" | grep -v "%(.*" || echo "Clean!"
```

Expected: No matches or only matches in comments/strings that aren't SQL parameters

**Step 2: Run full integration tests**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

**Step 3: Final commit**

```bash
git add -A
git commit -m "chore: verify SQLite to PostgreSQL param migration complete"
```

---

## Execution Notes

- **Test after each task**: The conversion function remains in place until Task 10, so partial migrations will still work.
- **Pattern**: `:param_name` → `%(param_name)s`
- **Tuple params**: `?` → `%s` (used with tuple parameters instead of dict)
- **No functional changes**: This is a pure refactoring - behavior should be identical.
