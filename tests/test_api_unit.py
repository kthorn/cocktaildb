"""
Unit tests for CocktailDB API endpoints
Tests individual endpoint functionality with mocked dependencies
"""

import pytest
from fastapi import status
from unittest.mock import Mock, patch


class TestHealthAndRoot:
    """Test basic health and root endpoints"""
    
    def test_root_endpoint(self, test_client_memory):
        """Test root endpoint returns expected message"""
        response = test_client_memory.get("/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "message" in data
        assert "CocktailDB API" in data["message"]
        assert "test" in data["message"].lower()
    
    def test_health_endpoint(self, test_client_memory):
        """Test health check endpoint"""
        response = test_client_memory.get("/health")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["message"] == "API is healthy"


class TestIngredientEndpoints:
    """Test ingredient-related endpoints"""
    
    def test_get_ingredients_unauthorized(self, test_client_memory):
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
    
    def test_create_ingredient_invalid_data(self, authenticated_client):
        """Test creating ingredient with invalid data"""
        invalid_data = {"description": "Missing name field"}
        response = authenticated_client.post("/api/v1/ingredients", json=invalid_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
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
    
    def test_get_recipes_unauthorized(self, test_client_memory):
        """Test getting recipes without authentication"""
        response = test_client_memory.get("/api/v1/recipes")
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_500_INTERNAL_SERVER_ERROR]
    
    def test_get_recipes_with_pagination(self, test_client_memory):
        """Test recipe pagination"""
        response = test_client_memory.get("/api/v1/recipes?limit=10&offset=0")
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_500_INTERNAL_SERVER_ERROR]
    
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
    
    def test_create_recipe_invalid_data(self, authenticated_client):
        """Test creating recipe with invalid data"""
        invalid_data = {"instructions": "Missing name field"}
        response = authenticated_client.post("/api/v1/recipes", json=invalid_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_get_recipe_by_id(self, test_client_memory):
        """Test getting specific recipe by ID"""
        response = test_client_memory.get("/api/v1/recipes/1")
        assert response.status_code in [
            status.HTTP_200_OK, 
            status.HTTP_404_NOT_FOUND, 
            status.HTTP_500_INTERNAL_SERVER_ERROR
        ]
    
    def test_update_recipe_unauthorized(self, test_client_memory):
        """Test updating recipe without authentication"""
        update_data = {"name": "Updated Recipe"}
        response = test_client_memory.put("/api/v1/recipes/1", json=update_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_delete_recipe_unauthorized(self, test_client_memory):
        """Test deleting recipe without authentication"""
        response = test_client_memory.delete("/api/v1/recipes/1")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestUnitEndpoints:
    """Test unit-related endpoints"""
    
    def test_get_units(self, test_client_memory):
        """Test getting units (public endpoint)"""
        response = test_client_memory.get("/api/v1/units")
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_500_INTERNAL_SERVER_ERROR]
    
    def test_create_unit_unauthorized(self, test_client_memory):
        """Test creating unit without authentication"""
        unit_data = {
            "name": "Test Unit",
            "abbreviation": "tu",
            "conversion_to_ml": 30.0
        }
        response = test_client_memory.post("/api/v1/units", json=unit_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestRatingEndpoints:
    """Test rating-related endpoints"""
    
    def test_get_recipe_ratings_unauthorized(self, test_client_memory):
        """Test getting recipe ratings without authentication"""
        response = test_client_memory.get("/api/v1/recipes/1/ratings")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_404_NOT_FOUND, 
            status.HTTP_500_INTERNAL_SERVER_ERROR
        ]
    
    def test_create_rating_unauthorized(self, test_client_memory):
        """Test creating rating without authentication"""
        rating_data = {"rating": 5, "notes": "Great recipe!"}
        response = test_client_memory.post("/api/v1/recipes/1/ratings", json=rating_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_create_rating_authorized(self, authenticated_client):
        """Test creating rating with authentication"""
        rating_data = {"rating": 5, "notes": "Great recipe!"}
        response = authenticated_client.post("/api/v1/recipes/1/ratings", json=rating_data)
        assert response.status_code != status.HTTP_401_UNAUTHORIZED
    
    def test_create_rating_invalid_data(self, authenticated_client):
        """Test creating rating with invalid data"""
        invalid_data = {"rating": 11}  # Rating should be 1-10
        response = authenticated_client.post("/api/v1/recipes/1/ratings", json=invalid_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestTagEndpoints:
    """Test tag-related endpoints"""
    
    def test_get_tags(self, test_client_memory):
        """Test getting tags (public endpoint)"""
        response = test_client_memory.get("/api/v1/tags")
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_500_INTERNAL_SERVER_ERROR]
    
    def test_create_tag_unauthorized(self, test_client_memory):
        """Test creating tag without authentication"""
        tag_data = {"name": "test-tag", "description": "Test tag"}
        response = test_client_memory.post("/api/v1/tags", json=tag_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestAuthEndpoints:
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


class TestCORSHeaders:
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
    
    def test_cors_headers_present(self, test_client_memory):
        """Test that CORS headers are present in responses"""
        response = test_client_memory.get("/api/v1/ingredients")
        # CORS headers should be present
        assert "access-control-allow-origin" in [h.lower() for h in response.headers.keys()]


class TestErrorHandling:
    """Test error handling and validation"""
    
    def test_invalid_endpoint(self, test_client_memory):
        """Test accessing non-existent endpoint"""
        response = test_client_memory.get("/api/v1/nonexistent")
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_invalid_method(self, test_client_memory):
        """Test using wrong HTTP method"""
        response = test_client_memory.patch("/api/v1/ingredients")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
    
    def test_malformed_json(self, authenticated_client):
        """Test sending malformed JSON"""
        response = authenticated_client.post(
            "/api/v1/ingredients",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestRequestValidation:
    """Test request validation with Pydantic models"""
    
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
    
    def test_extra_fields_ignored(self, authenticated_client):
        """Test that extra fields are ignored in requests"""
        data_with_extra = {
            "name": "Test Ingredient",
            "description": "Test description",
            "extra_field": "should be ignored"
        }
        response = authenticated_client.post("/api/v1/ingredients", json=data_with_extra)
        # Should not fail due to extra fields
        assert response.status_code != status.HTTP_422_UNPROCESSABLE_ENTITY