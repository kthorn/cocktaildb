# Analytics Backend Implementation Plan

> **For Claude:** Use `${CLAUDE_PLUGIN_ROOT}/skills/collaboration/executing-plans/SKILL.md` to implement this plan task-by-task. Follow TDD principles from `${CLAUDE_PLUGIN_ROOT}/skills/testing/test-driven-development/SKILL.md`.

**Goal:** Implement complete analytics backend infrastructure with pre-generated analytics stored in S3, automatic regeneration on database mutations, and FastAPI endpoints for analytics retrieval.

**Architecture:** Static pre-generated analytics stored as JSON files in S3, regenerated asynchronously via Lambda after database mutations. Root-level views are pre-generated; filtered views computed on-the-fly. FastAPI endpoints serve from S3 with database fallback.

**Tech Stack:** FastAPI, boto3 (AWS SDK), SQLite, AWS Lambda, S3, SAM/CloudFormation

---

## Task 1: Analytics Database Queries Module

**Files:**
- Create: `api/db/db_analytics.py`
- Test: `tests/test_db_analytics.py`

### Step 1: Write failing tests for analytics queries

Create `tests/test_db_analytics.py`:

```python
"""Tests for analytics database queries"""
import pytest
from api.db.db_analytics import AnalyticsQueries
from api.db.db_core import Database


def test_analytics_queries_initialization():
    """Test AnalyticsQueries can be initialized with Database instance"""
    db = Database()
    analytics = AnalyticsQueries(db)
    assert analytics.db is not None


def test_get_ingredient_usage_stats_root_level(db_with_test_data):
    """Test ingredient usage stats returns root level ingredients"""
    analytics = AnalyticsQueries(db_with_test_data)
    stats = analytics.get_ingredient_usage_stats()

    assert isinstance(stats, list)
    assert len(stats) > 0
    # Check structure
    first_stat = stats[0]
    assert "ingredient_id" in first_stat
    assert "ingredient_name" in first_stat
    assert "direct_usage" in first_stat
    assert "hierarchical_usage" in first_stat
    assert "has_children" in first_stat
    assert "path" in first_stat


def test_get_ingredient_usage_stats_by_parent(db_with_test_data):
    """Test ingredient usage stats filtered by parent_id"""
    analytics = AnalyticsQueries(db_with_test_data)
    # Assuming parent_id=1 exists
    stats = analytics.get_ingredient_usage_stats(parent_id=1)

    assert isinstance(stats, list)
    # All results should have parent_id=1
    for stat in stats:
        assert stat.get("parent_id") == 1


def test_get_recipe_complexity_distribution(db_with_test_data):
    """Test recipe complexity distribution returns ingredient count stats"""
    analytics = AnalyticsQueries(db_with_test_data)
    distribution = analytics.get_recipe_complexity_distribution()

    assert isinstance(distribution, list)
    assert len(distribution) > 0
    # Check structure
    first_item = distribution[0]
    assert "ingredient_count" in first_item
    assert "recipe_count" in first_item
```

### Step 2: Run tests to verify they fail

Run: `pytest tests/test_db_analytics.py -v`
Expected: FAIL with "No module named 'api.db.db_analytics'"

### Step 3: Implement AnalyticsQueries class

Create `api/db/db_analytics.py`:

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

### Step 4: Run tests to verify they pass

Run: `pytest tests/test_db_analytics.py -v`
Expected: PASS (may need test database fixture setup)

### Step 5: Commit

