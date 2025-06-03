"""Shared rating handlers to avoid code duplication between routes"""

import logging
from typing import Optional

from dependencies.auth import UserInfo
from db.db_core import Database
from models.requests import RatingCreate
from models.responses import RatingSummaryResponse, RatingResponse, MessageResponse
from core.exceptions import NotFoundException, DatabaseException

logger = logging.getLogger(__name__)


async def get_recipe_ratings_handler(
    recipe_id: int,
    db: Database,
    user: Optional[UserInfo] = None
) -> RatingSummaryResponse:
    """Get ratings for a specific recipe"""
    try:
        logger.info(f"Getting ratings for recipe {recipe_id}")
        
        # Check if recipe exists and get recipe data with avg_rating and rating_count
        recipe = db.get_recipe(recipe_id)
        if not recipe:
            raise NotFoundException(f"Recipe with ID {recipe_id} not found")
        
        # Get user's rating if authenticated
        user_rating = None
        if user:
            user_rating_data = db.get_user_rating(recipe_id, user.user_id)
            if user_rating_data:
                # Map cognito_user_id to user_id for the response model
                user_rating_data["user_id"] = user_rating_data["cognito_user_id"]
                user_rating = RatingResponse(**user_rating_data)
        
        return RatingSummaryResponse(
            recipe_id=recipe_id,
            avg_rating=recipe.get("avg_rating"),
            rating_count=recipe.get("rating_count", 0),
            user_rating=user_rating
        )
        
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error getting ratings for recipe {recipe_id}: {str(e)}")
        raise DatabaseException("Failed to retrieve ratings", detail=str(e))


async def create_or_update_rating_handler(
    recipe_id: int,
    rating_data: RatingCreate,
    db: Database,
    user: UserInfo
) -> RatingResponse:
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
        # Map cognito_user_id to user_id for the response model
        result["user_id"] = result["cognito_user_id"]
        return RatingResponse(**result)
        
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error setting rating for recipe {recipe_id}: {str(e)}")
        raise DatabaseException("Failed to set rating", detail=str(e))


async def delete_rating_handler(
    recipe_id: int,
    db: Database,
    user: UserInfo
) -> MessageResponse:
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