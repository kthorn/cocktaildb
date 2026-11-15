"""Ingredients endpoints for the CocktailDB API"""

import logging
import time

from bulk_ingredient_values import BULK_VALUE_LIMITS, parse_bulk_ingredient_values
from core.exceptions import (
    ConflictException,
    NotFoundException,
    ValidationException,
)
from db.database import get_database as get_db
from db.db_bulk_values import bulk_update_ingredient_values
from db.db_core import Database
from dependencies.auth import (
    UserInfo,
    get_current_user_optional,
    require_editor_access,
)
from fastapi import APIRouter, Body, Depends, status
from models.requests import BulkIngredientUpload, IngredientCreate, IngredientUpdate
from models.responses import (
    BulkIngredientUploadResponse,
    BulkIngredientUploadValidationError,
    IngredientResponse,
    MessageResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingredients", tags=["ingredients"])


@router.get("", response_model=list[IngredientResponse])
async def get_ingredients(
    db: Database = Depends(get_db),
    user: UserInfo | None = Depends(get_current_user_optional),
):
    """Get all ingredients"""
    logger.info("Getting all ingredients")
    ingredients = db.get_ingredients()
    return [IngredientResponse(**ingredient) for ingredient in ingredients]


@router.get("/search", response_model=list[IngredientResponse])
async def search_ingredients(
    q: str,
    db: Database = Depends(get_db),
    user: UserInfo | None = Depends(get_current_user_optional),
):
    """Search ingredients by name"""
    logger.info(f"Searching ingredients with query: {q}")
    ingredients = db.search_ingredients(q)
    return [IngredientResponse(**ingredient) for ingredient in ingredients]


@router.post("", response_model=IngredientResponse, status_code=status.HTTP_201_CREATED)
async def create_ingredient(
    ingredient_data: IngredientCreate,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_editor_access),
):
    """Create a new ingredient (requires editor access)"""
    logger.info(f"Creating ingredient: {ingredient_data.name}")

    # Prepare data for database
    ingredient_dict = ingredient_data.model_dump()
    ingredient_dict["created_by"] = user.user_id

    created_ingredient = db.create_ingredient(ingredient_dict)

    return IngredientResponse(**created_ingredient)


@router.get("/{ingredient_id}", response_model=IngredientResponse)
async def get_ingredient(
    ingredient_id: int,
    db: Database = Depends(get_db),
    user: UserInfo | None = Depends(get_current_user_optional),
):
    """Get a specific ingredient by ID"""
    logger.info(f"Getting ingredient {ingredient_id}")
    ingredient = db.get_ingredient(ingredient_id)

    if not ingredient:
        raise NotFoundException(f"Ingredient with ID {ingredient_id} not found")

    return IngredientResponse(**ingredient)


@router.put("/{ingredient_id}", response_model=IngredientResponse)
async def update_ingredient(
    ingredient_id: int,
    ingredient_data: IngredientUpdate,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_editor_access),
):
    """Update an ingredient (requires editor access)"""
    logger.info(f"Updating ingredient {ingredient_id}")

    # Check if ingredient exists
    existing_ingredient = db.get_ingredient(ingredient_id)
    if not existing_ingredient:
        raise NotFoundException(f"Ingredient with ID {ingredient_id} not found")

    update_dict = {
        k: v for k, v in ingredient_data.model_dump().items() if v is not None
    }
    # The form sends url: null to clear it, so pass an explicit null through.
    if "url" in ingredient_data.model_fields_set:
        update_dict["url"] = ingredient_data.url

    value_updates = {
        field: update_dict.pop(field)
        for field in BULK_VALUE_LIMITS
        if field in update_dict
    }
    if update_dict:
        db.update_ingredient(ingredient_id, update_dict)
    if value_updates:
        bulk_update_ingredient_values(
            db, {ingredient_id: value_updates}, overwrite=True
        )

    updated_ingredient = db.get_ingredient(ingredient_id)
    if updated_ingredient is None:
        raise NotFoundException(f"Ingredient with ID {ingredient_id} not found")
    return IngredientResponse(**updated_ingredient)


