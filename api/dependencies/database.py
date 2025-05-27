from fastapi import Depends
from typing import Generator

from core.database import get_database, get_db_session
from db.db_core import Database


def get_db() -> Database:
    """FastAPI dependency for database access"""
    return get_database()


def get_db_with_session() -> Generator[Database, None, None]:
    """FastAPI dependency for database access with session management"""
    yield from get_db_session()