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
