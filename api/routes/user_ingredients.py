"""User ingredient endpoints for the CocktailDB API"""

import logging

from core.exceptions import NotFoundException
from db.database import get_database as get_db
from db.db_core import Database
from dependencies.auth import UserInfo, require_authentication
from fastapi import APIRouter, Depends, HTTPException, status
from models.requests import (
    UserIngredientAdd,
    UserIngredientBulkAdd,
    UserIngredientBulkRemove,
)
from models.responses import (
    IngredientRecommendationListResponse,
    IngredientRecommendationResponse,
    MessageResponse,
    UserIngredientBulkResponse,
    UserIngredientListResponse,
    UserIngredientResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user-ingredients", tags=["user-ingredients"])


@router.post(
    "", response_model=UserIngredientResponse, status_code=status.HTTP_201_CREATED
)
def add_user_ingredient(
    ingredient_data: UserIngredientAdd,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Add an ingredient to user's inventory (requires authentication)"""
    try:
        logger.info(
            f"Adding ingredient {ingredient_data.ingredient_id} to user {user.user_id}"
        )

        result = db.add_user_ingredient(user.user_id, ingredient_data.ingredient_id)

        return UserIngredientResponse(
            ingredient_id=result["ingredient_id"],
            name=result["ingredient_name"],
            description=None,  # Not included in basic add response
            parent_id=None,  # Not included in basic add response
            path=None,  # Not included in basic add response
            added_at=result["added_at"],
        )

    except ValueError as e:
        if "does not exist" in str(e):
            raise NotFoundException(str(e)) from e
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/bulk", response_model=UserIngredientBulkResponse)
def remove_user_ingredients_bulk(
    bulk_data: UserIngredientBulkRemove,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Remove multiple ingredients from user's inventory (requires authentication)"""
    try:
        logger.info(
            f"Bulk removing {len(bulk_data.ingredient_ids)} ingredients from user {user.user_id}"
        )

        result = db.remove_user_ingredients_bulk(user.user_id, bulk_data.ingredient_ids)

        return UserIngredientBulkResponse(
            removed_count=result["removed_count"],
            not_found_count=result["not_found_count"],
        )

    except ValueError as e:
        # This is a validation error (e.g., parent-child constraint violation)
        logger.warning(
            f"Validation error during bulk remove for user {user.user_id}: {str(e)}"
        )
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/{ingredient_id}", response_model=MessageResponse)
def remove_user_ingredient(
    ingredient_id: int,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Remove an ingredient from user's inventory (requires authentication)"""
    logger.info(f"Removing ingredient {ingredient_id} from user {user.user_id}")

    success = db.remove_user_ingredient(user.user_id, ingredient_id)

    if not success:
        raise NotFoundException(
            f"Ingredient {ingredient_id} not found in user's inventory"
        )

    return MessageResponse(
        message=f"Ingredient {ingredient_id} removed from inventory successfully"
    )


@router.get("", response_model=UserIngredientListResponse)
def get_user_ingredients(
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Get all ingredients in user's inventory (requires authentication)"""
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
                added_at=ingredient["added_at"],
            )
        )

    return UserIngredientListResponse(
        ingredients=ingredient_responses, total_count=len(ingredient_responses)
    )


@router.post(
    "/bulk",
    response_model=UserIngredientBulkResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_user_ingredients_bulk(
    bulk_data: UserIngredientBulkAdd,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Add multiple ingredients to user's inventory (requires authentication)"""
    logger.info(
        f"Bulk adding {len(bulk_data.ingredient_ids)} ingredients to user {user.user_id}"
    )

    result = db.add_user_ingredients_bulk(user.user_id, bulk_data.ingredient_ids)

    return UserIngredientBulkResponse(
        added_count=result["added_count"],
        already_exists_count=result["already_exists_count"],
        failed_count=result["failed_count"],
        errors=result["errors"],
    )


@router.get("/recommendations", response_model=IngredientRecommendationListResponse)
def get_ingredient_recommendations(
    limit: int = 20,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Get ingredient recommendations that would unlock the most new recipes (requires authentication)"""
    logger.info(
        f"Getting ingredient recommendations for user {user.user_id} with limit {limit}"
    )

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
                recipe_names=rec["recipe_names"],
            )
        )

    return IngredientRecommendationListResponse(
        recommendations=recommendation_responses,
        total_count=len(recommendation_responses),
    )
