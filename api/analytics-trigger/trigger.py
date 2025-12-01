"""Lambda function to trigger analytics Batch job"""
import json
import logging
import os
from typing import Dict, Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize Batch client at module level
_batch_client = None


def _get_batch_client():
    """Get or create the Batch client (cached at module level)"""
    global _batch_client
    if _batch_client is None:
        _batch_client = boto3.client('batch')
    return _batch_client


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to submit analytics Batch job.

    Environment variables:
        BATCH_JOB_QUEUE: Name of the Batch job queue
        BATCH_JOB_DEFINITION: Name of the Batch job definition

    Returns:
        dict: Lambda response with jobId and jobArn
    """
    try:
        job_queue = os.environ.get('BATCH_JOB_QUEUE')
        job_definition = os.environ.get('BATCH_JOB_DEFINITION')

        if not job_queue or not job_definition:
            raise ValueError(
                "BATCH_JOB_QUEUE and BATCH_JOB_DEFINITION environment variables required"
            )

        logger.info(f"Submitting Batch job to queue: {job_queue}")

        batch_client = _get_batch_client()
        response = batch_client.submit_job(
            jobName='analytics-refresh',
            jobQueue=job_queue,
            jobDefinition=job_definition
        )

        job_id = response['jobId']
        job_arn = response['jobArn']

        logger.info(f"Batch job submitted: {job_id}")

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Analytics Batch job submitted",
                "jobId": job_id,
                "jobArn": job_arn
            })
        }

    except Exception as e:
        logger.error(f"Error submitting Batch job: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": "Failed to submit analytics Batch job",
                "details": str(e)
            })
        }
