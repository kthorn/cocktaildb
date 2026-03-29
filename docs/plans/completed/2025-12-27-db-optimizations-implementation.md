# Database Optimizations Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the Postgres-only query optimizations from the design: index-friendly ordering, citext-based case-insensitive search, and new ingredient metadata fields.

**Architecture:** Add a migration + schema updates to enable `citext`, add ingredient chemistry columns, and create `(field, id)` btree indexes. Refactor recipe search SQL to use validated sort expressions instead of CASE/CAST, and update name lookups to rely on `citext` equality rather than `LOWER()`.

**Tech Stack:** FastAPI, psycopg2, PostgreSQL, pytest, raw SQL migrations.

---

### Task 1: Add Postgres migration + schema updates for citext, ingredient metadata, and indexes

**Files:**
- Create: `migrations/11_migration_db_optimizations.sql`
- Modify: `infrastructure/postgres/schema.sql`
- Modify: `tests/conftest.py`
- Test: `tests/test_schema_optimizations.py`

**Step 1: Write the failing test**

```python
# tests/test_schema_optimizations.py
import psycopg2


def _fetch_column_types(cursor, table_name):
    cursor.execute(
        """
        SELECT column_name, data_type, udt_name
        FROM information_schema.columns
        WHERE table_name = %s
        """,
        (table_name,),
    )
    return {row[0]: (row[1], row[2]) for row in cursor.fetchall()}


def _fetch_indexes(cursor, table_name):
    cursor.execute(
        """
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename = %s
        """,
        (table_name,),
    )
    return {row[0]: row[1] for row in cursor.fetchall()}


def test_schema_adds_citext_and_ingredient_metadata(pg_db_with_schema):
    conn = psycopg2.connect(**pg_db_with_schema)
    conn.autocommit = True
    cursor = conn.cursor()

    columns = _fetch_column_types(cursor, "ingredients")
    assert "percent_abv" in columns
    assert "sugar_g_per_l" in columns
    assert "titratable_acidity_g_per_l" in columns
    assert "url" in columns

    # citext columns should report udt_name == 'citext'
    recipe_cols = _fetch_column_types(cursor, "recipes")
    ingredient_cols = _fetch_column_types(cursor, "ingredients")
    assert recipe_cols["name"][1] == "citext"
    assert ingredient_cols["name"][1] == "citext"

    cursor.close()
    conn.close()


def test_schema_adds_ordering_indexes(pg_db_with_schema):
    conn = psycopg2.connect(**pg_db_with_schema)
    conn.autocommit = True
    cursor = conn.cursor()

    indexes = _fetch_indexes(cursor, "recipes")
    expected = {
        "idx_recipes_name_id",
        "idx_recipes_avg_rating_id",
        "idx_recipes_created_at_id",
        "idx_recipes_rating_count_id",
    }
    assert expected.issubset(set(indexes.keys()))

    cursor.close()
    conn.close()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_schema_optimizations.py -v`
Expected: FAIL (missing columns/citext/indexes).

**Step 3: Write minimal implementation**

```sql
-- migrations/11_migration_db_optimizations.sql
CREATE EXTENSION IF NOT EXISTS citext;

ALTER TABLE recipes
    ALTER COLUMN name TYPE citext;

ALTER TABLE ingredients
    ALTER COLUMN name TYPE citext,
    ADD COLUMN IF NOT EXISTS percent_abv NUMERIC CHECK (percent_abv >= 0 AND percent_abv <= 100),
    ADD COLUMN IF NOT EXISTS sugar_g_per_l NUMERIC CHECK (sugar_g_per_l >= 0 AND sugar_g_per_l <= 1000),
    ADD COLUMN IF NOT EXISTS titratable_acidity_g_per_l NUMERIC CHECK (titratable_acidity_g_per_l >= 0 AND titratable_acidity_g_per_l <= 100),
    ADD COLUMN IF NOT EXISTS url TEXT;

CREATE INDEX IF NOT EXISTS idx_recipes_name_id ON recipes (name, id);
CREATE INDEX IF NOT EXISTS idx_recipes_avg_rating_id ON recipes (avg_rating, id);
CREATE INDEX IF NOT EXISTS idx_recipes_created_at_id ON recipes (created_at, id);
CREATE INDEX IF NOT EXISTS idx_recipes_rating_count_id ON recipes (rating_count, id);
```

