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
