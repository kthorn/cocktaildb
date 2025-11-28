"""Recipes endpoints for the CocktailDB API"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, status

from dependencies.auth import (
    UserInfo,
    get_current_user_optional,
    require_authentication,
    require_editor_access,
)
from db.database import get_database as get_db
from db.db_core import Database
from models.requests import (
    RecipeCreate,
    RecipeUpdate,
    RatingCreate,
    BulkRecipeUpload,
)
from models.responses import (
    RecipeResponse,
    MessageResponse,
    RatingSummaryResponse,
    RatingResponse,
    PaginatedSearchResponse,
    PaginationMetadata,
    BulkUploadResponse,
    BulkUploadValidationError,
)
from core.exceptions import NotFoundException, DatabaseException, ValidationException
from .rating_handlers import (
    get_recipe_ratings_handler,
    create_or_update_rating_handler,
    delete_rating_handler,
)
from utils.analytics_helpers import trigger_analytics_refresh

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recipes", tags=["recipes"])


def check_duplicate_ingredients(ingredients: list) -> list[int]:
    """
    Check for duplicate ingredient_ids in a recipe's ingredients list.

    Args:
        ingredients: List of ingredient dicts, each containing 'ingredient_id'

    Returns:
        List of duplicate ingredient_ids (empty if no duplicates)
    """
    ingredient_id_counts = {}
    for ingredient in ingredients:
        ingredient_id = ingredient.get("ingredient_id")
        if ingredient_id is not None:
            ingredient_id_counts[ingredient_id] = ingredient_id_counts.get(ingredient_id, 0) + 1

    # Return list of ingredient_ids that appear more than once
    duplicates = [ing_id for ing_id, count in ingredient_id_counts.items() if count > 1]
    return duplicates


@router.get("/search", response_model=PaginatedSearchResponse)
async def search_recipes(
    q: Optional[str] = Query(None, description="Search query"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    limit: int = Query(20, ge=1, le=1000, description="Number of items per page"),
    sort_by: str = Query(
        "name", description="Sort field: name, created_at, avg_rating, random"
    ),
    sort_order: str = Query("asc", description="Sort order: asc, desc"),
    min_rating: Optional[float] = Query(
        None, description="Minimum rating (type depends on rating_type)", ge=0, le=5
    ),
    max_rating: Optional[float] = Query(
        None, description="Maximum rating (type depends on rating_type)", ge=0, le=5
    ),
    rating_type: str = Query(
        "average", description="Rating filter type: 'average' (avg_rating) or 'user' (user's personal rating)"
    ),
    tags: Optional[str] = Query(None, description="Comma-separated list of tags"),
    ingredients: Optional[str] = Query(
        None,
        description="Comma-separated ingredient names with optional operators (e.g., 'Vodka,Gin:MUST,Vermouth:MUST_NOT')",
    ),
    inventory: Optional[bool] = Query(
        None,
        description="Filter recipes that can be made with user's ingredient inventory",
    ),
    db: Database = Depends(get_db),
    user: Optional[UserInfo] = Depends(get_current_user_optional),
):
    """Search recipes with pagination and filters"""
    try:
        logger.info(f"Searching recipes: q='{q}', page={page}, limit={limit}")
        logger.info(
            f"All search parameters: q={q}, min_rating={min_rating}, max_rating={max_rating}, tags={tags}, ingredients={ingredients}, inventory={inventory}"
        )

        # Validate sort parameters
        valid_sort_fields = ["name", "created_at", "avg_rating", "random"]
        valid_sort_orders = ["asc", "desc"]
        valid_rating_types = ["average", "user"]

        if sort_by not in valid_sort_fields:
            raise ValidationException(
                f"Invalid sort_by field. Must be one of: {valid_sort_fields}"
            )

        if sort_order not in valid_sort_orders:
            raise ValidationException(
                f"Invalid sort_order. Must be one of: {valid_sort_orders}"
            )

        if rating_type not in valid_rating_types:
            raise ValidationException(
                f"Invalid rating_type. Must be one of: {valid_rating_types}"
            )

        # Validate that user rating filter requires authentication
        if rating_type == "user" and user is None:
            raise ValidationException(
                "Filtering by user ratings requires authentication. Please log in to use this feature."
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
        if inventory is True:
            if user_id is None:
                raise ValidationException(
                    "Inventory filtering requires authentication. Please log in to use this feature."
                )
            search_params["inventory"] = True

        logger.info(f"Search params: {search_params}")
        logger.info(
            f"Database search will be called with limit={limit}, offset={offset}"
        )
        
        # Debug: Log the exact search query being passed to database
        if search_params.get("q"):
            logger.info(f"Search query 'q' parameter: '{search_params['q']}'")

        # Get paginated search results
        recipes_data = db.search_recipes_paginated(
            search_params=search_params,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            user_id=user_id,
            rating_type=rating_type,
        )

        logger.info(f"Database returned {len(recipes_data)} recipes")

        # Build pagination metadata
        has_next = len(recipes_data) == limit
        total_count = len(recipes_data)  # Show at least the returned count
        pagination = PaginationMetadata(
            page=page,
            limit=limit,
            total_count=total_count,
            has_next=has_next,
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


@router.get("/search/authenticated", response_model=PaginatedSearchResponse)
async def search_recipes_authenticated(
    q: Optional[str] = Query(None, description="Search query"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    limit: int = Query(20, ge=1, le=1000, description="Number of items per page"),
    sort_by: str = Query(
        "name", description="Sort field: name, created_at, avg_rating, random"
    ),
    sort_order: str = Query("asc", description="Sort order: asc, desc"),
    min_rating: Optional[float] = Query(
        None, description="Minimum rating (type depends on rating_type)", ge=0, le=5
    ),
    max_rating: Optional[float] = Query(
        None, description="Maximum rating (type depends on rating_type)", ge=0, le=5
    ),
    rating_type: str = Query(
        "average", description="Rating filter type: 'average' (avg_rating) or 'user' (user's personal rating)"
    ),
    tags: Optional[str] = Query(None, description="Comma-separated list of tags"),
    ingredients: Optional[str] = Query(
        None,
        description="Comma-separated ingredient names with optional operators (e.g., 'Vodka,Gin:MUST,Vermouth:MUST_NOT')",
    ),
    inventory: Optional[bool] = Query(
        False,
        description="Filter recipes that can be made with user's ingredient inventory",
    ),
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Search recipes with authentication (required) - includes user ratings and optional inventory filtering"""
    # Reuse the existing search_recipes function
    return await search_recipes(
        q=q,
        page=page,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order,
        min_rating=min_rating,
        max_rating=max_rating,
        rating_type=rating_type,
        tags=tags,
        ingredients=ingredients,
        inventory=inventory,
        db=db,
        user=user,
    )


