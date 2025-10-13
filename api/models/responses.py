from typing import List, Optional

from pydantic import BaseModel, Field


class IngredientResponse(BaseModel):
    """Response model for ingredient data"""

    id: int = Field(..., description="Ingredient ID")
    name: str = Field(..., description="Ingredient name")
    description: Optional[str] = Field(None, description="Ingredient description")
    parent_id: Optional[int] = Field(None, description="Parent ingredient ID")
    path: Optional[str] = Field(None, description="Ingredient hierarchy path")
    substitution_level: Optional[int] = Field(None, description="Substitution level: 0=no substitution, 1=parent-level, 2=grandparent-level, null=inherit")
    exact_match: Optional[bool] = Field(None, description="Whether this was an exact match for search queries")

    class Config:
        from_attributes = True


class UnitResponse(BaseModel):
    """Response model for unit data"""

    id: int = Field(..., description="Unit ID")
    name: str = Field(..., description="Unit name")
    abbreviation: Optional[str] = Field(None, description="Unit abbreviation")
    conversion_to_ml: Optional[float] = Field(
        None, description="Conversion factor to milliliters"
    )

    class Config:
        from_attributes = True


class RecipeIngredientResponse(BaseModel):
    """Response model for recipe ingredient data - matches actual database schema"""

    ingredient_id: int = Field(..., description="Ingredient ID")
    ingredient_name: str = Field(..., description="Ingredient name")
    ingredient_path: Optional[str] = Field(None, description="Ingredient hierarchy path")
    full_name: Optional[str] = Field(None, description="Full hierarchical ingredient name")
    hierarchy: Optional[List[str]] = Field(None, description="Ingredient hierarchy array from root to leaf (for tooltips)")
    amount: Optional[float] = Field(None, description="Ingredient amount")
    unit_id: Optional[int] = Field(None, description="Unit ID")
    unit_name: Optional[str] = Field(None, description="Unit name")
    unit_abbreviation: Optional[str] = Field(None, description="Unit abbreviation")

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


class RecipeResponse(BaseModel):
    """Response model for recipe data - matches actual database schema"""

    id: int = Field(..., description="Recipe ID")
    name: str = Field(..., description="Recipe name")
    instructions: Optional[str] = Field(None, description="Recipe instructions")
    description: Optional[str] = Field(None, description="Recipe description")
    image_url: Optional[str] = Field(None, description="Recipe image URL")
    source: Optional[str] = Field(None, description="Recipe source")
    source_url: Optional[str] = Field(None, description="Recipe source URL")
    avg_rating: Optional[float] = Field(None, description="Average rating")
    rating_count: Optional[int] = Field(None, description="Number of ratings")
    user_rating: Optional[int] = Field(None, description="Current user's rating for this recipe (1-5, null if not rated)")
    ingredients: List[RecipeIngredientResponse] = Field(
        default=[], description="Recipe ingredients"
    )
    tags: List[TagResponse] = Field(default=[], description="Unified tags with type field")
    # Legacy fields for backward compatibility (can be removed when frontend is updated)
    public_tags: List[PublicTagResponse] = Field(default=[], description="Public tags (deprecated)")
    private_tags: List[PrivateTagResponse] = Field(
        default=[], description="Private tags (deprecated)"
    )

    class Config:
        from_attributes = True


class RecipeListResponse(BaseModel):
    """Response model for recipe list data"""

    id: int = Field(..., description="Recipe ID")
    name: str = Field(..., description="Recipe name")
    description: Optional[str] = Field(None, description="Recipe description")
    avg_rating: Optional[float] = Field(None, description="Average rating")
    rating_count: Optional[int] = Field(None, description="Number of ratings")
    ingredient_count: Optional[int] = Field(None, description="Number of ingredients")

    class Config:
        from_attributes = True


class RatingResponse(BaseModel):
    """Response model for rating data - matches actual database schema"""

    recipe_id: int = Field(..., description="Recipe ID")
    user_id: str = Field(..., description="User ID")
    rating: int = Field(..., description="Rating value (1-5)")
    comment: Optional[str] = Field(None, description="Optional comment")
    # Note: created_at field removed as it doesn't exist in current database schema

    class Config:
        from_attributes = True


class RatingSummaryResponse(BaseModel):
    """Response model for rating summary data"""

    recipe_id: int = Field(..., description="Recipe ID")
    avg_rating: Optional[float] = Field(None, description="Average rating")
    rating_count: int = Field(..., description="Number of ratings")
    user_rating: Optional[RatingResponse] = Field(
        None, description="Current user's rating (if authenticated)"
    )

    class Config:
        from_attributes = True


class UserInfoResponse(BaseModel):
    """Response model for user information"""

    user_id: str = Field(..., description="User ID")
    username: Optional[str] = Field(None, description="Username")
    email: Optional[str] = Field(None, description="Email address")
    groups: List[str] = Field(default=[], description="User groups")

    class Config:
        from_attributes = True


class SearchResultsResponse(BaseModel):
    """Response model for search results"""

    recipes: List[RecipeListResponse] = Field(..., description="Recipe results")
    total_count: int = Field(..., description="Total number of matching recipes")
    offset: int = Field(..., description="Current offset")
    limit: int = Field(..., description="Current limit")

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
    detail: Optional[str] = Field(None, description="Additional error details")

    class Config:
        from_attributes = True


