"""Tests for analytics helper functions"""
import pytest
import sys
import os
from unittest.mock import patch, Mock

# Add api directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))

from utils import analytics_helpers
from utils.analytics_helpers import trigger_analytics_refresh


@pytest.fixture(autouse=True)
def reset_lambda_client():
    """Reset the module-level Lambda client cache for test isolation"""
    analytics_helpers._lambda_client = None
    yield
    analytics_helpers._lambda_client = None


@patch('boto3.client')
def test_trigger_analytics_refresh_success(mock_boto_client):
    """Test successful analytics refresh trigger"""
    mock_lambda = Mock()
    mock_boto_client.return_value = mock_lambda

    with patch.dict('os.environ', {'ANALYTICS_REFRESH_FUNCTION': 'test-function'}):
        trigger_analytics_refresh()

        mock_lambda.invoke.assert_called_once()
        call_args = mock_lambda.invoke.call_args
        assert call_args[1]['FunctionName'] == 'test-function'
        assert call_args[1]['InvocationType'] == 'Event'


@patch('boto3.client')
def test_trigger_analytics_refresh_no_function_configured(mock_boto_client):
    """Test trigger does nothing when function not configured"""
    mock_lambda = Mock()
    mock_boto_client.return_value = mock_lambda

    with patch.dict('os.environ', {}, clear=True):
        trigger_analytics_refresh()

        mock_lambda.invoke.assert_not_called()


@patch('boto3.client')
def test_trigger_analytics_refresh_failure_handling(mock_boto_client):
    """Test that trigger failures don't raise exceptions"""
    mock_lambda = Mock()
    mock_lambda.invoke.side_effect = Exception("Lambda invocation failed")
    mock_boto_client.return_value = mock_lambda

    with patch.dict('os.environ', {'ANALYTICS_REFRESH_FUNCTION': 'test-function'}):
        # Should not raise exception
        trigger_analytics_refresh()
