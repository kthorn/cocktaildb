"""
Tests for tag-based search functionality
"""

import pytest


class TestTagSearch:
    """Test recipe search by tags functionality"""

    def test_search_recipes_by_single_tag(self, test_client_with_data):
        client, app = test_client_with_data
        """Test searching recipes by a single tag"""
        # First, get all recipes to find available tags
        all_response = client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()

        # Find a recipe with tags to test with
        recipe_with_tags = None
        for recipe in all_data["recipes"]:
            if recipe.get("tags") and len(recipe["tags"]) > 0:
                recipe_with_tags = recipe
                break

        if recipe_with_tags:
            # Use the first tag from this recipe
            test_tag = recipe_with_tags["tags"][0]["name"]

            response = client.get(
                f"/recipes/search?tags={test_tag}"
            )
            assert response.status_code == 200
            data = response.json()

            assert "recipes" in data
            assert "pagination" in data
            assert data["pagination"]["total_count"] >= 1

            # All returned recipes should have the searched tag
            for recipe in data["recipes"]:
                tag_names = [tag["name"].lower() for tag in recipe.get("tags", [])]
                assert test_tag.lower() in tag_names, (
                    f"Recipe '{recipe['name']}' should contain tag '{test_tag}'. "
                    f"Found tags: {tag_names}"
                )

    def test_search_recipes_by_multiple_tags(self, test_client_with_data):
        client, app = test_client_with_data
        """Test searching recipes by multiple tags (AND logic)"""
        # Find a recipe with multiple tags
        all_response = client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()

        recipe_with_multiple_tags = None
        for recipe in all_data["recipes"]:
            if recipe.get("tags") and len(recipe["tags"]) >= 2:
                recipe_with_multiple_tags = recipe
                break

        if recipe_with_multiple_tags:
            # Use the first two tags
            tag1 = recipe_with_multiple_tags["tags"][0]["name"]
            tag2 = recipe_with_multiple_tags["tags"][1]["name"]

            response = client.get(
                f"/recipes/search?tags={tag1},{tag2}"
            )
            assert response.status_code == 200
            data = response.json()

            assert "recipes" in data
            assert "pagination" in data

            # All returned recipes should have BOTH tags
            for recipe in data["recipes"]:
                tag_names = [tag["name"].lower() for tag in recipe.get("tags", [])]
                assert tag1.lower() in tag_names, (
                    f"Recipe '{recipe['name']}' should contain tag '{tag1}'"
                )
                assert tag2.lower() in tag_names, (
                    f"Recipe '{recipe['name']}' should contain tag '{tag2}'"
                )

    def test_search_recipes_by_nonexistent_tag(self, test_client_with_data):
        client, app = test_client_with_data
        """Test searching recipes by a tag that doesn't exist"""
        response = client.get(
            "/recipes/search?tags=NonexistentTag123456"
        )
        assert response.status_code == 200
        data = response.json()

        # Should return no results
        assert data["pagination"]["total_count"] == 0
        assert len(data["recipes"]) == 0

    def test_search_recipes_by_empty_tag(self, test_client_with_data):
        client, app = test_client_with_data
        """Test searching with empty tag parameter"""
        response = client.get("/recipes/search?tags=")
        assert response.status_code == 200
        data = response.json()

        # Empty tag should return all recipes (same as no filter)
        all_response = client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()

        assert (
            data["pagination"]["total_count"] == all_data["pagination"]["total_count"]
        )

    def test_search_recipes_tag_filter_vs_no_filter(
        self, test_client_with_data
    ):
        """Test that tag filtering actually filters results"""
        # Get all recipes (no filter)
        all_response = client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()

        # Find a specific tag to filter by
        specific_tag = None
        for recipe in all_data["recipes"]:
            if recipe.get("tags") and len(recipe["tags"]) > 0:
                specific_tag = recipe["tags"][0]["name"]
                break

        if specific_tag:
            tag_response = client.get(
                f"/recipes/search?tags={specific_tag}"
            )
            assert tag_response.status_code == 200
            tag_data = tag_response.json()

            # Tag search should typically return fewer or equal results
            assert (
                tag_data["pagination"]["total_count"]
                <= all_data["pagination"]["total_count"]
            )

    def test_search_recipes_by_duplicate_tags(self, test_client_with_data):
        client, app = test_client_with_data
        """Test searching with duplicate tags in the list"""
        # Get a tag to duplicate
        all_response = client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()

        tag_to_duplicate = None
        for recipe in all_data["recipes"]:
            if recipe.get("tags") and len(recipe["tags"]) > 0:
                tag_to_duplicate = recipe["tags"][0]["name"]
                break

        if tag_to_duplicate:
            # Search with duplicate tags
            response = client.get(
                f"/recipes/search?tags={tag_to_duplicate},{tag_to_duplicate}"
            )
            assert response.status_code == 200
            data = response.json()

            # Should handle duplicates gracefully (same as single tag search)
            single_response = client.get(
                f"/recipes/search?tags={tag_to_duplicate}"
            )
            assert single_response.status_code == 200
            single_data = single_response.json()

            assert (
                data["pagination"]["total_count"]
                == single_data["pagination"]["total_count"]
            )

    def test_search_recipes_url_encoded_tags(self, test_client_with_data):
        client, app = test_client_with_data
        """Test that URL-encoded tag names work correctly"""
        import urllib.parse

        # Test with a tag that needs URL encoding
        tag_with_spaces = "Test Tag"
        encoded_tag = urllib.parse.quote_plus(tag_with_spaces)

        response = client.get(
            f"/recipes/search?tags={encoded_tag}"
        )
        assert response.status_code == 200
        data = response.json()

        # Should return valid response
        assert "recipes" in data
        assert "pagination" in data

    def test_search_recipes_by_numeric_tags(self, test_client_with_data):
        client, app = test_client_with_data
        """Test searching for purely numeric tags"""
        numeric_tags = ["2023", "1", "21", "100"]

        for tag in numeric_tags:
            response = client.get(
                f"/recipes/search?tags={tag}"
            )
            assert response.status_code == 200
            data = response.json()

            # Should return valid response
            assert "recipes" in data
            assert "pagination" in data