```bash
git add api/db/db_analytics.py tests/test_db_analytics.py
git commit -m "feat: add analytics database queries module

Implements AnalyticsQueries class with:
- Ingredient usage statistics with hierarchical aggregation
- Recipe complexity distribution by ingredient count

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: S3 Analytics Storage Manager

**Files:**
- Create: `api/utils/analytics_cache.py`
- Test: `tests/test_analytics_cache.py`

### Step 1: Write failing tests for storage manager

Create `tests/test_analytics_cache.py`:

```python
"""Tests for S3 analytics storage manager"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from api.utils.analytics_cache import AnalyticsStorage


@pytest.fixture
def mock_s3_client():
    """Mock boto3 S3 client"""
    with patch('boto3.client') as mock:
        yield mock.return_value


def test_analytics_storage_initialization():
    """Test AnalyticsStorage can be initialized"""
    storage = AnalyticsStorage("test-bucket")
    assert storage.bucket_name == "test-bucket"
    assert storage.storage_version == "v1"


def test_get_storage_key_generation():
    """Test storage key generation"""
    storage = AnalyticsStorage("test-bucket")
    key = storage._get_storage_key("ingredient-usage")
    assert key == "analytics/v1/ingredient-usage.json"


def test_get_analytics_success(mock_s3_client):
    """Test retrieving analytics data from S3"""
    storage = AnalyticsStorage("test-bucket")

    # Mock S3 response
    mock_body = Mock()
    mock_body.read.return_value = json.dumps({"data": [{"test": "value"}]}).encode('utf-8')
    mock_s3_client.get_object.return_value = {'Body': mock_body}
    storage.s3_client = mock_s3_client

    result = storage.get_analytics("ingredient-usage")

    assert result is not None
    assert "data" in result
    mock_s3_client.get_object.assert_called_once()


def test_get_analytics_not_found(mock_s3_client):
    """Test retrieving non-existent analytics returns None"""
    storage = AnalyticsStorage("test-bucket")
    storage.s3_client = mock_s3_client

    # Mock NoSuchKey exception
    from botocore.exceptions import ClientError
    mock_s3_client.get_object.side_effect = ClientError(
        {'Error': {'Code': 'NoSuchKey'}}, 'GetObject'
    )

    result = storage.get_analytics("nonexistent")
    assert result is None


def test_put_analytics_success(mock_s3_client):
    """Test storing analytics data in S3"""
    storage = AnalyticsStorage("test-bucket")
    storage.s3_client = mock_s3_client

    test_data = [{"ingredient_id": 1, "count": 10}]
    result = storage.put_analytics("ingredient-usage", test_data)

    assert result is True
    mock_s3_client.put_object.assert_called_once()
    # Verify call included metadata
    call_args = mock_s3_client.put_object.call_args
    assert call_args[1]['Bucket'] == "test-bucket"
    assert call_args[1]['ContentType'] == 'application/json'
```

### Step 2: Run tests to verify they fail

Run: `pytest tests/test_analytics_cache.py -v`
Expected: FAIL with "No module named 'api.utils.analytics_cache'"

### Step 3: Create utils directory and implement AnalyticsStorage

```bash
mkdir -p api/utils
touch api/utils/__init__.py
```

Create `api/utils/analytics_cache.py`:

```python
"""S3 storage manager for pre-generated analytics data"""

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

### Step 4: Run tests to verify they pass

Run: `pytest tests/test_analytics_cache.py -v`
Expected: PASS

### Step 5: Commit

```bash
git add api/utils/ tests/test_analytics_cache.py
git commit -m "feat: add S3 analytics storage manager

Implements AnalyticsStorage class for managing pre-generated analytics in S3:
- Storage key generation with versioning
- Get/put operations with error handling
- Automatic metadata injection

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: Analytics API Routes

**Files:**
- Create: `api/routes/analytics.py`
- Modify: `api/main.py` (register router)
- Test: `tests/test_analytics_routes.py`

### Step 1: Write failing tests for analytics endpoints

Create `tests/test_analytics_routes.py`:

```python
"""Tests for analytics API endpoints"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch


def test_get_ingredient_usage_no_filters(client):
    """Test ingredient usage endpoint without filters"""
    response = client.get("/analytics/ingredient-usage")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "metadata" in data
    assert isinstance(data["data"], list)


def test_get_ingredient_usage_with_parent_filter(client):
    """Test ingredient usage endpoint with parent_id filter"""
    response = client.get("/analytics/ingredient-usage?parent_id=1")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data


def test_get_recipe_complexity(client):
    """Test recipe complexity endpoint"""
    response = client.get("/analytics/recipe-complexity")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "metadata" in data
    assert isinstance(data["data"], list)


def test_analytics_fallback_when_storage_missing():
    """Test that analytics compute on-the-fly when S3 storage is unavailable"""
    # Mock storage to return None
    with patch('api.routes.analytics.storage_manager') as mock_storage:
        mock_storage.get_analytics.return_value = None
        # Test should still succeed by computing from database
        # Implementation details depend on client fixture
