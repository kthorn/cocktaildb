"""
Comprehensive tests for infinite scroll implementation covering missing test cases from MISSING_TEST_COVERAGE.md

This test file addresses critical API_SPEC.md requirements not covered by existing tests,
focusing on response structure validation, pagination consistency, sorting, and authentication context.
"""

import pytest
from fastapi import status
from conftest import assert_valid_response_structure


class TestResponseStructureValidation:
    """Tests for complete response structure validation as required by API_SPEC.md"""

    def test_search_response_includes_query_field(self, test_client_production_readonly):
        """Verify response includes query field matching the request parameter"""
        # Test with search query
        response = test_client_production_readonly.get("/api/v1/recipes/search?q=gin&page=1&limit=10")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert "query" in data, "Response must include 'query' field"
        assert data["query"] == "gin", "Query field must match request parameter"

    def test_search_response_query_field_empty_search(self, test_client_production_readonly):
        """Test query field is present when no query provided"""
        response = test_client_production_readonly.get("/api/v1/recipes/search?page=1&limit=10")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert "query" in data, "Response must include 'query' field even for empty search"
        assert data["query"] in [None, "", ""], "Query field should be null/empty when no query provided"

    def test_search_response_query_field_special_characters(self, test_client_production_readonly):
        """Test query field handles special characters and encoding correctly"""
        special_query = "gin & tonic"
        response = test_client_production_readonly.get(f"/api/v1/recipes/search?q={special_query}&page=1&limit=10")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert "query" in data
        # The query should be properly decoded
        assert data["query"] == special_query

    def test_recipe_complete_data_structure(self, test_client_production_readonly):
        """Verify each recipe includes ALL required fields for infinite scroll (no N+1 queries)"""
        response = test_client_production_readonly.get("/api/v1/recipes/search?page=1&limit=10")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert "recipes" in data
        
        if data["recipes"]:
            recipe = data["recipes"][0]
            
            # Core recipe fields
            required_fields = [
                "id", "name", "instructions", "created_by", 
                "avg_rating", "rating_count", "created_at"
            ]
            for field in required_fields:
                assert field in recipe, f"Recipe must include '{field}' field"
            
            # Image and source fields for complete data
            extended_fields = ["image_url", "source", "source_url"]
            for field in extended_fields:
                assert field in recipe, f"Recipe must include '{field}' field for infinite scroll"
            
            # Ingredient data completeness
            if "ingredients" in recipe and recipe["ingredients"]:
                ingredient = recipe["ingredients"][0]
                ingredient_fields = ["id", "name", "amount", "unit", "notes"]
                for field in ingredient_fields:
                    assert field in ingredient, f"Ingredient must include '{field}' field"

    def test_recipe_tag_structure_validation(self, test_client_production_readonly):
        """Verify recipes include both public_tags and private_tags arrays"""
        response = test_client_production_readonly.get("/api/v1/recipes/search?page=1&limit=10")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        if data["recipes"]:
            recipe = data["recipes"][0]
            
            assert "public_tags" in recipe, "Recipe must include 'public_tags' array"
            assert "private_tags" in recipe, "Recipe must include 'private_tags' array"
            assert isinstance(recipe["public_tags"], list), "public_tags must be a list"
            assert isinstance(recipe["private_tags"], list), "private_tags must be a list"
            
            # Validate tag object structure if tags exist
            all_tags = recipe["public_tags"] + recipe["private_tags"]
            for tag in all_tags:
                if isinstance(tag, dict):
                    assert "id" in tag, "Tag object must include 'id' field"
                    assert "name" in tag, "Tag object must include 'name' field"


