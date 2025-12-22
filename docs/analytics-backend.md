# Analytics Backend Infrastructure

## Overview
This document specifies the backend infrastructure for cocktail database analytics, including FastAPI endpoints, database queries for hierarchical ingredient usage, S3 storage for pre-generated analytics, and Lambda functions to regenerate analytics on database changes.

## Objectives
- Provide efficient API endpoints for retrieving pre-computed analytics
- Implement database queries that leverage hierarchical ingredient structure
- Store pre-generated analytics results in S3 as static files
- Automatically regenerate analytics when database changes occur
- Support versioning for analytics data

## Architecture Philosophy

**Static Pre-Generated Analytics:** Analytics data is stored as static JSON files in S3 that are regenerated asynchronously after every database mutation. There is no cache expiration or TTL - files are always assumed to be current. This provides:
- Eventual consistency (slightly stale data for a few seconds is acceptable)
- Predictable performance (always reading static files from S3)

**Storage Strategy:** Only root-level views (no filters) are pre-generated and stored in S3. Filtered views (specific `level` or `parent_id`) are computed on-the-fly from the database. This trade-off is appropriate given:
- Small dataset size (< 500 ingredients in current data)
- Existing database indexes on `parent_id` and `path` fields
- Fast query performance (< 100ms for filtered views)
- Infrequent drill-down access patterns (most users view root-level analytics)
- API already has fallback logic to compute on-the-fly when storage is missing

## Architecture

### Components
1. **FastAPI Analytics Routes** (`api/routes/analytics.py`)
2. **Analytics Database Queries** (`api/db/db_analytics.py` - `AnalyticsQueries` class)
3. **S3 Analytics Storage** (`api/utils/analytics_storage.py` - `AnalyticsStorage` class)
4. **Analytics Generation Lambda** (`api/analytics_refresh.py`)
5. **SAM Template Updates** (S3 bucket, Lambda function, permissions)

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
- Data is served from pre-generated S3 files; if missing, computed on-the-fly

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

### 3. S3 Analytics Storage Manager

The `api/utils/analytics_storage.py` file contains the `AnalyticsStorage` class:

```python
import json
import boto3
from datetime import datetime
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class AnalyticsStorage:
    """S3 storage manager for pre-generated analytics data"""

    def __init__(self, bucket_name: str):
        self.bucket_name = bucket_name
        self.s3_client = boto3.client('s3')
        self.storage_version = "v1"

    def _get_storage_key(self, analytics_type: str) -> str:
        """Generate S3 key for analytics type"""
        return f"analytics/{self.storage_version}/{analytics_type}.json"

    def get_analytics(self, analytics_type: str) -> Optional[Dict[Any, Any]]:
        """Retrieve pre-generated analytics data from storage"""
        try:
            key = self._get_storage_key(analytics_type)
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=key
            )

            data = json.loads(response['Body'].read().decode('utf-8'))
            logger.info(f"Retrieved analytics data for {analytics_type}")
            return data

        except self.s3_client.exceptions.NoSuchKey:
            logger.info(f"No analytics data found for {analytics_type}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving analytics data for {analytics_type}: {str(e)}")
            return None

    def put_analytics(self, analytics_type: str, data: Dict[Any, Any]) -> bool:
        """Store pre-generated analytics data in storage"""
        try:
            key = self._get_storage_key(analytics_type)

            # Add metadata
            storage_data = {
                "data": data,
                "metadata": {
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    "storage_version": self.storage_version,
                    "analytics_type": analytics_type
                }
            }

            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=json.dumps(storage_data),
                ContentType='application/json'
            )

            logger.info(f"Successfully stored analytics data for {analytics_type}")
            return True

        except Exception as e:
            logger.error(f"Error storing analytics data for {analytics_type}: {str(e)}")
            return False
```

**Key Design Decisions:**
- No cache expiration or TTL checking - files are always assumed to be current
- Simpler API: just `get_analytics()` and `put_analytics()`

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
ANALYTICS_BUCKET = os.environ.get("ANALYTICS_BUCKET", "")
storage_manager = AnalyticsStorage(ANALYTICS_BUCKET) if ANALYTICS_BUCKET else None


