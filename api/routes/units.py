"""Units endpoints for the CocktailDB API"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, Query

from dependencies.auth import (
    UserInfo,
    get_current_user_optional,
)
from db.database import get_database as get_db
from db.db_core import Database
from models.responses import UnitResponse
from core.exceptions import DatabaseException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/units", tags=["units"])


@router.get("", response_model=List[UnitResponse])
async def get_units(
    unit_type: Optional[str] = Query(None, description="Filter by unit type"),
    db: Database = Depends(get_db),
    user: Optional[UserInfo] = Depends(get_current_user_optional),
):
    """Get all units, optionally filtered by type"""
    try:
        logger.info(f"Getting units with type filter: {unit_type}")

        if unit_type:
            units = db.get_units_by_type(unit_type)
        else:
            units = db.get_units()

        return [UnitResponse(**unit) for unit in units]

    except Exception as e:
        logger.error(f"Error getting units: {str(e)}")
        raise DatabaseException("Failed to retrieve units", detail=str(e))
