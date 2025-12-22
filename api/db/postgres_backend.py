"""PostgreSQL database backend."""
import logging
import os
from typing import Any, Dict, List

import psycopg2
from psycopg2.extras import RealDictCursor

from .backend_base import DatabaseBackend

logger = logging.getLogger(__name__)


class PostgresBackend(DatabaseBackend):
    """PostgreSQL database backend implementation."""

    def __init__(self):
        self.conn_params = {
            'host': os.environ.get('DB_HOST', 'localhost'),
            'port': os.environ.get('DB_PORT', '5432'),
            'dbname': os.environ.get('DB_NAME', 'cocktaildb'),
            'user': os.environ.get('DB_USER', 'cocktaildb'),
            'password': os.environ.get('DB_PASSWORD', ''),
        }
        self._connection = None
        logger.info(f"PostgresBackend initialized for {self.conn_params['host']}:{self.conn_params['port']}")

    @property
    def connection(self):
        if self._connection is None or self._connection.closed:
            self._connection = psycopg2.connect(**self.conn_params)
        return self._connection

    @property
    def placeholder(self) -> str:
        return "%s"

    def _convert_placeholders(self, query: str) -> str:
        """Convert ? placeholders to %s for PostgreSQL."""
        return query.replace("?", "%s")

    def execute(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        query = self._convert_placeholders(query)
        cursor = self.connection.cursor(cursor_factory=RealDictCursor)

        try:
            cursor.execute(query, params)

            if query.strip().upper().startswith("SELECT"):
                rows = cursor.fetchall()
                result = [dict(row) for row in rows]
            else:
                self.connection.commit()
                result = [{"rowcount": cursor.rowcount}]
        except Exception:
            self.connection.rollback()
            raise
        finally:
            cursor.close()

        return result

    def execute_returning_id(self, query: str, params: tuple = ()) -> int:
        query = self._convert_placeholders(query)

        # Add RETURNING clause if not present
        if "RETURNING" not in query.upper():
            query = query.rstrip(";") + " RETURNING id"

        cursor = self.connection.cursor()
        try:
            cursor.execute(query, params)
            row_id = cursor.fetchone()[0]
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        finally:
            cursor.close()

        return row_id

    def execute_many(self, query: str, params_list: List[tuple]) -> int:
        query = self._convert_placeholders(query)
        cursor = self.connection.cursor()

        try:
            cursor.executemany(query, params_list)
            self.connection.commit()
            count = cursor.rowcount
        except Exception:
            self.connection.rollback()
            raise
        finally:
            cursor.close()

        return count

    def close(self):
        if self._connection:
            self._connection.close()
            self._connection = None
