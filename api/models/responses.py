from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class IngredientResponse(BaseModel):
    """Response model for ingredient data"""

    id: int = Field(..., description="Ingredient ID")
    name: str = Field(..., description="Ingredient name")
    description: str | None = Field(None, description="Ingredient description")
    parent_id: int | None = Field(None, description="Parent ingredient ID")
    path: str | None = Field(None, description="Ingredient hierarchy path")
    allow_substitution: bool = Field(
        ...,
        description="Whether this ingredient can be substituted with siblings/ancestors",
    )
    percent_abv: float | None = Field(None, description="Alcohol by volume percentage")
    sugar_g_per_l: float | None = Field(None, description="Sugar grams per liter")
    titratable_acidity_g_per_l: float | None = Field(
        None, description="Titratable acidity grams per liter"
    )
    url: str | None = Field(None, description="Reference URL")
    exact_match: bool | None = Field(
        None, description="Whether this was an exact match for search queries"
    )
    created_by: str | None = Field(
        None, description="User ID who created this ingredient"
    )

    class Config:
        from_attributes = True


class UnitResponse(BaseModel):
    """Response model for unit data"""

    id: int = Field(..., description="Unit ID")
    name: str = Field(..., description="Unit name")
    abbreviation: str | None = Field(None, description="Unit abbreviation")
    conversion_to_ml: float | None = Field(
        None, description="Conversion factor to milliliters"
    )

    class Config:
        from_attributes = True


class RecipeIngredientResponse(BaseModel):
    """Response model for recipe ingredient data - matches actual database schema"""

    ingredient_id: int = Field(..., description="Ingredient ID")
    ingredient_name: str = Field(..., description="Ingredient name")
    ingredient_path: str | None = Field(None, description="Ingredient hierarchy path")
    full_name: str | None = Field(None, description="Full hierarchical ingredient name")
    hierarchy: list[str] | None = Field(
        None, description="Ingredient hierarchy array from root to leaf (for tooltips)"
    )
    amount: float | None = Field(None, description="Ingredient amount")
    unit_id: int | None = Field(None, description="Unit ID")
    unit_name: str | None = Field(None, description="Unit name")
    unit_abbreviation: str | None = Field(None, description="Unit abbreviation")

    class Config:
        from_attributes = True


class PublicTagResponse(BaseModel):
    """Response model for public tag data"""

    id: int = Field(..., description="Tag ID")
    name: str = Field(..., description="Tag name")
    usage_count: int = Field(default=0, description="Number of recipes using this tag")

    class Config:
        from_attributes = True


class PrivateTagResponse(BaseModel):
    """Response model for private tag data"""

    id: int = Field(..., description="Tag ID")
    name: str = Field(..., description="Tag name")
    cognito_user_id: str = Field(..., description="User ID who created the tag")

    class Config:
        from_attributes = True


class TagResponse(BaseModel):
    """Response model for unified tag data with type field"""

    id: int = Field(..., description="Tag ID")
    name: str = Field(..., description="Tag name")
    type: str = Field(..., description="Tag type: 'public' or 'private'")

    class Config:
        from_attributes = True


