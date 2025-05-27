import logging
import time
from contextlib import contextmanager
from typing import Generator, Optional

from db.db_core import Database
from core.config import settings

logger = logging.getLogger(__name__)

# Global database connection cache for Lambda environments
_DB_INSTANCE: Optional[Database] = None
_DB_INIT_TIME: float = 0
_DB_CACHE_DURATION = 300  # 5 minutes


class DatabaseManager:
    """Database connection manager for FastAPI"""
    
    def __init__(self):
        self._db_instance: Optional[Database] = None
        self._db_init_time: float = 0
    
    def get_database(self) -> Database:
        """Get database with connection pooling and metadata caching"""
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
    
    @contextmanager
    def get_db_session(self) -> Generator[Database, None, None]:
        """Context manager for database sessions"""
        db = self.get_database()
        try:
            yield db
        except Exception as e:
            logger.error(f"Database session error: {str(e)}")
            raise
        finally:
            # In SQLite, we don't need to explicitly close connections
            # as they're managed by the Database class
            pass


# Global database manager instance
db_manager = DatabaseManager()


def get_database() -> Database:
    """Dependency function for FastAPI route injection"""
    return db_manager.get_database()


def get_db_session() -> Generator[Database, None, None]:
    """Dependency function for FastAPI route injection with session management"""
    with db_manager.get_db_session() as db:
        yield db