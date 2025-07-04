from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class IngredientCreate(BaseModel):
    """Request model for creating an ingredient"""
    name: str = Field(..., description="Ingredient name")
    description: Optional[str] = Field(None, description="Ingredient description")
    parent_id: Optional[int] = Field(None, description="Parent ingredient ID for hierarchy")


class IngredientUpdate(BaseModel):
    """Request model for updating an ingredient"""
    name: Optional[str] = Field(None, description="Ingredient name")
    description: Optional[str] = Field(None, description="Ingredient description")
    parent_id: Optional[int] = Field(None, description="Parent ingredient ID for hierarchy")


class RecipeIngredient(BaseModel):
    """Recipe ingredient specification"""
    ingredient_id: int = Field(..., description="Ingredient ID")
    amount: Optional[float] = Field(None, description="Quantity amount")
    unit_id: Optional[int] = Field(None, description="Unit ID")
    notes: Optional[str] = Field(None, description="Additional notes")


class RecipeCreate(BaseModel):
    """Request model for creating a recipe"""
    name: str = Field(..., description="Recipe name")
    instructions: Optional[str] = Field(None, description="Recipe instructions")
    description: Optional[str] = Field(None, description="Recipe description")
    ingredients: List[RecipeIngredient] = Field(default=[], description="Recipe ingredients")


class RecipeUpdate(BaseModel):
    """Request model for updating a recipe"""
    name: Optional[str] = Field(None, description="Recipe name")
    instructions: Optional[str] = Field(None, description="Recipe instructions")
    description: Optional[str] = Field(None, description="Recipe description")
    ingredients: Optional[List[RecipeIngredient]] = Field(None, description="Recipe ingredients")


class RecipeSearchRequest(BaseModel):
    """Request model for recipe search"""
    query: Optional[str] = Field(None, description="Search query")
    ingredients: Optional[List[Dict[str, Any]]] = Field(None, description="Ingredient filters")
    limit: Optional[int] = Field(20, description="Maximum number of results")
    offset: Optional[int] = Field(0, description="Offset for pagination")


class RatingCreate(BaseModel):
    """Request model for creating/updating a rating"""
    rating: int = Field(..., ge=1, le=5, description="Rating value (1-5)")
    comment: Optional[str] = Field(None, description="Optional comment")


class TagCreate(BaseModel):
    """Request model for creating a tag"""
    name: str = Field(..., description="Tag name")
    description: Optional[str] = Field(None, description="Tag description")


class RecipeTagAssociation(BaseModel):
    """Request model for associating a tag with a recipe"""
    tag_id: int = Field(..., description="Tag ID to associate")


class UnitCreate(BaseModel):
    """Request model for creating a unit"""
    name: str = Field(..., description="Unit name")
    abbreviation: Optional[str] = Field(None, description="Unit abbreviation")
    conversion_to_ml: Optional[float] = Field(None, description="Conversion factor to milliliters")


class PaginationParams(BaseModel):
    """Request model for pagination parameters"""
    page: int = Field(1, description="Page number (1-based)", ge=1)
    limit: int = Field(20, description="Number of items per page", ge=1, le=1000)

    @property
    def offset(self) -> int:
        """Calculate offset from page and limit"""
        return (self.page - 1) * self.limit


class RecipeListParams(PaginationParams):
    """Request model for recipe list parameters with pagination"""
    sort_by: Optional[str] = Field("name", description="Sort field: name, created_at, avg_rating")
    sort_order: Optional[str] = Field("asc", description="Sort order: asc, desc")


class SearchParams(PaginationParams):
    """Request model for search parameters with pagination"""
    q: Optional[str] = Field(None, description="Search query")
    ingredients: Optional[List[str]] = Field(None, description="Ingredient filter list")
    min_rating: Optional[float] = Field(None, description="Minimum average rating", ge=0, le=5)
    max_rating: Optional[float] = Field(None, description="Maximum average rating", ge=0, le=5)
    tags: Optional[List[str]] = Field(None, description="Tag filter list")