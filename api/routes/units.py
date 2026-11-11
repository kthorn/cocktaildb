"""Units endpoints for the CocktailDB API"""

import logging

from core.exceptions import DatabaseException
from db.database import get_database as get_db
from db.db_core import Database
from dependencies.auth import (
    UserInfo,
    get_current_user_optional,
)
from fastapi import APIRouter, Depends
from models.responses import UnitResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/units", tags=["units"])


@router.get("", response_model=list[UnitResponse])
async def get_units(
    db: Database = Depends(get_db),
    user: UserInfo | None = Depends(get_current_user_optional),
):
    """Get all units"""
    try:
        logger.info("Getting units")

        units = db.get_units()

        return [UnitResponse(**unit) for unit in units]

    except Exception as e:
        logger.error(f"Error getting units: {str(e)}")
        raise DatabaseException("Failed to retrieve units", detail=str(e)) from e
