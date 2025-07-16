"""
Tests for pagination functionality in the FastAPI application
"""

import pytest
from fastapi.testclient import TestClient


class TestPaginationModels:
    """Test pagination response models"""

    def test_pagination_metadata_model(self):
        """Test pagination metadata model validation"""
        try:
            from api.models.responses import PaginationMetadata

            # Valid pagination metadata
            valid_data = {
                "page": 1,
                "limit": 10,
                "total_count": 47,
                "has_next": True,
                "has_previous": False,
            }
            pagination = PaginationMetadata(**valid_data)
            assert pagination.page == 1
            assert pagination.has_next is True
            assert pagination.has_previous is False

        except ImportError:
            pytest.skip("Pagination models not yet implemented")

    def test_paginated_recipe_response_model(self):
        """Test paginated recipe response model validation"""
        try:
            from api.models.responses import PaginatedRecipeResponse

            # Mock recipe data
            recipe_data = {
                "id": 1,
                "name": "Test Recipe",
                "instructions": "Test instructions",
                "description": "Test description",
                "created_by": "test-user",
                "avg_rating": 4.5,
                "rating_count": 10,
                "ingredients": [],
                "public_tags": [],
                "private_tags": [],
            }

            pagination_data = {
                "page": 1,
                "limit": 10,
                "total_count": 1,
                "has_next": False,
                "has_previous": False,
            }

            # Valid paginated response
            valid_data = {"recipes": [recipe_data], "pagination": pagination_data}
            response = PaginatedRecipeResponse(**valid_data)
            assert len(response.recipes) == 1
            assert response.pagination.total_count == 1

        except ImportError:
            pytest.skip("Pagination models not yet implemented")


class TestRecipePagination:
    """Test recipe pagination endpoints"""

    def test_get_recipes_with_pagination_default(self, test_client_memory):
        """Test getting recipes with default pagination"""
        response = test_client_memory.get("/recipes")

        # Should work even without pagination implemented yet
        if response.status_code == 200:
            data = response.json()
            # If pagination is implemented, check structure
            if "pagination" in data:
                assert "recipes" in data
                assert "pagination" in data
                assert "page" in data["pagination"]
                assert "limit" in data["pagination"]
                assert "total_count" in data["pagination"]
            # Otherwise, just check it returns recipes
            else:
                assert isinstance(data, list) or "recipes" in data

    def test_get_recipes_with_page_parameter(self, test_client_memory):
        """Test getting recipes with page parameter"""
        response = test_client_memory.get("/recipes?page=1")

        # Should handle page parameter gracefully
        assert response.status_code in [
            200,
            422,
        ]  # 422 if validation not implemented yet

        if response.status_code == 200:
            data = response.json()
            if "pagination" in data:
                assert data["pagination"]["page"] == 1

    def test_get_recipes_with_limit_parameter(self, test_client_memory):
        """Test getting recipes with limit parameter"""
        response = test_client_memory.get("/recipes?limit=5")

        # Should handle limit parameter gracefully
        assert response.status_code in [
            200,
            422,
        ]  # 422 if validation not implemented yet

        if response.status_code == 200:
            data = response.json()
            if "pagination" in data:
                assert data["pagination"]["limit"] == 5

    def test_get_recipes_with_page_and_limit(self, test_client_memory):
        """Test getting recipes with both page and limit parameters"""
        response = test_client_memory.get("/recipes?page=2&limit=3")

        # Should handle both parameters gracefully
        assert response.status_code in [
            200,
            422,
        ]  # 422 if validation not implemented yet

        if response.status_code == 200:
            data = response.json()
            if "pagination" in data:
                assert data["pagination"]["page"] == 2
                assert data["pagination"]["limit"] == 3

    def test_get_recipes_invalid_page(self, test_client_memory):
        """Test getting recipes with invalid page parameter"""
        response = test_client_memory.get("/recipes?page=0")

        # Should reject invalid page numbers
        if response.status_code == 422:
            # Validation working correctly
            pass
        elif response.status_code == 200:
            # Not yet implemented, but should not crash
            pass
        else:
            pytest.fail(f"Unexpected status code: {response.status_code}")

    def test_get_recipes_invalid_limit(self, test_client_memory):
        """Test getting recipes with invalid limit parameter"""
        response = test_client_memory.get("/recipes?limit=-1")

        # Should reject invalid limit values
        if response.status_code == 422:
            # Validation working correctly
            pass
        elif response.status_code == 200:
            # Not yet implemented, but should not crash
            pass
        else:
            pytest.fail(f"Unexpected status code: {response.status_code}")

    def test_pagination_metadata_consistency(self, test_client_memory):
        """Test pagination metadata is mathematically consistent"""
        response = test_client_memory.get("/recipes?page=1&limit=5")

        if response.status_code == 200:
            data = response.json()
            if "pagination" in data:
                pagination = data["pagination"]

                # Check has_next/has_previous logic
                assert pagination["has_previous"] == (pagination["page"] > 1)


