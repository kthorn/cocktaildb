"""Authenticated bar membership and shared inventory routes."""

from fastapi import APIRouter, Depends, HTTPException, Response
from dependencies.auth import UserInfo, require_authentication
from db.database import get_database
from db.db_core import Database
from models.requests import (
    GroupCreate,
    GroupUpdate,
    GroupJoin,
    GroupLeave,
    UserIngredientAdd,
    UserIngredientBulkAdd,
    UserIngredientBulkRemove,
)
from models.responses import (
    GroupDetailResponse,
    UserIngredientResponse,
    UserIngredientListResponse,
    UserIngredientBulkResponse,
    IngredientRecommendationListResponse,
    MessageResponse,
)
from core.exceptions import NotFoundException


def private_response(response: Response):
    response.headers["Cache-Control"] = "private, no-store"


router = APIRouter(
    prefix="/groups", tags=["groups"], dependencies=[Depends(private_response)]
)


@router.post("", response_model=GroupDetailResponse, status_code=201)
def create_group(
    data: GroupCreate,
    user: UserInfo = Depends(require_authentication),
    db: Database = Depends(get_database),
):
    return db.create_group(user.user_id, data.name, data.description)


@router.get("/mine", response_model=GroupDetailResponse)
def get_my_group(
    user: UserInfo = Depends(require_authentication),
    db: Database = Depends(get_database),
):
    return db.ensure_user_has_group(user.user_id)


@router.post("/join", response_model=GroupDetailResponse)
def join_group(
    data: GroupJoin,
    user: UserInfo = Depends(require_authentication),
    db: Database = Depends(get_database),
):
    return db.join_group_by_code(user.user_id, data.invite_code)


@router.put("/{group_id}", response_model=GroupDetailResponse)
def update_group(
    group_id: int,
    data: GroupUpdate,
    user: UserInfo = Depends(require_authentication),
    db: Database = Depends(get_database),
):
    return db.update_group(user.user_id, group_id, data.model_dump(exclude_unset=True))


@router.post("/{group_id}/leave", response_model=GroupDetailResponse)
def leave_group(
    group_id: int,
    data: GroupLeave,
    user: UserInfo = Depends(require_authentication),
    db: Database = Depends(get_database),
):
    return db.leave_group(user.user_id, group_id, data.copy_inventory)


@router.delete("/{group_id}/members/{user_id}", response_model=MessageResponse)
def remove_member(
    group_id: int,
    user_id: str,
    user: UserInfo = Depends(require_authentication),
    db: Database = Depends(get_database),
):
    db.remove_group_member(user.user_id, group_id, user_id)
    return {"message": "Member removed and inventory copied to their personal bar"}


@router.post("/{group_id}/invite-code/regenerate", response_model=GroupDetailResponse)
def regenerate_invite(
    group_id: int,
    user: UserInfo = Depends(require_authentication),
    db: Database = Depends(get_database),
):
    return db.regenerate_invite_code(user.user_id, group_id)


@router.get("/{group_id}/ingredients", response_model=UserIngredientListResponse)
def get_inventory(
    group_id: int,
    user: UserInfo = Depends(require_authentication),
    db: Database = Depends(get_database),
):
    rows = db.get_group_ingredients(user.user_id, group_id)
    return {"ingredients": rows, "total_count": len(rows)}


@router.post(
    "/{group_id}/ingredients", response_model=UserIngredientResponse, status_code=201
)
def add_inventory(
    group_id: int,
    data: UserIngredientAdd,
    user: UserInfo = Depends(require_authentication),
    db: Database = Depends(get_database),
):
    try:
        row = db.add_group_ingredient(user.user_id, group_id, data.ingredient_id)
    except ValueError as error:
        if "does not exist" in str(error):
            raise NotFoundException(str(error)) from error
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "ingredient_id": row["ingredient_id"],
        "name": row["ingredient_name"],
        "added_at": row["added_at"],
    }


@router.post(
    "/{group_id}/ingredients/bulk",
    response_model=UserIngredientBulkResponse,
    status_code=201,
)
def add_bulk(
    group_id: int,
    data: UserIngredientBulkAdd,
    user: UserInfo = Depends(require_authentication),
    db: Database = Depends(get_database),
):
    return db.add_group_ingredients_bulk(user.user_id, group_id, data.ingredient_ids)


# Static DELETE must precede the dynamic ingredient ID route.
@router.delete(
    "/{group_id}/ingredients/bulk", response_model=UserIngredientBulkResponse
)
def remove_bulk(
    group_id: int,
    data: UserIngredientBulkRemove,
    user: UserInfo = Depends(require_authentication),
    db: Database = Depends(get_database),
):
    try:
        return db.remove_group_ingredients_bulk(
            user.user_id, group_id, data.ingredient_ids
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.delete(
    "/{group_id}/ingredients/{ingredient_id}", response_model=MessageResponse
)
def remove_inventory(
    group_id: int,
    ingredient_id: int,
    user: UserInfo = Depends(require_authentication),
    db: Database = Depends(get_database),
):
    try:
        removed = db.remove_group_ingredient(user.user_id, group_id, ingredient_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not removed:
        raise NotFoundException("Ingredient not found in inventory")
    return {
        "message": f"Ingredient {ingredient_id} removed from group inventory successfully"
    }


@router.get(
    "/{group_id}/ingredients/recommendations",
    response_model=IngredientRecommendationListResponse,
)
def recommendations(
    group_id: int,
    limit: int = 20,
    user: UserInfo = Depends(require_authentication),
    db: Database = Depends(get_database),
):
    rows = db.get_group_ingredient_recommendations(user.user_id, group_id, limit)
    return {"recommendations": rows, "total_count": len(rows)}
