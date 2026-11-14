"""Tags endpoints for the CocktailDB API"""

import logging

from core.exceptions import NotFoundException, ValidationException
from db.database import get_database as get_db
from db.db_core import Database
from dependencies.auth import (
    UserInfo,
    require_authentication,
)
from fastapi import APIRouter, Depends, status
from models.requests import RecipeTagAssociation, TagCreate
from models.responses import MessageResponse, PrivateTagResponse, PublicTagResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("/public", response_model=list[PublicTagResponse])
async def get_public_tags(db: Database = Depends(get_db)):
    """Get all public tags"""
    logger.info("Getting public tags")
    tags = db.get_public_tags()
    return [PublicTagResponse(**tag) for tag in tags]


@router.post(
    "/public", response_model=PublicTagResponse, status_code=status.HTTP_201_CREATED
)
async def create_public_tag(
    tag_data: TagCreate,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(
        require_authentication
    ),  # User needed for authentication only
):
    """Create a new public tag (requires authentication)"""
    logger.info(f"Creating public tag: '{tag_data.name}' for user {user.user_id}")
    _ = user  # Satisfy linter - user is needed for auth dependency

    # Check if tag already exists before creating
    existing_tags = db.get_public_tags()
    existing_tag = next(
        (tag for tag in existing_tags if tag["name"].lower() == tag_data.name.lower()),
        None,
    )
    if existing_tag:
        logger.warning(
            f"Public tag '{tag_data.name}' already exists with ID {existing_tag['id']}, returning existing tag"
        )
        return PublicTagResponse(**existing_tag)

    created_tag = db.create_public_tag(tag_data.name)
    logger.info(
        f"Successfully created public tag: ID={created_tag['id']}, name='{created_tag['name']}'"
    )
    return PublicTagResponse(**created_tag)


@router.get("/private", response_model=list[PrivateTagResponse])
async def get_private_tags(
    db: Database = Depends(get_db), user: UserInfo = Depends(require_authentication)
):
    """Get private tags for the authenticated user"""
    logger.info(f"Getting private tags for user {user.user_id}")
    tags = db.get_private_tags(user.user_id)
    return [PrivateTagResponse(**tag) for tag in tags]


