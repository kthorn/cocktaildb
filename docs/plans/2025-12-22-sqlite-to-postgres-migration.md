# SQLite to PostgreSQL Migration Design

## Overview

Migrate the CocktailDB API database layer from SQLite to PostgreSQL entirely. After migration, SQLite support will be removed.

## Current State

- **PostgreSQL**: Schema deployed on EC2, 8 tables ready, triggers working
- **SQLite**: `db_core.py` (2791 lines, ~50 methods), `sql_queries.py` (452 lines)
- **Existing work**: `postgres_backend.py`, `sqlite_backend.py`, `backend_base.py` (not integrated)
- **Docker**: Already configured with `DB_TYPE=postgres` environment variables

## Migration Goal

Complete migration to PostgreSQL only. Files to delete after migration:
- `api/db/sqlite_backend.py`
- `api/db/backend_base.py` (no longer needed without multiple backends)
- SQLite-specific code in `db_core.py`

## Architecture

### Final Structure
```
api/db/
├── database.py         # Connection management (use postgres_backend.py code)
├── db_core.py          # Database class (converted to PostgreSQL)
├── sql_queries.py      # Queries (converted to PostgreSQL syntax)
├── db_analytics.py     # Analytics queries (verify PostgreSQL compatible)
├── db_utils.py         # Utilities (keep as-is)
└── postgres_backend.py # DELETE after integrating into database.py
```

## Key Syntax Changes

### Parameter Placeholders
| SQLite | PostgreSQL |
|--------|------------|
| `:param` | `%(param)s` |
| `?` | `%s` |

### Functions
| SQLite | PostgreSQL |
|--------|------------|
| `GROUP_CONCAT(x, ',')` | `STRING_AGG(x, ',')` |
| `LOWER(x) LIKE LOWER(y)` | `x ILIKE y` |
| `LENGTH(x) - LENGTH(REPLACE(x, '/', ''))` | `LENGTH(x) - LENGTH(REPLACE(x, '/', ''))` (same) |
| `RANDOM()` | `RANDOM()` (same) |

### Booleans
| SQLite | PostgreSQL |
|--------|------------|
| `= 1` / `= 0` | `= TRUE` / `= FALSE` or bare boolean |
| `allow_substitution = 1` | `allow_substitution = TRUE` |

### Other
| SQLite | PostgreSQL |
|--------|------------|
| `PRAGMA foreign_keys = ON` | Remove (PostgreSQL enforces by default) |
| `BEGIN IMMEDIATE` | `BEGIN` |
| `cursor.lastrowid` | `RETURNING id` clause |

## Implementation Phases

### Phase 1: Connection Infrastructure
**Goal**: Replace SQLite connection with PostgreSQL connection pool

Tasks:
1. Update `database.py`:
   - Import psycopg2 and connection pool
   - Replace `Database()` instantiation with PostgreSQL-based class
   - Use connection pooling from `postgres_backend.py`
   - Remove `get_backend()` function and backend abstraction

2. Update `db_core.py` Database class `__init__`:
   - Replace sqlite3 connection with psycopg2 pool
   - Remove `db_path` and file-based logic
   - Add PostgreSQL connection parameters from env vars
   - Remove `_test_connection()` SQLite-specific code

3. Update `execute_query()` method:
   - Use psycopg2 cursor with `RealDictCursor`
   - Handle parameter conversion (`:name` -> `%(name)s`)
   - Remove `retry_on_db_locked` decorator

4. Update `execute_transaction()` method:
   - Use PostgreSQL transaction semantics
   - Remove SQLite-specific retry logic

### Phase 2: Query Conversion by Domain

Convert in dependency order to allow incremental testing:

#### 2.1 Units (simplest, no dependencies)
Methods: `get_units`, `get_units_by_type`, `get_unit_by_name`, `get_unit_by_abbreviation`, `get_unit_by_name_or_abbreviation`, `validate_units_batch`

- Simple SELECT queries, minimal changes needed
- Test: GET `/api/v1/units`

#### 2.2 Tags (simple CRUD)
Methods: `create_public_tag`, `get_public_tag_by_name`, `create_private_tag`, `get_private_tag_by_name_and_user`, `get_public_tags`, `get_private_tags`, `add_public_tag_to_recipe`, `add_private_tag_to_recipe`, `remove_public_tag_from_recipe`, `remove_private_tag_from_recipe`, `_get_recipe_public_tags`, `_get_recipe_private_tags`, `get_tag`, `add_recipe_tag`, `remove_recipe_tag`, `delete_public_tag`, `delete_private_tag`

