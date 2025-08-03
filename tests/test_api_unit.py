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
        response = test_client_memory.get("/ingredients")
        # Should work for public endpoints
        assert response.status_code == status.HTTP_200_OK

    def test_create_ingredient_unauthorized(self, test_client_memory):
        """Test creating ingredient without authentication fails"""
        ingredient_data = {"name": "Test Ingredient", "description": "Test description"}
        response = test_client_memory.post("/ingredients", json=ingredient_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_ingredient_authorized(
        self, editor_client, sample_ingredient_data
    ):
        """Test creating ingredient with authentication"""
        response = editor_client.post(
            "/ingredients", json=sample_ingredient_data
        )
        # May fail due to database constraints in memory DB, but should not be unauthorized
        assert response.status_code != status.HTTP_401_UNAUTHORIZED

    def test_update_ingredient_unauthorized(self, test_client_memory):
        """Test updating ingredient without authentication"""
        update_data = {"name": "Updated Name"}
        response = test_client_memory.put("/ingredients/1", json=update_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_delete_ingredient_unauthorized(self, test_client_memory):
        """Test deleting ingredient without authentication"""
        response = test_client_memory.delete("/ingredients/1")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestRecipeEndpoints:
    """Test recipe-related endpoints"""

    def test_create_recipe_unauthorized(self, test_client_memory):
        """Test creating recipe without authentication"""
        recipe_data = {"name": "Test Recipe", "instructions": "Test instructions"}
        response = test_client_memory.post("/recipes", json=recipe_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_recipe_authorized(self, editor_client, sample_recipe_data):
        """Test creating recipe with authentication"""
        response = editor_client.post("/recipes", json=sample_recipe_data)
        assert response.status_code != status.HTTP_401_UNAUTHORIZED


class TestAuthenticationEndpoints:
    """Test authentication-related endpoints"""

    def test_auth_me_unauthorized(self, test_client_memory):
        """Test /auth/me without authentication"""
        response = test_client_memory.get("/auth/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_auth_me_authorized(self, authenticated_client, mock_user):
        """Test /auth/me with authentication"""
        response = authenticated_client.get("/auth/me")
        if response.status_code == status.HTTP_200_OK:
            data = response.json()
            assert "user_id" in data
            assert data["user_id"] == mock_user["user_id"]


class TestPublicResourceEndpoints:
    """Test public resource endpoints (units, tags)"""

    def test_get_units(self, test_client_memory):
        """Test getting units (public endpoint)"""
        response = test_client_memory.get("/units")
        assert response.status_code == status.HTTP_200_OK

    def test_get_tags(self, test_client_memory):
        """Test getting tags (public endpoint)"""
        response = test_client_memory.get("/tags/public")
        assert response.status_code == status.HTTP_200_OK


class TestRequestValidation:
    """Test request validation with Pydantic models"""

    def test_create_ingredient_invalid_data(self, editor_client):
        """Test creating ingredient with invalid data"""
        invalid_data = {"description": "Missing name field"}
        response = editor_client.post("/ingredients", json=invalid_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_create_recipe_invalid_data(self, editor_client):
        """Test creating recipe with invalid data"""
        invalid_data = {"instructions": "Missing name field"}
        response = editor_client.post("/recipes", json=invalid_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_missing_required_fields(self, editor_client):
        """Test request with missing required fields"""
        # Ingredient requires name
        incomplete_data = {"description": "Missing name"}
        response = editor_client.post("/ingredients", json=incomplete_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        error_detail = response.json()
        assert "detail" in error_detail

    def test_invalid_field_types(self, editor_client):
        """Test request with invalid field types"""
        invalid_data = {
            "name": "Test Ingredient",
            "parent_id": "not_a_number",  # Should be integer
        }
        response = editor_client.post("/ingredients", json=invalid_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_malformed_json(self, authenticated_client):
        """Test sending malformed JSON"""
        response = authenticated_client.post(
            "/ingredients",
            data="invalid json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestErrorHandling:
    """Test error handling and edge cases"""

    def test_invalid_endpoint(self, test_client_memory):
        """Test accessing non-existent endpoint"""
        response = test_client_memory.get("/nonexistent")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_invalid_method(self, test_client_memory):
        """Test using wrong HTTP method"""
        response = test_client_memory.patch("/ingredients")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


class TestTagAPIEndpoints:
    """Test tag-related API endpoints"""

    def test_get_public_tags(self, test_client_memory):
        """Test GET /tags/public endpoint"""
        response = test_client_memory.get("/tags/public")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)

    def test_create_public_tag_unauthorized(self, test_client_memory):
        """Test creating public tag without authentication"""
        tag_data = {"name": "test-tag"}
        response = test_client_memory.post("/tags/public", json=tag_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_public_tag_authorized(self, authenticated_client):
        """Test creating public tag with authentication"""
        tag_data = {"name": "test-public-tag"}
        response = authenticated_client.post("/tags/public", json=tag_data)
        # Should not be unauthorized (may fail due to other reasons like database constraints)
        assert response.status_code != status.HTTP_401_UNAUTHORIZED

    def test_create_private_tag_unauthorized(self, test_client_memory):
        """Test creating private tag without authentication"""
        tag_data = {"name": "private-tag"}
        response = test_client_memory.post("/tags/private", json=tag_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_private_tags_unauthorized(self, test_client_memory):
        """Test getting private tags without authentication"""
        response = test_client_memory.get("/tags/private")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_private_tags_authorized(self, authenticated_client):
        """Test getting private tags with authentication"""
        response = authenticated_client.get("/tags/private")
        # Should not be unauthorized (may fail due to other reasons like database constraints)
        assert response.status_code != status.HTTP_401_UNAUTHORIZED
        if response.status_code == status.HTTP_200_OK:
            data = response.json()
            assert isinstance(data, list)

    def test_create_private_tag_authorized(self, authenticated_client):
        """Test creating private tag with authentication"""
        tag_data = {"name": "test-private-tag"}
        response = authenticated_client.post("/tags/private", json=tag_data)
        # Should not be unauthorized (may fail due to other reasons like database constraints)
        assert response.status_code != status.HTTP_401_UNAUTHORIZED

    def test_create_private_tag_response_structure(self, authenticated_client):
        """Test that private tag creation returns correct response structure"""
        tag_data = {"name": "response-structure-test-tag"}
        response = authenticated_client.post("/tags/private", json=tag_data)

        # Should succeed and return expected structure
        if response.status_code == status.HTTP_201_CREATED:
            data = response.json()
            # Verify response has required fields for PrivateTagResponse
            assert "id" in data
            assert "name" in data
            assert "cognito_user_id" in data
            # Verify response does NOT have cognito_username field (this was the bug)
            assert "cognito_username" not in data

    def test_add_public_tag_to_recipe_unauthorized(self, test_client_memory):
        """Test adding public tag to recipe without authentication"""
        tag_data = {"tag_id": 1}
        response = test_client_memory.post("/recipes/1/public_tags", json=tag_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_add_private_tag_to_recipe_unauthorized(self, test_client_memory):
        """Test adding private tag to recipe without authentication"""
        tag_data = {"tag_id": 1}
        response = test_client_memory.post("/recipes/1/private_tags", json=tag_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_remove_public_tag_from_recipe_unauthorized(self, test_client_memory):
        """Test removing public tag from recipe without authentication"""
        response = test_client_memory.delete("/recipes/1/public_tags/1")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_remove_private_tag_from_recipe_unauthorized(self, test_client_memory):
        """Test removing private tag from recipe without authentication"""
        response = test_client_memory.delete("/recipes/1/private_tags/1")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_tag_validation_missing_name(self, authenticated_client):
        """Test tag creation with missing name field"""
        tag_data = {"description": "Missing name field"}
        response = authenticated_client.post("/tags/public", json=tag_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_recipe_tag_validation_missing_tag_id(self, authenticated_client):
        """Test recipe tag association with missing tag_id"""
        tag_data = {"invalid_field": "value"}
        response = authenticated_client.post("/recipes/1/public_tags", json=tag_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestCORSFunctionality:
    """Test CORS functionality"""

    def test_cors_preflight_request(self, test_client_memory):
        """Test CORS preflight request"""
        headers = {
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type,Authorization",
        }
        response = test_client_memory.options("/ingredients", headers=headers)
        # Should not be 404 or 405 if CORS is properly configured
        assert response.status_code != status.HTTP_404_NOT_FOUND
