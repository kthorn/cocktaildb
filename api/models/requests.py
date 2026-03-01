from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator


class IngredientCreate(BaseModel):
    """Request model for creating an ingredient"""

    name: str = Field(..., min_length=1, description="Ingredient name")
    description: Optional[str] = Field(None, description="Ingredient description")
    parent_id: Optional[int] = Field(
        None, description="Parent ingredient ID for hierarchy"
    )
    allow_substitution: bool = Field(
        default=False,
        description="Whether this ingredient can be substituted with siblings/ancestors"
    )
    percent_abv: Optional[float] = Field(None, ge=0, le=100)
    sugar_g_per_l: Optional[float] = Field(None, ge=0, le=1000)
    titratable_acidity_g_per_l: Optional[float] = Field(None, ge=0, le=100)
    url: Optional[str] = Field(None, description="Reference URL")

    @field_validator("name")
    @classmethod
    def trim_name(cls, v: str) -> str:
        """Trim leading and trailing whitespace from name"""
        if v:
            return v.strip()
        return v

    @field_validator("description")
    @classmethod
    def trim_description(cls, v: Optional[str]) -> Optional[str]:
        """Trim leading and trailing whitespace from description"""
        if v:
            return v.strip()
        return v


class IngredientUpdate(BaseModel):
    """Request model for updating an ingredient"""

    name: Optional[str] = Field(None, description="Ingredient name")
    description: Optional[str] = Field(None, description="Ingredient description")
    parent_id: Optional[int] = Field(
        None, description="Parent ingredient ID for hierarchy"
    )
    allow_substitution: Optional[bool] = Field(
        None,
        description="Whether this ingredient can be substituted with siblings/ancestors"
    )
    percent_abv: Optional[float] = Field(None, ge=0, le=100)
    sugar_g_per_l: Optional[float] = Field(None, ge=0, le=1000)
    titratable_acidity_g_per_l: Optional[float] = Field(None, ge=0, le=100)
    url: Optional[str] = Field(None, description="Reference URL")

    @field_validator("name", "description")
    @classmethod
    def trim_strings(cls, v: Optional[str]) -> Optional[str]:
        """Trim leading and trailing whitespace from string fields"""
        if v:
            return v.strip()
        return v


class RecipeIngredient(BaseModel):
    """Recipe ingredient specification"""

    ingredient_id: int = Field(..., description="Ingredient ID")
    amount: Optional[float] = Field(None, description="Quantity amount")
    unit_id: Optional[int] = Field(None, description="Unit ID")


class BulkRecipeIngredient(BaseModel):
    """Recipe ingredient specification for bulk upload using ingredient names"""

    ingredient_name: str = Field(
        ..., description="Ingredient name (will be looked up by exact match)"
    )
    amount: Optional[float] = Field(None, description="Quantity amount")
    unit_name: Optional[str] = Field(None, description="Unit name (will be looked up by exact match)")
    # Kept for backward compatibility - deprecated in favor of unit_name
    unit_id: Optional[int] = Field(None, description="Unit ID (deprecated, use unit_name)")

    @field_validator("ingredient_name", "unit_name")
    @classmethod
    def trim_strings(cls, v: Optional[str]) -> Optional[str]:
        """Trim leading and trailing whitespace from string fields"""
        if v:
            return v.strip()
        return v

    def get_unit_identifier(self) -> Optional[str]:
        """Get the unit identifier - prioritize unit_name over unit_id"""
        return self.unit_name if self.unit_name is not None else str(self.unit_id) if self.unit_id is not None else None


class RecipeCreate(BaseModel):
    """Request model for creating a recipe"""

    name: str = Field(..., description="Recipe name")
    instructions: Optional[str] = Field(None, description="Recipe instructions")
    description: Optional[str] = Field(None, description="Recipe description")
    source: Optional[str] = Field(None, description="Recipe source")
    source_url: Optional[str] = Field(None, description="Recipe source URL")
    ingredients: List[RecipeIngredient] = Field(
        default=[], description="Recipe ingredients"
    )

    @field_validator("name", "instructions", "description", "source", "source_url")
    @classmethod
    def trim_strings(cls, v: Optional[str]) -> Optional[str]:
        """Trim leading and trailing whitespace from string fields"""
        if v:
            return v.strip()
        return v