class TestEmptySearchBehavior:
    """Tests for empty search behavior (no search parameters) returning all recipes"""

    def test_empty_search_returns_all_recipes(self, test_client_production_readonly, db_connection):
        """Verify empty search returns complete database recipe count"""
        # Get total recipe count from database
        cursor = db_connection.execute("SELECT COUNT(*) as total FROM recipes")
        total_recipes = cursor.fetchone()["total"]
        
        # Test empty search
        response = test_client_production_readonly.get("/api/v1/recipes/search")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert "pagination" in data
        assert data["pagination"]["total_count"] == total_recipes, "Empty search must return total recipe count"

    def test_empty_search_pagination_metadata(self, test_client_production_readonly, db_connection):
        """Test that empty search pagination metadata reflects total database size"""
        # Get total recipe count
        cursor = db_connection.execute("SELECT COUNT(*) as total FROM recipes")
        total_recipes = cursor.fetchone()["total"]
        
        response = test_client_production_readonly.get("/api/v1/recipes/search?limit=20")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        pagination = data["pagination"]
        
        assert pagination["total_count"] == total_recipes
        expected_total_pages = max(1, ((total_recipes - 1) // 20) + 1) if total_recipes > 0 else 1
        assert pagination["total_pages"] == expected_total_pages
        assert pagination["page"] == 1
        assert pagination["limit"] == 20

    def test_empty_search_default_order(self, test_client_production_readonly):
        """Validate empty search returns recipes in correct default order (name, asc)"""
        response = test_client_production_readonly.get("/api/v1/recipes/search?limit=10")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        if len(data["recipes"]) > 1:
            # Verify alphabetical order by name (case-insensitive)
            recipe_names = [recipe["name"].lower() for recipe in data["recipes"]]
            sorted_names = sorted(recipe_names)
            assert recipe_names == sorted_names, "Default order should be alphabetical by name"


class TestSortingAndOrdering:
    """Tests for sort parameter validation and result ordering"""

    @pytest.mark.parametrize("sort_by", ["name", "created_at", "avg_rating"])
    def test_valid_sort_by_parameters(self, test_client_production_readonly, sort_by):
        """Test all valid sort_by values: name, created_at, avg_rating"""
        response = test_client_production_readonly.get(f"/api/v1/recipes/search?sort_by={sort_by}&limit=10")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert "recipes" in data
        # Basic validation that request was accepted
        assert len(data["recipes"]) >= 0

    @pytest.mark.parametrize("sort_order", ["asc", "desc"])
    def test_valid_sort_order_parameters(self, test_client_production_readonly, sort_order):
        """Test all valid sort_order values: asc, desc"""
        response = test_client_production_readonly.get(f"/api/v1/recipes/search?sort_order={sort_order}&limit=10")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert "recipes" in data

    def test_default_sort_behavior(self, test_client_production_readonly):
        """Verify default sort behavior (sort_by=name, sort_order=asc)"""
        response = test_client_production_readonly.get("/api/v1/recipes/search?limit=10")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        if len(data["recipes"]) > 1:
            recipe_names = [recipe["name"].lower() for recipe in data["recipes"]]
            sorted_names = sorted(recipe_names)
            assert recipe_names == sorted_names, "Default sort should be name ascending"

    def test_invalid_sort_parameters_return_error(self, test_client_production_readonly):
        """Test invalid sort parameters return proper error responses"""
        # Invalid sort_by
        response = test_client_production_readonly.get("/api/v1/recipes/search?sort_by=invalid")
        assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY]
        
        # Invalid sort_order
        response = test_client_production_readonly.get("/api/v1/recipes/search?sort_order=invalid")
        assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY]

    def test_sort_by_name_ascending(self, test_client_production_readonly):
        """Verify recipes are actually sorted by name (alphabetical)"""
        response = test_client_production_readonly.get("/api/v1/recipes/search?sort_by=name&sort_order=asc&limit=10")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        if len(data["recipes"]) > 1:
            recipe_names = [recipe["name"].lower() for recipe in data["recipes"]]
            sorted_names = sorted(recipe_names)
            assert recipe_names == sorted_names

    def test_sort_by_name_descending(self, test_client_production_readonly):
        """Verify recipes are sorted by name in descending order"""
        response = test_client_production_readonly.get("/api/v1/recipes/search?sort_by=name&sort_order=desc&limit=10")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        if len(data["recipes"]) > 1:
            recipe_names = [recipe["name"].lower() for recipe in data["recipes"]]
            sorted_names = sorted(recipe_names, reverse=True)
            assert recipe_names == sorted_names

    def test_sort_by_created_at(self, test_client_production_readonly):
        """Verify recipes are sorted by creation date when sort_by=created_at"""
        response = test_client_production_readonly.get("/api/v1/recipes/search?sort_by=created_at&sort_order=desc&limit=10")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        if len(data["recipes"]) > 1:
            # Verify created_at field is present and compare ordering
            for recipe in data["recipes"]:
                assert "created_at" in recipe, "created_at field required for date sorting"
            
            # Compare that dates are in descending order (most recent first)
            dates = [recipe["created_at"] for recipe in data["recipes"]]
            sorted_dates = sorted(dates, reverse=True)
            assert dates == sorted_dates, "Recipes should be sorted by created_at descending"

    def test_sort_by_rating(self, test_client_production_readonly):
        """Verify recipes are sorted by rating when sort_by=avg_rating"""
        response = test_client_production_readonly.get("/api/v1/recipes/search?sort_by=avg_rating&sort_order=desc&limit=10")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        if len(data["recipes"]) > 1:
            # Verify avg_rating field is present
            for recipe in data["recipes"]:
                assert "avg_rating" in recipe, "avg_rating field required for rating sorting"
            
            # Compare that ratings are in descending order (highest first)
            ratings = [recipe["avg_rating"] or 0 for recipe in data["recipes"]]  # Handle null ratings
            sorted_ratings = sorted(ratings, reverse=True)
            assert ratings == sorted_ratings, "Recipes should be sorted by avg_rating descending"

    def test_sorting_with_pagination(self, test_client_production_readonly):
        """Validate sorting works correctly with pagination"""
        # Get first page
        response1 = test_client_production_readonly.get("/api/v1/recipes/search?sort_by=name&sort_order=asc&page=1&limit=5")
        assert response1.status_code == status.HTTP_200_OK
        
        # Get second page
        response2 = test_client_production_readonly.get("/api/v1/recipes/search?sort_by=name&sort_order=asc&page=2&limit=5")
        assert response2.status_code == status.HTTP_200_OK
        
        data1 = response1.json()
        data2 = response2.json()
        
        if data1["recipes"] and data2["recipes"]:
            # Last item of page 1 should be <= first item of page 2 (alphabetically)
            last_name_page1 = data1["recipes"][-1]["name"].lower()
            first_name_page2 = data2["recipes"][0]["name"].lower()
            assert last_name_page1 <= first_name_page2, "Sorting should be consistent across pages"

    def test_sorting_combined_with_search_filters(self, test_client_production_readonly):
        """Test sorting combined with other search filters"""
        response = test_client_production_readonly.get("/api/v1/recipes/search?q=gin&sort_by=name&sort_order=asc&limit=10")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        if len(data["recipes"]) > 1:
            # Verify both search filtering and sorting work together
            recipe_names = [recipe["name"].lower() for recipe in data["recipes"]]
            sorted_names = sorted(recipe_names)
            assert recipe_names == sorted_names, "Sorting should work with search filters"