```

### Step 2: Run tests to verify they fail

Run: `pytest tests/test_analytics_routes.py -v`
Expected: FAIL with "No module named 'api.routes.analytics'"

### Step 3: Implement analytics routes

Create `api/routes/analytics.py`:

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

### Step 4: Register router in main.py

Modify `api/main.py`:

```python
# Add import at top
from routes import ingredients, recipes, ratings, units, tags, auth, admin, user_ingredients, stats, analytics

# Add router registration after other routers
app.include_router(analytics.router)
```

### Step 5: Run tests to verify they pass

Run: `pytest tests/test_analytics_routes.py -v`
Expected: PASS

### Step 6: Commit

```bash
git add api/routes/analytics.py api/main.py tests/test_analytics_routes.py
git commit -m "feat: add analytics API endpoints

Implements FastAPI analytics routes:
- /analytics/ingredient-usage with level and parent_id filters
- /analytics/recipe-complexity for ingredient count distribution
- S3 storage fallback to on-the-fly computation

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: Analytics Refresh Helper

**Files:**
- Create: `api/utils/analytics_helpers.py`
- Test: `tests/test_analytics_helpers.py`

### Step 1: Write failing tests for analytics refresh trigger

Create `tests/test_analytics_helpers.py`:

```python
"""Tests for analytics helper functions"""
import pytest
from unittest.mock import patch, Mock
from api.utils.analytics_helpers import trigger_analytics_refresh


def test_trigger_analytics_refresh_success():
    """Test successful analytics refresh trigger"""
    with patch('boto3.client') as mock_boto:
        mock_lambda = Mock()
        mock_boto.return_value = mock_lambda

        with patch.dict('os.environ', {'ANALYTICS_REFRESH_FUNCTION': 'test-function'}):
            trigger_analytics_refresh()

            mock_lambda.invoke.assert_called_once()
            call_args = mock_lambda.invoke.call_args
            assert call_args[1]['FunctionName'] == 'test-function'
            assert call_args[1]['InvocationType'] == 'Event'


def test_trigger_analytics_refresh_no_function_configured():
    """Test trigger does nothing when function not configured"""
    with patch('boto3.client') as mock_boto:
        mock_lambda = Mock()
        mock_boto.return_value = mock_lambda

        with patch.dict('os.environ', {}, clear=True):
            trigger_analytics_refresh()

            mock_lambda.invoke.assert_not_called()


def test_trigger_analytics_refresh_failure_handling():
    """Test that trigger failures don't raise exceptions"""
    with patch('boto3.client') as mock_boto:
        mock_lambda = Mock()
        mock_lambda.invoke.side_effect = Exception("Lambda invocation failed")
        mock_boto.return_value = mock_lambda

        with patch.dict('os.environ', {'ANALYTICS_REFRESH_FUNCTION': 'test-function'}):
            # Should not raise exception
            trigger_analytics_refresh()
```

### Step 2: Run tests to verify they fail

Run: `pytest tests/test_analytics_helpers.py -v`
Expected: FAIL with "No module named 'api.utils.analytics_helpers'"

### Step 3: Implement analytics refresh helper

Create `api/utils/analytics_helpers.py`:

```python
"""Helper functions for analytics operations"""

import logging
import os

logger = logging.getLogger(__name__)


def trigger_analytics_refresh():
    """Trigger async analytics regeneration

    Invokes the analytics refresh Lambda function asynchronously.
    Failures are logged but don't fail the main operation.
    """
    try:
        function_name = os.environ.get("ANALYTICS_REFRESH_FUNCTION")
        if not function_name:
            logger.debug("ANALYTICS_REFRESH_FUNCTION not configured, skipping trigger")
            return

        import boto3
        lambda_client = boto3.client('lambda')
        lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='Event'  # Async - non-blocking
        )
        logger.info("Analytics regeneration triggered")
    except Exception as e:
        logger.warning(f"Failed to trigger analytics regeneration: {str(e)}")
        # Don't fail the main operation if analytics trigger fails
```

### Step 4: Run tests to verify they pass

Run: `pytest tests/test_analytics_helpers.py -v`
Expected: PASS

### Step 5: Commit

