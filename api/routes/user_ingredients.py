"""User ingredient endpoints for the CocktailDB API"""

import logging
from fastapi import APIRouter, Depends, status, HTTPException

from dependencies.auth import UserInfo, require_authentication
from db.database import get_database as get_db
from db.db_core import Database
from models.requests import UserIngredientAdd, UserIngredientBulkAdd, UserIngredientBulkRemove
from models.responses import (
    UserIngredientResponse,
    UserIngredientListResponse,
    UserIngredientBulkResponse,
    MessageResponse,
    IngredientRecommendationResponse,
    IngredientRecommendationListResponse,
)
from core.exceptions import NotFoundException, DatabaseException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user-ingredients", tags=["user-ingredients"])


@router.post("", response_model=UserIngredientResponse, status_code=status.HTTP_201_CREATED)
async def add_user_ingredient(
    ingredient_data: UserIngredientAdd,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Add an ingredient to user's inventory (requires authentication)"""
    try:
        logger.info(f"Adding ingredient {ingredient_data.ingredient_id} to user {user.user_id}")

        result = db.add_user_ingredient(user.user_id, ingredient_data.ingredient_id)
        
        return UserIngredientResponse(
            ingredient_id=result["ingredient_id"],
            name=result["ingredient_name"],
            description=None,  # Not included in basic add response
            parent_id=None,    # Not included in basic add response
            path=None,         # Not included in basic add response
            added_at=result["added_at"]
        )

    except ValueError as e:
        if "does not exist" in str(e):
            raise NotFoundException(str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding ingredient to user inventory: {str(e)}")
        raise DatabaseException("Failed to add ingredient to inventory", detail=str(e))


@router.delete("/bulk", response_model=UserIngredientBulkResponse)
async def remove_user_ingredients_bulk(
    bulk_data: UserIngredientBulkRemove,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Remove multiple ingredients from user's inventory (requires authentication)"""
    try:
        logger.info(f"Bulk removing {len(bulk_data.ingredient_ids)} ingredients from user {user.user_id}")

        result = db.remove_user_ingredients_bulk(user.user_id, bulk_data.ingredient_ids)
        
        return UserIngredientBulkResponse(
            removed_count=result["removed_count"],
            not_found_count=result["not_found_count"]
        )

    except ValueError as e:
        # This is a validation error (e.g., parent-child constraint violation)
        logger.warning(f"Validation error during bulk remove for user {user.user_id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error bulk removing ingredients from user inventory: {str(e)}")
        raise DatabaseException("Failed to bulk remove ingredients from inventory", detail=str(e))


@router.delete("/{ingredient_id}", response_model=MessageResponse)
async def remove_user_ingredient(
    ingredient_id: int,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Remove an ingredient from user's inventory (requires authentication)"""
    try:
        logger.info(f"Removing ingredient {ingredient_id} from user {user.user_id}")

        success = db.remove_user_ingredient(user.user_id, ingredient_id)
        
        if not success:
            raise NotFoundException(f"Ingredient {ingredient_id} not found in user's inventory")

        return MessageResponse(
            message=f"Ingredient {ingredient_id} removed from inventory successfully"
        )

    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error removing ingredient from user inventory: {str(e)}")
        raise DatabaseException("Failed to remove ingredient from inventory", detail=str(e))


@router.get("", response_model=UserIngredientListResponse)
async def get_user_ingredients(
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Get all ingredients in user's inventory (requires authentication)"""
    try:
        logger.info(f"Getting ingredients for user {user.user_id}")

        ingredients = db.get_user_ingredients(user.user_id)
        
        ingredient_responses = []
        for ingredient in ingredients:
            ingredient_responses.append(
                UserIngredientResponse(
                    ingredient_id=ingredient["ingredient_id"],
                    name=ingredient["name"],
                    description=ingredient.get("description"),
                    parent_id=ingredient.get("parent_id"),
                    path=ingredient.get("path"),
                    added_at=ingredient["added_at"]
                )
            )

        return UserIngredientListResponse(
            ingredients=ingredient_responses,
            total_count=len(ingredient_responses)
        )

    except Exception as e:
        logger.error(f"Error getting user ingredients: {str(e)}")
        raise DatabaseException("Failed to retrieve user ingredients", detail=str(e))


@router.post("/bulk", response_model=UserIngredientBulkResponse, status_code=status.HTTP_201_CREATED)
async def add_user_ingredients_bulk(
    bulk_data: UserIngredientBulkAdd,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Add multiple ingredients to user's inventory (requires authentication)"""
    try:
        logger.info(f"Bulk adding {len(bulk_data.ingredient_ids)} ingredients to user {user.user_id}")

        result = db.add_user_ingredients_bulk(user.user_id, bulk_data.ingredient_ids)

        return UserIngredientBulkResponse(
            added_count=result["added_count"],
            already_exists_count=result["already_exists_count"],
            failed_count=result["failed_count"],
            errors=result["errors"]
        )

    except Exception as e:
        logger.error(f"Error bulk adding ingredients to user inventory: {str(e)}")
        raise DatabaseException("Failed to bulk add ingredients to inventory", detail=str(e))


@router.get("/recommendations", response_model=IngredientRecommendationListResponse)
async def get_ingredient_recommendations(
    limit: int = 20,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Get ingredient recommendations that would unlock the most new recipes (requires authentication)"""
    try:
        logger.info(f"Getting ingredient recommendations for user {user.user_id} with limit {limit}")

        recommendations = db.get_ingredient_recommendations(user.user_id, limit)

        recommendation_responses = []
        for rec in recommendations:
            recommendation_responses.append(
                IngredientRecommendationResponse(
                    id=rec["id"],
                    name=rec["name"],
                    description=rec.get("description"),
                    parent_id=rec.get("parent_id"),
                    path=rec.get("path"),
                    allow_substitution=rec.get("allow_substitution", False),
                    recipes_unlocked=rec["recipes_unlocked"],
                    recipe_names=rec["recipe_names"]
                )
            )

        return IngredientRecommendationListResponse(
            recommendations=recommendation_responses,
            total_count=len(recommendation_responses)
        )

    except Exception as e:
        logger.error(f"Error getting ingredient recommendations: {str(e)}")
        raise DatabaseException("Failed to retrieve ingredient recommendations", detail=str(e))