@router.post("/bulk-values")
async def upload_ingredient_values(
    csv_text: str = Body(..., media_type="text/csv"),
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_editor_access),
):
    """Populate blank ingredient measurement fields from CSV."""
    try:
        rows = parse_bulk_ingredient_values(csv_text)
    except ValueError as error:
        raise ValidationException(
            "Invalid ingredient value CSV", detail=str(error)
        ) from error

    ingredients = {}
    updates = {}
    expected_values = {}
    validation_errors = []
    conflicts = []
    unchanged_count = 0

    for row in rows:
        ingredient_id = row["ingredient_id"]
        if ingredient_id not in ingredients:
            ingredients[ingredient_id] = db.get_ingredient(ingredient_id)
        ingredient = ingredients[ingredient_id]
        if ingredient is None:
            validation_errors.append(f"Ingredient {ingredient_id} does not exist")
            continue
        if ingredient["name"] != row["ingredient_name"]:
            validation_errors.append(
                f"Ingredient {ingredient_id} name '{row['ingredient_name']}' "
                f"does not match '{ingredient['name']}'"
            )
            continue

        field = row["field"]
        value = row["value"]
        ingredient_updates = updates.setdefault(ingredient_id, {})
        if field in ingredient_updates:
            if ingredient_updates[field] != value:
                conflicts.append(
                    f"{ingredient['name']} ({ingredient_id}): {field} has conflicting "
                    f"CSV values {ingredient_updates[field]} and {value}"
                )
            else:
                unchanged_count += 1
            continue

        existing_value = ingredient.get(field)
        expected_values.setdefault(ingredient_id, {})[field] = existing_value
        if existing_value is None:
            ingredient_updates[field] = value
        elif existing_value == value:
            unchanged_count += 1
        else:
            conflicts.append(
                f"{ingredient['name']} ({ingredient_id}): {field} is {existing_value}, "
                f"CSV requested {value}"
            )

    if validation_errors:
        raise ValidationException(
            "Invalid ingredient value CSV", detail="; ".join(validation_errors)
        )
    if conflicts:
        raise ConflictException(
            "Ingredient values conflict with curated data", detail=conflicts
        )

    updates = {
        ingredient_id: fields for ingredient_id, fields in updates.items() if fields
    }
    if expected_values:
        try:
            bulk_update_ingredient_values(
                db,
                updates,
                expected_names={
                    ingredient_id: ingredients[ingredient_id]["name"]
                    for ingredient_id in expected_values
                },
                expected_values=expected_values,
            )
        except ValueError as error:
            raise ConflictException(
                "Ingredient values changed during upload", detail=str(error)
            ) from error
    return {
        "updated_count": sum(len(fields) for fields in updates.values()),
        "unchanged_count": unchanged_count,
        "errors": [],
    }


@router.delete("/{ingredient_id}", response_model=MessageResponse)
async def delete_ingredient(
    ingredient_id: int,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_editor_access),
):
    """Delete an ingredient (requires editor access)"""
    logger.info(f"Deleting ingredient {ingredient_id}")

    # Check if ingredient exists
    existing_ingredient = db.get_ingredient(ingredient_id)
    if not existing_ingredient:
        raise NotFoundException(f"Ingredient with ID {ingredient_id} not found")

    db.delete_ingredient(ingredient_id)

    return MessageResponse(message=f"Ingredient {ingredient_id} deleted successfully")


# Maximum number of levels in the ingredient hierarchy, counting the
# top-level ingredient as level 1. The deepest chain today is about 4.
MAX_INGREDIENT_DEPTH = 10