```sql
-- infrastructure/postgres/schema.sql (additions/changes)
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TABLE ingredients (
  id SERIAL PRIMARY KEY,
  name CITEXT NOT NULL UNIQUE,
  description TEXT,
  parent_id INTEGER,
  path TEXT,
  allow_substitution BOOLEAN NOT NULL DEFAULT FALSE,
  percent_abv NUMERIC CHECK (percent_abv >= 0 AND percent_abv <= 100),
  sugar_g_per_l NUMERIC CHECK (sugar_g_per_l >= 0 AND sugar_g_per_l <= 1000),
  titratable_acidity_g_per_l NUMERIC CHECK (titratable_acidity_g_per_l >= 0 AND titratable_acidity_g_per_l <= 100),
  url TEXT,
  created_by TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (parent_id) REFERENCES ingredients(id)
);

CREATE TABLE recipes (
  id SERIAL PRIMARY KEY,
  name CITEXT NOT NULL UNIQUE,
  ...
);

CREATE INDEX idx_recipes_name_id ON recipes(name, id);
CREATE INDEX idx_recipes_avg_rating_id ON recipes(avg_rating, id);
CREATE INDEX idx_recipes_created_at_id ON recipes(created_at, id);
CREATE INDEX idx_recipes_rating_count_id ON recipes(rating_count, id);
```

```python
# tests/conftest.py (drop citext extension during reset)
    cursor.execute("""
        DO $$ DECLARE
            r RECORD;
        BEGIN
            -- Drop extensions first (they own functions that can't be dropped)
            DROP EXTENSION IF EXISTS pg_trgm CASCADE;
            DROP EXTENSION IF EXISTS citext CASCADE;
            ...
        END $$;
    """)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_schema_optimizations.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add migrations/11_migration_db_optimizations.sql infrastructure/postgres/schema.sql tests/conftest.py tests/test_schema_optimizations.py
git commit -m "feat: add citext and ingredient metadata schema"
```

---

### Task 2: Centralize sort validation + switch ordering SQL to index-friendly expressions

**Files:**
- Modify: `api/db/db_utils.py`
- Modify: `api/db/sql_queries.py`
- Modify: `api/db/db_core.py`
- Modify: `api/routes/recipes.py`
- Test: `tests/test_search_sorting.py`

**Step 1: Write the failing test**

```python
# tests/test_search_sorting.py
from api.db.db_core import Database


def test_search_sort_by_rating_count_uses_id_tiebreaker(set_pg_env):
    db = Database()

    # Seed minimal recipes with deterministic ids
    db.execute_query(
        """
        INSERT INTO recipes (id, name, rating_count)
        VALUES (100, 'Tie A', 5), (101, 'Tie B', 5)
        """
    )

    results = db.search_recipes_paginated(
        search_params={},
        limit=10,
        offset=0,
        sort_by="rating_count",
        sort_order="asc",
        return_pagination=False,
    )

    # When rating_count ties, order by id ASC
    ids = [recipe["id"] for recipe in results]
    assert ids[:2] == [100, 101]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_search_sorting.py -v`
Expected: FAIL (sort_by not accepted / ordering not stable).

**Step 3: Write minimal implementation**

