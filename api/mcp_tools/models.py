"""Output models for the public MCP tools.

Field descriptions become part of the tool schema, so keep them short and plain.
"""

from pydantic import BaseModel, Field


class RecipeSummary(BaseModel):
    id: int = Field(description="Recipe id")
    name: str = Field(description="Recipe name")
    url: str = Field(description="Link to the recipe page")
    ingredients: list[str] = Field(description="Ingredient names")
    abv: str | None = Field(default=None, description="Estimated ABV, e.g. 24%")
    avg_rating: float | None = Field(default=None, description="Average rating")
    rating_count: int = Field(description="Number of ratings")
    tags: list[str] = Field(description="Public tags")


class RecipeIngredientLine(BaseModel):
    ingredient_id: int = Field(description="Ingredient id")
    name: str = Field(description="Ingredient name")
    url: str = Field(description="Link to the ingredient page")
    amount: float | None = Field(default=None, description="Amount")
    unit: str | None = Field(default=None, description="Unit of the amount")


class RecipeDetail(BaseModel):
    id: int = Field(description="Recipe id")
    name: str = Field(description="Recipe name")
    url: str = Field(description="Link to the recipe page")
    description: str | None = Field(default=None, description="Recipe description")
    instructions: str | None = Field(default=None, description="Preparation steps")
    ingredients: list[RecipeIngredientLine] = Field(description="Ingredient lines")
    abv: str | None = Field(default=None, description="Estimated ABV, e.g. 24%")
    abv_notes: list[str] = Field(description="Notes about the ABV estimate")
    avg_rating: float | None = Field(default=None, description="Average rating")
    rating_count: int = Field(description="Number of ratings")
    tags: list[str] = Field(description="Public tags")
    source: str | None = Field(default=None, description="Where the recipe is from")
    source_url: str | None = Field(default=None, description="Link to the source")


class RecipeSearchResult(BaseModel):
    recipes: list[RecipeSummary] = Field(description="Matching recipes")
    has_more: bool = Field(description="True if more results exist after this page")
    offset: int = Field(description="Offset of the first result")
    unresolved_ingredients: list[str] = Field(
        description="Requested ingredient names that matched nothing"
    )


class IngredientSwap(BaseModel):
    from_ingredient: str = Field(description="Ingredient in the original recipe")
    to_ingredient: str = Field(description="Ingredient in the similar recipe")
    weight: float = Field(description="How much of the recipe this swap accounts for")


class SimilarRecipe(BaseModel):
    id: int = Field(description="Recipe id")
    name: str = Field(description="Recipe name")
    url: str = Field(description="Link to the recipe page")
    distance: float = Field(description="Distance from the original; lower is closer")
    swaps: list[IngredientSwap] = Field(description="Main ingredient differences")


class SimilarRecipesResult(BaseModel):
    recipe_id: int = Field(description="Id of the original recipe")
    recipe_name: str = Field(description="Name of the original recipe")
    recipe_url: str = Field(description="Link to the original recipe page")
    similar: list[SimilarRecipe] = Field(description="Similar recipes, closest first")


class IngredientMatch(BaseModel):
    id: int = Field(description="Ingredient id")
    name: str = Field(description="Ingredient name")
    url: str = Field(description="Link to the ingredient page")
    hierarchy: list[str] = Field(description="Ancestor names, broadest first")
    description: str | None = Field(default=None, description="Ingredient description")
    percent_abv: float | None = Field(default=None, description="Percent ABV")


class IngredientSearchResult(BaseModel):
    ingredients: list[IngredientMatch] = Field(description="Matching ingredients")
