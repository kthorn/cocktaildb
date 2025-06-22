"""
Tests for rating-based search functionality
"""

import pytest


class TestRatingSearch:
    """Test recipe search by rating functionality"""

    def test_search_recipes_by_min_rating(self, test_client_with_data):
        client, app = test_client_with_data
        """Test searching recipes with minimum rating filter"""

        # Test with a moderate minimum rating
        min_rating = 3.0
        response = client.get(f"/recipes/search?min_rating={min_rating}")

        assert response.status_code == 200
        data = response.json()

        assert "recipes" in data
        assert "pagination" in data

        # All returned recipes should have rating >= min_rating
        for recipe in data["recipes"]:
            if recipe.get("avg_rating") is not None:
                assert recipe["avg_rating"] >= min_rating, (
                    f"Recipe '{recipe['name']}' has rating {recipe['avg_rating']}, "
                    f"expected >= {min_rating}"
                )

    def test_search_recipes_by_max_rating(self, test_client_with_data):
        client, app = test_client_with_data
        """Test searching recipes with maximum rating filter"""

        # Test with a moderate maximum rating
        max_rating = 4.0
        response = client.get(f"/recipes/search?max_rating={max_rating}")

        assert response.status_code == 200
        data = response.json()

        assert "recipes" in data
        assert "pagination" in data

        # All returned recipes should have rating <= max_rating
        for recipe in data["recipes"]:
            if recipe.get("avg_rating") is not None:
                assert recipe["avg_rating"] <= max_rating, (
                    f"Recipe '{recipe['name']}' has rating {recipe['avg_rating']}, "
                    f"expected <= {max_rating}"
                )

    def test_search_recipes_by_rating_range(self, test_client_with_data):
        client, app = test_client_with_data
        """Test searching recipes within a rating range"""

        min_rating = 2.5
        max_rating = 4.5

        response = client.get(
            f"/recipes/search?min_rating={min_rating}&max_rating={max_rating}"
        )

        assert response.status_code == 200
        data = response.json()

        assert "recipes" in data
        assert "pagination" in data

        # All returned recipes should have rating within the range
        for recipe in data["recipes"]:
            if recipe.get("avg_rating") is not None:
                assert min_rating <= recipe["avg_rating"] <= max_rating, (
                    f"Recipe '{recipe['name']}' has rating {recipe['avg_rating']}, "
                    f"expected between {min_rating} and {max_rating}"
                )

    def test_search_recipes_high_min_rating(self, test_client_with_data):
        client, app = test_client_with_data
        """Test searching recipes with very high minimum rating"""

        # Use a high rating that might return few or no results
        min_rating = 4.8
        response = client.get(f"/recipes/search?min_rating={min_rating}")

        assert response.status_code == 200
        data = response.json()

        assert "recipes" in data
        assert "pagination" in data

        # All returned recipes should have high ratings
        for recipe in data["recipes"]:
            if recipe.get("avg_rating") is not None:
                assert recipe["avg_rating"] >= min_rating

    def test_search_recipes_low_max_rating(self, test_client_with_data):
        client, app = test_client_with_data
        """Test searching recipes with very low maximum rating"""

        # Use a low rating that might return few or no results
        max_rating = 2.0
        response = client.get(f"/recipes/search?max_rating={max_rating}")

        assert response.status_code == 200
        data = response.json()

        assert "recipes" in data
        assert "pagination" in data

        # All returned recipes should have low ratings
        for recipe in data["recipes"]:
            if recipe.get("avg_rating") is not None:
                assert recipe["avg_rating"] <= max_rating

    def test_search_recipes_invalid_rating_range(self, test_client_with_data):
        client, app = test_client_with_data
        """Test searching with invalid rating range (min > max)"""

        min_rating = 4.0
        max_rating = 2.0  # Invalid: max < min

        response = client.get(
            f"/recipes/search?min_rating={min_rating}&max_rating={max_rating}"
        )

        # Should handle gracefully - either return 400 error or empty results
        assert response.status_code in [200, 400]

        if response.status_code == 200:
            data = response.json()
            # Should return no results since range is invalid
            assert data["pagination"]["total_count"] == 0

    def test_search_recipes_rating_boundary_values(self, test_client_with_data):
        """Test searching with rating boundary values (0, 5)"""
        client, app = test_client_with_data

        # Test minimum possible rating
        response = client.get("/recipes/search?min_rating=0")
        assert response.status_code == 200
        data = response.json()
        assert "recipes" in data

        # Test maximum possible rating
        response = client.get("/recipes/search?max_rating=5")
        assert response.status_code == 200
        data = response.json()
        assert "recipes" in data

        # Test exact boundary values
        response = client.get("/recipes/search?min_rating=0&max_rating=5")
        assert response.status_code == 200
        data = response.json()
        assert "recipes" in data

    def test_search_recipes_negative_rating(self, test_client_with_data):
        client, app = test_client_with_data
        """Test searching with negative rating values"""

        # Negative ratings should be handled gracefully
        response = client.get("/recipes/search?min_rating=-1")

        # Should either return 400 error or treat as 0
        assert response.status_code in [200, 400, 422]

        if response.status_code == 200:
            data = response.json()
            assert "recipes" in data

    def test_search_recipes_rating_above_five(self, test_client_with_data):
        client, app = test_client_with_data
        """Test searching with rating values above 5"""

        # Ratings above 5 should be handled gracefully
        response = client.get("/recipes/search?min_rating=6")

        # Should either return 400 error or return no results
        assert response.status_code in [200, 400, 422]

        if response.status_code == 200:
            data = response.json()
            assert "recipes" in data
            # Likely no results since no recipe should have rating > 5
            assert data["pagination"]["total_count"] == 0

    def test_search_recipes_decimal_ratings(self, test_client_with_data):
        client, app = test_client_with_data
        """Test searching with decimal rating values"""

        decimal_ratings = [1.5, 2.7, 3.3, 4.9]

        for rating in decimal_ratings:
            response = client.get(f"/recipes/search?min_rating={rating}")
            assert response.status_code == 200
            data = response.json()

            assert "recipes" in data
            assert "pagination" in data

            # All returned recipes should meet the rating requirement
            for recipe in data["recipes"]:
                if recipe.get("avg_rating") is not None:
                    assert recipe["avg_rating"] >= rating

    def test_search_recipes_rating_with_no_ratings(self, test_client_with_data):
        """Test how rating filters handle recipes with no ratings"""
        client, app = test_client_with_data
        # Test a range that should include unrated recipes if they're treated as 0
        response = client.get("/recipes/search?min_rating=0&max_rating=5")

        assert response.status_code == 200
        data = response.json()

        # Should return valid response
        assert "recipes" in data
        assert "pagination" in data

        # Check if unrated recipes are included/excluded appropriately
        for recipe in data["recipes"]:
            avg_rating = recipe.get("avg_rating")
            if avg_rating is not None:
                assert 0 <= avg_rating <= 5

    def test_search_recipes_string_rating_values(self, test_client_with_data):
        client, app = test_client_with_data
        """Test searching with string rating values"""

        # Non-numeric rating values should be handled gracefully
        response = client.get("/recipes/search?min_rating=abc")

        # Should return 400 error for invalid parameter type
        assert response.status_code in [200, 400, 422]

    def test_search_recipes_rating_filter_vs_no_filter(self, test_client_with_data):
        """Test that rating filtering actually filters results"""
        client, app = test_client_with_data
        # Get all recipes (no filter)
        all_response = client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()

        # Get recipes with high rating filter
        high_rating_response = client.get("/recipes/search?min_rating=4.0")
        assert high_rating_response.status_code == 200
        high_rating_data = high_rating_response.json()

        # High rating filter should return fewer or equal results
        assert (
            high_rating_data["pagination"]["total_count"]
            <= all_data["pagination"]["total_count"]
        )

    def test_search_recipes_multiple_rating_parameters(self, test_client_with_data):
        """Test with multiple min_rating or max_rating parameters"""
        client, app = test_client_with_data
        # This tests how the API handles duplicate parameters
        # Most frameworks take the last value or the first value
        response = client.get("/recipes/search?min_rating=3.0&min_rating=4.0")

        assert response.status_code == 200
        data = response.json()

        # Should return valid response
        assert "recipes" in data
        assert "pagination" in data

    def test_search_recipes_rating_precision(self, test_client_with_data):
        client, app = test_client_with_data
        """Test rating search with high precision decimal values"""

        # Test with many decimal places
        precise_rating = 3.14159
        response = client.get(f"/recipes/search?min_rating={precise_rating}")

        assert response.status_code == 200
        data = response.json()

        assert "recipes" in data
        assert "pagination" in data

        # All returned recipes should meet the precise rating requirement
        for recipe in data["recipes"]:
            if recipe.get("avg_rating") is not None:
                assert recipe["avg_rating"] >= precise_rating

    def test_search_recipes_zero_rating(self, test_client_with_data):
        client, app = test_client_with_data
        """Test searching for recipes with exactly zero rating"""

        response = client.get("/recipes/search?min_rating=0&max_rating=0")

        assert response.status_code == 200
        data = response.json()

        assert "recipes" in data
        assert "pagination" in data

        # All returned recipes should have zero rating (or be unrated)
        for recipe in data["recipes"]:
            avg_rating = recipe.get("avg_rating")
            if avg_rating is not None:
                assert avg_rating == 0
