"""Ratings endpoints for the CocktailDB API"""

import logging
from fastapi import APIRouter, Depends, status

from dependencies.auth import (
    UserInfo,
    get_current_user_optional,
    require_authentication,
)
from core.database import get_database as get_db
from db.db_core import Database
from models.requests import RatingCreate
from models.responses import RatingSummaryResponse, RatingResponse, MessageResponse
from .rating_handlers import (
    get_recipe_ratings_handler,
    create_or_update_rating_handler,
    delete_rating_handler,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ratings", tags=["ratings"])


@router.get("/{recipe_id}", response_model=RatingSummaryResponse)
async def get_recipe_ratings(
    recipe_id: int,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(get_current_user_optional),
):
    """Get ratings for a specific recipe"""
    return await get_recipe_ratings_handler(recipe_id, db, user)


@router.post(
    "/{recipe_id}", response_model=RatingResponse, status_code=status.HTTP_201_CREATED
)
async def create_or_update_rating(
    recipe_id: int,
    rating_data: RatingCreate,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Create or update a rating for a recipe (requires authentication)"""
    return await create_or_update_rating_handler(recipe_id, rating_data, db, user)


@router.put("/{recipe_id}", response_model=RatingResponse)
async def update_rating(
    recipe_id: int,
    rating_data: RatingCreate,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Update a rating for a recipe (requires authentication)"""
    # PUT and POST have the same logic for ratings (upsert)
    return await create_or_update_rating_handler(recipe_id, rating_data, db, user)


@router.delete("/{recipe_id}", response_model=MessageResponse)
async def delete_rating(
    recipe_id: int,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Delete a user's rating for a recipe (requires authentication)"""
    return await delete_rating_handler(recipe_id, db, user)