```bash
git add api/utils/analytics_helpers.py tests/test_analytics_helpers.py
git commit -m "feat: add analytics refresh trigger helper

Implements trigger_analytics_refresh() for async Lambda invocation:
- Non-blocking async invocation
- Graceful failure handling
- Configurable via ANALYTICS_REFRESH_FUNCTION env var

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: Analytics Refresh Lambda Function

**Files:**
- Create: `api/analytics_refresh.py`
- Test: `tests/test_analytics_refresh.py`

### Step 1: Write failing tests for Lambda function

Create `tests/test_analytics_refresh.py`:

```python
"""Tests for analytics refresh Lambda function"""
import pytest
import json
from unittest.mock import Mock, patch
from api.analytics_refresh import lambda_handler


def test_lambda_handler_success():
    """Test successful analytics generation"""
    with patch('api.analytics_refresh.get_database') as mock_get_db, \
         patch('api.analytics_refresh.AnalyticsQueries') as mock_analytics, \
         patch('api.analytics_refresh.AnalyticsStorage') as mock_storage:

        # Setup mocks
        mock_db = Mock()
        mock_get_db.return_value = mock_db
        mock_db.execute_query.return_value = [{"count": 150}]

        mock_analytics_instance = Mock()
        mock_analytics.return_value = mock_analytics_instance
        mock_analytics_instance.get_ingredient_usage_stats.return_value = [{"test": "data"}]
        mock_analytics_instance.get_recipe_complexity_distribution.return_value = [{"count": 5}]

        mock_storage_instance = Mock()
        mock_storage.return_value = mock_storage_instance
        mock_storage_instance.put_analytics.return_value = True

        # Execute
        result = lambda_handler({}, {})

        # Verify
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert "message" in body


def test_lambda_handler_failure():
    """Test analytics generation failure handling"""
    with patch('api.analytics_refresh.get_database') as mock_get_db:
        mock_get_db.side_effect = Exception("Database connection failed")

        result = lambda_handler({}, {})

        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "error" in body
```

### Step 2: Run tests to verify they fail

Run: `pytest tests/test_analytics_refresh.py -v`
Expected: FAIL with "No module named 'api.analytics_refresh'"

### Step 3: Implement analytics refresh Lambda

Create `api/analytics_refresh.py`:

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

### Step 4: Run tests to verify they pass

Run: `pytest tests/test_analytics_refresh.py -v`
Expected: PASS

### Step 5: Commit

```bash
git add api/analytics_refresh.py tests/test_analytics_refresh.py
git commit -m "feat: add analytics refresh Lambda function

Implements analytics generation Lambda:
- Root-level ingredient usage statistics
- Recipe complexity distribution
- S3 storage via AnalyticsStorage
- Comprehensive error handling

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: Update SAM Template

**Files:**
- Modify: `template.yaml`

### Step 1: Add analytics infrastructure to template.yaml

Add after the existing resources section:

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
    DependsOn:
      - MountTarget
    Properties:
      FunctionName: !Sub "${AWS::StackName}-analytics-refresh"
      CodeUri: api/
      Handler: analytics_refresh.lambda_handler
      Runtime: python3.11
      Timeout: 300
      MemorySize: 512
      Environment:
        Variables:
          DB_PATH: !Sub /mnt/efs/${DatabaseName}.db
          ANALYTICS_BUCKET: !Ref AnalyticsStorageBucket
      FileSystemConfigs:
        - Arn: !GetAtt EFSAccessPoint.Arn
          LocalMountPath: /mnt/efs
      VpcConfig:
        SecurityGroupIds:
          - !Ref LambdaSecurityGroup
        SubnetIds:
          - !Ref PrivateSubnet
      Policies:
        - S3CrudPolicy:
            BucketName: !Ref AnalyticsStorageBucket
        - VPCAccessPolicy: {}
        - Statement:
            - Effect: Allow
              Action:
                - elasticfilesystem:ClientMount
                - elasticfilesystem:ClientWrite
              Resource: !GetAtt CocktailEFS.Arn
```

### Step 2: Update CocktailLambda (ApiFunction) environment and policies

In the existing `CocktailLambda` resource, add:

```yaml
  CocktailLambda:
    Properties:
      Environment:
        Variables:
          # ... existing vars ...
          ANALYTICS_BUCKET: !Ref AnalyticsStorageBucket
          ANALYTICS_REFRESH_FUNCTION: !Ref AnalyticsRefreshFunction
      Policies:
        # ... existing policies ...
        - S3ReadPolicy:
            BucketName: !Ref AnalyticsStorageBucket
        - Statement:
            - Effect: Allow
              Action:
                - lambda:InvokeFunction
              Resource: !GetAtt AnalyticsRefreshFunction.Arn
