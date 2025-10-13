"""Ingredients endpoints for the CocktailDB API"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, status

from dependencies.auth import (
    UserInfo,
    get_current_user_optional,
    require_authentication,
    require_editor_access,
)
from db.database import get_database as get_db
from db.db_core import Database
from models.requests import IngredientCreate, IngredientUpdate, BulkIngredientUpload
from models.responses import (
    IngredientResponse,
    MessageResponse,
    BulkIngredientUploadResponse,
    BulkIngredientUploadValidationError,
)
from core.exceptions import NotFoundException, DatabaseException
from utils.analytics_helpers import trigger_analytics_refresh

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingredients", tags=["ingredients"])


@router.get("", response_model=List[IngredientResponse])
async def get_ingredients(
    db: Database = Depends(get_db),
    user: Optional[UserInfo] = Depends(get_current_user_optional),
):
    """Get all ingredients"""
    try:
        logger.info("Getting all ingredients")
        ingredients = db.get_ingredients()
        return [IngredientResponse(**ingredient) for ingredient in ingredients]
    except Exception as e:
        logger.error(f"Error getting ingredients: {str(e)}")
        raise DatabaseException("Failed to retrieve ingredients", detail=str(e))


@router.post("", response_model=IngredientResponse, status_code=status.HTTP_201_CREATED)
async def create_ingredient(
    ingredient_data: IngredientCreate,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_editor_access),
):
    """Create a new ingredient (requires editor access)"""
    try:
        logger.info(f"Creating ingredient: {ingredient_data.name}")

        # Prepare data for database
        ingredient_dict = ingredient_data.model_dump()
        ingredient_dict["created_by"] = user.user_id

        created_ingredient = db.create_ingredient(ingredient_dict)

        # Trigger analytics refresh asynchronously
        trigger_analytics_refresh()

        return IngredientResponse(**created_ingredient)

    except Exception as e:
        logger.error(f"Error creating ingredient: {str(e)}")
        raise DatabaseException("Failed to create ingredient", detail=str(e))


@router.get("/{ingredient_id}", response_model=IngredientResponse)
async def get_ingredient(
    ingredient_id: int,
    db: Database = Depends(get_db),
    user: Optional[UserInfo] = Depends(get_current_user_optional),
):
    """Get a specific ingredient by ID"""
    try:
        logger.info(f"Getting ingredient {ingredient_id}")
        ingredient = db.get_ingredient(ingredient_id)

        if not ingredient:
            raise NotFoundException(f"Ingredient with ID {ingredient_id} not found")

        return IngredientResponse(**ingredient)

    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error getting ingredient {ingredient_id}: {str(e)}")
        raise DatabaseException("Failed to retrieve ingredient", detail=str(e))


@router.put("/{ingredient_id}", response_model=IngredientResponse)
async def update_ingredient(
    ingredient_id: int,
    ingredient_data: IngredientUpdate,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_editor_access),
):
    """Update an ingredient (requires editor access)"""
    try:
        logger.info(f"Updating ingredient {ingredient_id}")

        # Check if ingredient exists
        existing_ingredient = db.get_ingredient(ingredient_id)
        if not existing_ingredient:
            raise NotFoundException(f"Ingredient with ID {ingredient_id} not found")

        # Prepare data for database (only include non-None values)
        update_dict = {
            k: v for k, v in ingredient_data.model_dump().items() if v is not None
        }

        updated_ingredient = db.update_ingredient(ingredient_id, update_dict)

        # Trigger analytics refresh asynchronously
        trigger_analytics_refresh()

        return IngredientResponse(**updated_ingredient)

    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error updating ingredient {ingredient_id}: {str(e)}")
        raise DatabaseException("Failed to update ingredient", detail=str(e))


@router.delete("/{ingredient_id}", response_model=MessageResponse)
async def delete_ingredient(
    ingredient_id: int,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_editor_access),
):
    """Delete an ingredient (requires editor access)"""
    try:
        logger.info(f"Deleting ingredient {ingredient_id}")

        # Check if ingredient exists
        existing_ingredient = db.get_ingredient(ingredient_id)
        if not existing_ingredient:
            raise NotFoundException(f"Ingredient with ID {ingredient_id} not found")

        db.delete_ingredient(ingredient_id)

        # Trigger analytics refresh asynchronously
        trigger_analytics_refresh()

        return MessageResponse(
            message=f"Ingredient {ingredient_id} deleted successfully"
        )

    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting ingredient {ingredient_id}: {str(e)}")
        raise DatabaseException("Failed to delete ingredient", detail=str(e))


@router.post(
    "/bulk",
    response_model=BulkIngredientUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def bulk_upload_ingredients(
    bulk_data: BulkIngredientUpload,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_editor_access),
):
    """Bulk upload ingredients (requires editor access)"""
    import time

    start_time = time.time()
    try:
        logger.info(
            f"Bulk ingredient upload started: {len(bulk_data.ingredients)} ingredients"
        )

        validation_errors = []
        uploaded_ingredients = []
        failed_ingredient_indices = set()

        # Step 1: Validate all ingredients before creating any using batch operations
        validation_start = time.time()
        logger.info("Starting validation phase with batch operations")

        # Collect all unique names for batch validation
        all_ingredient_names = [ingredient.name for ingredient in bulk_data.ingredients]
        all_parent_names = list(
            set(
                ingredient.parent_name
                for ingredient in bulk_data.ingredients
                if ingredient.parent_name is not None
            )
        )

        logger.info(
            f"Batch validation: {len(all_ingredient_names)} ingredients, {len(all_parent_names)} unique parent names"
        )
        duplicate_names = db.check_ingredient_names_batch(all_ingredient_names)
        valid_parents = (
            db.search_ingredients_batch(all_parent_names) if all_parent_names else {}
        )
        batch_validation_duration = time.time() - validation_start
        logger.info(f"Batch validation completed in {batch_validation_duration:.3f}s")

        # Now validate each ingredient using the batch results
        individual_validation_start = time.time()

        for idx, ingredient_data in enumerate(bulk_data.ingredients):
            try:
                ingredient_validation_start = time.time()
                logger.info(f"Validating ingredient {idx}: {ingredient_data.name}")

                # Check if ingredient name already exists (using batch results)
                if duplicate_names.get(ingredient_data.name, False):
                    validation_errors.append(
                        BulkIngredientUploadValidationError(
                            ingredient_index=idx,
                            ingredient_name=ingredient_data.name,
                            error_type="duplicate_name",
                            error_message=f"Ingredient with name '{ingredient_data.name}' already exists",
                        )
                    )
                    failed_ingredient_indices.add(idx)
                    continue

                # Check if parent exists (using batch results)
                if ingredient_data.parent_name is not None:
                    if ingredient_data.parent_name not in valid_parents:
                        validation_errors.append(
                            BulkIngredientUploadValidationError(
                                ingredient_index=idx,
                                ingredient_name=ingredient_data.name,
                                error_type="parent_not_found",
                                error_message=f"No exact match found for parent ingredient '{ingredient_data.parent_name}'",
                            )
                        )
                        failed_ingredient_indices.add(idx)
                        continue
                elif ingredient_data.parent_id is not None:
                    # Legacy parent ID validation (still needs individual query)
                    parent_exists = db.execute_query(
                        "SELECT id FROM ingredients WHERE id = ?",
                        (ingredient_data.parent_id,),
                    )
                    if not parent_exists:
                        validation_errors.append(
                            BulkIngredientUploadValidationError(
                                ingredient_index=idx,
                                ingredient_name=ingredient_data.name,
                                error_type="invalid_parent",
                                error_message=f"Parent ingredient with ID {ingredient_data.parent_id} does not exist",
                            )
                        )
                        failed_ingredient_indices.add(idx)
                        continue

                ingredient_validation_duration = (
                    time.time() - ingredient_validation_start
                )
                logger.info(
                    f"Ingredient {idx} validation took {ingredient_validation_duration:.3f}s"
                )

            except Exception as e:
                validation_errors.append(
                    BulkIngredientUploadValidationError(
                        ingredient_index=idx,
                        ingredient_name=ingredient_data.name,
                        error_type="validation_error",
                        error_message=f"Validation error: {str(e)}",
                    )
                )
                failed_ingredient_indices.add(idx)

        individual_validation_duration = time.time() - individual_validation_start
        logger.info(
            f"Individual validation completed in {individual_validation_duration:.3f}s"
        )
        validation_duration = time.time() - validation_start
        logger.info(f"Validation phase completed in {validation_duration:.3f}s")

        # Step 2: If there are validation errors, return them without creating any ingredients
        if validation_errors:
            total_duration = time.time() - start_time
            logger.warning(
                f"Bulk ingredient upload validation failed with {len(validation_errors)} errors in {total_duration:.3f}s"
            )
            return BulkIngredientUploadResponse(
                uploaded_count=0,
                failed_count=len(failed_ingredient_indices),
                validation_errors=validation_errors,
                uploaded_ingredients=[],
            )

        # Step 3: Create all ingredients (all validations passed)
        creation_start = time.time()
        logger.info("Starting ingredient creation phase")

        for idx, ingredient_data in enumerate(bulk_data.ingredients):
            try:
                ingredient_creation_start = time.time()
                logger.debug(f"Creating ingredient {idx}: {ingredient_data.name}")

                # Convert parent name to ID if needed
                parent_id = None
                if ingredient_data.parent_name is not None:
                    parent_data = valid_parents.get(ingredient_data.parent_name)
                    if parent_data:
                        parent_id = parent_data["id"]
                    else:
                        # This shouldn't happen since we validated above, but just in case
                        raise ValueError(
                            f"Parent ingredient '{ingredient_data.parent_name}' not found during conversion"
                        )
                elif ingredient_data.parent_id is not None:
                    # Use parent ID directly (backward compatibility)
                    parent_id = ingredient_data.parent_id

                # Prepare data for database
                ingredient_dict = {
                    "name": ingredient_data.name,
                    "description": ingredient_data.description,
                    "parent_id": parent_id,
                    "substitution_level": ingredient_data.substitution_level,
                    "created_by": user.user_id,
                }

                # Create the ingredient
                created_ingredient = db.create_ingredient(ingredient_dict)
                uploaded_ingredients.append(IngredientResponse(**created_ingredient))

                ingredient_creation_duration = time.time() - ingredient_creation_start
                logger.debug(
                    f"Ingredient {idx} creation took {ingredient_creation_duration:.3f}s"
                )

            except Exception as e:
                logger.error(
                    f"Error creating ingredient {idx} ('{ingredient_data.name}'): {str(e)}"
                )
                validation_errors.append(
                    BulkIngredientUploadValidationError(
                        ingredient_index=idx,
                        ingredient_name=ingredient_data.name,
                        error_type="creation_error",
                        error_message=f"Failed to create ingredient: {str(e)}",
                    )
                )
                failed_ingredient_indices.add(idx)

        creation_duration = time.time() - creation_start
        total_duration = time.time() - start_time

        logger.info(
            f"Bulk ingredient upload completed: {len(uploaded_ingredients)} uploaded, {len(validation_errors)} failed"
        )
        logger.info(f"Creation phase took {creation_duration:.3f}s")
        logger.info(f"Total bulk upload took {total_duration:.3f}s")

        # Trigger analytics refresh asynchronously if any ingredients were uploaded
        if uploaded_ingredients:
            trigger_analytics_refresh()

        return BulkIngredientUploadResponse(
            uploaded_count=len(uploaded_ingredients),
            failed_count=len(failed_ingredient_indices),
            validation_errors=validation_errors,
            uploaded_ingredients=uploaded_ingredients,
        )

    except Exception as e:
        total_duration = time.time() - start_time
        logger.error(
            f"Error in bulk ingredient upload after {total_duration:.3f}s: {str(e)}"
        )
        raise DatabaseException("Failed to bulk upload ingredients", detail=str(e))