@router.get("/ingredient-usage")
async def get_ingredient_usage_analytics(
    level: Optional[int] = None,
    parent_id: Optional[int] = None,
    db: Database = Depends(get_db),
    user: Optional[UserInfo] = Depends(get_current_user_optional),
):
    """Get ingredient usage statistics with hierarchical aggregation"""
    try:
        storage_key = f"ingredient-usage-{level}-{parent_id}"

        # Try to get from storage
        if storage_manager:
            stored_data = storage_manager.get_analytics(storage_key)
            if stored_data:
                return stored_data

        # If no pre-generated data exists, compute on-the-fly
        logger.info(f"No pre-generated data, computing stats (level={level}, parent_id={parent_id})")
        analytics = AnalyticsQueries(db)
        stats = analytics.get_ingredient_usage_stats(level=level, parent_id=parent_id)
        total_recipes = db.execute_query("SELECT COUNT(*) as count FROM recipes")[0]["count"]

        return {
            "data": stats,
            "metadata": {"total_recipes": total_recipes}
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

        # Try to get from storage
        if storage_manager:
            stored_data = storage_manager.get_analytics(storage_key)
            if stored_data:
                return stored_data

        # If no pre-generated data exists, compute on-the-fly
        logger.info("No pre-generated data, computing recipe complexity")
        analytics = AnalyticsQueries(db)
        distribution = analytics.get_recipe_complexity_distribution()

        return {"data": distribution, "metadata": {}}

    except Exception as e:
        logger.error(f"Error getting recipe complexity analytics: {str(e)}")
        raise DatabaseException("Failed to retrieve recipe complexity analytics", detail=str(e))
```

**Key Design Notes:**
- Imports `AnalyticsQueries` from `db.db_analytics` module
- Creates `AnalyticsQueries` instance with `Database` dependency
- Computes on-the-fly as fallback when storage is missing

### 5. Helper Function for Triggering Analytics Regeneration

Add to `api/utils/analytics_helpers.py` (called from recipes.py, ingredients.py after mutations):

```python
def trigger_analytics_refresh():
    """Trigger async analytics regeneration"""
    try:
        if os.environ.get("ANALYTICS_REFRESH_FUNCTION"):
            import boto3
            lambda_client = boto3.client('lambda')
            lambda_client.invoke(
                FunctionName=os.environ.get("ANALYTICS_REFRESH_FUNCTION"),
                InvocationType='Event'  # Async - non-blocking
            )
            logger.info("Analytics regeneration triggered")
    except Exception as e:
        logger.warning(f"Failed to trigger analytics regeneration: {str(e)}")
        # Don't fail the main operation if analytics trigger fails
```

**Called after all database mutations:**
- `create_recipe()`, `update_recipe()`, `delete_recipe()`
- `create_ingredient()`, `update_ingredient()`, `delete_ingredient()`
- `bulk_upload_recipes()`, `bulk_upload_ingredients()`

**Behavior:** Async invocation means the API returns immediately without waiting for analytics regeneration to complete. This provides eventual consistency - analytics may be slightly stale (a few seconds) until regeneration completes.

### 6. SAM Template Updates

Add to `template.yaml`:

```yaml
  # S3 Bucket for Analytics Storage
  AnalyticsStorageBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: !Sub "${AWS::StackName}-analytics-storage"
      PublicAccessBlockConfiguration:
        BlockPublicAcls: true
        BlockPublicPolicy: true
        IgnorePublicAcls: true
        RestrictPublicBuckets: true

  # Lambda function to regenerate analytics
  AnalyticsRefreshFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: !Sub "${AWS::StackName}-analytics-refresh"
      CodeUri: api/
      Handler: analytics_refresh.lambda_handler
      Runtime: python3.11
      Timeout: 300
      MemorySize: 512
      Environment:
        Variables:
          DB_PATH: !Ref DatabasePath
          ANALYTICS_BUCKET: !Ref AnalyticsStorageBucket
      FileSystemConfigs:
        - Arn: !GetAtt AccessPoint.Arn
          LocalMountPath: /mnt/efs
      VpcConfig:
        SecurityGroupIds:
          - !Ref LambdaSecurityGroup
        SubnetIds: !Ref PrivateSubnetIds
      Policies:
        - S3CrudPolicy:
            BucketName: !Ref AnalyticsStorageBucket
        - Statement:
            - Effect: Allow
              Action:
                - elasticfilesystem:ClientMount
                - elasticfilesystem:ClientWrite
              Resource: !GetAtt FileSystem.Arn

  # Update ApiFunction to include analytics bucket access
  ApiFunction:
    Properties:
      Environment:
        Variables:
          ANALYTICS_BUCKET: !Ref AnalyticsStorageBucket
          ANALYTICS_REFRESH_FUNCTION: !Ref AnalyticsRefreshFunction
      Policies:
        - S3ReadPolicy:
            BucketName: !Ref AnalyticsStorageBucket
        - Statement:
            - Effect: Allow
              Action:
                - lambda:InvokeFunction
              Resource: !GetAtt AnalyticsRefreshFunction.Arn
```

### 7. Analytics Generation Lambda Function

The `api/analytics_refresh.py` Lambda function generates all analytics data:

```python
"""Lambda function to generate pre-computed analytics data"""

import json
import logging
import os
from db.database import get_database
from db.db_analytics import AnalyticsQueries
from utils.analytics_cache import AnalyticsStorage

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """Generate all pre-computed analytics data files"""
    try:
        logger.info("Starting analytics data generation")

        # Initialize
        db = get_database()
        analytics = AnalyticsQueries(db)
        storage_manager = AnalyticsStorage(os.environ.get("ANALYTICS_BUCKET"))

        # Generate ingredient usage stats (ROOT LEVEL ONLY)
        # Note: Filtered views (level/parent_id) are computed on-the-fly by the API
        logger.info("Generating root-level ingredient usage stats")
        stats = analytics.get_ingredient_usage_stats()  # No parameters = root level
        total_recipes = db.execute_query("SELECT COUNT(*) as count FROM recipes")[0]["count"]
        storage_manager.put_analytics("ingredient-usage-None-None", {
            "data": stats,
            "total_recipes": total_recipes
        })

        # Generate recipe complexity distribution
        logger.info("Generating recipe complexity distribution")
        complexity = analytics.get_recipe_complexity_distribution()
        storage_manager.put_analytics("recipe-complexity", {
            "data": complexity
        })

        # Add more analytics types here as needed

        logger.info("Analytics data generation completed successfully")
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Analytics generation completed"})
        }

    except Exception as e:
        logger.error(f"Error generating analytics data: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
```

**Key Design Notes:**
- Imports `AnalyticsQueries` from `db.db_analytics` module
- Creates `AnalyticsQueries` instance with `Database` dependency
- Uses `AnalyticsStorage` for S3 operations
- Only generates root-level views (no filter parameters)
- Wraps data with metadata (`total_recipes` for ingredient-usage)
- Filtered views are computed on-the-fly by the API endpoints

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

- `boto3` (AWS SDK for Python) - already in requirements
- No new Python packages required

## Environment Variables

- `ANALYTICS_BUCKET`: S3 bucket name for analytics storage
- `ANALYTICS_REFRESH_FUNCTION`: Lambda function name for analytics regeneration

## Initialization

### Manual Analytics Generation Script

Add to `scripts/trigger-analytics-refresh.sh`:

```bash
#!/bin/bash
# Script to manually trigger analytics regeneration
# Usage: ./scripts/trigger-analytics-refresh.sh [dev|prod]

ENVIRONMENT=${1:-dev}
STACK_NAME="cocktail-db-${ENVIRONMENT}"
FUNCTION_NAME="${STACK_NAME}-analytics-refresh"

echo "Triggering analytics refresh for ${ENVIRONMENT} environment..."
aws lambda invoke \
  --function-name "${FUNCTION_NAME}" \
  --invocation-type Event \
  --region us-east-1 \
  /dev/stdout

echo "Analytics refresh triggered successfully"
echo "Check CloudWatch logs for progress: /aws/lambda/${FUNCTION_NAME}"
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
  ./scripts/trigger-analytics-refresh.sh $ENVIRONMENT
fi
```

## Considerations

1. **Eventual Consistency**: Analytics are regenerated asynchronously, so data may be slightly stale (a few seconds) after DB mutations
2. **Storage Updates**: Automatically triggered by DB changes via Lambda invocation
3. **Selective Pre-generation**: Only root-level views are pre-generated in S3. Filtered views (specific `level` or `parent_id`) are computed on-the-fly, leveraging database indexes for acceptable performance (<100ms)
4. **Hierarchy Performance**: Path-based queries with LIKE use existing indexes on `parent_id` and `path` fields
5. **Lambda Timeout**: 5-minute timeout for analytics regeneration should be sufficient for root-level views
6. **Storage Persistence**: Analytics files persist indefinitely in S3 (no lifecycle expiration)
7. **Error Handling**: Analytics regeneration failures should not block API operations (async invocation)
8. **No Manual Refresh**: Analytics regeneration is fully automatic after initialization - no user-facing API endpoint needed
9. **Initial Generation**: Use `scripts/trigger-analytics-refresh.sh` for first-time setup or manual regeneration
10. **Scalability**: If dataset grows beyond ~1000 ingredients or filtered queries become slow, consider pre-generating additional combinations

## Future Enhancements

- Add analytics warming on deployment (pre-generate all analytics files)
- Implement incremental updates (delta-based regeneration for large datasets)
- Add analytics for user-specific statistics
- Support date range filtering for time-based analytics
- Add pub/sub pattern for real-time analytics updates
