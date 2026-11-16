"""
Unit tests for CocktailDB API endpoints
Tests individual endpoint functionality with mocked dependencies
"""

import pytest
from fastapi import status

pytestmark = pytest.mark.asyncio


class TestBasicEndpoints:
    """Test basic application endpoints"""

    async def test_root_endpoint(self, test_client_memory):
        """Test root endpoint returns self-describing API information"""
        response = await test_client_memory.get("/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "Mixology Tools API"
        assert "description" in data
        assert "docs" in data
        assert "openapi" in data
        assert "endpoints" in data
        # Verify key endpoints are listed
        endpoints = data["endpoints"]
        assert "search_recipes" in endpoints
        assert "ingredients" in endpoints
        assert "stats" in endpoints


class TestIngredientEndpoints:
    """Test ingredient-related endpoints"""

    async def test_get_ingredients_public_access(self, test_client_memory):
        """Test getting ingredients without authentication"""
        response = await test_client_memory.get("/ingredients")
        # Should work for public endpoints
        assert response.status_code == status.HTTP_200_OK

    async def test_create_ingredient_unauthorized(self, test_client_memory):
        """Test creating ingredient without authentication fails"""
        ingredient_data = {"name": "Test Ingredient", "description": "Test description"}
        response = await test_client_memory.post("/ingredients", json=ingredient_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_create_ingredient_authorized(
        self, editor_client, sample_ingredient_data
    ):
        """Test creating ingredient with authentication"""
        response = await editor_client.post("/ingredients", json=sample_ingredient_data)
        assert response.status_code == status.HTTP_201_CREATED, response.text
        assert response.json()["name"] == sample_ingredient_data["name"]

    async def test_update_ingredient_unauthorized(self, test_client_memory):
        """Test updating ingredient without authentication"""
        update_data = {"name": "Updated Name"}
        response = await test_client_memory.put("/ingredients/1", json=update_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_delete_ingredient_unauthorized(self, test_client_memory):
        """Test deleting ingredient without authentication"""
        response = await test_client_memory.delete("/ingredients/1")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestRecipeEndpoints:
    """Test recipe-related endpoints"""

    async def test_create_recipe_unauthorized(self, test_client_memory):
        """Test creating recipe without authentication"""
        recipe_data = {"name": "Test Recipe", "instructions": "Test instructions"}
        response = await test_client_memory.post("/recipes", json=recipe_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_create_recipe_authorized(
        self, editor_client_with_data, sample_recipe_data
    ):
        """Test creating recipe with authentication"""
        # sample_recipe_data references seeded ingredients 1 and 2.
        response = await editor_client_with_data.post(
            "/recipes", json=sample_recipe_data
        )
        assert response.status_code == status.HTTP_201_CREATED, response.text
        assert response.json()["name"] == sample_recipe_data["name"]


class TestAuthenticationEndpoints:
    """Test authentication-related endpoints"""

    async def test_auth_me_unauthorized(self, test_client_memory):
        """Test /auth/me without authentication"""
        response = await test_client_memory.get("/auth/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_auth_me_authorized(self, authenticated_client, mock_user):
        """Test /auth/me with authentication"""
        response = await authenticated_client.get("/auth/me")
        assert response.status_code == status.HTTP_200_OK, response.text
        assert response.json()["user_id"] == mock_user["user_id"]


class TestPublicResourceEndpoints:
    """Test public resource endpoints (units, tags)"""

    async def test_get_units(self, test_client_memory):
        """Test getting units (public endpoint)"""
        response = await test_client_memory.get("/units")
        assert response.status_code == status.HTTP_200_OK

    async def test_get_tags(self, test_client_memory):
        """Test getting tags (public endpoint)"""
        response = await test_client_memory.get("/tags/public")
        assert response.status_code == status.HTTP_200_OK


class TestRequestValidation:
    """Test request validation with Pydantic models"""

    async def test_create_ingredient_invalid_data(self, editor_client):
        """Test creating ingredient with invalid data"""
        invalid_data = {"description": "Missing name field"}
        response = await editor_client.post("/ingredients", json=invalid_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_create_recipe_invalid_data(self, editor_client):
        """Test creating recipe with invalid data"""
        invalid_data = {"instructions": "Missing name field"}
        response = await editor_client.post("/recipes", json=invalid_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_missing_required_fields(self, editor_client):
        """Test request with missing required fields"""
        # Ingredient requires name
        incomplete_data = {"description": "Missing name"}
        response = await editor_client.post("/ingredients", json=incomplete_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        error_detail = response.json()
        assert "detail" in error_detail

    async def test_invalid_field_types(self, editor_client):
        """Test request with invalid field types"""
        invalid_data = {
            "name": "Test Ingredient",
            "parent_id": "not_a_number",  # Should be integer
        }
        response = await editor_client.post("/ingredients", json=invalid_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_malformed_json(self, authenticated_client):
        """Test sending malformed JSON"""
        response = await authenticated_client.post(
            "/ingredients",
            data="invalid json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestErrorHandling:
    """Test error handling and edge cases"""

    async def test_invalid_endpoint(self, test_client_memory):
        """Test accessing non-existent endpoint"""
        response = await test_client_memory.get("/nonexistent")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_invalid_method(self, test_client_memory):
        """Test using wrong HTTP method"""
        response = await test_client_memory.patch("/ingredients")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


class TestTagAPIEndpoints:
    """Test tag-related API endpoints"""

    async def test_get_public_tags(self, test_client_memory):
        """Test GET /tags/public endpoint"""
        response = await test_client_memory.get("/tags/public")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)

    async def test_create_public_tag_unauthorized(self, test_client_memory):
        """Test creating public tag without authentication"""
        tag_data = {"name": "test-tag"}
        response = await test_client_memory.post("/tags/public", json=tag_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_create_public_tag_authorized(self, authenticated_client):
        """Test creating public tag with authentication"""
        tag_data = {"name": "test-public-tag"}
        response = await authenticated_client.post("/tags/public", json=tag_data)
        assert response.status_code == status.HTTP_201_CREATED, response.text
        assert response.json()["name"] == "test-public-tag"

    async def test_create_private_tag_unauthorized(self, test_client_memory):
        """Test creating private tag without authentication"""
        tag_data = {"name": "private-tag"}
        response = await test_client_memory.post("/tags/private", json=tag_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_get_private_tags_unauthorized(self, test_client_memory):
        """Test getting private tags without authentication"""
        response = await test_client_memory.get("/tags/private")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_get_private_tags_authorized(self, authenticated_client):
        """Test getting private tags with authentication"""
        response = await authenticated_client.get("/tags/private")
        assert response.status_code == status.HTTP_200_OK, response.text
        assert response.json() == []

    async def test_create_private_tag_authorized(self, authenticated_client):
        """Test creating private tag with authentication"""
        tag_data = {"name": "test-private-tag"}
        response = await authenticated_client.post("/tags/private", json=tag_data)
        assert response.status_code == status.HTTP_201_CREATED, response.text
        assert response.json()["name"] == "test-private-tag"

    async def test_create_private_tag_response_structure(self, authenticated_client):
        """Test that private tag creation returns correct response structure"""
        tag_data = {"name": "response-structure-test-tag"}
        response = await authenticated_client.post("/tags/private", json=tag_data)

        assert response.status_code == status.HTTP_201_CREATED, response.text
        data = response.json()
        assert "id" in data
        assert data["name"] == "response-structure-test-tag"
        assert "cognito_user_id" in data
        # Regression: the response must not carry a cognito_username field.
        assert "cognito_username" not in data

    async def test_add_public_tag_to_recipe_unauthorized(self, test_client_memory):
        """Test adding public tag to recipe without authentication"""
        tag_data = {"tag_id": 1}
        response = await test_client_memory.post(
            "/recipes/1/public_tags", json=tag_data
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_add_private_tag_to_recipe_unauthorized(self, test_client_memory):
        """Test adding private tag to recipe without authentication"""
        tag_data = {"tag_id": 1}
        response = await test_client_memory.post(
            "/recipes/1/private_tags", json=tag_data
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_remove_public_tag_from_recipe_unauthorized(self, test_client_memory):
        """Test removing public tag from recipe without authentication"""
        response = await test_client_memory.delete("/recipes/1/public_tags/1")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_remove_private_tag_from_recipe_unauthorized(
        self, test_client_memory
    ):
        """Test removing private tag from recipe without authentication"""
        response = await test_client_memory.delete("/recipes/1/private_tags/1")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_tag_validation_missing_name(self, authenticated_client):
        """Test tag creation with missing name field"""
        tag_data = {"description": "Missing name field"}
        response = await authenticated_client.post("/tags/public", json=tag_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_recipe_tag_validation_missing_tag_id(self, authenticated_client):
        """Test recipe tag association with missing tag_id"""
        tag_data = {"invalid_field": "value"}
        response = await authenticated_client.post(
            "/recipes/1/public_tags", json=tag_data
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestNoCrossOriginAccess:
    """The API is same-origin only and sends no CORS headers (issue #138)."""

    async def test_responses_have_no_cors_headers(self, test_client_memory):
        response = await test_client_memory.get(
            "/ingredients", headers={"Origin": "https://example.com"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert not any(h.startswith("access-control-") for h in response.headers)
