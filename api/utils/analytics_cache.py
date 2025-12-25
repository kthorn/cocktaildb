"""Local storage manager for pre-generated analytics data"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class AnalyticsStorage:
    """Local filesystem storage for pre-generated analytics data"""

    def __init__(self, storage_path: str):
        self.storage_path = Path(storage_path)
        self.storage_version = "v1"
        version_path = self.storage_path / self.storage_version
        version_path.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, analytics_type: str) -> Path:
        """Generate file path for analytics type"""
        return self.storage_path / self.storage_version / f"{analytics_type}.json"

    def get_analytics(self, analytics_type: str) -> Optional[Dict[Any, Any]]:
        """Retrieve pre-generated analytics data from storage"""
        try:
            file_path = self._get_file_path(analytics_type)
            if not file_path.exists():
                logger.info(f"No analytics data found for {analytics_type}")
                return None

            with open(file_path, "r", encoding="utf-8") as file_handle:
                data = json.load(file_handle)
            logger.info(f"Retrieved analytics data for {analytics_type}")
            return data

        except Exception as e:
            logger.error(f"Error retrieving analytics data for {analytics_type}: {str(e)}")
            return None

    def put_analytics(self, analytics_type: str, data: Dict[Any, Any]) -> bool:
        """Store pre-generated analytics data in storage"""
        try:
            file_path = self._get_file_path(analytics_type)
            storage_data = {
                "data": data,
                "metadata": {
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    "storage_version": self.storage_version,
                    "analytics_type": analytics_type
                }
            }

            with open(file_path, "w", encoding="utf-8") as file_handle:
                json.dump(storage_data, file_handle)

            logger.info(f"Successfully stored analytics data for {analytics_type}")
            return True

        except Exception as e:
            logger.error(f"Error storing analytics data for {analytics_type}: {str(e)}")
            return False
