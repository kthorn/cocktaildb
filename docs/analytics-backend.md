# Analytics Backend Infrastructure

## Overview
This document specifies the backend infrastructure for cocktail database analytics, including FastAPI endpoints, database queries for hierarchical ingredient usage, local filesystem storage for pre-generated analytics, and the EC2-based analytics refresh workflow.

## Objectives
- Provide efficient API endpoints for retrieving pre-computed analytics
- Implement database queries that leverage hierarchical ingredient structure
- Store pre-generated analytics results on local disk as static files
- Automatically regenerate analytics when database changes occur
- Support versioning for analytics data

## Architecture Philosophy

**Static Pre-Generated Analytics:** Analytics data is stored as static JSON files on disk (configured via `ANALYTICS_PATH`) and regenerated asynchronously after database mutations. There is no cache expiration or TTL - files are always assumed to be current. This provides:
- Eventual consistency (slightly stale data for a few seconds is acceptable)
- Predictable performance (always reading static files from disk)

**Storage Strategy:** Only root-level views (no filters) are pre-generated and stored on disk. Filtered views (specific `level` or `parent_id`) are computed on-the-fly from the database. This trade-off is appropriate given:
- Small dataset size (< 500 ingredients in current data)
- Existing database indexes on `parent_id` and `path` fields
- Fast query performance (< 100ms for filtered views)
- Infrequent drill-down access patterns (most users view root-level analytics)
- Root-level analytics require pre-generation; filtered views are computed on-the-fly

## Architecture

### Components
1. **FastAPI Analytics Routes** (`api/routes/analytics.py`)
2. **Analytics Database Queries** (`api/db/db_analytics.py` - `AnalyticsQueries` class)
3. **Local Analytics Storage** (`api/utils/analytics_cache.py` - `AnalyticsStorage` class)
4. **Analytics Refresh Job** (`infrastructure/systemd/cocktaildb-analytics.service` + `infrastructure/scripts/trigger-analytics.sh`)

## Technical Specifications

### 1. Analytics API Endpoints

#### GET `/api/v1/analytics/ingredient-usage`
Returns ingredient usage statistics across all recipes, with hierarchical aggregation.

**Query Parameters:**
- `level` (optional): Hierarchy level (0=root, 1=first level children, etc.)
- `parent_id` (optional): Filter to children of specific ingredient

**Response Format:**
```json
{
  "data": [
    {
      "ingredient_id": 1,
      "ingredient_name": "Whiskey",
      "recipe_count": 45,
      "direct_usage": 12,
      "hierarchical_usage": 45,
      "has_children": true,
      "path": "/1/",
      "children_preview": ["Bourbon", "Rye", "Scotch"]
    }
  ],
  "metadata": {
    "generated_at": "2025-01-15T10:30:00Z",
    "storage_version": "v1",
    "total_recipes": 150
  }
}
```

**Logic:**
- `direct_usage`: Recipes that use this exact ingredient
- `hierarchical_usage`: Recipes that use this ingredient OR any child ingredients
- Aggregation follows the path hierarchy (e.g., `/1/23/45/` aggregates to `/1/23/` and `/1/`)
- Root-level data is served from pre-generated local files; filtered views are computed on-the-fly

#### GET `/api/v1/analytics/recipe-complexity`
Returns distribution of recipes by ingredient count.

**Response Format:**
```json
{
  "data": [
    {"ingredient_count": 2, "recipe_count": 15},
    {"ingredient_count": 3, "recipe_count": 42},
    {"ingredient_count": 4, "recipe_count": 38}
  ],
  "metadata": {
    "generated_at": "2025-01-15T10:30:00Z"
  }
}
```

### 2. Analytics Database Queries

Create a new file `api/db/db_analytics.py` with the `AnalyticsQueries` class:

```python
"""Analytics-specific database queries for CocktailDB"""

import logging
from typing import Dict, List, Any, Optional, cast

logger = logging.getLogger(__name__)


class AnalyticsQueries:
    """Analytics database query methods - separate from core Database class"""

    def __init__(self, db):
        """Initialize with a Database instance

        Args:
            db: Database instance from db_core.py
        """
        self.db = db

    def get_ingredient_usage_stats(
        self, level: Optional[int] = None, parent_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get ingredient usage statistics with hierarchical aggregation

        Args:
            level: Hierarchy level (0=root, 1=first level children, etc.) - currently unused
            parent_id: Filter to children of specific ingredient

        Returns:
            List of ingredient usage statistics with direct and hierarchical counts
        """
        try:
            # Build WHERE clause for parent_id filtering
            where_clause = "WHERE i.parent_id IS NULL" if parent_id is None else "WHERE i.parent_id = :parent_id"
            params = {} if parent_id is None else {"parent_id": parent_id}

            sql = f"""
            SELECT
              i.id as ingredient_id,
              i.name as ingredient_name,
              i.path,
              i.parent_id,
              COUNT(DISTINCT ri.recipe_id) as direct_usage,
              (
                SELECT COUNT(DISTINCT ri2.recipe_id)
                FROM recipe_ingredients ri2
                INNER JOIN ingredients i2 ON ri2.ingredient_id = i2.id
                WHERE i2.path LIKE i.path || '%'
              ) as hierarchical_usage,
              EXISTS(SELECT 1 FROM ingredients WHERE parent_id = i.id) as has_children
            FROM ingredients i
            LEFT JOIN recipe_ingredients ri ON ri.ingredient_id = i.id
            {where_clause}
            GROUP BY i.id, i.name, i.path, i.parent_id
            ORDER BY hierarchical_usage DESC
            """

            result = cast(List[Dict[str, Any]], self.db.execute_query(sql, params))
            return result
        except Exception as e:
            logger.error(f"Error getting ingredient usage stats: {str(e)}")
            raise

    def get_recipe_complexity_distribution(self) -> List[Dict[str, Any]]:
        """Get recipe complexity distribution by ingredient count

        Returns:
            List of {ingredient_count, recipe_count} dictionaries
        """
        try:
            sql = """
            SELECT
              ingredient_count,
              COUNT(*) as recipe_count
            FROM (
              SELECT
                recipe_id,
                COUNT(DISTINCT ingredient_id) as ingredient_count
              FROM recipe_ingredients
              GROUP BY recipe_id
            ) counts
            GROUP BY ingredient_count
            ORDER BY ingredient_count
            """

            result = cast(List[Dict[str, Any]], self.db.execute_query(sql))
            return result
        except Exception as e:
            logger.error(f"Error getting recipe complexity distribution: {str(e)}")
            raise
```

**Design Notes:**
- Separate file keeps `db_core.py` focused on core CRUD operations
- `AnalyticsQueries` uses composition pattern, accepting a `Database` instance
- Uses the existing `execute_query()` method from `Database` class
- Easy to test independently and extend with new analytics queries

### 3. Local Analytics Storage Manager

The `api/utils/analytics_cache.py` file contains the `AnalyticsStorage` class:

```python
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class AnalyticsStorage:
    """Local filesystem storage for pre-generated analytics data"""

    def __init__(self, storage_path: str):
        self.storage_path = Path(storage_path)
        self.storage_version = "v1"
        version_path = self.storage_path / self.storage_version
        version_path.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, analytics_type: str) -> Path:
        """Generate file path for analytics type"""
        return self.storage_path / self.storage_version / f"{analytics_type}.json"

    def get_analytics(self, analytics_type: str) -> Optional[Dict[Any, Any]]:
        """Retrieve pre-generated analytics data from storage"""
        try:
            file_path = self._get_file_path(analytics_type)
            if not file_path.exists():
                logger.info(f"No analytics data found for {analytics_type}")
                return None

            with open(file_path, "r", encoding="utf-8") as file_handle:
                data = json.load(file_handle)
            logger.info(f"Retrieved analytics data for {analytics_type}")
            return data

        except Exception as e:
            logger.error(f"Error retrieving analytics data for {analytics_type}: {str(e)}")
            return None

    def put_analytics(self, analytics_type: str, data: Dict[Any, Any]) -> bool:
        """Store pre-generated analytics data in storage"""
        try:
            file_path = self._get_file_path(analytics_type)
            storage_data = {
                "data": data,
                "metadata": {
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    "storage_version": self.storage_version,
                    "analytics_type": analytics_type
                }
            }

            with open(file_path, "w", encoding="utf-8") as file_handle:
                json.dump(storage_data, file_handle)

            logger.info(f"Successfully stored analytics data for {analytics_type}")
            return True

        except Exception as e:
            logger.error(f"Error storing analytics data for {analytics_type}: {str(e)}")
            return False
```

**Key Design Decisions:**
- No cache expiration or TTL checking - files are always assumed to be current
- Storage path is configured via `ANALYTICS_PATH` and versioned under `v1/`

### 4. Analytics Routes Implementation

The `api/routes/analytics.py` file implements the analytics endpoints:

