"""Helper functions for analytics operations"""

import datetime
import logging
import os

logger = logging.getLogger(__name__)

# Initialize boto3 client at module level for Lambda optimization
# This avoids creating a new client on every request, which is slow
_lambda_client = None
_scheduler_client = None


def _get_lambda_client():
    """Get or create the Lambda client (cached at module level)"""
    global _lambda_client
    if _lambda_client is None:
        try:
            import boto3
            _lambda_client = boto3.client('lambda')
        except Exception as e:
            logger.error(f"Failed to create Lambda client: {str(e)}")
            raise
    return _lambda_client


def _get_scheduler_client():
    """Get or create the EventBridge Scheduler client (cached at module level)"""
    global _scheduler_client
    if _scheduler_client is None:
        try:
            import boto3
            _scheduler_client = boto3.client('scheduler')
        except Exception as e:
            logger.error(f"Failed to create Scheduler client: {str(e)}")
            raise
    return _scheduler_client


def trigger_analytics_refresh():
    """Trigger async analytics regeneration

    Invokes the analytics trigger Lambda function asynchronously,
    which submits an AWS Batch job.
    Failures are logged but don't fail the main operation.
    """
    try:
        function_name = os.environ.get("ANALYTICS_TRIGGER_FUNCTION")
        if not function_name:
            logger.debug("ANALYTICS_TRIGGER_FUNCTION not configured, skipping trigger")
            return

        lambda_client = _get_lambda_client()
        lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='Event'  # Async - non-blocking
        )
        logger.info("Analytics Batch job trigger invoked")
    except Exception as e:
        logger.warning(f"Failed to trigger analytics regeneration: {str(e)}")
        # Don't fail the main operation if analytics trigger fails


def signal_analytics_run():
    """Signal that analytics should be regenerated.

    Uses EventBridge Scheduler to debounce rapid mutations.
    Each call pushes the scheduled run further out by DEBOUNCE_MINUTES.
    Failures are logged but don't fail the main operation.
    """
    try:
        from botocore.exceptions import ClientError

        schedule_name = os.environ.get("ANALYTICS_SCHEDULE_NAME")
        target_arn = os.environ.get("ANALYTICS_TRIGGER_FUNCTION")
        invoke_role_arn = os.environ.get("ANALYTICS_SCHEDULER_ROLE_ARN")
        debounce_minutes = int(os.environ.get("ANALYTICS_DEBOUNCE_MINUTES", "15"))

        if not all([schedule_name, target_arn, invoke_role_arn]):
            logger.debug("Analytics debounce not configured, skipping")
            return

        run_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=debounce_minutes)
        schedule_expression = f"at({run_at.strftime('%Y-%m-%dT%H:%M:%S')})"

        scheduler = _get_scheduler_client()
        args = {
            "Name": schedule_name,
            "ScheduleExpression": schedule_expression,
            "FlexibleTimeWindow": {"Mode": "OFF"},
            "Target": {
                "Arn": target_arn,
                "RoleArn": invoke_role_arn,
                "Input": "{}",
            },
        }

        try:
            scheduler.update_schedule(**args)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                scheduler.create_schedule(**args)
            else:
                raise

        logger.info(f"Analytics scheduled for {run_at.isoformat()}")
    except Exception as e:
        logger.warning(f"Failed to schedule analytics: {str(e)}")
