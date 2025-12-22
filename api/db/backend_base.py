"""Abstract base class for database backends."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List


class DatabaseBackend(ABC):
    """Abstract database backend interface."""

    @abstractmethod
    def execute(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute a query and return results as list of dicts."""
        pass

    @abstractmethod
    def execute_returning_id(self, query: str, params: tuple = ()) -> int:
        """Execute an INSERT and return the new row's ID."""
        pass

    @abstractmethod
    def execute_many(self, query: str, params_list: List[tuple]) -> int:
        """Execute a query with multiple parameter sets."""
        pass

    @abstractmethod
    def close(self):
        """Close the database connection."""
        pass

    @property
    @abstractmethod
    def placeholder(self) -> str:
        """Return the parameter placeholder ('?' for SQLite, '%s' for PostgreSQL)."""
        pass
