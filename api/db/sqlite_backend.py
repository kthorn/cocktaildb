"""SQLite database backend."""
import functools
import logging
import os
import sqlite3
import time
from typing import Any, Dict, List

from .backend_base import DatabaseBackend

logger = logging.getLogger(__name__)


def retry_on_db_locked(max_retries=3, initial_backoff=0.1):
    """Decorator to retry operations when database is locked."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            backoff = initial_backoff
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e):
                        last_error = e
                        logger.warning(
                            f"Database locked on attempt {attempt + 1}/{max_retries}. "
                            f"Retrying in {backoff:.2f}s..."
                        )
                        time.sleep(backoff)
                        backoff *= 2  # Exponential backoff
                    else:
                        # Other SQLite operational error, don't retry
                        raise
            logger.error(
                f"Database still locked after {max_retries} attempts: {str(last_error)}"
            )
            raise last_error or sqlite3.OperationalError(
                "Database still locked after multiple attempts"
            )
        return wrapper
    return decorator


class SQLiteBackend(DatabaseBackend):
    """SQLite database backend implementation."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.environ.get("DB_PATH", "/mnt/efs/cocktaildb.db")
        self._connection = None
        logger.info(f"SQLiteBackend initialized with path: {self.db_path}")

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
        return self._connection

    @property
    def placeholder(self) -> str:
        return "?"

    @retry_on_db_locked()
    def execute(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        cursor = self.connection.cursor()
        cursor.execute(query, params)

        if query.strip().upper().startswith("SELECT"):
            rows = cursor.fetchall()
            result = [dict(row) for row in rows]
        else:
            self.connection.commit()
            result = [{"rowcount": cursor.rowcount}]

        cursor.close()
        return result

    @retry_on_db_locked()
    def execute_returning_id(self, query: str, params: tuple = ()) -> int:
        cursor = self.connection.cursor()
        cursor.execute(query, params)
        self.connection.commit()
        row_id = cursor.lastrowid
        cursor.close()
        return row_id

    @retry_on_db_locked()
    def execute_many(self, query: str, params_list: List[tuple]) -> int:
        cursor = self.connection.cursor()
        cursor.executemany(query, params_list)
        self.connection.commit()
        count = cursor.rowcount
        cursor.close()
        return count

    def close(self):
        if self._connection:
            self._connection.close()
            self._connection = None
