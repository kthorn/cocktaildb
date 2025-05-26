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
    quantity: Optional[float] = Field(None, description="Quantity amount")
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