@router.post("", response_model=RecipeResponse, status_code=status.HTTP_201_CREATED)
async def create_recipe(
    recipe_data: RecipeCreate,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_editor_access),
):
    """Create a new recipe (requires editor access)"""
    try:
        logger.info(f"Creating recipe: {recipe_data.name}")

        # Prepare data for database
        recipe_dict = recipe_data.model_dump()
        recipe_dict["created_by"] = user.user_id

        # Check for duplicate ingredients
        if "ingredients" in recipe_dict and recipe_dict["ingredients"]:
            duplicate_ids = check_duplicate_ingredients(recipe_dict["ingredients"])
            if duplicate_ids:
                # Get ingredient names for better error message
                ingredient_names = []
                for ing_id in duplicate_ids:
                    ingredient = db.execute_query(
                        "SELECT name FROM ingredients WHERE id = ?", (ing_id,)
                    )
                    if ingredient:
                        ingredient_names.append(ingredient[0]["name"])

                raise ValidationException(
                    f"Recipe cannot have duplicate ingredients: {', '.join(ingredient_names)}"
                )

        created_recipe = db.create_recipe(recipe_dict)

        # Trigger analytics refresh asynchronously
        trigger_analytics_refresh()

        # Get the full recipe data with ingredients
        full_recipe = db.get_recipe(created_recipe["id"], user.user_id)
        return RecipeResponse(**full_recipe)

    except ValidationException:
        raise  # Re-raise ValidationException without wrapping
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
    user: UserInfo = Depends(require_editor_access),
):
    """Update a recipe (requires editor access)"""
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

        # Trigger analytics refresh asynchronously
        trigger_analytics_refresh()

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
    user: UserInfo = Depends(require_editor_access),
):
    """Delete a recipe (requires editor access)"""
    try:
        logger.info(f"Deleting recipe {recipe_id}")

        # Check if recipe exists
        existing_recipe = db.get_recipe(recipe_id, user.user_id)
        if not existing_recipe:
            raise NotFoundException(f"Recipe with ID {recipe_id} not found")

        db.delete_recipe(recipe_id)

        # Trigger analytics refresh asynchronously
        trigger_analytics_refresh()

        return MessageResponse(message=f"Recipe {recipe_id} deleted successfully")

    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting recipe {recipe_id}: {str(e)}")
        raise DatabaseException("Failed to delete recipe", detail=str(e))


