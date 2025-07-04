"""Recipes endpoints for the CocktailDB API"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, status

from dependencies.auth import (
    UserInfo,
    get_current_user_optional,
    require_authentication,
)
from db.database import get_database as get_db
from db.db_core import Database
from models.requests import (
    RecipeCreate,
    RecipeUpdate,
    RatingCreate,
    RecipeListParams,
    PaginationParams,
    SearchParams,
)
from models.responses import (
    RecipeResponse,
    RecipeListResponse,
    MessageResponse,
    RatingSummaryResponse,
    RatingResponse,
    PaginatedRecipeResponse,
    PaginatedSearchResponse,
    PaginationMetadata,
)
from core.exceptions import NotFoundException, DatabaseException, ValidationException
from .rating_handlers import (
    get_recipe_ratings_handler,
    create_or_update_rating_handler,
    delete_rating_handler,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recipes", tags=["recipes"])


@router.get("", response_model=PaginatedRecipeResponse)
async def get_recipes(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    limit: int = Query(20, ge=1, le=1000, description="Number of items per page"),
    sort_by: str = Query(
        "name", description="Sort field: name, created_at, avg_rating"
    ),
    sort_order: str = Query("asc", description="Sort order: asc, desc"),
    db: Database = Depends(get_db),
    user: Optional[UserInfo] = Depends(get_current_user_optional),
):
    """Get paginated recipes with full details"""
    try:
        logger.info(
            f"Getting recipes page {page}, limit {limit}, sort_by {sort_by}, sort_order {sort_order}"
        )

        # Validate sort parameters
        valid_sort_fields = ["name", "created_at", "avg_rating"]
        valid_sort_orders = ["asc", "desc"]

        if sort_by not in valid_sort_fields:
            raise ValidationException(
                f"Invalid sort_by field. Must be one of: {valid_sort_fields}"
            )

        if sort_order not in valid_sort_orders:
            raise ValidationException(
                f"Invalid sort_order. Must be one of: {valid_sort_orders}"
            )

        # Calculate offset
        offset = (page - 1) * limit
        user_id = user.user_id if user else None

        # Get paginated recipes with full details including ingredients
        recipes_data = db.get_recipes_paginated(
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            user_id=user_id,
        )

        # Get total count for pagination metadata
        total_count = db.get_recipes_count()
        total_pages = max(1, (total_count + limit - 1) // limit)

        # Build pagination metadata
        pagination = PaginationMetadata(
            page=page,
            limit=limit,
            total_pages=total_pages,
            total_count=total_count,
            has_next=page < total_pages,
            has_previous=page > 1,
        )

        # Convert to response models
        recipes = [RecipeResponse(**recipe) for recipe in recipes_data]

        return PaginatedRecipeResponse(recipes=recipes, pagination=pagination)

    except ValidationException:
        raise
    except Exception as e:
        logger.error(f"Error getting paginated recipes: {str(e)}")
        raise DatabaseException("Failed to retrieve recipes", detail=str(e))


@router.get("/search", response_model=PaginatedSearchResponse)
async def search_recipes(
    q: Optional[str] = Query(None, description="Search query"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    limit: int = Query(20, ge=1, le=1000, description="Number of items per page"),
    sort_by: str = Query(
        "name", description="Sort field: name, created_at, avg_rating"
    ),
    sort_order: str = Query("asc", description="Sort order: asc, desc"),
    min_rating: Optional[float] = Query(
        None, description="Minimum average rating", ge=0, le=5
    ),
    max_rating: Optional[float] = Query(
        None, description="Maximum average rating", ge=0, le=5
    ),
    tags: Optional[str] = Query(None, description="Comma-separated list of tags"),
    ingredients: Optional[str] = Query(
        None,
        description="Comma-separated ingredient names with optional operators (e.g., 'Vodka,Gin:MUST,Vermouth:MUST_NOT')",
    ),
    db: Database = Depends(get_db),
    user: Optional[UserInfo] = Depends(get_current_user_optional),
):
    """Search recipes with pagination and filters"""
    try:
        logger.info(f"Searching recipes: q='{q}', page={page}, limit={limit}")
        logger.info(
            f"All search parameters: q={q}, min_rating={min_rating}, max_rating={max_rating}, tags={tags}, ingredients={ingredients}"
        )

        # Validate sort parameters
        valid_sort_fields = ["name", "created_at", "avg_rating"]
        valid_sort_orders = ["asc", "desc"]

        if sort_by not in valid_sort_fields:
            raise ValidationException(
                f"Invalid sort_by field. Must be one of: {valid_sort_fields}"
            )

        if sort_order not in valid_sort_orders:
            raise ValidationException(
                f"Invalid sort_order. Must be one of: {valid_sort_orders}"
            )

        # Calculate offset
        offset = (page - 1) * limit
        user_id = user.user_id if user else None

        # Build search parameters
        search_params = {}
        if q and q.strip():
            search_params["q"] = q.strip()
        if min_rating is not None:
            search_params["min_rating"] = min_rating
        if max_rating is not None:
            search_params["max_rating"] = max_rating
        if tags:
            search_params["tags"] = [
                tag.strip() for tag in tags.split(",") if tag.strip()
            ]
        if ingredients:
            search_params["ingredients"] = [
                ing.strip() for ing in ingredients.split(",") if ing.strip()
            ]

        logger.info(f"Search params: {search_params}")
        logger.info(
            f"Database search will be called with limit={limit}, offset={offset}"
        )

        # Get paginated search results
        recipes_data, total_count = db.search_recipes_paginated(
            search_params=search_params,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            user_id=user_id,
        )

        logger.info(
            f"Database returned {len(recipes_data)} recipes, total_count={total_count}"
        )

        # Build pagination metadata
        total_pages = max(1, (total_count + limit - 1) // limit)
        pagination = PaginationMetadata(
            page=page,
            limit=limit,
            total_pages=total_pages,
            total_count=total_count,
            has_next=page < total_pages,
            has_previous=page > 1,
        )

        # Convert to response models
        recipes = [RecipeResponse(**recipe) for recipe in recipes_data]

        return PaginatedSearchResponse(recipes=recipes, pagination=pagination, query=q)

    except ValidationException:
        raise
    except Exception as e:
        logger.error(f"Error searching recipes: {str(e)}")
        raise DatabaseException("Failed to search recipes", detail=str(e))


@router.post("", response_model=RecipeResponse, status_code=status.HTTP_201_CREATED)
async def create_recipe(
    recipe_data: RecipeCreate,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Create a new recipe (requires authentication)"""
    try:
        logger.info(f"Creating recipe: {recipe_data.name}")

        # Prepare data for database
        recipe_dict = recipe_data.model_dump()
        recipe_dict["created_by"] = user.user_id

        created_recipe = db.create_recipe(recipe_dict)

        # Get the full recipe data with ingredients
        full_recipe = db.get_recipe(created_recipe["id"], user.user_id)
        return RecipeResponse(**full_recipe)

    except Exception as e:
        logger.error(f"Error creating recipe: {str(e)}")
        raise DatabaseException("Failed to create recipe", detail=str(e))


@router.get("/{recipe_id}", response_model=RecipeResponse)
async def get_recipe(
    recipe_id: int,
    db: Database = Depends(get_db),
    user: Optional[UserInfo] = Depends(get_current_user_optional),
):
    """Get a specific recipe by ID"""
    try:
        logger.info(f"Getting recipe {recipe_id}")
        logger.info(f"Database instance: {db}")
        logger.info(f"User info: {user}")

        user_id = user.user_id if user else None
        logger.info(f"Resolved user_id: {user_id}")

        recipe = db.get_recipe(recipe_id, user_id)
        logger.info(f"Recipe retrieved: {recipe is not None}")

        if not recipe:
            logger.warning(f"Recipe {recipe_id} not found")
            raise NotFoundException(f"Recipe with ID {recipe_id} not found")

        logger.info(f"Returning recipe: {recipe.get('name', 'unnamed')}")
        return RecipeResponse(**recipe)

    except NotFoundException:
        logger.warning(f"NotFoundException for recipe {recipe_id}")
        raise
    except Exception as e:
        logger.error(f"Error getting recipe {recipe_id}: {str(e)}", exc_info=True)
        raise DatabaseException("Failed to retrieve recipe", detail=str(e))


@router.put("/{recipe_id}", response_model=RecipeResponse)
async def update_recipe(
    recipe_id: int,
    recipe_data: RecipeUpdate,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Update a recipe (requires authentication)"""
    try:
        logger.info(f"Updating recipe {recipe_id}")

        # Check if recipe exists
        existing_recipe = db.get_recipe(recipe_id, user.user_id)
        if not existing_recipe:
            raise NotFoundException(f"Recipe with ID {recipe_id} not found")

        # Prepare data for database (only include non-None values)
        update_dict = {
            k: v for k, v in recipe_data.model_dump().items() if v is not None
        }

        db.update_recipe(recipe_id, update_dict)

        # Get the full recipe data with ingredients
        full_recipe = db.get_recipe(recipe_id, user.user_id)
        return RecipeResponse(**full_recipe)

    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error updating recipe {recipe_id}: {str(e)}")
        raise DatabaseException("Failed to update recipe", detail=str(e))


@router.delete("/{recipe_id}", response_model=MessageResponse)
async def delete_recipe(
    recipe_id: int,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Delete a recipe (requires authentication)"""
    try:
        logger.info(f"Deleting recipe {recipe_id}")

        # Check if recipe exists
        existing_recipe = db.get_recipe(recipe_id, user.user_id)
        if not existing_recipe:
            raise NotFoundException(f"Recipe with ID {recipe_id} not found")

        db.delete_recipe(recipe_id)
        return MessageResponse(message=f"Recipe {recipe_id} deleted successfully")

    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting recipe {recipe_id}: {str(e)}")
        raise DatabaseException("Failed to delete recipe", detail=str(e))


# Nested ratings endpoints for RESTful API design
@router.get("/{recipe_id}/ratings", response_model=RatingSummaryResponse)
async def get_recipe_ratings(
    recipe_id: int,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(get_current_user_optional),
):
    """Get ratings for a specific recipe"""
    return await get_recipe_ratings_handler(recipe_id, db, user)


@router.post(
    "/{recipe_id}/ratings",
    response_model=RatingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_or_update_rating(
    recipe_id: int,
    rating_data: RatingCreate,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Create or update a rating for a recipe (requires authentication)"""
    return await create_or_update_rating_handler(recipe_id, rating_data, db, user)


@router.put("/{recipe_id}/ratings", response_model=RatingResponse)
async def update_recipe_rating(
    recipe_id: int,
    rating_data: RatingCreate,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Update a rating for a recipe (requires authentication)"""
    # PUT and POST have the same logic for ratings (upsert)
    return await create_or_update_rating_handler(recipe_id, rating_data, db, user)


@router.delete("/{recipe_id}/ratings", response_model=MessageResponse)
async def delete_recipe_rating(
    recipe_id: int,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Delete a user's rating for a recipe (requires authentication)"""
    return await delete_rating_handler(recipe_id, db, user)