```

### Step 3: Add analytics API Gateway events

In `CocktailLambda` Events section, add:

```yaml
        GetIngredientUsageAnalytics:
          Type: Api
          Properties:
            RestApiId: !Ref CocktailAPI
            Path: /analytics/ingredient-usage
            Method: get
        GetRecipeComplexityAnalytics:
          Type: Api
          Properties:
            RestApiId: !Ref CocktailAPI
            Path: /analytics/recipe-complexity
            Method: get
```

### Step 4: Verify template syntax

Run: `sam validate --template-file template.yaml --lint`
Expected: No errors

### Step 5: Commit

```bash
git add template.yaml
git commit -m "feat: add analytics infrastructure to SAM template

Adds to CloudFormation template:
- AnalyticsStorageBucket for S3 storage
- AnalyticsRefreshFunction Lambda for regeneration
- API Gateway events for analytics endpoints
- IAM policies for S3 read/write and Lambda invocation
- Environment variables for analytics configuration

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 7: Manual Analytics Refresh Script

**Files:**
- Create: `scripts/trigger-analytics-refresh.sh`

### Step 1: Create shell script for manual refresh

Create `scripts/trigger-analytics-refresh.sh`:

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

### Step 2: Make script executable

Run: `chmod +x scripts/trigger-analytics-refresh.sh`
Expected: Script becomes executable

### Step 3: Test script locally (dry run)

Run: `./scripts/trigger-analytics-refresh.sh dev --dry-run` (if AWS CLI available)
Expected: Shows what would be executed

### Step 4: Commit

```bash
git add scripts/trigger-analytics-refresh.sh
git commit -m "feat: add manual analytics refresh script

Shell script for triggering analytics regeneration:
- Supports dev/prod environments
- Async Lambda invocation
- CloudWatch logs reference

Usage: ./scripts/trigger-analytics-refresh.sh [dev|prod]

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 8: Integrate Analytics Refresh Triggers

**Files:**
- Modify: `api/routes/recipes.py`
- Modify: `api/routes/ingredients.py`

### Step 1: Import trigger function in recipes.py

At top of `api/routes/recipes.py`:

```python
from utils.analytics_helpers import trigger_analytics_refresh
```

### Step 2: Add trigger calls after recipe mutations

Add after successful mutations in:
- `create_recipe()`
- `update_recipe()`
- `delete_recipe()`
- `bulk_upload_recipes()`

```python
    # Trigger analytics refresh (async)
    trigger_analytics_refresh()
```

### Step 3: Import trigger function in ingredients.py

At top of `api/routes/ingredients.py`:

```python
from utils.analytics_helpers import trigger_analytics_refresh
```

### Step 4: Add trigger calls after ingredient mutations

Add after successful mutations in:
- `create_ingredient()`
- `update_ingredient()`
- `delete_ingredient()`
- `bulk_upload_ingredients()`

```python
    # Trigger analytics refresh (async)
    trigger_analytics_refresh()
```

### Step 5: Test mutation endpoints still work

Run: `pytest tests/test_recipes.py tests/test_ingredients.py -v`
Expected: PASS (tests should still pass with trigger added)

### Step 6: Commit

```bash
git add api/routes/recipes.py api/routes/ingredients.py
git commit -m "feat: integrate analytics refresh triggers in mutation endpoints

Adds trigger_analytics_refresh() calls after:
- Recipe create/update/delete/bulk operations
- Ingredient create/update/delete/bulk operations

Analytics regeneration occurs asynchronously without blocking API responses.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 9: Write Integration Tests

**Files:**
- Create: `tests/integration/test_analytics_e2e.py`

### Step 1: Write end-to-end analytics tests

Create `tests/integration/test_analytics_e2e.py`:

