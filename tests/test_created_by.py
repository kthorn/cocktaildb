"""Tests for created_by field on recipes and ingredients"""

import pytest
from api.models.responses import IngredientResponse, RecipeResponse


class TestIngredientCreatedByField:
    """Test created_by field on ingredient responses"""

    def test_ingredient_response_has_created_by_field(self):
        """IngredientResponse model should accept created_by field"""
        ingredient = IngredientResponse(
            id=1,
            name="Test Ingredient",
            allow_substitution=False,
            created_by="user-123"
        )
        assert ingredient.created_by == "user-123"

    def test_ingredient_response_created_by_optional(self):
        """created_by should be optional (None for legacy data)"""
        ingredient = IngredientResponse(
            id=1,
            name="Test Ingredient",
            allow_substitution=False
        )
        assert ingredient.created_by is None


class TestRecipeCreatedByField:
    """Test created_by field on recipe responses"""

    def test_recipe_response_has_created_by_field(self):
        """RecipeResponse model should accept created_by field"""
        recipe = RecipeResponse(
            id=1,
            name="Test Recipe",
            created_by="user-456"
        )
        assert recipe.created_by == "user-456"

    def test_recipe_response_created_by_optional(self):
        """created_by should be optional (None for legacy data)"""
        recipe = RecipeResponse(
            id=1,
            name="Test Recipe"
        )
        assert recipe.created_by is None


class TestIngredientCreatedByDatabase:
    """Test created_by is saved to database for ingredients"""

    @pytest.mark.asyncio
    async def test_create_ingredient_saves_created_by(self, editor_client_with_data, mock_editor_user):
        """Creating an ingredient should save created_by to database"""
        # Create ingredient using editor client (which has proper auth mocking)
        response = await editor_client_with_data.post("/ingredients", json={
            "name": "Test Created By Ingredient",
            "description": "Testing created_by field"
        })

        assert response.status_code == 201
        data = response.json()
        assert data.get("created_by") == mock_editor_user["user_id"]


class TestRecipeCreatedByDatabase:
    """Test created_by is saved to database for recipes"""

    @pytest.mark.asyncio
    async def test_create_recipe_saves_created_by(self, editor_client_with_data, mock_editor_user):
        """Creating a recipe should save created_by to database"""
        response = await editor_client_with_data.post("/recipes", json={
            "name": "Test Created By Recipe",
            "instructions": "Test instructions"
        })

        assert response.status_code == 201
        data = response.json()
        assert data.get("created_by") == mock_editor_user["user_id"]
