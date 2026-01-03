"""
Tests for combined search functionality (multiple filters together)
"""

import pytest

pytestmark = pytest.mark.asyncio


class TestCombinedSearch:
    """Test recipe search with multiple filters combined"""

    async def test_search_name_and_ingredients(self, test_client_with_data):
        client, app = test_client_with_data
        """Test combining name search with ingredient filters"""
        # Get some recipes to understand what data we have
        all_response = await client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()

        if all_data["recipes"]:
            # Find a recipe with ingredients to test with
            recipe_with_ingredients = None
            for recipe in all_data["recipes"]:
                if recipe.get("ingredients") and len(recipe["ingredients"]) > 0:
                    recipe_with_ingredients = recipe
                    break

            if recipe_with_ingredients:
                recipe_name_part = recipe_with_ingredients["name"][:3]
                ingredient_name = recipe_with_ingredients["ingredients"][0][
                    "ingredient_name"
                ]

                response = await client.get(
                    f"/recipes/search?q={recipe_name_part}&ingredients={ingredient_name}"
                )
                assert response.status_code == 200
                data = response.json()

                assert "recipes" in data
                assert "pagination" in data

                # All returned recipes should match BOTH filters
                for recipe in data["recipes"]:
                    # Check name filter
                    assert recipe_name_part.lower() in recipe["name"].lower()

                    # Check ingredient filter
                    ingredient_names = [
                        ing["ingredient_name"].lower() for ing in recipe["ingredients"]
                    ]
                    assert ingredient_name.lower() in ingredient_names

    async def test_search_name_and_rating(self, test_client_with_data):
        client, app = test_client_with_data
        """Test combining name search with rating filters"""
        min_rating = (
            4.0  # Should match Test Old Fashioned (4.5) and Test Gin Martini (5.0)
        )
        name_query = "test"  # All test recipes contain "test" in their names

        response = await client.get(f"/recipes/search?q={name_query}&min_rating={min_rating}")
        assert response.status_code == 200
        data = response.json()

        assert "recipes" in data
        assert "pagination" in data

        # Should return at least one recipe (Test Old Fashioned and Test Gin Martini both match)
        assert len(data["recipes"]) >= 1

        # All returned recipes should match both filters
        for recipe in data["recipes"]:
            # Check name filter
            assert name_query.lower() in recipe["name"].lower()

            # Check rating filter
            if recipe.get("avg_rating") is not None:
                assert recipe["avg_rating"] >= min_rating

    async def test_search_name_and_tags(self, test_client_with_data):
        client, app = test_client_with_data
        """Test combining name search with tag filters"""
        # Get recipes with tags to create a realistic test
        all_response = await client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()

        recipe_with_tags = None
        for recipe in all_data["recipes"]:
            if recipe.get("tags") and len(recipe["tags"]) > 0:
                recipe_with_tags = recipe
                break

        if recipe_with_tags:
            name_part = recipe_with_tags["name"][:4]
            tag_name = recipe_with_tags["tags"][0]["name"]

            response = await client.get(f"/recipes/search?q={name_part}&tags={tag_name}")
            assert response.status_code == 200
            data = response.json()

            assert "recipes" in data
            assert "pagination" in data

            # All returned recipes should match both filters
            for recipe in data["recipes"]:
                # Check name filter
                assert name_part.lower() in recipe["name"].lower()

                # Check tag filter
                tag_names = [tag["name"].lower() for tag in recipe.get("tags", [])]
                assert tag_name.lower() in tag_names

    async def test_search_ingredients_and_rating(self, test_client_with_data):
        client, app = test_client_with_data
        """Test combining ingredient search with rating filters"""
        # Use common ingredients and moderate rating
        ingredient = "Gin"
        min_rating = 2.5

        response = await client.get(
            f"/recipes/search?ingredients={ingredient}&min_rating={min_rating}"
        )
        assert response.status_code == 200
        data = response.json()

        assert "recipes" in data
        assert "pagination" in data

        # All returned recipes should match both filters
        for recipe in data["recipes"]:
            # Check ingredient filter
            ingredient_names = [
                ing["ingredient_name"].lower() for ing in recipe["ingredients"]
            ]
            assert any(ingredient.lower() in name for name in ingredient_names)

            # Check rating filter
            if recipe.get("avg_rating") is not None:
                assert recipe["avg_rating"] >= min_rating

    async def test_search_ingredients_and_tags(self, test_client_with_data):
        client, app = test_client_with_data
        """Test combining ingredient search with tag filters"""
        # Get data to find realistic combinations
        all_response = await client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()

        # Find a recipe with both ingredients and tags
        suitable_recipe = None
        for recipe in all_data["recipes"]:
            if (
                recipe.get("ingredients")
                and len(recipe["ingredients"]) > 0
                and recipe.get("tags")
                and len(recipe["tags"]) > 0
            ):
                suitable_recipe = recipe
                break

        if suitable_recipe:
            ingredient_name = suitable_recipe["ingredients"][0]["ingredient_name"]
            tag_name = suitable_recipe["tags"][0]["name"]

            response = await client.get(
                f"/recipes/search?ingredients={ingredient_name}&tags={tag_name}"
            )
            assert response.status_code == 200
            data = response.json()

            assert "recipes" in data
            assert "pagination" in data

            # All returned recipes should match both filters
            for recipe in data["recipes"]:
                # Check ingredient filter
                ingredient_names = [
                    ing["ingredient_name"].lower() for ing in recipe["ingredients"]
                ]
                assert ingredient_name.lower() in ingredient_names

                # Check tag filter
                tag_names = [tag["name"].lower() for tag in recipe.get("tags", [])]
                assert tag_name.lower() in tag_names

    async def test_search_rating_and_tags(self, test_client_with_data):
        client, app = test_client_with_data
        """Test combining rating search with tag filters"""
        # Get data to find recipes with tags
        all_response = await client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()

        tag_to_use = None
        for recipe in all_data["recipes"]:
            if recipe.get("tags") and len(recipe["tags"]) > 0:
                tag_to_use = recipe["tags"][0]["name"]
                break

        if tag_to_use:
            min_rating = 2.0

            response = await client.get(
                f"/recipes/search?min_rating={min_rating}&tags={tag_to_use}"
            )
            assert response.status_code == 200
            data = response.json()

            assert "recipes" in data
            assert "pagination" in data

            # All returned recipes should match both filters
            for recipe in data["recipes"]:
                # Check rating filter
                if recipe.get("avg_rating") is not None:
                    assert recipe["avg_rating"] >= min_rating

                # Check tag filter
                tag_names = [tag["name"].lower() for tag in recipe.get("tags", [])]
                assert tag_to_use.lower() in tag_names

    async def test_search_triple_combination(self, test_client_with_data):
        client, app = test_client_with_data
        """Test combining name, ingredient, and rating filters"""
        # Use broad filters to increase chance of matches
        response = await client.get("/recipes/search?q=a&ingredients=Gin&min_rating=1.0")
        assert response.status_code == 200
        data = response.json()

        assert "recipes" in data
        assert "pagination" in data

        # All returned recipes should match all three filters
        for recipe in data["recipes"]:
            # Check name filter (contains 'a')
            assert "a" in recipe["name"].lower()

            # Check ingredient filter
            ingredient_names = [
                ing["ingredient_name"].lower() for ing in recipe["ingredients"]
            ]
            assert any("gin" in name for name in ingredient_names)

            # Check rating filter
            if recipe.get("avg_rating") is not None:
                assert recipe["avg_rating"] >= 1.0

    async def test_search_quadruple_combination(self, test_client_with_data):
        client, app = test_client_with_data
        """Test combining name, ingredient, rating, and tag filters"""
        # Get data to find a realistic combination
        all_response = await client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()

        # Find a recipe with all required elements
        suitable_recipe = None
        for recipe in all_data["recipes"]:
            if (
                recipe.get("ingredients")
                and len(recipe["ingredients"]) > 0
                and recipe.get("tags")
                and len(recipe["tags"]) > 0
            ):
                suitable_recipe = recipe
                break

        if suitable_recipe:
            name_part = suitable_recipe["name"][:2]
            ingredient_name = suitable_recipe["ingredients"][0]["ingredient_name"]
            tag_name = suitable_recipe["tags"][0]["name"]
            min_rating = 0.0  # Very low to ensure matches

            response = await client.get(
                f"/recipes/search?q={name_part}&ingredients={ingredient_name}"
                f"&tags={tag_name}&min_rating={min_rating}"
            )
            assert response.status_code == 200
            data = response.json()

            assert "recipes" in data
            assert "pagination" in data

            # Should return at least the original recipe
            assert data["pagination"]["total_count"] >= 1

    async def test_search_with_pagination_combination(self, test_client_with_data):
        client, app = test_client_with_data
        """Test combining multiple search filters with pagination"""
        response = await client.get("/recipes/search?q=old&min_rating=1.0&page=1&limit=5")
        assert response.status_code == 200
        data = response.json()

        assert "recipes" in data
        assert "pagination" in data

        # Check pagination metadata
        assert "page" in data["pagination"]
        assert "limit" in data["pagination"]
        assert "total_count" in data["pagination"]

        # Should respect limit
        assert len(data["recipes"]) <= 5

        # All results should match filters
        for recipe in data["recipes"]:
            assert "old" in recipe["name"].lower()
            if recipe.get("avg_rating") is not None:
                assert recipe["avg_rating"] >= 1.0

    async def test_search_no_results_combination(self, test_client_with_data):
        client, app = test_client_with_data
        """Test combination that should return no results"""
        # Create a combination that's very unlikely to match
        response = await client.get(
            "/recipes/search?q=NonexistentRecipe123&ingredients=NonexistentIngredient456"
            "&tags=NonexistentTag789&min_rating=4.9"
        )
        assert response.status_code == 200
        data = response.json()

        assert "recipes" in data
        assert "pagination" in data
        assert data["pagination"]["total_count"] == 0
        assert len(data["recipes"]) == 0

    async def test_search_conflicting_filters(self, test_client_with_data):
        client, app = test_client_with_data
        """Test filters that might conflict or produce edge cases"""
        # Very high rating with very specific requirements
        response = await client.get(
            "/recipes/search?min_rating=4.8&max_rating=5.0"
            "&ingredients=Aperol&tags=Summer"
        )
        assert response.status_code == 200
        data = response.json()

        assert "recipes" in data
        assert "pagination" in data

        # May return no results, which is valid
        for recipe in data["recipes"]:
            if recipe.get("avg_rating") is not None:
                assert 4.8 <= recipe["avg_rating"] <= 5.0

    async def test_search_must_and_must_not_ingredients_with_other_filters(
        self, test_client_with_data
    ):
        """Test MUST/MUST_NOT ingredient logic combined with other filters"""
        client, app = test_client_with_data
        response = await client.get(
            "/recipes/search?ingredients=Gin:MUST,Aperol:MUST_NOT"
            "&min_rating=2.0&sort_by=name&sort_order=asc"
        )
        assert response.status_code == 200
        data = response.json()

        assert "recipes" in data
        assert "pagination" in data

        # All results should match all filters
        for recipe in data["recipes"]:
            ingredient_names = [
                ing["ingredient_name"].lower() for ing in recipe["ingredients"]
            ]

            # Must contain gin
            assert any("gin" in name for name in ingredient_names)

            # Must NOT contain aperol
            assert not any("aperol" in name for name in ingredient_names)

            # Must meet rating requirement
            if recipe.get("avg_rating") is not None:
                assert recipe["avg_rating"] >= 2.0

    async def test_search_combination_with_special_characters(self, test_client_with_data):
        """Test combined search with special characters in parameters"""
        client, app = test_client_with_data
        # Test URL encoding and special characters
        response = await client.get(
            "/recipes/search?q=Mom's&tags=Old-Fashioned&ingredients=Rye Whiskey"
        )
        assert response.status_code == 200
        data = response.json()

        assert "recipes" in data
        assert "pagination" in data

    async def test_search_combination_empty_parameters(self, test_client_with_data):
        client, app = test_client_with_data
        """Test combined search with some empty parameters"""
        response = await client.get("/recipes/search?q=&ingredients=Gin&tags=&min_rating=2.0")
        assert response.status_code == 200
        data = response.json()

        assert "recipes" in data
        assert "pagination" in data

        # Should only apply non-empty filters
        for recipe in data["recipes"]:
            ingredient_names = [
                ing["ingredient_name"].lower() for ing in recipe["ingredients"]
            ]
            assert any("gin" in name for name in ingredient_names)

            if recipe.get("avg_rating") is not None:
                assert recipe["avg_rating"] >= 2.0

    async def test_search_combination_result_consistency(self, test_client_with_data):
        """Test that the same combined search returns consistent results"""
        client, app = test_client_with_data
        search_params = "?q=test&min_rating=2.0&sort_by=name&sort_order=asc"

        # Make the same request twice
        response1 = await client.get(f"/recipes/search{search_params}")
        response2 = await client.get(f"/recipes/search{search_params}")

        assert response1.status_code == 200
        assert response2.status_code == 200

        data1 = response1.json()
        data2 = response2.json()

        # Results should be identical
        assert data1["pagination"]["total_count"] == data2["pagination"]["total_count"]
        assert len(data1["recipes"]) == len(data2["recipes"])

        # Recipe IDs should be in the same order
        if data1["recipes"] and data2["recipes"]:
            ids1 = [recipe["id"] for recipe in data1["recipes"]]
            ids2 = [recipe["id"] for recipe in data2["recipes"]]
            assert ids1 == ids2