```python
# api/db/db_utils.py
from dataclasses import dataclass


@dataclass(frozen=True)
class RecipeSortSpec:
    expression: str
    direction: str


RECIPE_SORT_FIELDS = {
    "name": "r.name",
    "avg_rating": "COALESCE(r.avg_rating, 0)",
    "created_at": "r.created_at",
    "rating_count": "r.rating_count",
}


def build_recipe_sort_spec(sort_by: str, sort_order: str) -> RecipeSortSpec:
    sort_expr = RECIPE_SORT_FIELDS.get(sort_by, RECIPE_SORT_FIELDS["name"])
    direction = "DESC" if sort_order == "desc" else "ASC"
    return RecipeSortSpec(sort_expr, direction)
```

```python
# api/db/sql_queries.py (replace CASE/CAST blocks with validated expressions)
from .db_utils import build_recipe_sort_spec


def build_search_recipes_paginated_sql(..., sort_by: str, sort_order: str, ...):
    sort_spec = build_recipe_sort_spec(sort_by, sort_order)
    base_sql = f"""
        ...
        ORDER BY
            {sort_spec.expression} {sort_spec.direction},
            r.id {sort_spec.direction}
        LIMIT %(limit)s OFFSET %(offset)s
    """
    ...
        ORDER BY
            {sort_spec.expression.replace('r.', 'sr.')} {sort_spec.direction},
            sr.id {sort_spec.direction},
            COALESCE(ri.amount * u.conversion_to_ml, 0) DESC,
            ri.id ASC
    """
```

```python
# api/db/sql_queries.py (keyset)
    sort_spec = build_recipe_sort_spec(sort_by, sort_order)
    sort_expr = sort_spec.expression
    sort_direction = sort_spec.direction
    cursor_operator = "<" if sort_direction == "DESC" else ">"
```

```python
# api/routes/recipes.py (allow rating_count)
valid_sort_fields = ["name", "created_at", "avg_rating", "rating_count", "random"]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_search_sorting.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add api/db/db_utils.py api/db/sql_queries.py api/db/db_core.py api/routes/recipes.py tests/test_search_sorting.py
git commit -m "refactor: use whitelisted sort expressions for recipe search"
```

---

### Task 3: Switch ingredient name matching to citext equality (remove LOWER in SQL + tests)

**Files:**
- Modify: `api/db/db_core.py`
- Modify: `tests/test_bulk_recipe_upload.py`
- Test: `tests/test_ingredient_name_case_insensitive.py`

**Step 1: Write the failing test**

```python
# tests/test_ingredient_name_case_insensitive.py
from api.db.db_core import Database


def test_get_ingredient_by_name_is_case_insensitive(set_pg_env_with_data):
    db = Database()

    # Create an ingredient with mixed case
    created = db.create_ingredient({"name": "Campari", "description": "Bitter"})
    found = db.get_ingredient_by_name("cAmPaRi")

    assert found is not None
    assert found["id"] == created["id"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ingredient_name_case_insensitive.py -v`
Expected: FAIL (if LOWER is removed without citext / or after migration mismatch).

**Step 3: Write minimal implementation**

```python
# api/db/db_core.py (remove LOWER() usage in SQL)
"SELECT id, name, description, parent_id, path, allow_substitution, created_by
 FROM ingredients WHERE name = %s"

"SELECT id, name, description, parent_id, path, allow_substitution, created_by
 FROM ingredients WHERE name = ANY(%s)"

"SELECT name FROM recipes WHERE name = %s"
```

```python
# api/db/db_core.py (batch mapping without LOWER in SQL)
unique_names = list({name.casefold() for name in ingredient_names})
...
results_map = {ingredient["name"].casefold(): ingredient for ingredient in exact_results}
```

```python
# tests/test_bulk_recipe_upload.py (replace LOWER(name) checks)
"SELECT name FROM recipes WHERE name = %s"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_ingredient_name_case_insensitive.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add api/db/db_core.py tests/test_bulk_recipe_upload.py tests/test_ingredient_name_case_insensitive.py
git commit -m "refactor: rely on citext for case-insensitive name matching"
```