- Convert `:param` to `%(param)s`
- Test: GET/POST `/api/v1/tags`

#### 2.3 Ingredients (hierarchy logic)
Methods: `create_ingredient`, `update_ingredient`, `delete_ingredient`, `get_ingredients`, `get_ingredient_by_name`, `search_ingredients`, `search_ingredients_batch`, `check_ingredient_names_batch`, `get_ingredient`, `get_ingredient_descendants`

- Convert path-based queries (LIKE with `||` - works in both)
- Convert boolean `= 1` to `= TRUE`
- Test: GET/POST `/api/v1/ingredients`

#### 2.4 Recipes (core entity)
Methods: `_validate_recipe_ingredients`, `_validate_ingredients_exist`, `create_recipe`, `bulk_create_recipes`, `get_recipes_with_ingredients`, `get_recipe`, `_get_recipe_ingredients`, `check_recipe_names_batch`, `delete_recipe`, `update_recipe`

- Convert `GROUP_CONCAT` to `STRING_AGG` in `get_recipe` queries
- Convert `:param` placeholders
- Convert `cursor.lastrowid` to `RETURNING id`
- Test: GET/POST `/api/v1/recipes`

#### 2.5 Ratings (depends on recipes)
Methods: `get_recipe_ratings`, `get_user_rating`, `set_rating`, `delete_rating`

- Simple queries, convert placeholders
- Test: GET/POST `/api/v1/recipes/{id}/ratings`

#### 2.6 User Ingredients (depends on ingredients)
Methods: `add_user_ingredient`, `remove_user_ingredient`, `get_user_ingredients`, `add_user_ingredients_bulk`, `remove_user_ingredients_bulk`

- Convert placeholders and booleans
- Test: GET/POST `/api/v1/user/ingredients`

#### 2.7 Search & Recommendations (complex queries)
Methods: `search_recipes_paginated`, `get_ingredient_recommendations`

- Convert `GROUP_CONCAT` to `STRING_AGG` in sql_queries.py
- Convert `INGREDIENT_SUBSTITUTION_MATCH` booleans
- Convert `build_search_recipes_paginated_sql()` function
- Convert `get_ingredient_recommendations_sql()` function
- Test: GET `/api/v1/recipes/search`, GET `/api/v1/recommendations`

#### 2.8 Analytics & Counts
Methods: `get_recipes_count`, `get_ingredients_count`

- Simple COUNT queries, minimal changes
- Verify `db_analytics.py` is PostgreSQL compatible
- Test: GET `/api/v1/analytics/*`

### Phase 3: Cleanup
1. Delete `sqlite_backend.py`
2. Delete `backend_base.py`
3. Remove `remove_accents()` function if using PostgreSQL collation
4. Remove `retry_on_db_locked()` decorator
5. Update `database.py` to remove backend switching logic
6. Update CLAUDE.md to remove SQLite references

### Phase 4: Deployment & Testing
1. Deploy to EC2 dev environment
2. Test all API endpoints
3. Verify analytics queries work
4. Test with frontend application
5. Monitor for connection pool issues

## Environment Variables

```
DB_HOST=localhost (or host.docker.internal from container)
DB_PORT=5432
DB_NAME=cocktaildb
DB_USER=cocktaildb
DB_PASSWORD=<password>
```

## Query Parameter Conversion Helper

For systematic conversion, use these patterns:

```python
# In db_core.py, add helper method:
def _convert_params(self, query: str, params: dict) -> tuple[str, tuple]:
    """Convert SQLite named params to PostgreSQL format."""
    import re
    # Find all :param patterns
    sqlite_params = re.findall(r':(\w+)', query)
    # Replace with %(param)s
    pg_query = re.sub(r':(\w+)', r'%(\1)s', query)
    return pg_query, params
```

## Rollback

Branch-based rollback - this work is on `feature/ec2-migration` branch. Main branch retains SQLite implementation.

## Testing Approach

- Test each domain after conversion via existing API endpoints
- EC2 already has data in PostgreSQL from earlier migration
- Run existing pytest tests (update test fixtures for PostgreSQL)
- Verify all CRUD operations work
- Verify search and filtering
- Verify analytics queries
