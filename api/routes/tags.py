"""Tags endpoints for the CocktailDB API"""

import logging
from typing import List
from fastapi import APIRouter, Depends, status

from ..dependencies.auth import UserInfo, get_current_user_optional, require_authentication
from ..dependencies.database import get_db
from ..db.db_core import Database
from ..models.requests import TagCreate, RecipeTagAssociation
from ..models.responses import TagResponse, MessageResponse
from ..core.exceptions import NotFoundException, DatabaseException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("/public", response_model=List[TagResponse])
async def get_public_tags(
    db: Database = Depends(get_db),
    user: UserInfo = Depends(get_current_user_optional)
):
    """Get all public tags"""
    try:
        logger.info("Getting public tags")
        tags = db.get_public_tags()
        return [TagResponse(**tag) for tag in tags]
    except Exception as e:
        logger.error(f"Error getting public tags: {str(e)}")
        raise DatabaseException("Failed to retrieve public tags", detail=str(e))


@router.post("/public", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_public_tag(
    tag_data: TagCreate,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication)
):
    """Create a new public tag (requires authentication)"""
    try:
        logger.info(f"Creating public tag: {tag_data.name}")
        
        tag_dict = tag_data.model_dump()
        tag_dict.update({
            "is_private": False,
            "created_by": user.user_id
        })
        
        created_tag = db.create_tag(tag_dict)
        return TagResponse(**created_tag)
        
    except Exception as e:
        logger.error(f"Error creating public tag: {str(e)}")
        raise DatabaseException("Failed to create public tag", detail=str(e))


@router.get("/private", response_model=List[TagResponse])
async def get_private_tags(
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication)
):
    """Get private tags for the authenticated user"""
    try:
        logger.info(f"Getting private tags for user {user.user_id}")
        tags = db.get_private_tags(user.user_id)
        return [TagResponse(**tag) for tag in tags]
    except Exception as e:
        logger.error(f"Error getting private tags: {str(e)}")
        raise DatabaseException("Failed to retrieve private tags", detail=str(e))


@router.post("/private", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_private_tag(
    tag_data: TagCreate,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication)
):
    """Create a new private tag (requires authentication)"""
    try:
        logger.info(f"Creating private tag: {tag_data.name}")
        
        tag_dict = tag_data.model_dump()
        tag_dict.update({
            "is_private": True,
            "created_by": user.user_id
        })
        
        created_tag = db.create_tag(tag_dict)
        return TagResponse(**created_tag)
        
    except Exception as e:
        logger.error(f"Error creating private tag: {str(e)}")
        raise DatabaseException("Failed to create private tag", detail=str(e))


# Recipe tag association endpoints
recipe_tags_router = APIRouter(prefix="/recipes", tags=["recipe-tags"])


@recipe_tags_router.post("/{recipe_id}/public_tags", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def add_public_tag_to_recipe(
    recipe_id: int,
    tag_association: RecipeTagAssociation,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication)
):
    """Add a public tag to a recipe (requires authentication)"""
    try:
        logger.info(f"Adding public tag {tag_association.tag_id} to recipe {recipe_id}")
        
        # Check if recipe exists
        recipe = db.get_recipe(recipe_id)
        if not recipe:
            raise NotFoundException(f"Recipe with ID {recipe_id} not found")
        
        # Check if tag exists and is public
        tag = db.get_tag(tag_association.tag_id)
        if not tag:
            raise NotFoundException(f"Tag with ID {tag_association.tag_id} not found")
        
        if tag.get("is_private", False):
            raise DatabaseException("Cannot add private tag as public tag")
        
        db.add_recipe_tag(recipe_id, tag_association.tag_id, is_private=False, user_id=user.user_id)
        return MessageResponse(message="Public tag added to recipe successfully")
        
    except (NotFoundException, DatabaseException):
        raise
    except Exception as e:
        logger.error(f"Error adding public tag to recipe: {str(e)}")
        raise DatabaseException("Failed to add public tag to recipe", detail=str(e))


@recipe_tags_router.delete("/{recipe_id}/public_tags/{tag_id}", response_model=MessageResponse)
async def remove_public_tag_from_recipe(
    recipe_id: int,
    tag_id: int,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication)
):
    """Remove a public tag from a recipe (requires authentication)"""
    try:
        logger.info(f"Removing public tag {tag_id} from recipe {recipe_id}")
        
        # Check if recipe exists
        recipe = db.get_recipe(recipe_id)
        if not recipe:
            raise NotFoundException(f"Recipe with ID {recipe_id} not found")
        
        db.remove_recipe_tag(recipe_id, tag_id, is_private=False, user_id=user.user_id)
        return MessageResponse(message="Public tag removed from recipe successfully")
        
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error removing public tag from recipe: {str(e)}")
        raise DatabaseException("Failed to remove public tag from recipe", detail=str(e))


@recipe_tags_router.post("/{recipe_id}/private_tags", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def add_private_tag_to_recipe(
    recipe_id: int,
    tag_association: RecipeTagAssociation,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication)
):
    """Add a private tag to a recipe (requires authentication)"""
    try:
        logger.info(f"Adding private tag {tag_association.tag_id} to recipe {recipe_id}")
        
        # Check if recipe exists
        recipe = db.get_recipe(recipe_id)
        if not recipe:
            raise NotFoundException(f"Recipe with ID {recipe_id} not found")
        
        # Check if tag exists and belongs to user
        tag = db.get_tag(tag_association.tag_id)
        if not tag:
            raise NotFoundException(f"Tag with ID {tag_association.tag_id} not found")
        
        if not tag.get("is_private", False) or tag.get("created_by") != user.user_id:
            raise DatabaseException("Can only add your own private tags")
        
        db.add_recipe_tag(recipe_id, tag_association.tag_id, is_private=True, user_id=user.user_id)
        return MessageResponse(message="Private tag added to recipe successfully")
        
    except (NotFoundException, DatabaseException):
        raise
    except Exception as e:
        logger.error(f"Error adding private tag to recipe: {str(e)}")
        raise DatabaseException("Failed to add private tag to recipe", detail=str(e))


@recipe_tags_router.delete("/{recipe_id}/private_tags/{tag_id}", response_model=MessageResponse)
async def remove_private_tag_from_recipe(
    recipe_id: int,
    tag_id: int,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication)
):
    """Remove a private tag from a recipe (requires authentication)"""
    try:
        logger.info(f"Removing private tag {tag_id} from recipe {recipe_id}")
        
        # Check if recipe exists
        recipe = db.get_recipe(recipe_id)
        if not recipe:
            raise NotFoundException(f"Recipe with ID {recipe_id} not found")
        
        db.remove_recipe_tag(recipe_id, tag_id, is_private=True, user_id=user.user_id)
        return MessageResponse(message="Private tag removed from recipe successfully")
        
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error removing private tag from recipe: {str(e)}")
        raise DatabaseException("Failed to remove private tag from recipe", detail=str(e))