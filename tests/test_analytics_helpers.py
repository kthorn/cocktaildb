"""Tests for analytics helper functions"""
import pytest
import sys
import os
from unittest.mock import patch, Mock

# Add api directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))

from utils import analytics_helpers
from utils.analytics_helpers import trigger_analytics_refresh, signal_analytics_run


@pytest.fixture(autouse=True)
def reset_clients():
    """Reset the module-level client caches for test isolation"""
    analytics_helpers._lambda_client = None
    analytics_helpers._scheduler_client = None
    yield
    analytics_helpers._lambda_client = None
    analytics_helpers._scheduler_client = None


@patch('boto3.client')
def test_trigger_analytics_refresh_success(mock_boto_client):
    """Test successful analytics refresh trigger"""
    mock_lambda = Mock()
    mock_boto_client.return_value = mock_lambda

    with patch.dict('os.environ', {'ANALYTICS_TRIGGER_FUNCTION': 'test-function'}):
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

    with patch.dict('os.environ', {'ANALYTICS_TRIGGER_FUNCTION': 'test-function'}):
        # Should not raise exception
        trigger_analytics_refresh()


@patch('boto3.client')
def test_signal_analytics_run_updates_existing_schedule(mock_boto_client):
    """Test that signal_analytics_run updates an existing schedule"""
    mock_scheduler = Mock()
    mock_boto_client.return_value = mock_scheduler

    env = {
        'ANALYTICS_SCHEDULE_NAME': 'test-stack-analytics-debounce',
        'ANALYTICS_TRIGGER_FUNCTION': 'arn:aws:lambda:us-east-1:123456789:function:test-trigger',
        'ANALYTICS_SCHEDULER_ROLE_ARN': 'arn:aws:iam::123456789:role/test-role',
        'ANALYTICS_DEBOUNCE_MINUTES': '5'
    }

    with patch.dict('os.environ', env):
        signal_analytics_run()

    mock_boto_client.assert_called_with('scheduler')
    mock_scheduler.update_schedule.assert_called_once()
    call_args = mock_scheduler.update_schedule.call_args[1]
    assert call_args['Name'] == 'test-stack-analytics-debounce'
    assert call_args['Target']['Arn'] == env['ANALYTICS_TRIGGER_FUNCTION']
    assert call_args['Target']['RoleArn'] == env['ANALYTICS_SCHEDULER_ROLE_ARN']
    assert call_args['FlexibleTimeWindow'] == {'Mode': 'OFF'}
    assert call_args['ScheduleExpression'].startswith('at(')


@patch('boto3.client')
def test_signal_analytics_run_creates_schedule_when_not_found(mock_boto_client):
    """Test that signal_analytics_run creates schedule if it doesn't exist"""
    from botocore.exceptions import ClientError

    mock_scheduler = Mock()
    mock_scheduler.update_schedule.side_effect = ClientError(
        {'Error': {'Code': 'ResourceNotFoundException', 'Message': 'Schedule not found'}},
        'UpdateSchedule'
    )
    mock_boto_client.return_value = mock_scheduler

    env = {
        'ANALYTICS_SCHEDULE_NAME': 'test-stack-analytics-debounce',
        'ANALYTICS_TRIGGER_FUNCTION': 'arn:aws:lambda:us-east-1:123456789:function:test-trigger',
        'ANALYTICS_SCHEDULER_ROLE_ARN': 'arn:aws:iam::123456789:role/test-role',
        'ANALYTICS_DEBOUNCE_MINUTES': '15'
    }

    with patch.dict('os.environ', env):
        signal_analytics_run()

    mock_scheduler.create_schedule.assert_called_once()
    call_args = mock_scheduler.create_schedule.call_args[1]
    assert call_args['Name'] == 'test-stack-analytics-debounce'


@patch('boto3.client')
def test_signal_analytics_run_skips_when_not_configured(mock_boto_client):
    """Test that signal_analytics_run skips when env vars missing"""
    mock_scheduler = Mock()
    mock_boto_client.return_value = mock_scheduler

    with patch.dict('os.environ', {}, clear=True):
        signal_analytics_run()

    mock_scheduler.update_schedule.assert_not_called()
    mock_scheduler.create_schedule.assert_not_called()


@patch('boto3.client')
def test_signal_analytics_run_handles_errors_gracefully(mock_boto_client):
    """Test that signal_analytics_run logs errors but doesn't raise"""
    mock_scheduler = Mock()
    mock_scheduler.update_schedule.side_effect = Exception("Scheduler error")
    mock_boto_client.return_value = mock_scheduler

    env = {
        'ANALYTICS_SCHEDULE_NAME': 'test-stack-analytics-debounce',
        'ANALYTICS_TRIGGER_FUNCTION': 'arn:aws:lambda:us-east-1:123456789:function:test-trigger',
        'ANALYTICS_SCHEDULER_ROLE_ARN': 'arn:aws:iam::123456789:role/test-role',
        'ANALYTICS_DEBOUNCE_MINUTES': '5'
    }

    with patch.dict('os.environ', env):
        # Should not raise
        signal_analytics_run()