class PaginationMetadata(BaseModel):
    """Response model for pagination metadata"""

    page: int = Field(..., description="Current page number (1-based)", ge=1)
    limit: int = Field(..., description="Number of items per page", ge=1, le=1000)
    total_count: int = Field(..., description="Total number of items", ge=0)
    has_next: bool = Field(..., description="Whether there is a next page")
    has_previous: bool = Field(..., description="Whether there is a previous page")

    class Config:
        from_attributes = True


class PaginatedRecipeResponse(BaseModel):
    """Response model for paginated recipe data"""

    recipes: List[RecipeResponse] = Field(..., description="List of recipes with full details")
    pagination: PaginationMetadata = Field(..., description="Pagination metadata")

    class Config:
        from_attributes = True


class PaginatedRecipeListResponse(BaseModel):
    """Response model for paginated recipe list data (lighter version)"""

    recipes: List[RecipeListResponse] = Field(..., description="List of recipe summaries")
    pagination: PaginationMetadata = Field(..., description="Pagination metadata")

    class Config:
        from_attributes = True


class PaginatedSearchResponse(BaseModel):
    """Response model for paginated search results"""

    recipes: List[RecipeResponse] = Field(..., description="List of matching recipes with full details")
    pagination: PaginationMetadata = Field(..., description="Pagination metadata")
    query: Optional[str] = Field(None, description="Search query used")

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

    ingredient_index: int = Field(..., description="Index of the ingredient with the error")
    ingredient_name: str = Field(..., description="Name of the ingredient with the error")
    error_type: str = Field(..., description="Type of validation error")
    error_message: str = Field(..., description="Detailed error message")

    class Config:
        from_attributes = True


class BulkUploadResponse(BaseModel):
    """Response model for bulk recipe upload results"""

    uploaded_count: int = Field(..., description="Number of recipes successfully uploaded")
    failed_count: int = Field(..., description="Number of recipes that failed validation")
    validation_errors: List[BulkUploadValidationError] = Field(
        default=[], description="List of validation errors"
    )
    uploaded_recipes: List[RecipeResponse] = Field(
        default=[], description="List of successfully uploaded recipes"
    )

    class Config:
        from_attributes = True


class BulkIngredientUploadResponse(BaseModel):
    """Response model for bulk ingredient upload results"""

    uploaded_count: int = Field(..., description="Number of ingredients successfully uploaded")
    failed_count: int = Field(..., description="Number of ingredients that failed validation")
    validation_errors: List[BulkIngredientUploadValidationError] = Field(
        default=[], description="List of validation errors"
    )
    uploaded_ingredients: List[IngredientResponse] = Field(
        default=[], description="List of successfully uploaded ingredients"
    )

    class Config:
        from_attributes = True


class UserIngredientResponse(BaseModel):
    """Response model for user ingredient data"""

    ingredient_id: int = Field(..., description="Ingredient ID")
    name: str = Field(..., description="Ingredient name")
    description: Optional[str] = Field(None, description="Ingredient description")
    parent_id: Optional[int] = Field(None, description="Parent ingredient ID")
    path: Optional[str] = Field(None, description="Ingredient hierarchy path")
    added_at: str = Field(..., description="When ingredient was added to user's inventory")

    class Config:
        from_attributes = True


class UserIngredientListResponse(BaseModel):
    """Response model for list of user ingredients"""

    ingredients: List[UserIngredientResponse] = Field(
        default=[], description="List of user's ingredients"
    )
    total_count: int = Field(..., description="Total number of ingredients in user's inventory")

    class Config:
        from_attributes = True


class UserIngredientBulkResponse(BaseModel):
    """Response model for bulk user ingredient operations"""

    added_count: Optional[int] = Field(None, description="Number of ingredients added")
    already_exists_count: Optional[int] = Field(None, description="Number of ingredients already in inventory")
    removed_count: Optional[int] = Field(None, description="Number of ingredients removed")
    not_found_count: Optional[int] = Field(None, description="Number of ingredients not found in inventory")
    failed_count: Optional[int] = Field(None, description="Number of ingredients that failed to process")
    errors: List[str] = Field(default=[], description="List of error messages")

    class Config:
        from_attributes = True


class IngredientRecommendationResponse(BaseModel):
    """Response model for ingredient recommendation data"""

    id: int = Field(..., description="Ingredient ID")
    name: str = Field(..., description="Ingredient name")
    description: Optional[str] = Field(None, description="Ingredient description")
    parent_id: Optional[int] = Field(None, description="Parent ingredient ID")
    path: Optional[str] = Field(None, description="Ingredient hierarchy path")
    substitution_level: Optional[int] = Field(None, description="Substitution level")
    recipes_unlocked: int = Field(..., description="Number of recipes that would be unlocked")
    recipe_names: List[str] = Field(default=[], description="Names of recipes that would be unlocked")

    class Config:
        from_attributes = True


class IngredientRecommendationListResponse(BaseModel):
    """Response model for list of ingredient recommendations"""

    recommendations: List[IngredientRecommendationResponse] = Field(
        default=[], description="List of recommended ingredients"
    )
    total_count: int = Field(..., description="Total number of recommendations")

    class Config:
        from_attributes = True
