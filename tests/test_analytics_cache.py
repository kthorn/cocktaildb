"""Tests for S3 analytics storage manager"""
import pytest
import json
import sys
import os
from unittest.mock import Mock, patch, MagicMock

# Add api directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))

from utils.analytics_cache import AnalyticsStorage


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


@patch('boto3.client')
def test_get_analytics_success(mock_boto_client):
    """Test retrieving analytics data from S3"""
    # Setup mock
    mock_s3 = Mock()
    mock_boto_client.return_value = mock_s3

    storage = AnalyticsStorage("test-bucket")

    # Mock S3 response
    mock_body = Mock()
    test_data = {"data": [{"test": "value"}], "metadata": {"generated_at": "2025-01-01T00:00:00Z"}}
    mock_body.read.return_value = json.dumps(test_data).encode('utf-8')
    mock_s3.get_object.return_value = {'Body': mock_body}

    result = storage.get_analytics("ingredient-usage")

    assert result is not None
    assert "data" in result
    assert result["data"][0]["test"] == "value"
    mock_s3.get_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="analytics/v1/ingredient-usage.json"
    )


@patch('boto3.client')
def test_get_analytics_not_found(mock_boto_client):
    """Test retrieving non-existent analytics returns None"""
    # Setup mock
    mock_s3 = Mock()
    mock_boto_client.return_value = mock_s3

    storage = AnalyticsStorage("test-bucket")

    # Mock NoSuchKey exception
    from botocore.exceptions import ClientError
    mock_s3.exceptions.NoSuchKey = ClientError
    mock_s3.get_object.side_effect = ClientError(
        {'Error': {'Code': 'NoSuchKey'}}, 'GetObject'
    )

    result = storage.get_analytics("nonexistent")
    assert result is None


@patch('boto3.client')
def test_put_analytics_success(mock_boto_client):
    """Test storing analytics data in S3"""
    # Setup mock
    mock_s3 = Mock()
    mock_boto_client.return_value = mock_s3

    storage = AnalyticsStorage("test-bucket")

    test_data = [{"ingredient_id": 1, "count": 10}]
    result = storage.put_analytics("ingredient-usage", test_data)

    assert result is True
    mock_s3.put_object.assert_called_once()

    # Verify call structure
    call_args = mock_s3.put_object.call_args
    assert call_args[1]['Bucket'] == "test-bucket"
    assert call_args[1]['Key'] == "analytics/v1/ingredient-usage.json"
    assert call_args[1]['ContentType'] == 'application/json'

    # Verify body contains wrapped data
    body_data = json.loads(call_args[1]['Body'])
    assert "data" in body_data
    assert "metadata" in body_data
    assert body_data["data"] == test_data


@patch('boto3.client')
def test_put_analytics_failure(mock_boto_client):
    """Test storing analytics handles failures gracefully"""
    # Setup mock
    mock_s3 = Mock()
    mock_boto_client.return_value = mock_s3

    storage = AnalyticsStorage("test-bucket")

    # Mock failure
    mock_s3.put_object.side_effect = Exception("S3 error")

    test_data = [{"ingredient_id": 1}]
    result = storage.put_analytics("ingredient-usage", test_data)

    assert result is False
