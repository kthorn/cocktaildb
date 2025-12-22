# SQLite to PostgreSQL Migration Design

## Overview

Migrate the CocktailDB API database layer from SQLite to PostgreSQL. The EC2 instance already has PostgreSQL running with the schema deployed and tables populated.

## Current State

- **PostgreSQL**: Schema deployed on EC2, 8 tables ready, triggers working
- **SQLite**: `db_core.py` (2791 lines), `sql_queries.py` with complex queries
- **Docker**: Already configured with `DB_TYPE=postgres` environment variables

## Architecture

### New Files

```
api/db/
├── db_postgres.py      # New PostgreSQL Database class
├── sql_queries_pg.py   # PostgreSQL-specific queries
```

### Files to Delete (after migration)

- `api/db/db_core.py`
- `api/db/sql_queries.py`

## Key Changes

### Driver & Connection

| SQLite | PostgreSQL |
|--------|------------|
| `sqlite3` module | `psycopg2` with `ThreadedConnectionPool` |
| `sqlite3.connect(path)` | `psycopg2.connect(host, db, user, pwd)` |
| `sqlite3.Row` | `RealDictCursor` |
| File-based | Network connection with pooling |

### Query Syntax

| SQLite | PostgreSQL |
|--------|------------|
| `:param` named params | `%(param)s` named params |
| `GROUP_CONCAT(x, ',')` | `STRING_AGG(x, ',')` |
| `= 1` / `= 0` for boolean | `= TRUE` / `= FALSE` or bare boolean |
| `LOWER(x) LIKE LOWER(y)` | `x ILIKE y` |
| `PRAGMA` statements | Remove |
| `BEGIN IMMEDIATE` | Standard `BEGIN` |

### Simplifications

1. Remove `retry_on_db_locked` decorator - PostgreSQL handles concurrency properly
2. Remove PRAGMA statements - SQLite-specific
3. Use connection pooling instead of per-request connections
4. Use `RETURNING` clause on INSERT/UPDATE where beneficial
5. Use `ILIKE` for case-insensitive search

## Database Class Structure

```python
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

class Database:
    _pool: pool.ThreadedConnectionPool = None

    def __init__(self):
        self._init_pool()

    def _init_pool(self):
        # Create connection pool from env vars
        # Min 1, max 10 connections

    def _get_connection(self):
        # Get connection from pool (context manager)

    def execute(self, sql, params=None):
        # Simplified execute with auto-commit for reads

    def execute_write(self, sql, params=None):
        # For single writes with commit

    def transaction(self):
        # Context manager for multi-statement transactions
```

## Implementation Phases

### Phase 1: Core Infrastructure
- Create `db_postgres.py` with connection pool and base execute methods
- Create `sql_queries_pg.py` with converted queries

### Phase 2: Migrate by Domain (dependency order)
1. **Units** - simplest, no dependencies
2. **Ingredients** - hierarchy logic, used by recipes
3. **Tags** - simple CRUD
4. **Recipes** - core entity, depends on ingredients/units/tags
5. **Ratings** - depends on recipes
6. **User ingredients** - depends on ingredients
7. **Search & recommendations** - complex queries, migrate last

### Phase 3: Wire Up
- Update `database.py` to instantiate PostgreSQL Database
- Update `config.py` with PostgreSQL settings
- Deploy and test on EC2

## Testing Approach

- Test each domain after migration via existing API endpoints
- EC2 already has data in PostgreSQL from earlier migration
- Verify all CRUD operations work
- Verify search and filtering
- Verify analytics queries

## Environment Variables

```
DB_HOST=localhost (or host.docker.internal from container)
DB_PORT=5432
DB_NAME=cocktaildb
DB_USER=cocktaildb
DB_PASSWORD=<password>
```

## Rollback

Branch-based rollback - this work is on `feature/ec2-migration` branch. Main branch retains SQLite implementation.