```python
"""End-to-end integration tests for analytics infrastructure"""
import pytest
import json
from unittest.mock import Mock, patch


def test_analytics_ingredient_usage_e2e(client, db_with_test_data):
    """Test complete flow: DB -> Analytics Query -> API Response"""
    response = client.get("/analytics/ingredient-usage")

    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "metadata" in data
    assert isinstance(data["data"], list)

    # Verify data structure
    if len(data["data"]) > 0:
        item = data["data"][0]
        assert "ingredient_id" in item
        assert "ingredient_name" in item
        assert "direct_usage" in item
        assert "hierarchical_usage" in item


def test_analytics_recipe_complexity_e2e(client, db_with_test_data):
    """Test complete flow: DB -> Analytics Query -> API Response"""
    response = client.get("/analytics/recipe-complexity")

    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert isinstance(data["data"], list)


def test_recipe_mutation_triggers_analytics_refresh(client, authenticated_headers):
    """Test that recipe creation triggers analytics refresh"""
    with patch('api.routes.recipes.trigger_analytics_refresh') as mock_trigger:
        recipe_data = {
            "name": "Test Recipe",
            "ingredients": [{"ingredient_id": 1, "quantity": "1", "unit_id": 1}],
            "instructions": "Test instructions"
        }

        response = client.post("/recipes", json=recipe_data, headers=authenticated_headers)

        if response.status_code == 201:
            mock_trigger.assert_called_once()


def test_ingredient_mutation_triggers_analytics_refresh(client, authenticated_headers):
    """Test that ingredient creation triggers analytics refresh"""
    with patch('api.routes.ingredients.trigger_analytics_refresh') as mock_trigger:
        ingredient_data = {"name": "Test Ingredient"}

        response = client.post("/ingredients", json=ingredient_data, headers=authenticated_headers)

        if response.status_code == 201:
            mock_trigger.assert_called_once()
```

### Step 2: Run integration tests

Run: `pytest tests/integration/test_analytics_e2e.py -v`
Expected: PASS

### Step 3: Commit

```bash
git add tests/integration/test_analytics_e2e.py
git commit -m "test: add end-to-end analytics integration tests

Tests complete analytics flow:
- Database queries to API responses
- Analytics refresh triggers on mutations
- Data structure validation

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 10: Documentation and Verification

**Files:**
- Update: `CLAUDE.md` (add analytics commands)
- Update: `.gitignore` (if needed)

### Step 1: Update CLAUDE.md with analytics commands

Add to CLAUDE.md:

```markdown
### Analytics Operations
- **Manual analytics regeneration**: `./scripts/trigger-analytics-refresh.sh [dev|prod]`
- **Check analytics logs**: View CloudWatch logs for `<stack-name>-analytics-refresh` function
```

### Step 2: Run full test suite

Run: `pytest tests/ -v`
Expected: All tests PASS

### Step 3: Verify SAM build

Run: `sam build --template-file template.yaml`
Expected: Build succeeds

### Step 4: Final verification checklist

- [ ] All tests pass
- [ ] SAM template validates
- [ ] Analytics endpoints accessible locally (`uvicorn api.main:app`)
- [ ] Integration tests cover mutations and analytics
- [ ] Documentation updated

### Step 5: Final commit

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with analytics operations

Adds analytics commands and operational guidance.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Deployment Notes

After implementation is complete:

1. **Build and deploy**:
   ```bash
   scripts/deploy.bat dev
   ```

2. **Initial analytics generation**:
   ```bash
   ./scripts/trigger-analytics-refresh.sh dev
   ```

3. **Verify endpoints**:
   ```bash
   curl https://<api-endpoint>/analytics/ingredient-usage
   curl https://<api-endpoint>/analytics/recipe-complexity
   ```

4. **Monitor CloudWatch logs** for analytics refresh function

---

## Testing Strategy

- **Unit Tests**: Each module (db_analytics, analytics_cache, analytics_helpers) tested in isolation
- **Integration Tests**: API endpoints with mocked S3 and database
- **End-to-End Tests**: Complete flow from mutation to analytics refresh
- **Manual Testing**: Deploy to dev and test with real AWS infrastructure

## Success Criteria

- [ ] Analytics queries return correct data structure
- [ ] S3 storage and retrieval work correctly
- [ ] API endpoints serve from S3 with database fallback
- [ ] Analytics refresh triggers on database mutations
- [ ] Lambda function generates analytics successfully
- [ ] Manual refresh script works
- [ ] All tests pass
- [ ] SAM deployment succeeds
