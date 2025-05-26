"""Ratings endpoints for the CocktailDB API"""

import logging
from fastapi import APIRouter, Depends, status

from ..dependencies.auth import UserInfo, get_current_user_optional, require_authentication
from ..dependencies.database import get_db
from ..db.db_core import Database
from ..models.requests import RatingCreate
from ..models.responses import RatingSummaryResponse, RatingResponse, MessageResponse
from ..core.exceptions import NotFoundException, DatabaseException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ratings", tags=["ratings"])


@router.get("/{recipe_id}", response_model=RatingSummaryResponse)
async def get_recipe_ratings(
    recipe_id: int,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(get_current_user_optional)
):
    """Get ratings for a specific recipe"""
    try:
        logger.info(f"Getting ratings for recipe {recipe_id}")
        
        # Check if recipe exists
        recipe = db.get_recipe(recipe_id)
        if not recipe:
            raise NotFoundException(f"Recipe with ID {recipe_id} not found")
        
        ratings_data = db.get_recipe_ratings(recipe_id)
        
        # Get user's rating if authenticated
        user_rating = None
        if user:
            user_rating_data = db.get_user_rating(recipe_id, user.user_id)
            if user_rating_data:
                user_rating = RatingResponse(**user_rating_data)
        
        return RatingSummaryResponse(
            recipe_id=recipe_id,
            avg_rating=ratings_data.get("avg_rating"),
            rating_count=ratings_data.get("rating_count", 0),
            user_rating=user_rating
        )
        
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error getting ratings for recipe {recipe_id}: {str(e)}")
        raise DatabaseException("Failed to retrieve ratings", detail=str(e))


@router.post("/{recipe_id}", response_model=RatingResponse, status_code=status.HTTP_201_CREATED)
async def create_or_update_rating(
    recipe_id: int,
    rating_data: RatingCreate,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication)
):
    """Create or update a rating for a recipe (requires authentication)"""
    try:
        logger.info(f"Setting rating for recipe {recipe_id} by user {user.user_id}")
        
        # Check if recipe exists
        recipe = db.get_recipe(recipe_id)
        if not recipe:
            raise NotFoundException(f"Recipe with ID {recipe_id} not found")
        
        # Prepare data for database
        rating_dict = rating_data.model_dump()
        rating_dict.update({
            "recipe_id": recipe_id,
            "cognito_user_id": user.user_id,
            "cognito_username": user.username or user.user_id
        })
        
        result = db.set_rating(rating_dict)
        return RatingResponse(**result)
        
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error setting rating for recipe {recipe_id}: {str(e)}")
        raise DatabaseException("Failed to set rating", detail=str(e))


@router.put("/{recipe_id}", response_model=RatingResponse)
async def update_rating(
    recipe_id: int,
    rating_data: RatingCreate,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication)
):
    """Update a rating for a recipe (requires authentication)"""
    # PUT and POST have the same logic for ratings (upsert)
    return await create_or_update_rating(recipe_id, rating_data, db, user)


@router.delete("/{recipe_id}", response_model=MessageResponse)
async def delete_rating(
    recipe_id: int,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication)
):
    """Delete a user's rating for a recipe (requires authentication)"""
    try:
        logger.info(f"Deleting rating for recipe {recipe_id} by user {user.user_id}")
        
        # Check if recipe exists
        recipe = db.get_recipe(recipe_id)
        if not recipe:
            raise NotFoundException(f"Recipe with ID {recipe_id} not found")
        
        # Check if user has a rating for this recipe
        existing_rating = db.get_user_rating(recipe_id, user.user_id)
        if not existing_rating:
            raise NotFoundException("No rating found for this recipe by the current user")
        
        db.delete_rating(recipe_id, user.user_id)
        return MessageResponse(message="Rating deleted successfully")
        
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting rating for recipe {recipe_id}: {str(e)}")
        raise DatabaseException("Failed to delete rating", detail=str(e))