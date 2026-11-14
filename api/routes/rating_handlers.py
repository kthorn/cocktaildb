"""Shared rating handlers to avoid code duplication between routes"""

import logging

from core.exceptions import NotFoundException
from db.db_core import Database
from dependencies.auth import UserInfo
from models.requests import RatingCreate
from models.responses import RatingResponse, RatingSummaryResponse

logger = logging.getLogger(__name__)


async def get_recipe_ratings_handler(
    recipe_id: int, db: Database, user: UserInfo | None = None
) -> RatingSummaryResponse:
    """Get ratings for a specific recipe"""
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
        user_rating=user_rating,
    )


async def create_or_update_rating_handler(
    recipe_id: int, rating_data: RatingCreate, db: Database, user: UserInfo
) -> RatingResponse:
    """Create or update a rating for a recipe (requires authentication)"""
    logger.info(f"Setting rating for recipe {recipe_id} by user {user.user_id}")

    # Check if recipe exists
    recipe = db.get_recipe(recipe_id)
    if not recipe:
        raise NotFoundException(f"Recipe with ID {recipe_id} not found")

    # Prepare data for database
    rating_dict = rating_data.model_dump()
    rating_dict.update(
        {
            "recipe_id": recipe_id,
            "cognito_user_id": user.user_id,
        }
    )

    result = db.set_rating(rating_dict)
    # Map cognito_user_id to user_id for the response model
    result["user_id"] = result["cognito_user_id"]
    return RatingResponse(**result)