---

### Task 4: Add ingredient metadata fields to API models and DB CRUD

**Files:**
- Modify: `api/models/requests.py`
- Modify: `api/models/responses.py`
- Modify: `api/db/db_core.py`
- Modify: `api/routes/ingredients.py`
- Test: `tests/test_ingredient_metadata.py`

**Step 1: Write the failing test**

```python
# tests/test_ingredient_metadata.py

def test_create_ingredient_with_metadata(editor_client):
    payload = {
        "name": "Test Vermouth",
        "description": "Sweet",
        "percent_abv": 15.5,
        "sugar_g_per_l": 120.0,
        "titratable_acidity_g_per_l": 5.0,
        "url": "https://example.com/vermouth",
    }

    response = editor_client.post("/ingredients", json=payload)
    assert response.status_code == 201
    body = response.json()

    assert body["percent_abv"] == 15.5
    assert body["sugar_g_per_l"] == 120.0
    assert body["titratable_acidity_g_per_l"] == 5.0
    assert body["url"] == "https://example.com/vermouth"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ingredient_metadata.py -v`
Expected: FAIL (fields missing / validation errors).

**Step 3: Write minimal implementation**

```python
# api/models/requests.py
class IngredientCreate(BaseModel):
    ...
    percent_abv: Optional[float] = Field(None, ge=0, le=100)
    sugar_g_per_l: Optional[float] = Field(None, ge=0, le=1000)
    titratable_acidity_g_per_l: Optional[float] = Field(None, ge=0, le=100)
    url: Optional[str] = Field(None, description="Reference URL")

class IngredientUpdate(BaseModel):
    ...
    percent_abv: Optional[float] = Field(None, ge=0, le=100)
    sugar_g_per_l: Optional[float] = Field(None, ge=0, le=1000)
    titratable_acidity_g_per_l: Optional[float] = Field(None, ge=0, le=100)
    url: Optional[str] = Field(None, description="Reference URL")
```

```python
# api/models/responses.py
class IngredientResponse(BaseModel):
    ...
    percent_abv: Optional[float] = None
    sugar_g_per_l: Optional[float] = None
    titratable_acidity_g_per_l: Optional[float] = None
    url: Optional[str] = None
```

```python
# api/db/db_core.py (include new columns in selects/inserts/updates)
INSERT INTO ingredients (name, description, parent_id, allow_substitution, created_by,
                         percent_abv, sugar_g_per_l, titratable_acidity_g_per_l, url)
VALUES (%(name)s, %(description)s, %(parent_id)s, %(allow_substitution)s, %(created_by)s,
        %(percent_abv)s, %(sugar_g_per_l)s, %(titratable_acidity_g_per_l)s, %(url)s)

SELECT id, name, description, parent_id, path, allow_substitution,
       percent_abv, sugar_g_per_l, titratable_acidity_g_per_l, url, created_by
FROM ingredients ...
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_ingredient_metadata.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add api/models/requests.py api/models/responses.py api/db/db_core.py api/routes/ingredients.py tests/test_ingredient_metadata.py
git commit -m "feat: expose ingredient metadata fields"
```

---

### Task 5: Regression test sweep for search/order changes

**Files:**
- (No code changes expected unless failures)

**Step 1: Run focused suites**

Run: `pytest tests/test_recipe_name_search.py tests/test_ingredient_search.py tests/test_bulk_recipe_upload.py -v`
Expected: PASS.

**Step 2: Run broader suite**

Run: `python -m pytest tests/ -v`
Expected: PASS.

**Step 3: Commit (if any fixes required)**

```bash
git add <files>
git commit -m "test: fix regressions from db optimizations"
```

---

## Execution Notes

- Apply the migration in environments that use PostgreSQL before running the API.
- If `citext` introduces duplicate conflicts, run a one-off audit query to find case-insensitive duplicates before the type change.
