"""Helper functions for analytics operations"""

import logging
import os

logger = logging.getLogger(__name__)

# Initialize boto3 client at module level for Lambda optimization
# This avoids creating a new client on every request, which is slow
_lambda_client = None


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

        lambda_client = _get_lambda_client()
        lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='Event'  # Async - non-blocking
        )
        logger.info("Analytics regeneration triggered")
    except Exception as e:
        logger.warning(f"Failed to trigger analytics regeneration: {str(e)}")
        # Don't fail the main operation if analytics trigger fails