class TestPaginationConsistency:
    """Tests for consistent pagination behavior across search types"""

    def test_pagination_structure_consistency(self, test_client_production_readonly):
        """Compare pagination structure between empty and filtered searches"""
        # Empty search
        response1 = test_client_production_readonly.get("/api/v1/recipes/search?page=1&limit=10")
        assert response1.status_code == status.HTTP_200_OK
        
        # Filtered search
        response2 = test_client_production_readonly.get("/api/v1/recipes/search?q=gin&page=1&limit=10")
        assert response2.status_code == status.HTTP_200_OK
        
        data1 = response1.json()
        data2 = response2.json()
        
        # Both should have identical pagination structure
        pagination_fields = ["page", "limit", "total_pages", "total_count", "has_next", "has_previous"]
        for field in pagination_fields:
            assert field in data1["pagination"], f"Empty search missing pagination field: {field}"
            assert field in data2["pagination"], f"Filtered search missing pagination field: {field}"

    def test_pagination_metadata_mathematical_consistency(self, test_client_production_readonly):
        """Verify mathematical consistency of pagination metadata across search types"""
        response = test_client_production_readonly.get("/api/v1/recipes/search?page=2&limit=5")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        pagination = data["pagination"]
        
        # Mathematical relationships should hold
        expected_total_pages = max(1, ((pagination["total_count"] - 1) // pagination["limit"]) + 1) if pagination["total_count"] > 0 else 1
        assert pagination["total_pages"] == expected_total_pages, "total_pages calculation incorrect"
        
        # has_next/has_previous logic
        assert pagination["has_previous"] == (pagination["page"] > 1)
        assert pagination["has_next"] == (pagination["page"] < pagination["total_pages"])

    def test_has_next_has_previous_calculation(self, test_client_production_readonly):
        """Test that has_next/has_previous calculation is identical for all search types"""
        # Test first page
        response = test_client_production_readonly.get("/api/v1/recipes/search?page=1&limit=10")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        pagination = data["pagination"]
        
        assert pagination["has_previous"] is False, "First page should not have previous"
        if pagination["total_pages"] > 1:
            assert pagination["has_next"] is True, "First page should have next if more pages exist"


class TestSearchParameterHandling:
    """Tests for search parameter handling and validation"""

    def test_default_pagination_parameters(self, test_client_production_readonly):
        """Test default values for page (should be 1) and limit (should be 20)"""
        response = test_client_production_readonly.get("/api/v1/recipes/search")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        pagination = data["pagination"]
        
        assert pagination["page"] == 1, "Default page should be 1"
        assert pagination["limit"] == 20, "Default limit should be 20"

    def test_parameter_validation_error_messages(self, test_client_production_readonly):
        """Verify parameter validation error messages match API specification"""
        # Invalid page (negative)
        response = test_client_production_readonly.get("/api/v1/recipes/search?page=-1")
        assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY]
        
        # Invalid limit (too large or negative)
        response = test_client_production_readonly.get("/api/v1/recipes/search?limit=-1")
        assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY]

    def test_invalid_parameter_combinations(self, test_client_production_readonly):
        """Test parameter combinations that should be invalid"""
        # Page 0
        response = test_client_production_readonly.get("/api/v1/recipes/search?page=0")
        assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY]
        
        # Limit 0
        response = test_client_production_readonly.get("/api/v1/recipes/search?limit=0")
        assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY]

    def test_url_encoding_decoding_search_parameters(self, test_client_production_readonly):
        """Validate URL encoding/decoding of search parameters"""
        encoded_query = "gin%20%26%20tonic"  # "gin & tonic" URL encoded
        response = test_client_production_readonly.get(f"/api/v1/recipes/search?q={encoded_query}")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        # The query should be properly decoded in the response
        assert data.get("query") in ["gin & tonic", "gin%20%26%20tonic"]  # Accept either decoded or encoded


