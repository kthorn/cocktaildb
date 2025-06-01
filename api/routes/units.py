"""Units endpoints for the CocktailDB API"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status

from dependencies.auth import UserInfo, get_current_user_optional, require_authentication
from core.database import get_database as get_db
from db.db_core import Database
from models.requests import UnitCreate
from models.responses import UnitResponse, MessageResponse
from core.exceptions import NotFoundException, DatabaseException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/units", tags=["units"])


@router.get("", response_model=List[UnitResponse])
async def get_units(
    unit_type: Optional[str] = Query(None, description="Filter by unit type"),
    db: Database = Depends(get_db),
    user: Optional[UserInfo] = Depends(get_current_user_optional)
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


@router.post("", response_model=UnitResponse, status_code=status.HTTP_201_CREATED)
async def create_unit(
    unit_data: UnitCreate,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication)
):
    """Create a new unit (requires authentication)"""
    try:
        logger.info(f"Creating unit: {unit_data.name}")
        
        # Prepare data for database
        unit_dict = unit_data.model_dump()
        unit_dict["created_by"] = user.user_id
        
        created_unit = db.create_unit(unit_dict)
        return UnitResponse(**created_unit)
        
    except Exception as e:
        logger.error(f"Error creating unit: {str(e)}")
        raise DatabaseException("Failed to create unit", detail=str(e))


@router.get("/{unit_id}", response_model=UnitResponse)
async def get_unit(
    unit_id: int,
    db: Database = Depends(get_db),
    user: Optional[UserInfo] = Depends(get_current_user_optional)
):
    """Get a specific unit by ID"""
    try:
        logger.info(f"Getting unit {unit_id}")
        unit = db.get_unit(unit_id)
        
        if not unit:
            raise NotFoundException(f"Unit with ID {unit_id} not found")
            
        return UnitResponse(**unit)
        
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error getting unit {unit_id}: {str(e)}")
        raise DatabaseException("Failed to retrieve unit", detail=str(e))


@router.put("/{unit_id}", response_model=UnitResponse)
async def update_unit(
    unit_id: int,
    unit_data: UnitCreate,  # Reuse create model for updates
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication)
):
    """Update a unit (requires authentication)"""
    try:
        logger.info(f"Updating unit {unit_id}")
        
        # Check if unit exists
        existing_unit = db.get_unit(unit_id)
        if not existing_unit:
            raise NotFoundException(f"Unit with ID {unit_id} not found")
        
        # Prepare data for database
        update_dict = unit_data.model_dump()
        update_dict["id"] = unit_id
        
        updated_unit = db.update_unit(update_dict)
        return UnitResponse(**updated_unit)
        
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error updating unit {unit_id}: {str(e)}")
        raise DatabaseException("Failed to update unit", detail=str(e))


@router.delete("/{unit_id}", response_model=MessageResponse)
async def delete_unit(
    unit_id: int,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication)
):
    """Delete a unit (requires authentication)"""
    try:
        logger.info(f"Deleting unit {unit_id}")
        
        # Check if unit exists
        existing_unit = db.get_unit(unit_id)
        if not existing_unit:
            raise NotFoundException(f"Unit with ID {unit_id} not found")
        
        db.delete_unit(unit_id)
        return MessageResponse(message=f"Unit {unit_id} deleted successfully")
        
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting unit {unit_id}: {str(e)}")
        raise DatabaseException("Failed to delete unit", detail=str(e))