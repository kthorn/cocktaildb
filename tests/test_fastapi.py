"""
Basic tests for the FastAPI application - focused on app-level concerns
"""

import pytest
from fastapi.testclient import TestClient


class TestApplicationBootstrap:
    """Test basic application startup and configuration"""
    
    def test_health_endpoint(self, test_client_memory):
        """Test the health check endpoint"""
        response = test_client_memory.get("/health")
        assert response.status_code == 200
        assert response.json()["message"] == "API is healthy"


class TestModelsAndValidation:
    """Test Pydantic models and validation"""
    
    def test_ingredient_create_model(self):
        """Test ingredient creation model validation"""
        try:
            from api.models.requests import IngredientCreate
            
            # Valid data
            valid_data = {"name": "Test Ingredient"}
            ingredient = IngredientCreate(**valid_data)
            assert ingredient.name == "Test Ingredient"
            
            # Test with optional fields
            full_data = {
                "name": "Test Ingredient",
                "description": "Test description",
                "parent_id": 1
            }
            ingredient = IngredientCreate(**full_data)
            assert ingredient.description == "Test description"
            assert ingredient.parent_id == 1
            
        except ImportError:
            pytest.skip("Request models not available")
    
    def test_recipe_create_model(self):
        """Test recipe creation model validation"""
        try:
            from api.models.requests import RecipeCreate, RecipeIngredient
            
            # Valid recipe data
            recipe_data = {
                "name": "Test Recipe",
                "instructions": "Test instructions",
                "ingredients": [
                    {
                        "ingredient_id": 1,
                        "amount": 2.0,
                        "unit_id": 1
                    }
                ]
            }
            
            recipe = RecipeCreate(**recipe_data)
            assert recipe.name == "Test Recipe"
            assert len(recipe.ingredients) == 1
            assert recipe.ingredients[0].ingredient_id == 1
            
        except ImportError:
            pytest.skip("Request models not available")


# Pytest configuration
@pytest.fixture(scope="session")
def test_settings():
    """Test settings fixture"""
    return {
        "db_path": ":memory:",  # Use in-memory SQLite for tests
        "environment": "test",
        "debug": True,
        "log_level": "DEBUG"
    }


if __name__ == "__main__":
    pytest.main([__file__, "-v"])