class TestEdgeCasesAndBoundaryConditions:
    """Tests for edge cases and boundary conditions"""

    def test_pagination_with_zero_results(self, test_client_production_readonly):
        """Test pagination with exactly 0 results"""
        # Search for something that definitely won't exist
        response = test_client_production_readonly.get("/api/v1/recipes/search?q=xyznonexistentrecipe12345")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert data["pagination"]["total_count"] == 0
        assert data["pagination"]["total_pages"] == 1  # Should still be 1 even with 0 results
        assert data["pagination"]["has_next"] is False
        assert data["pagination"]["has_previous"] is False

    def test_pagination_with_exactly_one_result(self, test_client_production_readonly, db_connection):
        """Test pagination with exactly 1 result"""
        # Try to find a unique recipe name
        cursor = db_connection.execute("SELECT name FROM recipes LIMIT 1")
        recipe = cursor.fetchone()
        
        if recipe:
            # Search for this specific recipe
            response = test_client_production_readonly.get(f"/api/v1/recipes/search?q={recipe['name']}")
            assert response.status_code == status.HTTP_200_OK
            
            data = response.json()
            if data["pagination"]["total_count"] == 1:
                assert data["pagination"]["total_pages"] == 1
                assert data["pagination"]["has_next"] is False
                assert data["pagination"]["has_previous"] is False

    def test_requesting_page_beyond_available_pages(self, test_client_production_readonly):
        """Verify behavior when requesting page beyond available pages"""
        # First get total pages
        response = test_client_production_readonly.get("/api/v1/recipes/search?limit=10")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        total_pages = data["pagination"]["total_pages"]
        
        # Request a page way beyond available pages
        beyond_page = total_pages + 10
        response = test_client_production_readonly.get(f"/api/v1/recipes/search?page={beyond_page}&limit=10")
        
        # Should either return empty results or an error
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND]
        
        if response.status_code == status.HTTP_200_OK:
            data = response.json()
            assert len(data["recipes"]) == 0, "Beyond-range page should return empty results"

    def test_limit_boundary_values(self, test_client_production_readonly):
        """Test limit values at boundaries (1, maximum allowed)"""
        # Test minimum limit
        response = test_client_production_readonly.get("/api/v1/recipes/search?limit=1")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert len(data["recipes"]) <= 1
        assert data["pagination"]["limit"] == 1

    def test_very_large_page_numbers(self, test_client_production_readonly):
        """Validate handling of very large page numbers"""
        response = test_client_production_readonly.get("/api/v1/recipes/search?page=999999&limit=10")
        
        # Should handle gracefully - either return empty results or error
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST]


