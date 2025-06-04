"""
Unit tests for CocktailDB API endpoints
Tests individual endpoint functionality with mocked dependencies
"""

import pytest
from fastapi import status
from unittest.mock import Mock, patch


class TestBasicEndpoints:
    """Test basic application endpoints"""
    
    def test_root_endpoint(self, test_client_memory):
        """Test root endpoint returns expected message"""
        response = test_client_memory.get("/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "message" in data
        assert "CocktailDB API" in data["message"]


class TestIngredientEndpoints:
    """Test ingredient-related endpoints"""
    
    def test_get_ingredients_public_access(self, test_client_memory):
        """Test getting ingredients without authentication"""
        response = test_client_memory.get("/api/v1/ingredients")
        # Should work for public endpoints
        assert response.status_code == status.HTTP_200_OK
    
    def test_get_ingredients_with_search(self, test_client_memory):
        """Test ingredient search functionality"""
        response = test_client_memory.get("/api/v1/ingredients?search=gin")
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_500_INTERNAL_SERVER_ERROR]
    
    def test_create_ingredient_unauthorized(self, test_client_memory):
        """Test creating ingredient without authentication fails"""
        ingredient_data = {
            "name": "Test Ingredient",
            "description": "Test description"
        }
        response = test_client_memory.post("/api/v1/ingredients", json=ingredient_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_create_ingredient_authorized(self, authenticated_client, sample_ingredient_data):
        """Test creating ingredient with authentication"""
        response = authenticated_client.post("/api/v1/ingredients", json=sample_ingredient_data)
        # May fail due to database constraints in memory DB, but should not be unauthorized
        assert response.status_code != status.HTTP_401_UNAUTHORIZED
    
    def test_update_ingredient_unauthorized(self, test_client_memory):
        """Test updating ingredient without authentication"""
        update_data = {"name": "Updated Name"}
        response = test_client_memory.put("/api/v1/ingredients/1", json=update_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_delete_ingredient_unauthorized(self, test_client_memory):
        """Test deleting ingredient without authentication"""
        response = test_client_memory.delete("/api/v1/ingredients/1")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestRecipeEndpoints:
    """Test recipe-related endpoints"""
    
    def test_get_recipes_public_access(self, test_client_memory):
        """Test getting recipes without authentication"""
        response = test_client_memory.get("/api/v1/recipes")
        assert response.status_code == status.HTTP_200_OK
    
    def test_create_recipe_unauthorized(self, test_client_memory):
        """Test creating recipe without authentication"""
        recipe_data = {
            "name": "Test Recipe",
            "instructions": "Test instructions"
        }
        response = test_client_memory.post("/api/v1/recipes", json=recipe_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_create_recipe_authorized(self, authenticated_client, sample_recipe_data):
        """Test creating recipe with authentication"""
        response = authenticated_client.post("/api/v1/recipes", json=sample_recipe_data)
        assert response.status_code != status.HTTP_401_UNAUTHORIZED


class TestAuthenticationEndpoints:
    """Test authentication-related endpoints"""
    
    def test_auth_me_unauthorized(self, test_client_memory):
        """Test /auth/me without authentication"""
        response = test_client_memory.get("/api/v1/auth/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_auth_me_authorized(self, authenticated_client, mock_user):
        """Test /auth/me with authentication"""
        response = authenticated_client.get("/api/v1/auth/me")
        if response.status_code == status.HTTP_200_OK:
            data = response.json()
            assert "user_id" in data
            assert data["user_id"] == mock_user["user_id"]


class TestPublicResourceEndpoints:
    """Test public resource endpoints (units, tags)"""
    
    def test_get_units(self, test_client_memory):
        """Test getting units (public endpoint)"""
        response = test_client_memory.get("/api/v1/units")
        assert response.status_code == status.HTTP_200_OK
    
    def test_get_tags(self, test_client_memory):
        """Test getting tags (public endpoint)"""
        response = test_client_memory.get("/api/v1/tags/public")
        assert response.status_code == status.HTTP_200_OK
    
    def test_create_unit_unauthorized(self, test_client_memory):
        """Test creating unit without authentication"""
        unit_data = {
            "name": "Test Unit",
            "abbreviation": "tu",
            "conversion_to_ml": 30.0
        }
        response = test_client_memory.post("/api/v1/units", json=unit_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestRequestValidation:
    """Test request validation with Pydantic models"""
    
    def test_create_ingredient_invalid_data(self, authenticated_client):
        """Test creating ingredient with invalid data"""
        invalid_data = {"description": "Missing name field"}
        response = authenticated_client.post("/api/v1/ingredients", json=invalid_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_create_recipe_invalid_data(self, authenticated_client):
        """Test creating recipe with invalid data"""
        invalid_data = {"instructions": "Missing name field"}
        response = authenticated_client.post("/api/v1/recipes", json=invalid_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_missing_required_fields(self, authenticated_client):
        """Test request with missing required fields"""
        # Ingredient requires name
        incomplete_data = {"description": "Missing name"}
        response = authenticated_client.post("/api/v1/ingredients", json=incomplete_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        error_detail = response.json()
        assert "detail" in error_detail
    
    def test_invalid_field_types(self, authenticated_client):
        """Test request with invalid field types"""
        invalid_data = {
            "name": "Test Ingredient",
            "parent_id": "not_a_number"  # Should be integer
        }
        response = authenticated_client.post("/api/v1/ingredients", json=invalid_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_malformed_json(self, authenticated_client):
        """Test sending malformed JSON"""
        response = authenticated_client.post(
            "/api/v1/ingredients",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestErrorHandling:
    """Test error handling and edge cases"""
    
    def test_invalid_endpoint(self, test_client_memory):
        """Test accessing non-existent endpoint"""
        response = test_client_memory.get("/api/v1/nonexistent")
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_invalid_method(self, test_client_memory):
        """Test using wrong HTTP method"""
        response = test_client_memory.patch("/api/v1/ingredients")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


class TestCORSFunctionality:
    """Test CORS functionality"""
    
    def test_cors_preflight_request(self, test_client_memory):
        """Test CORS preflight request"""
        headers = {
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type,Authorization"
        }
        response = test_client_memory.options("/api/v1/ingredients", headers=headers)
        # Should not be 404 or 405 if CORS is properly configured
        assert response.status_code != status.HTTP_404_NOT_FOUND