class RecipeABVResponse(BaseModel):
    """Ingredient-only recipe ABV estimate and explanatory metadata."""

    status: Literal["calculated", "estimated", "unknown"]
    min_percent: float | None = None
    max_percent: float | None = None
    display: str
    notes: list[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


class RecipeResponse(BaseModel):
    """Response model for recipe data - matches actual database schema"""

    id: int = Field(..., description="Recipe ID")
    name: str = Field(..., description="Recipe name")
    instructions: str | None = Field(None, description="Recipe instructions")
    description: str | None = Field(None, description="Recipe description")
    image_url: str | None = Field(None, description="Recipe image URL")
    source: str | None = Field(None, description="Recipe source")
    source_url: str | None = Field(None, description="Recipe source URL")
    avg_rating: float | None = Field(None, description="Average rating")
    rating_count: int | None = Field(None, description="Number of ratings")
    user_rating: int | None = Field(
        None,
        description="Current user's rating for this recipe (1-5, null if not rated)",
    )
    created_by: str | None = Field(None, description="User ID who created this recipe")
    abv: RecipeABVResponse | None = Field(
        None, description="Ingredient-only ABV estimate before dilution"
    )
    ingredients: list[RecipeIngredientResponse] = Field(
        default=[], description="Recipe ingredients"
    )
    tags: list[TagResponse] = Field(
        default=[], description="Unified tags with type field"
    )
    # Legacy fields for backward compatibility (can be removed when frontend is updated)
    public_tags: list[PublicTagResponse] = Field(
        default=[], description="Public tags (deprecated)"
    )
    private_tags: list[PrivateTagResponse] = Field(
        default=[], description="Private tags (deprecated)"
    )

    class Config:
        from_attributes = True


class RatingResponse(BaseModel):
    """Response model for rating data - matches actual database schema"""

    recipe_id: int = Field(..., description="Recipe ID")
    user_id: str = Field(..., description="User ID")
    rating: int = Field(..., description="Rating value (1-5)")
    comment: str | None = Field(None, description="Optional comment")
    # Note: created_at field removed as it doesn't exist in current database schema

    class Config:
        from_attributes = True


class RatingSummaryResponse(BaseModel):
    """Response model for rating summary data"""

    recipe_id: int = Field(..., description="Recipe ID")
    avg_rating: float | None = Field(None, description="Average rating")
    rating_count: int = Field(..., description="Number of ratings")
    user_rating: RatingResponse | None = Field(
        None, description="Current user's rating (if authenticated)"
    )

    class Config:
        from_attributes = True


class UserInfoResponse(BaseModel):
    """Response model for user information"""

    user_id: str = Field(..., description="User ID")
    username: str | None = Field(None, description="Username")
    email: str | None = Field(None, description="Email address")
    groups: list[str] = Field(default=[], description="User groups")

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    """Generic response model for simple messages"""

    message: str = Field(..., description="Response message")

    class Config:
        from_attributes = True


class ErrorResponse(BaseModel):
    """Response model for error messages"""

    error: str = Field(..., description="Error message")
    detail: str | list[str] | None = Field(None, description="Additional error details")

    class Config:
        from_attributes = True


class PaginationMetadata(BaseModel):
    """Response model for pagination metadata"""

    page: int = Field(..., description="Current page number (1-based)", ge=1)
    limit: int = Field(..., description="Number of items per page", ge=1, le=1000)
    total_count: int = Field(..., description="Total number of items", ge=0)
    has_next: bool = Field(..., description="Whether there is a next page")
    has_previous: bool = Field(..., description="Whether there is a previous page")
    next_cursor: str | None = Field(
        None, description="Opaque cursor for the next page (cursor-based pagination)"
    )

    class Config:
        from_attributes = True


class PaginatedSearchResponse(BaseModel):
    """Response model for paginated search results"""

    recipes: list[RecipeResponse] = Field(
        ..., description="List of matching recipes with full details"
    )
    pagination: PaginationMetadata = Field(..., description="Pagination metadata")
    query: str | None = Field(None, description="Search query used")

    class Config:
        from_attributes = True


class BulkUploadValidationError(BaseModel):
    """Response model for bulk upload validation errors"""

    recipe_index: int = Field(..., description="Index of the recipe with the error")
    recipe_name: str = Field(..., description="Name of the recipe with the error")
    error_type: str = Field(..., description="Type of validation error")
    error_message: str = Field(..., description="Detailed error message")

    class Config:
        from_attributes = True


class BulkIngredientUploadValidationError(BaseModel):
    """Response model for bulk ingredient upload validation errors"""

    ingredient_index: int = Field(
        ..., description="Index of the ingredient with the error"
    )
    ingredient_name: str = Field(
        ..., description="Name of the ingredient with the error"
    )
    error_type: str = Field(..., description="Type of validation error")
    error_message: str = Field(..., description="Detailed error message")

    class Config:
        from_attributes = True


class BulkUploadResponse(BaseModel):
    """Response model for bulk recipe upload results"""

    uploaded_count: int = Field(
        ..., description="Number of recipes successfully uploaded"
    )
    failed_count: int = Field(
        ..., description="Number of recipes that failed validation"
    )
    validation_errors: list[BulkUploadValidationError] = Field(
        default=[], description="List of validation errors"
    )
    uploaded_recipes: list[RecipeResponse] = Field(
        default=[], description="List of successfully uploaded recipes"
    )

    class Config:
        from_attributes = True


class BulkIngredientUploadResponse(BaseModel):
    """Response model for bulk ingredient upload results"""

    uploaded_count: int = Field(
        ..., description="Number of ingredients successfully uploaded"
    )
    failed_count: int = Field(
        ..., description="Number of ingredients that failed validation"
    )
    validation_errors: list[BulkIngredientUploadValidationError] = Field(
        default=[], description="List of validation errors"
    )
    uploaded_ingredients: list[IngredientResponse] = Field(
        default=[], description="List of successfully uploaded ingredients"
    )

    class Config:
        from_attributes = True


class UserIngredientResponse(BaseModel):
    """Response model for user ingredient data"""

    ingredient_id: int = Field(..., description="Ingredient ID")
    name: str = Field(..., description="Ingredient name")
    description: str | None = Field(None, description="Ingredient description")
    parent_id: int | None = Field(None, description="Parent ingredient ID")
    path: str | None = Field(None, description="Ingredient hierarchy path")
    added_at: datetime = Field(
        ..., description="When ingredient was added to user's inventory"
    )

    class Config:
        from_attributes = True


class UserIngredientListResponse(BaseModel):
    """Response model for list of user ingredients"""

    ingredients: list[UserIngredientResponse] = Field(
        default=[], description="List of user's ingredients"
    )
    total_count: int = Field(
        ..., description="Total number of ingredients in user's inventory"
    )

    class Config:
        from_attributes = True


class UserIngredientBulkResponse(BaseModel):
    """Response model for bulk user ingredient operations"""

    added_count: int | None = Field(None, description="Number of ingredients added")
    already_exists_count: int | None = Field(
        None, description="Number of ingredients already in inventory"
    )
    removed_count: int | None = Field(None, description="Number of ingredients removed")
    not_found_count: int | None = Field(
        None, description="Number of ingredients not found in inventory"
    )
    failed_count: int | None = Field(
        None, description="Number of ingredients that failed to process"
    )
    errors: list[str] = Field(default=[], description="List of error messages")

    class Config:
        from_attributes = True


class IngredientRecommendationResponse(BaseModel):
    """Response model for ingredient recommendation data"""

    id: int = Field(..., description="Ingredient ID")
    name: str = Field(..., description="Ingredient name")
    description: str | None = Field(None, description="Ingredient description")
    parent_id: int | None = Field(None, description="Parent ingredient ID")
    path: str | None = Field(None, description="Ingredient hierarchy path")
    allow_substitution: bool = Field(
        ...,
        description="Whether this ingredient can be substituted with siblings/ancestors",
    )
    recipes_unlocked: int = Field(
        ..., description="Number of recipes that would be unlocked"
    )
    recipe_names: list[str] = Field(
        default=[], description="Names of recipes that would be unlocked"
    )

    class Config:
        from_attributes = True


class IngredientRecommendationListResponse(BaseModel):
    """Response model for list of ingredient recommendations"""

    recommendations: list[IngredientRecommendationResponse] = Field(
        default=[], description="List of recommended ingredients"
    )
    total_count: int = Field(..., description="Total number of recommendations")

    class Config:
        from_attributes = True


class GroupMemberResponse(BaseModel):
    cognito_user_id: str
    joined_at: datetime


class GroupDetailResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    invite_code: str
    created_at: datetime
    updated_at: datetime
    members: list[GroupMemberResponse] = Field(default_factory=list)
    member_count: int
