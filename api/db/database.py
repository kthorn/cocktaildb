import logging
import os
import time
from typing import Optional

from .db_core import Database

logger = logging.getLogger(__name__)

# Global database connection cache for Lambda environments
_DB_INSTANCE: Optional[Database] = None
_DB_INIT_TIME: float = 0
_DB_CACHE_DURATION = 300  # 5 minutes


def get_backend():
    """Factory function to get appropriate database backend based on DB_TYPE env var."""
    db_type = os.environ.get('DB_TYPE', 'sqlite').lower()

    if db_type in ('postgres', 'postgresql'):
        from .postgres_backend import PostgresBackend
        return PostgresBackend()
    else:
        from .sqlite_backend import SQLiteBackend
        return SQLiteBackend()


def get_database() -> Database:
    """FastAPI dependency for database access with connection pooling"""
    global _DB_INSTANCE, _DB_INIT_TIME

    try:
        current_time = time.time()

        # In test environment, force refresh for each test
        is_test_env = os.environ.get("ENVIRONMENT") == "test"
        cache_duration = 0 if is_test_env else _DB_CACHE_DURATION

        # If DB instance exists and is less than cache duration old, reuse it
        if _DB_INSTANCE is not None and current_time - _DB_INIT_TIME < cache_duration:
            logger.debug(
                f"Reusing existing database connection (age: {current_time - _DB_INIT_TIME:.2f}s)"
            )
            return _DB_INSTANCE

        # Initialize a new database connection
        logger.info("Creating new database connection")
        logger.info(
            f"DB_PATH environment variable: {os.environ.get('DB_PATH', 'not set')}"
        )

        _DB_INSTANCE = Database()
        _DB_INIT_TIME = current_time

        logger.info("Database connection created successfully")
        return _DB_INSTANCE

    except Exception as e:
        logger.error(f"Failed to create database connection: {str(e)}", exc_info=True)
        raise
