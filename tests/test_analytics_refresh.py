"""Tests for analytics refresh Lambda function"""
import pytest
import json
import sys
import os
from unittest.mock import Mock, patch

# Add api directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))

from analytics.analytics_refresh import lambda_handler


@patch('analytics.analytics_refresh.get_database')
@patch('analytics.analytics_refresh.AnalyticsQueries')
@patch('analytics.analytics_refresh.AnalyticsStorage')
def test_lambda_handler_success(mock_storage_class, mock_analytics_class, mock_get_db):
    """Test successful analytics generation"""
    # Setup mocks
    mock_db = Mock()
    mock_get_db.return_value = mock_db
    mock_db.execute_query.return_value = [{"count": 150}]

    mock_analytics = Mock()
    mock_analytics_class.return_value = mock_analytics
    mock_analytics.get_ingredient_usage_stats.return_value = [{"test": "data"}]
    mock_analytics.get_recipe_complexity_distribution.return_value = [{"count": 5}]
    mock_analytics.compute_cocktail_space_umap.return_value = [{"x": 1.0, "y": 2.0}]

    mock_storage = Mock()
    mock_storage_class.return_value = mock_storage
    mock_storage.put_analytics.return_value = True

    # Execute
    with patch.dict('os.environ', {'ANALYTICS_BUCKET': 'test-bucket'}):
        result = lambda_handler({}, {})

    # Verify
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert "message" in body


@patch('analytics.analytics_refresh.get_database')
def test_lambda_handler_failure(mock_get_db):
    """Test analytics generation failure handling"""
    mock_get_db.side_effect = Exception("Database connection failed")

    result = lambda_handler({}, {})

    assert result["statusCode"] == 500
    body = json.loads(result["body"])
    assert "error" in body