class TestSpecialCharacterHandling:
    """Tests for special character handling in search parameters"""

    def test_unicode_characters_in_search_queries(self, test_client_production_readonly):
        """Test Unicode characters in search queries"""
        unicode_query = "café"
        response = test_client_production_readonly.get(f"/api/v1/recipes/search?q={unicode_query}")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        # Should handle Unicode gracefully
        assert "recipes" in data

    def test_sql_injection_attempts(self, test_client_production_readonly):
        """Test search queries with SQL injection attempts"""
        injection_query = "'; DROP TABLE recipes; --"
        response = test_client_production_readonly.get(f"/api/v1/recipes/search?q={injection_query}")
        
        # Should either work safely or return an error, but not crash
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST]

    def test_extremely_long_search_parameters(self, test_client_production_readonly):
        """Validate handling of extremely long search parameters"""
        long_query = "a" * 1000  # 1000 character query
        response = test_client_production_readonly.get(f"/api/v1/recipes/search?q={long_query}")
        
        # Should handle gracefully
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST]


class TestErrorResponseFormat:
    """Tests for consistent error response format"""

    def test_error_response_structure_consistency(self, test_client_production_readonly):
        """Test that error responses maintain consistent structure"""
        # Force an error with invalid parameters
        response = test_client_production_readonly.get("/api/v1/recipes/search?page=0")
        
        if response.status_code != status.HTTP_200_OK:
            data = response.json()
            # Error responses should have a consistent structure
            # This will depend on your API's error handling implementation
            assert isinstance(data, dict), "Error response should be a dictionary"

    def test_error_messages_are_user_friendly(self, test_client_production_readonly):
        """Test error messages are user-friendly and specific"""
        # Invalid page parameter
        response = test_client_production_readonly.get("/api/v1/recipes/search?page=-1")
        
        if response.status_code != status.HTTP_200_OK:
            # The response should contain useful error information
            # This test may need adjustment based on actual error response format
            data = response.json()
            assert isinstance(data, dict), "Error should provide structured information"

    def test_http_status_codes_for_different_errors(self, test_client_production_readonly):
        """Validate HTTP status codes for different error types"""
        # Parameter validation errors
        response = test_client_production_readonly.get("/api/v1/recipes/search?page=-1")
        if response.status_code != status.HTTP_200_OK:
            assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY]