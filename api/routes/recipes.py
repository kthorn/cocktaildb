"""Recipes endpoints for the CocktailDB API"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, status

from dependencies.auth import UserInfo, get_current_user_optional, require_authentication
from core.database import get_database as get_db
from db.db_core import Database
from models.requests import RecipeCreate, RecipeUpdate, RecipeSearchRequest
from models.responses import (
    RecipeResponse, RecipeListResponse, MessageResponse, SearchResultsResponse
)
from core.exceptions import NotFoundException, DatabaseException, ValidationException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recipes", tags=["recipes"])


@router.get("", response_model=List[RecipeListResponse])
async def get_recipes(
    search: Optional[bool] = Query(None, description="Whether to perform search"),
    query: Optional[str] = Query(None, description="Search query"),
    ingredients: Optional[str] = Query(None, description="Ingredient filters (JSON)"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Database = Depends(get_db),
    user: Optional[UserInfo] = Depends(get_current_user_optional)
):
    """Get all recipes or search recipes"""
    try:
        if search:
            logger.info(f"Searching recipes with query: {query}")
            
            # Parse ingredients filter if provided
            ingredient_filters = []
            if ingredients:
                import json
                try:
                    ingredient_filters = json.loads(ingredients)
                except json.JSONDecodeError:
                    raise ValidationException("Invalid ingredients filter format")
            
            # Perform search
            search_params = {
                "query": query,
                "ingredients": ingredient_filters,
                "limit": limit,
                "offset": offset
            }
            
            results = db.search_recipes(search_params)
            
            return SearchResultsResponse(
                recipes=[RecipeListResponse(**recipe) for recipe in results.get("recipes", [])],
                total_count=results.get("total_count", 0),
                offset=offset,
                limit=limit
            )
        else:
            logger.info("Getting all recipes")
            recipes = db.get_recipes()
            return [RecipeListResponse(**recipe) for recipe in recipes]
            
    except ValidationException:
        raise
    except Exception as e:
        logger.error(f"Error getting recipes: {str(e)}")
        raise DatabaseException("Failed to retrieve recipes", detail=str(e))


@router.post("", response_model=RecipeResponse, status_code=status.HTTP_201_CREATED)
async def create_recipe(
    recipe_data: RecipeCreate,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication)
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
    user: Optional[UserInfo] = Depends(get_current_user_optional)
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
    user: UserInfo = Depends(require_authentication)
):
    """Update a recipe (requires authentication)"""
    try:
        logger.info(f"Updating recipe {recipe_id}")
        
        # Check if recipe exists
        existing_recipe = db.get_recipe(recipe_id, user.user_id)
        if not existing_recipe:
            raise NotFoundException(f"Recipe with ID {recipe_id} not found")
        
        # Prepare data for database (only include non-None values)
        update_dict = {k: v for k, v in recipe_data.model_dump().items() if v is not None}
        update_dict["id"] = recipe_id
        
        updated_recipe = db.update_recipe(update_dict)
        
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
    user: UserInfo = Depends(require_authentication)
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