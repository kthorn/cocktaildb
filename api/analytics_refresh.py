"""Lambda function for regenerating pre-computed analytics"""
import json
import logging
import os
from typing import Dict, Any

from db.database import get_database
from db.db_analytics import AnalyticsQueries
from utils.analytics_cache import AnalyticsStorage

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to regenerate and store pre-computed analytics.

    Generates:
    - Root-level ingredient usage statistics
    - Recipe complexity distribution

    Stores results in S3 via AnalyticsStorage.

    Returns:
        dict: Lambda response with statusCode and body
    """
    try:
        # Get environment configuration
        bucket_name = os.environ.get('ANALYTICS_BUCKET')
        if not bucket_name:
            raise ValueError("ANALYTICS_BUCKET environment variable not set")

        logger.info("Starting analytics regeneration")

        # Initialize components
        db = get_database()
        analytics_queries = AnalyticsQueries(db)
        storage = AnalyticsStorage(bucket_name)

        # Generate root-level ingredient usage stats
        logger.info("Generating ingredient usage statistics")
        ingredient_stats = analytics_queries.get_ingredient_usage_stats()

        # Generate recipe complexity distribution
        logger.info("Generating recipe complexity distribution")
        complexity_stats = analytics_queries.get_recipe_complexity_distribution()

        # Store in S3
        logger.info("Storing analytics in S3")
        storage.put_analytics('ingredient-usage', ingredient_stats)
        storage.put_analytics('recipe-complexity', complexity_stats)

        logger.info("Analytics regeneration completed successfully")

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Analytics regenerated successfully",
                "ingredient_stats_count": len(ingredient_stats),
                "complexity_stats_count": len(complexity_stats)
            })
        }

    except Exception as e:
        logger.error(f"Error regenerating analytics: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": "Failed to regenerate analytics",
                "details": str(e)
            })
        }