def _path_depth(path: str | None) -> int:
    """Number of levels in a materialized path such as '/1/5/12/'."""
    return len([segment for segment in (path or "").split("/") if segment])


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
    """Bulk upload ingredients (requires editor access).

    A parent may be an existing ingredient or another row in the same upload.
    Every row is validated before anything is created.
    """
    start_time = time.time()
    ingredients = bulk_data.ingredients
    logger.info(f"Bulk ingredient upload started: {len(ingredients)} ingredients")

    errors: dict[int, BulkIngredientUploadValidationError] = {}

    def fail(idx: int, error_type: str, message: str) -> None:
        errors[idx] = BulkIngredientUploadValidationError(
            ingredient_index=idx,
            ingredient_name=ingredients[idx].name,
            error_type=error_type,
            error_message=message,
        )

    # Step 1: look up existing names and parents in two batch queries.
    existing_names = db.check_ingredient_names_batch([i.name for i in ingredients])
    parent_names = list(
        {i.parent_name for i in ingredients if i.parent_name is not None}
    )
    found_parents = db.search_ingredients_batch(parent_names) if parent_names else {}
    # Names are compared with lower(), as the CITEXT name column does.
    db_parents_by_key = {name.lower(): row for name, row in found_parents.items()}
    first_index_by_key: dict[str, int] = {}
    for idx, ingredient in enumerate(ingredients):
        first_index_by_key.setdefault(ingredient.name.lower(), idx)

    # Step 2: resolve each row's parent once. A row's parent is either another
    # row in this upload (batch_parent) or an existing ingredient (db_parent_id,
    # whose depth is parent_depth).
    batch_parent: list[int | None] = [None] * len(ingredients)
    db_parent_id: list[int | None] = [None] * len(ingredients)
    parent_depth: list[int] = [0] * len(ingredients)

    for idx, ingredient in enumerate(ingredients):
        if existing_names.get(ingredient.name, False):
            fail(
                idx,
                "duplicate_name",
                f"Ingredient with name '{ingredient.name}' already exists",
            )
            continue
        first_idx = first_index_by_key[ingredient.name.lower()]
        if first_idx != idx:
            fail(
                idx,
                "duplicate_name",
                f"Ingredient name '{ingredient.name}' appears more than once in "
                f"this upload (also ingredient {first_idx + 1})",
            )
            continue

        if ingredient.parent_name is not None:
            parent_key = ingredient.parent_name.lower()
            db_parent = db_parents_by_key.get(parent_key)
            if db_parent is not None:
                db_parent_id[idx] = db_parent["id"]
                parent_depth[idx] = _path_depth(db_parent["path"])
            elif parent_key in first_index_by_key:
                batch_parent[idx] = first_index_by_key[parent_key]
            else:
                fail(
                    idx,
                    "parent_not_found",
                    f"No exact match found for parent ingredient '{ingredient.parent_name}'",
                )
        elif ingredient.parent_id is not None:
            # Legacy parent ID (still needs an individual query)
            parent_rows = db.execute_query(
                "SELECT path FROM ingredients WHERE id = %s",
                (ingredient.parent_id,),
            )
            if parent_rows:
                db_parent_id[idx] = ingredient.parent_id
                parent_depth[idx] = _path_depth(parent_rows[0]["path"])
            else:
                fail(
                    idx,
                    "invalid_parent",
                    f"Parent ingredient with ID {ingredient.parent_id} does not exist",
                )

    # Step 3: work out each row's depth, following same-upload parents
    # iteratively. None means the row can't be created. This also catches
    # cycles (including a row that is its own parent), rows below an invalid
    # row, and rows that would exceed MAX_INGREDIENT_DEPTH.
    depth: dict[int, int | None] = dict.fromkeys(errors)
    for start in range(len(ingredients)):
        chain: list[int] = []
        on_chain: set[int] = set()
        idx: int | None = start
        while idx is not None and idx not in depth and idx not in on_chain:
            chain.append(idx)
            on_chain.add(idx)
            idx = batch_parent[idx]

        if idx is not None and idx in on_chain:
            cycle_start = chain.index(idx)
            for member in chain[cycle_start:]:
                fail(
                    member, "invalid_parent", "Circular parent reference in this upload"
                )
                depth[member] = None
            del chain[cycle_start:]

        # Resolve from the top of the chain down, so each parent is done first.
        for member in reversed(chain):
            parent = batch_parent[member]
            if parent is None:
                member_depth = parent_depth[member] + 1
            else:
                resolved_parent_depth = depth[parent]
                if resolved_parent_depth is None:
                    fail(
                        member,
                        "invalid_parent",
                        f"Parent ingredient '{ingredients[member].parent_name}' "
                        "in this upload has an error",
                    )
                    depth[member] = None
                    continue
                member_depth = resolved_parent_depth + 1
            if member_depth > MAX_INGREDIENT_DEPTH:
                fail(
                    member,
                    "depth_exceeded",
                    f"Ingredient would be at hierarchy level {member_depth}; "
                    f"the maximum is {MAX_INGREDIENT_DEPTH}",
                )
                depth[member] = None
            else:
                depth[member] = member_depth

    if errors:
        logger.warning(
            f"Bulk ingredient upload validation failed with {len(errors)} errors "
            f"in {time.time() - start_time:.3f}s"
        )
        return BulkIngredientUploadResponse(
            uploaded_count=0,
            failed_count=len(errors),
            validation_errors=[errors[idx] for idx in sorted(errors)],
            uploaded_ingredients=[],
        )

    # Step 4: create rows shallowest first, so every same-upload parent is
    # created before its children.
    created: dict[int, dict] = {}
    for idx in sorted(range(len(ingredients)), key=lambda i: (depth[i], i)):
        ingredient = ingredients[idx]
        parent = batch_parent[idx]
        if parent is not None and parent not in created:
            fail(
                idx,
                "creation_error",
                f"Not created because parent ingredient '{ingredient.parent_name}' "
                "failed to create",
            )
            continue
        parent_id = created[parent]["id"] if parent is not None else db_parent_id[idx]
        try:
            created[idx] = db.create_ingredient(
                {
                    "name": ingredient.name,
                    "description": ingredient.description,
                    "parent_id": parent_id,
                    "allow_substitution": ingredient.allow_substitution,
                    "created_by": user.user_id,
                }
            )
        except Exception as e:
            logger.error(f"Error creating ingredient {idx} ('{ingredient.name}'): {e}")
            fail(idx, "creation_error", f"Failed to create ingredient: {e}")

    logger.info(
        f"Bulk ingredient upload completed: {len(created)} uploaded, "
        f"{len(errors)} failed in {time.time() - start_time:.3f}s"
    )
    return BulkIngredientUploadResponse(
        uploaded_count=len(created),
        failed_count=len(errors),
        validation_errors=[errors[idx] for idx in sorted(errors)],
        uploaded_ingredients=[
            IngredientResponse(**created[idx]) for idx in sorted(created)
        ],
    )
