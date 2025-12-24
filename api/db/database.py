import logging
import os
from typing import Optional

from .db_core import Database

logger = logging.getLogger(__name__)

# Singleton database instance
_DB_INSTANCE: Optional[Database] = None


def get_database() -> Database:
    """FastAPI dependency for database access (singleton pattern)"""
    global _DB_INSTANCE

    try:
        if _DB_INSTANCE is not None:
            return _DB_INSTANCE

        # Initialize database connection
        db_host = os.environ.get('DB_HOST', 'localhost')
        db_name = os.environ.get('DB_NAME', 'cocktaildb')
        logger.info(f"Creating PostgreSQL connection to {db_host}/{db_name}")

        _DB_INSTANCE = Database()
        logger.info("Database connection created successfully")
        return _DB_INSTANCE

    except Exception as e:
        logger.error(f"Failed to create database connection: {str(e)}", exc_info=True)
        raise