```python
"""Analytics endpoints for the CocktailDB API"""

import logging
import os
from typing import Optional
from fastapi import APIRouter, Depends

from dependencies.auth import UserInfo, get_current_user_optional
from db.database import get_database as get_db
from db.db_core import Database
from db.db_analytics import AnalyticsQueries
from core.exceptions import DatabaseException
from utils.analytics_cache import AnalyticsStorage

# Configure logger (inherits from main.py configuration)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])

# Initialize storage manager
ANALYTICS_PATH = os.environ.get("ANALYTICS_PATH", "")
storage_manager = AnalyticsStorage(ANALYTICS_PATH) if ANALYTICS_PATH else None


@router.get("/ingredient-usage")
async def get_ingredient_usage_analytics(
    level: Optional[int] = None,
    parent_id: Optional[int] = None,
    db: Database = Depends(get_db),
    user: Optional[UserInfo] = Depends(get_current_user_optional),
):
    """Get ingredient usage statistics with hierarchical aggregation"""
    try:
        # Root-level data is pre-generated and cached on disk
        if level is None and parent_id is None:
            if not storage_manager:
                raise DatabaseException("Analytics storage not configured")

            stored_data = storage_manager.get_analytics("ingredient-usage")
            if not stored_data:
                raise DatabaseException(
                    "Analytics not generated. Please trigger analytics refresh.",
                    detail="ingredient-usage data not found in storage"
                )

            return stored_data

        # Filtered views are computed on-the-fly
        analytics = AnalyticsQueries(db)
        stats = analytics.get_ingredient_usage_stats(parent_id=parent_id)

        return {
            "data": stats,
            "metadata": {
                "computed_on_the_fly": True,
                "level": level,
                "parent_id": parent_id
            }
        }

    except Exception as e:
        logger.error(f"Error getting ingredient usage analytics: {str(e)}")
        raise DatabaseException("Failed to retrieve ingredient usage analytics", detail=str(e))


@router.get("/recipe-complexity")
async def get_recipe_complexity_analytics(
    db: Database = Depends(get_db),
    user: Optional[UserInfo] = Depends(get_current_user_optional),
):
    """Get recipe complexity distribution"""
    try:
        storage_key = "recipe-complexity"

        if not storage_manager:
            raise DatabaseException("Analytics storage not configured")

        stored_data = storage_manager.get_analytics(storage_key)
        if not stored_data:
            raise DatabaseException(
                "Analytics not generated. Please trigger analytics refresh.",
                detail=f"{storage_key} data not found in storage"
            )

        return stored_data

    except Exception as e:
        logger.error(f"Error getting recipe complexity analytics: {str(e)}")
        raise DatabaseException("Failed to retrieve recipe complexity analytics", detail=str(e))
```

**Key Design Notes:**
- Imports `AnalyticsQueries` from `db.db_analytics` module
- Creates `AnalyticsQueries` instance with `Database` dependency
- Uses `AnalyticsStorage` for local filesystem operations
- Root-level analytics require pre-generation; ingredient usage drill-down is computed on-the-fly

### 5. Analytics Refresh Workflow (EC2)

Analytics data is generated out-of-band on EC2 and written to `ANALYTICS_PATH`. Refresh is managed by systemd and helper scripts:

- `infrastructure/systemd/cocktaildb-analytics.service` runs the refresh job in the API container
- `infrastructure/systemd/cocktaildb-analytics.timer` schedules periodic refreshes
- `infrastructure/systemd/cocktaildb-analytics-debounce.timer` and `infrastructure/scripts/analytics-debounce-check.sh` debounce frequent changes
- Manual trigger: `infrastructure/scripts/trigger-analytics.sh`

**Output:** JSON files under `${ANALYTICS_PATH}/v1/` (for example, `ingredient-usage.json`, `recipe-complexity.json`).

## Testing Approach

### Unit Tests
- Test database query functions with mock data
- Test storage manager get/put operations
- Test analytics calculation logic

### Integration Tests
- Test full endpoint flow (DB → Storage → API response)
- Test storage hit/miss scenarios
- Test analytics regeneration triggers

### Performance Tests
- Benchmark query performance with different dataset sizes
- Test storage retrieval latency
- Test concurrent access to stored analytics data

## Dependencies

- No new Python packages required for local analytics storage

## Environment Variables

- `ANALYTICS_PATH`: Filesystem path for analytics storage (for example, `/var/lib/cocktaildb/analytics`)

## Initialization

### Manual Analytics Generation

Use the EC2 helper script to run the refresh job:

```bash
./infrastructure/scripts/trigger-analytics.sh
```

To run in the background via systemd:

```bash
./infrastructure/scripts/trigger-analytics.sh --bg
```

**When to use:**
- Initial deployment (no analytics data exists yet)
- After database restore from backup
- Manual regeneration for testing or debugging
- Post-migration when analytics structure changes

**Integration with deployment:**
Consider adding to `scripts/deploy.bat` or `scripts/deploy.sh` after successful deployment:
```bash
# Optional: Trigger initial analytics generation
if [ "$SKIP_ANALYTICS_INIT" != "true" ]; then
  echo "Triggering initial analytics generation..."
  ./infrastructure/scripts/trigger-analytics.sh
fi
```

## Considerations

1. **Eventual Consistency**: Analytics are regenerated asynchronously, so data may be slightly stale after DB mutations
2. **Storage Updates**: Refresh is driven by the EC2 systemd job and debounce checks
3. **Selective Pre-generation**: Only root-level views are pre-generated on disk; filtered views are computed on-the-fly
4. **Hierarchy Performance**: Path-based queries with LIKE use existing indexes on `parent_id` and `path` fields
5. **Refresh Duration**: Long-running analytics refresh is handled by the systemd service timeout (currently 1 hour)
6. **Storage Persistence**: Analytics files persist on disk until regenerated or cleaned up
7. **Error Handling**: Analytics refresh failures should not block API operations
8. **Manual Refresh**: Use `infrastructure/scripts/trigger-analytics.sh` for first-time setup or manual regeneration
9. **Scalability**: If dataset grows beyond ~1000 ingredients or filtered queries become slow, consider pre-generating additional combinations

## Future Enhancements

- Add analytics warming on deployment (pre-generate all analytics files)
- Implement incremental updates (delta-based regeneration for large datasets)
- Add analytics for user-specific statistics
- Support date range filtering for time-based analytics
- Add pub/sub pattern for real-time analytics updates