@router.post(
    "/bulk", response_model=BulkUploadResponse, status_code=status.HTTP_201_CREATED
)
async def bulk_upload_recipes(
    bulk_data: BulkRecipeUpload,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_editor_access),
):
    """Bulk upload recipes (requires editor access)"""
    import time

    start_time = time.time()
    try:
        logger.info(f"Bulk upload started: {len(bulk_data.recipes)} recipes")

        # Log payload size for debugging
        total_ingredients = sum(len(recipe.ingredients) for recipe in bulk_data.recipes)
        logger.info(f"Total ingredients to validate: {total_ingredients}")

        validation_errors = []
        uploaded_recipes = []
        failed_recipe_indices = set()  # Track which recipes failed validation

        # Step 1: Validate all recipes before creating any using batch operations
        validation_start = time.time()
        logger.info("Starting validation phase with batch operations")

        # Collect all unique names for batch validation
        all_recipe_names = [recipe.name for recipe in bulk_data.recipes]
        all_ingredient_names = list(
            set(
                ingredient.ingredient_name
                for recipe in bulk_data.recipes
                for ingredient in recipe.ingredients
            )
        )
        all_unit_names = list(
            set(
                ingredient.unit_name
                for recipe in bulk_data.recipes
                for ingredient in recipe.ingredients
                if ingredient.unit_name is not None
            )
        )

        logger.info(
            f"Batch validation: {len(all_recipe_names)} recipes, {len(all_ingredient_names)} unique ingredients, {len(all_unit_names)} unique units"
        )

        # Batch validate recipe names
        batch_validation_start = time.time()
        duplicate_names = db.check_recipe_names_batch(all_recipe_names)

        # Defensive check: ensure duplicate_names is a dict
        if not isinstance(duplicate_names, dict):
            logger.error(f"check_recipe_names_batch returned {type(duplicate_names)} instead of dict: {duplicate_names}")
            raise DatabaseException(f"Internal error: batch recipe name validation returned invalid type {type(duplicate_names)}")

        # Batch validate ingredients
        valid_ingredients = db.search_ingredients_batch(all_ingredient_names)

        # Defensive check: ensure valid_ingredients is a dict
        if not isinstance(valid_ingredients, dict):
            logger.error(f"search_ingredients_batch returned {type(valid_ingredients)} instead of dict: {valid_ingredients}")
            raise DatabaseException(f"Internal error: batch ingredient validation returned invalid type {type(valid_ingredients)}")

        # Batch validate units
        valid_units = db.validate_units_batch(all_unit_names)

        # Defensive check: ensure valid_units is a dict
        if not isinstance(valid_units, dict):
            logger.error(f"validate_units_batch returned {type(valid_units)} instead of dict: {valid_units}")
            raise DatabaseException(f"Internal error: batch unit validation returned invalid type {type(valid_units)}")

        batch_validation_duration = time.time() - batch_validation_start
        logger.info(f"Batch validation completed in {batch_validation_duration:.3f}s")

        # Now validate each recipe using the batch results
        individual_validation_start = time.time()

        for idx, recipe_data in enumerate(bulk_data.recipes):
            try:
                recipe_validation_start = time.time()
                logger.info(f"Validating recipe {idx}: {recipe_data.name}")

                # Check if recipe name already exists (using batch results)
                if duplicate_names.get(recipe_data.name, False):
                    validation_errors.append(
                        BulkUploadValidationError(
                            recipe_index=idx,
                            recipe_name=recipe_data.name,
                            error_type="duplicate_name",
                            error_message=f"Recipe with name '{recipe_data.name}' already exists",
                        )
                    )
                    failed_recipe_indices.add(idx)
                    continue

                # Check if all ingredients exist by name (using batch results)
                for ingredient_idx, ingredient in enumerate(recipe_data.ingredients):
                    if ingredient.ingredient_name not in valid_ingredients:
                        validation_errors.append(
                            BulkUploadValidationError(
                                recipe_index=idx,
                                recipe_name=recipe_data.name,
                                error_type="ingredient_not_found",
                                error_message=f"No exact match found for ingredient '{ingredient.ingredient_name}'",
                            )
                        )
                        failed_recipe_indices.add(idx)
                # Check if units exist (using batch results)
                for ingredient in recipe_data.ingredients:
                    if ingredient.unit_name is not None:
                        if ingredient.unit_name not in valid_units:
                            validation_errors.append(
                                BulkUploadValidationError(
                                    recipe_index=idx,
                                    recipe_name=recipe_data.name,
                                    error_type="invalid_unit",
                                    error_message=f"Unit with name '{ingredient.unit_name}' does not exist",
                                )
                            )
                            failed_recipe_indices.add(idx)
                    elif ingredient.unit_id is not None:
                        # Legacy unit ID validation (still needs individual query)
                        unit_exists = db.execute_query(
                            "SELECT id FROM units WHERE id = ?",
                            (ingredient.unit_id,),
                        )
                        if not unit_exists:
                            validation_errors.append(
                                BulkUploadValidationError(
                                    recipe_index=idx,
                                    recipe_name=recipe_data.name,
                                    error_type="invalid_unit",
                                    error_message=f"Unit with ID {ingredient.unit_id} does not exist",
                                )
                            )
                            failed_recipe_indices.add(idx)
                            break

                # Check for duplicate ingredients in this recipe (by ingredient_name)
                ingredient_names = [ing.ingredient_name.lower().strip() for ing in recipe_data.ingredients]
                seen_names = set()
                duplicate_ingredient_names = []
                for name in ingredient_names:
                    if name in seen_names:
                        duplicate_ingredient_names.append(name)
                    else:
                        seen_names.add(name)

                if duplicate_ingredient_names:
                    unique_duplicates = list(set(duplicate_ingredient_names))
                    validation_errors.append(
                        BulkUploadValidationError(
                            recipe_index=idx,
                            recipe_name=recipe_data.name,
                            error_type="duplicate_ingredient",
                            error_message=f"Recipe has duplicate ingredients: {', '.join(unique_duplicates)}",
                        )
                    )
                    failed_recipe_indices.add(idx)
                    continue

                recipe_validation_duration = time.time() - recipe_validation_start
                logger.info(
                    f"Recipe {idx} validation took {recipe_validation_duration:.3f}s"
                )

            except Exception as e:
                # Log detailed error for debugging
                logger.error(
                    f"Validation error for recipe {idx} ('{recipe_data.name}'): {type(e).__name__}: {str(e)}",
                    exc_info=True
                )
                validation_errors.append(
                    BulkUploadValidationError(
                        recipe_index=idx,
                        recipe_name=recipe_data.name,
                        error_type="validation_error",
                        error_message=f"Validation error: {type(e).__name__}: {str(e)}",
                    )
                )
                failed_recipe_indices.add(idx)

        individual_validation_duration = time.time() - individual_validation_start
        logger.info(
            f"Individual validation completed in {individual_validation_duration:.3f}s"
        )

        validation_duration = time.time() - validation_start
        logger.info(f"Validation phase completed in {validation_duration:.3f}s")

        # Step 2: If there are validation errors, return them without creating any recipes
        if validation_errors:
            total_duration = time.time() - start_time
            logger.warning(
                f"Bulk upload validation failed with {len(validation_errors)} errors in {total_duration:.3f}s"
            )
            return BulkUploadResponse(
                uploaded_count=0,
                failed_count=len(failed_recipe_indices),
                validation_errors=validation_errors,
                uploaded_recipes=[],
            )

        # Step 3: Create all recipes (all validations passed) - using bulk transaction
        creation_start = time.time()
        logger.info("Starting recipe creation phase (bulk transaction)")

        # Prepare all recipes data for bulk creation
        recipes_to_create = []
        for idx, recipe_data in enumerate(bulk_data.recipes):
            # Skip recipes that failed validation
            if idx in failed_recipe_indices:
                continue

            # Convert ingredient names to IDs and unit names to IDs (using batch results)
            converted_ingredients = []
            for ingredient in recipe_data.ingredients:
                # Get the ingredient by exact name match from batch results
                ingredient_data = valid_ingredients.get(ingredient.ingredient_name)
                if ingredient_data:
                    ingredient_id = ingredient_data["id"]

                    # Handle unit conversion
                    unit_id = None
                    if ingredient.unit_name is not None:
                        # Convert unit name to ID using batch results
                        unit_data = valid_units.get(ingredient.unit_name)
                        if unit_data:
                            unit_id = unit_data["id"]
                        else:
                            # This shouldn't happen since we validated above, but just in case
                            raise ValueError(
                                f"Unit '{ingredient.unit_name}' not found during conversion"
                            )
                    elif ingredient.unit_id is not None:
                        # Use unit ID directly (backward compatibility)
                        unit_id = ingredient.unit_id

                    converted_ingredients.append(
                        {
                            "ingredient_id": ingredient_id,
                            "amount": ingredient.amount,
                            "unit_id": unit_id,
                        }
                    )
                else:
                    # This shouldn't happen since we validated above, but just in case
                    raise ValueError(
                        f"Ingredient '{ingredient.ingredient_name}' not found during conversion"
                    )

            # Prepare data for database
            recipe_dict = {
                "name": recipe_data.name,
                "instructions": recipe_data.instructions,
                "description": recipe_data.description,
                "source": recipe_data.source,
                "source_url": recipe_data.source_url,
                "ingredients": converted_ingredients,
            }
            recipes_to_create.append(recipe_dict)

        # Create all recipes in a single transaction
        try:
            created_recipes = db.bulk_create_recipes(recipes_to_create, user.user_id)

            # Convert to response format (no extra queries needed!)
            for created_recipe in created_recipes:
                uploaded_recipes.append(RecipeResponse(**created_recipe))

            logger.info(f"Successfully created {len(created_recipes)} recipes in bulk transaction")

        except Exception as e:
            logger.error(f"Error in bulk recipe creation: {str(e)}")
            # If bulk creation fails, log it as a general error
            validation_errors.append(
                BulkUploadValidationError(
                    recipe_index=0,
                    recipe_name="Bulk creation",
                    error_type="creation_error",
                    error_message=f"Bulk creation failed: {str(e)}",
                )
            )

        creation_duration = time.time() - creation_start
        total_duration = time.time() - start_time

        logger.info(
            f"Bulk upload completed: {len(uploaded_recipes)} uploaded, {len(validation_errors)} failed"
        )
        logger.info(f"Creation phase took {creation_duration:.3f}s")
        logger.info(f"Total bulk upload took {total_duration:.3f}s")

        # Trigger analytics refresh asynchronously if any recipes were uploaded
        if uploaded_recipes:
            trigger_analytics_refresh()

        return BulkUploadResponse(
            uploaded_count=len(uploaded_recipes),
            failed_count=len(failed_recipe_indices),
            validation_errors=validation_errors,
            uploaded_recipes=uploaded_recipes,
        )

    except Exception as e:
        total_duration = time.time() - start_time
        logger.error(f"Error in bulk upload after {total_duration:.3f}s: {str(e)}")
        raise DatabaseException("Failed to bulk upload recipes", detail=str(e))