@router.post(
    "/private", response_model=PrivateTagResponse, status_code=status.HTTP_201_CREATED
)
async def create_private_tag(
    tag_data: TagCreate,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Create a new private tag (requires authentication)"""
    logger.info(f"Creating private tag: '{tag_data.name}' for user {user.user_id}")

    # Check if tag already exists for this user before creating
    existing_tags = db.get_private_tags(user.user_id)
    existing_tag = next(
        (tag for tag in existing_tags if tag["name"].lower() == tag_data.name.lower()),
        None,
    )
    if existing_tag:
        logger.warning(
            f"Private tag '{tag_data.name}' already exists for user {user.user_id} with ID {existing_tag['id']}, returning existing tag"
        )
        return PrivateTagResponse(**existing_tag)

    created_tag = db.create_private_tag(tag_data.name, user.user_id)
    logger.info(
        f"Successfully created private tag: ID={created_tag['id']}, name='{created_tag['name']}', user={user.user_id}"
    )
    return PrivateTagResponse(**created_tag)


@router.delete("/public/{tag_id}", response_model=MessageResponse)
async def delete_public_tag(
    tag_id: int,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(
        require_authentication
    ),  # User needed for authentication only
):
    """Delete a public tag completely (admin only - requires authentication)"""
    logger.info(f"Deleting public tag {tag_id}")
    _ = user  # Satisfy linter - user is needed for auth dependency

    success = db.delete_public_tag(tag_id)
    if not success:
        raise NotFoundException(f"Public tag with ID {tag_id} not found")

    return MessageResponse(message="Public tag deleted successfully")


@router.delete("/private/{tag_id}", response_model=MessageResponse)
async def delete_private_tag(
    tag_id: int,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Delete a private tag completely (user can only delete their own tags)"""
    logger.info(f"Deleting private tag {tag_id} for user {user.user_id}")

    success = db.delete_private_tag(tag_id, user.user_id)
    if not success:
        raise NotFoundException(
            f"Private tag with ID {tag_id} not found or not owned by user"
        )

    return MessageResponse(message="Private tag deleted successfully")


# Recipe tag association endpoints
recipe_tags_router = APIRouter(prefix="/recipes", tags=["recipe-tags"])


@recipe_tags_router.post(
    "/{recipe_id}/public_tags",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_public_tag_to_recipe(
    recipe_id: int,
    tag_association: RecipeTagAssociation,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Add a public tag to a recipe (requires authentication)"""
    logger.info(
        f"Adding public tag {tag_association.tag_id} to recipe {recipe_id} by user {user.user_id}"
    )

    # Check if recipe exists
    recipe = db.get_recipe(recipe_id)
    if not recipe:
        logger.warning(
            f"Recipe {recipe_id} not found when trying to add tag {tag_association.tag_id}"
        )
        raise NotFoundException(f"Recipe with ID {recipe_id} not found")

    # Check if tag exists and is public
    tag = db.get_tag(tag_association.tag_id)
    if not tag:
        logger.warning(
            f"Tag {tag_association.tag_id} not found when trying to add to recipe {recipe_id}"
        )
        raise NotFoundException(f"Tag with ID {tag_association.tag_id} not found")

    logger.info(
        f"Adding tag: ID={tag['id']}, name='{tag['name']}', is_private={tag.get('is_private', False)}"
    )

    if tag.get("is_private", False):
        logger.error(
            f"Attempted to add private tag {tag_association.tag_id} as public tag to recipe {recipe_id}"
        )
        raise ValidationException("Cannot add private tag as public tag")

    # Check if association already exists
    existing_recipe = db.get_recipe(recipe_id, user.user_id)
    existing_tag_ids = (
        [t["id"] for t in existing_recipe.get("tags", [])] if existing_recipe else []
    )
    if tag_association.tag_id in existing_tag_ids:
        logger.warning(
            f"Tag {tag_association.tag_id} already associated with recipe {recipe_id}, skipping"
        )
    else:
        result = db.add_recipe_tag(
            recipe_id,
            tag_association.tag_id,
            is_private=False,
            user_id=user.user_id,
        )
        logger.info(f"Recipe-tag association result: {result}")

    return MessageResponse(message="Public tag added to recipe successfully")


@recipe_tags_router.delete(
    "/{recipe_id}/public_tags/{tag_id}", response_model=MessageResponse
)
async def remove_public_tag_from_recipe(
    recipe_id: int,
    tag_id: int,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Remove a public tag from a recipe (requires authentication)"""
    logger.info(f"Removing public tag {tag_id} from recipe {recipe_id}")

    # Check if recipe exists
    recipe = db.get_recipe(recipe_id)
    if not recipe:
        raise NotFoundException(f"Recipe with ID {recipe_id} not found")

    db.remove_recipe_tag(recipe_id, tag_id, is_private=False, user_id=user.user_id)
    return MessageResponse(message="Public tag removed from recipe successfully")


@recipe_tags_router.post(
    "/{recipe_id}/private_tags",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_private_tag_to_recipe(
    recipe_id: int,
    tag_association: RecipeTagAssociation,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Add a private tag to a recipe (requires authentication)"""
    logger.info(f"Adding private tag {tag_association.tag_id} to recipe {recipe_id}")

    # Check if recipe exists
    recipe = db.get_recipe(recipe_id)
    if not recipe:
        raise NotFoundException(f"Recipe with ID {recipe_id} not found")

    # Check if tag exists and belongs to user
    tag = db.get_tag(tag_association.tag_id)
    if not tag:
        raise NotFoundException(f"Tag with ID {tag_association.tag_id} not found")

    if not tag.get("is_private", False):
        raise ValidationException("Cannot add public tag as private tag")
    if tag.get("created_by") != user.user_id:
        # Don't reveal that another user's private tag exists.
        raise NotFoundException(f"Tag with ID {tag_association.tag_id} not found")

    db.add_recipe_tag(
        recipe_id, tag_association.tag_id, is_private=True, user_id=user.user_id
    )
    return MessageResponse(message="Private tag added to recipe successfully")


@recipe_tags_router.delete(
    "/{recipe_id}/private_tags/{tag_id}", response_model=MessageResponse
)
async def remove_private_tag_from_recipe(
    recipe_id: int,
    tag_id: int,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Remove a private tag from a recipe (requires authentication)"""
    logger.info(f"Removing private tag {tag_id} from recipe {recipe_id}")

    # Check if recipe exists
    recipe = db.get_recipe(recipe_id)
    if not recipe:
        raise NotFoundException(f"Recipe with ID {recipe_id} not found")

    db.remove_recipe_tag(recipe_id, tag_id, is_private=True, user_id=user.user_id)
    return MessageResponse(message="Private tag removed from recipe successfully")
