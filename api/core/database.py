import logging
import time
from typing import Optional

from db.db_core import Database

logger = logging.getLogger(__name__)

# Global database connection cache for Lambda environments
_DB_INSTANCE: Optional[Database] = None
_DB_INIT_TIME: float = 0
_DB_CACHE_DURATION = 300  # 5 minutes


def get_database() -> Database:
    """FastAPI dependency for database access with connection pooling"""
    global _DB_INSTANCE, _DB_INIT_TIME
    
    current_time = time.time()
    
    # If DB instance exists and is less than cache duration old, reuse it
    if _DB_INSTANCE is not None and current_time - _DB_INIT_TIME < _DB_CACHE_DURATION:
        logger.debug(
            f"Reusing existing database connection (age: {current_time - _DB_INIT_TIME:.2f}s)"
        )
        return _DB_INSTANCE
    
    # Initialize a new database connection
    logger.info("Creating new database connection")
    _DB_INSTANCE = Database()
    _DB_INIT_TIME = current_time
    return _DB_INSTANCE