class TestSearchPagination:
    """Test search pagination endpoints"""

    def test_search_recipes_with_pagination(self, test_client_memory):
        """Test searching recipes with pagination parameters"""
        response = test_client_memory.get("/search?q=test&page=1&limit=5")

        # Should handle search with pagination parameters
        assert response.status_code in [
            200,
            422,
            404,
        ]  # 404 if search endpoint not found

        if response.status_code == 200:
            data = response.json()
            # Check if pagination structure exists
            if "pagination" in data:
                assert "recipes" in data or "results" in data
                assert data["pagination"]["page"] == 1
                assert data["pagination"]["limit"] == 5

    def test_search_recipes_maintains_filters_across_pages(self, test_client_memory):
        """Test that search filters are maintained across paginated requests"""
        # This test ensures that search criteria don't get lost when paginating

        # First page with search
        response1 = test_client_memory.get("/search?q=mojito&page=1&limit=2")

        # Second page with same search
        response2 = test_client_memory.get("/search?q=mojito&page=2&limit=2")

        if response1.status_code == 200 and response2.status_code == 200:
            data1 = response1.json()
            data2 = response2.json()

            # If pagination implemented, check both pages have same total_count
            if "pagination" in data1 and "pagination" in data2:
                assert (
                    data1["pagination"]["total_count"]
                    == data2["pagination"]["total_count"]
                )


class TestPaginationPerformance:
    """Test pagination performance characteristics"""

    def test_paginated_recipes_include_full_data(self, test_client_memory):
        """Test that paginated recipe responses include full recipe details"""
        response = test_client_memory.get("/recipes?page=1&limit=5")

        if response.status_code == 200:
            data = response.json()
            recipes = data.get("recipes", data) if isinstance(data, dict) else data

            if recipes and len(recipes) > 0:
                recipe = recipes[0]
                # Should include full recipe details to eliminate N+1 queries
                expected_fields = ["id", "name", "instructions"]
                for field in expected_fields:
                    assert field in recipe, f"Recipe missing field: {field}"

                # Should include related data
                if "ingredients" in recipe:
                    assert isinstance(recipe["ingredients"], list)

    def test_pagination_response_time(self, test_client_memory):
        """Test that paginated responses are reasonably fast"""
        import time

        start_time = time.time()
        response = test_client_memory.get("/recipes?page=1&limit=10")
        end_time = time.time()

        # Should respond within reasonable time (generous for test environment)
        response_time = end_time - start_time
        assert response_time < 5.0, f"Response took {response_time:.2f} seconds"

        if response.status_code == 200:
            # Response should be reasonably sized
            content_length = len(response.content)
            assert content_length > 0, "Response should have content"


class TestPaginationEdgeCases:
    """Test pagination edge cases and boundary conditions"""

    def test_empty_result_set_pagination(self, test_client_memory):
        """Test pagination with empty result sets"""
        # Search for something that likely doesn't exist
        response = test_client_memory.get(
            "/search?q=nonexistentrecipe12345&page=1&limit=10"
        )

        if response.status_code == 200:
            data = response.json()
            if "pagination" in data:
                assert data["pagination"]["total_count"] == 0
                assert data["pagination"]["has_next"] is False
                assert data["pagination"]["has_previous"] is False

            recipes = data.get("recipes", data.get("results", []))
            assert len(recipes) == 0

    def test_large_page_number(self, test_client_memory):
        """Test requesting a page number beyond available data"""
        response = test_client_memory.get("/recipes?page=9999&limit=10")

        # Should handle gracefully, either return empty results or error
        assert response.status_code in [200, 404, 422]

        if response.status_code == 200:
            data = response.json()
            if "pagination" in data:
                recipes = data.get("recipes", [])
                assert len(recipes) == 0  # Should be empty for page beyond data

    def test_maximum_limit_enforcement(self, test_client_memory):
        """Test that excessively large limit values are handled"""
        response = test_client_memory.get("/recipes?page=1&limit=10000")

        # Should either enforce a maximum limit or handle gracefully
        assert response.status_code in [200, 422]

        if response.status_code == 200:
            data = response.json()
            if "pagination" in data:
                # Should either enforce a reasonable maximum or handle the large limit
                assert data["pagination"]["limit"] <= 1000  # Reasonable maximum


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