class BulkRecipeCreate(BaseModel):
    """Request model for creating a recipe in bulk upload using ingredient names"""

    name: str = Field(..., description="Recipe name")
    instructions: Optional[str] = Field(None, description="Recipe instructions")
    description: Optional[str] = Field(None, description="Recipe description")
    source: Optional[str] = Field(None, description="Recipe source")
    source_url: Optional[str] = Field(None, description="Recipe source URL")
    ingredients: List[BulkRecipeIngredient] = Field(
        default=[], description="Recipe ingredients"
    )

    @field_validator("name", "instructions", "description", "source", "source_url")
    @classmethod
    def trim_strings(cls, v: Optional[str]) -> Optional[str]:
        """Trim leading and trailing whitespace from string fields"""
        if v:
            return v.strip()
        return v


class RecipeUpdate(BaseModel):
    """Request model for updating a recipe"""

    name: Optional[str] = Field(None, description="Recipe name")
    instructions: Optional[str] = Field(None, description="Recipe instructions")
    description: Optional[str] = Field(None, description="Recipe description")
    source: Optional[str] = Field(None, description="Recipe source")
    source_url: Optional[str] = Field(None, description="Recipe source URL")
    ingredients: Optional[List[RecipeIngredient]] = Field(
        None, description="Recipe ingredients"
    )

    @field_validator("name", "instructions", "description", "source", "source_url")
    @classmethod
    def trim_strings(cls, v: Optional[str]) -> Optional[str]:
        """Trim leading and trailing whitespace from string fields"""
        if v:
            return v.strip()
        return v


class RatingCreate(BaseModel):
    """Request model for creating/updating a rating"""

    rating: int = Field(..., ge=1, le=5, description="Rating value (1-5)")
    comment: Optional[str] = Field(None, description="Optional comment")


class TagCreate(BaseModel):
    """Request model for creating a tag"""

    name: str = Field(..., description="Tag name")
    description: Optional[str] = Field(None, description="Tag description")

    @field_validator("name", "description")
    @classmethod
    def trim_strings(cls, v: Optional[str]) -> Optional[str]:
        """Trim leading and trailing whitespace from string fields"""
        if v:
            return v.strip()
        return v


class RecipeTagAssociation(BaseModel):
    """Request model for associating a tag with a recipe"""

    tag_id: int = Field(..., description="Tag ID to associate")




class BulkIngredientCreate(BaseModel):
    """Ingredient specification for bulk upload"""

    name: str = Field(..., min_length=1, description="Ingredient name")
    description: Optional[str] = Field(None, description="Ingredient description")
    parent_name: Optional[str] = Field(None, description="Parent ingredient name (will be looked up by exact match)")
    # Kept for backward compatibility - deprecated in favor of parent_name
    parent_id: Optional[int] = Field(None, description="Parent ingredient ID (deprecated, use parent_name)")
    allow_substitution: Optional[bool] = Field(
        default=False,
        description="Whether this ingredient can be substituted with siblings/ancestors"
    )

    @field_validator("name", "description", "parent_name")
    @classmethod
    def trim_strings(cls, v: Optional[str]) -> Optional[str]:
        """Trim leading and trailing whitespace from string fields"""
        if v:
            return v.strip()
        return v


class BulkIngredientUpload(BaseModel):
    """Request model for bulk ingredient upload"""

    ingredients: List[BulkIngredientCreate] = Field(
        ..., description="List of ingredients to upload", min_length=1
    )


class BulkRecipeUpload(BaseModel):
    """Request model for bulk recipe upload"""

    recipes: List[BulkRecipeCreate] = Field(
        ..., description="List of recipes to upload", min_length=1, max_length=100
    )


class UserIngredientAdd(BaseModel):
    """Request model for adding an ingredient to user's inventory"""

    ingredient_id: int = Field(..., description="Ingredient ID to add to inventory")


class UserIngredientBulkAdd(BaseModel):
    """Request model for bulk adding ingredients to user's inventory"""

    ingredient_ids: List[int] = Field(
        ..., description="List of ingredient IDs to add to inventory", min_length=1
    )


class UserIngredientBulkRemove(BaseModel):
    """Request model for bulk removing ingredients from user's inventory"""

    ingredient_ids: List[int] = Field(
        ..., description="List of ingredient IDs to remove from inventory", min_length=1
    )
