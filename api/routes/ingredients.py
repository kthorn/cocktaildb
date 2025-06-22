"""Ingredients endpoints for the CocktailDB API"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, status

from dependencies.auth import (
    UserInfo,
    get_current_user_optional,
    require_authentication,
)
from db.database import get_database as get_db
from db.db_core import Database
from models.requests import IngredientCreate, IngredientUpdate
from models.responses import IngredientResponse, MessageResponse
from core.exceptions import NotFoundException, DatabaseException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingredients", tags=["ingredients"])


@router.get("", response_model=List[IngredientResponse])
async def get_ingredients(
    db: Database = Depends(get_db),
    user: Optional[UserInfo] = Depends(get_current_user_optional),
):
    """Get all ingredients"""
    try:
        logger.info("Getting all ingredients")
        ingredients = db.get_ingredients()
        return [IngredientResponse(**ingredient) for ingredient in ingredients]
    except Exception as e:
        logger.error(f"Error getting ingredients: {str(e)}")
        raise DatabaseException("Failed to retrieve ingredients", detail=str(e))


@router.post("", response_model=IngredientResponse, status_code=status.HTTP_201_CREATED)
async def create_ingredient(
    ingredient_data: IngredientCreate,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Create a new ingredient (requires authentication)"""
    try:
        logger.info(f"Creating ingredient: {ingredient_data.name}")

        # Prepare data for database
        ingredient_dict = ingredient_data.model_dump()
        ingredient_dict["created_by"] = user.user_id

        created_ingredient = db.create_ingredient(ingredient_dict)
        return IngredientResponse(**created_ingredient)

    except Exception as e:
        logger.error(f"Error creating ingredient: {str(e)}")
        raise DatabaseException("Failed to create ingredient", detail=str(e))


@router.get("/{ingredient_id}", response_model=IngredientResponse)
async def get_ingredient(
    ingredient_id: int,
    db: Database = Depends(get_db),
    user: Optional[UserInfo] = Depends(get_current_user_optional),
):
    """Get a specific ingredient by ID"""
    try:
        logger.info(f"Getting ingredient {ingredient_id}")
        ingredient = db.get_ingredient(ingredient_id)

        if not ingredient:
            raise NotFoundException(f"Ingredient with ID {ingredient_id} not found")

        return IngredientResponse(**ingredient)

    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error getting ingredient {ingredient_id}: {str(e)}")
        raise DatabaseException("Failed to retrieve ingredient", detail=str(e))


@router.put("/{ingredient_id}", response_model=IngredientResponse)
async def update_ingredient(
    ingredient_id: int,
    ingredient_data: IngredientUpdate,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Update an ingredient (requires authentication)"""
    try:
        logger.info(f"Updating ingredient {ingredient_id}")

        # Check if ingredient exists
        existing_ingredient = db.get_ingredient(ingredient_id)
        if not existing_ingredient:
            raise NotFoundException(f"Ingredient with ID {ingredient_id} not found")

        # Prepare data for database (only include non-None values)
        update_dict = {
            k: v for k, v in ingredient_data.model_dump().items() if v is not None
        }

        updated_ingredient = db.update_ingredient(ingredient_id, update_dict)
        return IngredientResponse(**updated_ingredient)

    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error updating ingredient {ingredient_id}: {str(e)}")
        raise DatabaseException("Failed to update ingredient", detail=str(e))


@router.delete("/{ingredient_id}", response_model=MessageResponse)
async def delete_ingredient(
    ingredient_id: int,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Delete an ingredient (requires authentication)"""
    try:
        logger.info(f"Deleting ingredient {ingredient_id}")

        # Check if ingredient exists
        existing_ingredient = db.get_ingredient(ingredient_id)
        if not existing_ingredient:
            raise NotFoundException(f"Ingredient with ID {ingredient_id} not found")

        db.delete_ingredient(ingredient_id)
        return MessageResponse(
            message=f"Ingredient {ingredient_id} deleted successfully"
        )

    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting ingredient {ingredient_id}: {str(e)}")
        raise DatabaseException("Failed to delete ingredient", detail=str(e))
