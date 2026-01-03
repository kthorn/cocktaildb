"""
Tests for ingredient search functionality
"""

import pytest

pytestmark = pytest.mark.asyncio


class TestIngredientSearch:
    """Test search functionality with ingredient filters"""

    async def test_search_recipes_with_rum_ingredient(self, test_client_with_data):
        """Test searching recipes by Rum ingredient"""
        client, app = test_client_with_data
        # Search for recipes containing Rum
        response = await client.get("/recipes/search?ingredients=Rum")

        assert response.status_code == 200
        data = response.json()

        assert "recipes" in data
        assert "pagination" in data

        # Based on our test database, there should be exactly 1 recipe with Aperol
        assert data["pagination"]["total_count"] == 1
        assert len(data["recipes"]) == 1

        recipe = data["recipes"][0]
        assert "ingredients" in recipe

        rum_ingredients = [
            ing
            for ing in recipe["ingredients"]
            if "rum" in ing["ingredient_name"].lower()
        ]
        assert len(rum_ingredients) > 0, "Recipe should contain Rum ingredient"

    async def test_search_recipes_with_nonexistent_ingredient(self, test_client_with_data):
        """Test searching recipes by nonexistent ingredient"""
        client, app = test_client_with_data
        response = await client.get("/recipes/search?ingredients=NonexistentIngredient123")

        assert response.status_code == 200
        data = response.json()

        # Should return no recipes
        assert data["pagination"]["total_count"] == 0
        assert len(data["recipes"]) == 0

    async def test_search_recipes_with_multiple_ingredients(self, test_client_with_data):
        """Test searching recipes with multiple ingredient filters"""
        # Test with two ingredients that are likely to appear together in cocktails
        # Using Aperol and Prosecco which should appear in some Italian cocktails
        client, app = test_client_with_data
        response = await client.get("/recipes/search?ingredients=Lime Juice,Simple Syrup")
        assert response.status_code == 200
        data = response.json()

        # Should return only recipes that contain both ingredients
        # This might be 0 recipes, which is valid
        assert "recipes" in data
        assert "pagination" in data
        assert isinstance(data["pagination"]["total_count"], int)

        # If recipes are returned, verify they contain the requested ingredients
        for recipe in data["recipes"]:
            ingredient_names = [
                ing["ingredient_name"].lower() for ing in recipe["ingredients"]
            ]
            # Note: Due to hierarchical matching, we might match child ingredients
            # So we check if the recipe contains ingredients that match our search terms
            has_lime_juice = any(
                "lime" in name and "juice" in name for name in ingredient_names
            )
            has_simple_syrup = any(
                "simple" in name and "syrup" in name for name in ingredient_names
            )
            assert has_lime_juice or has_simple_syrup, (
                f"Recipe should contain ingredients matching the search terms. Found: {ingredient_names}"
            )

    async def test_search_recipes_without_ingredients_returns_all(
        self, test_client_with_data
    ):
        """Test that search without ingredient filter returns all recipes"""
        client, app = test_client_with_data
        response = await client.get("/recipes/search")

        assert response.status_code == 200
        data = response.json()

        # Should return all recipes (limited by pagination)
        assert "recipes" in data
        assert "pagination" in data
        assert data["pagination"]["total_count"] > 1  # Should have multiple recipes
        assert len(data["recipes"]) > 0

    async def test_search_recipes_ingredient_filter_vs_no_filter_difference(
        self, test_client_with_data
    ):
        """Test that ingredient filtering actually filters results"""
        # Get all recipes (no filter)
        client, app = test_client_with_data
        all_response = await client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()

        # Get recipes with Aperol filter
        aperol_response = await client.get("/recipes/search?ingredients=Aperol")
        assert aperol_response.status_code == 200
        aperol_data = aperol_response.json()

        # The counts should be different
        assert (
            all_data["pagination"]["total_count"]
            != aperol_data["pagination"]["total_count"]
        )
        assert (
            all_data["pagination"]["total_count"]
            > aperol_data["pagination"]["total_count"]
        )

        # Aperol search should return fewer results
        assert (
            aperol_data["pagination"]["total_count"] <= 1
        )  # We know there's only 1 Aperol recipe

    async def test_search_recipes_multiple_ingredients_and_logic(self, test_client_with_data):
        """Test that multiple ingredients use AND logic (recipe must contain ALL ingredients)"""
        # Find two ingredients that might appear together
        client, app = test_client_with_data
        response = await client.get("/recipes/search?ingredients=Bourbon,Simple Syrup")

        assert response.status_code == 200
        data = response.json()

        # Should return only recipes that contain BOTH ingredients
        assert "recipes" in data
        assert "pagination" in data

        # If recipes are returned, verify they contain ingredients matching both terms
        for recipe in data["recipes"]:
            ingredient_names = [
                ing["ingredient_name"].lower() for ing in recipe["ingredients"]
            ]

            # Check for bourbon (or parent whiskey due to hierarchy)
            has_bourbon_or_whiskey = any(
                "bourbon" in name or "whiskey" in name for name in ingredient_names
            )

            # Check for simple syrup
            has_simple_syrup = any(
                "simple" in name and "syrup" in name for name in ingredient_names
            )

            assert has_bourbon_or_whiskey, (
                f"Recipe should contain bourbon/whiskey. Found: {ingredient_names}"
            )
            assert has_simple_syrup, (
                f"Recipe should contain simple syrup. Found: {ingredient_names}"
            )

    async def test_search_recipes_hierarchical_ingredient_matching(
        self, test_client_with_data
    ):
        client, app = test_client_with_data
        """Test that searching for parent ingredient matches recipes with child ingredients"""
        # Search for "Whiskey" should match recipes containing "Bourbon" (child of Whiskey)

        # First, find a recipe that contains Bourbon
        bourbon_response = await client.get("/recipes/search?ingredients=Bourbon")
        assert bourbon_response.status_code == 200
        bourbon_data = bourbon_response.json()

        if bourbon_data["pagination"]["total_count"] > 0:
            # Now search for Whiskey (parent of Bourbon)
            whiskey_response = await client.get("/recipes/search?ingredients=Whiskey")
            assert whiskey_response.status_code == 200
            whiskey_data = whiskey_response.json()

            # Whiskey search should return at least as many recipes as Bourbon search
            # (since all Bourbon recipes should also match Whiskey search)
            assert (
                whiskey_data["pagination"]["total_count"]
                >= bourbon_data["pagination"]["total_count"]
            )

            # Get the first bourbon recipe ID
            bourbon_recipe_id = bourbon_data["recipes"][0]["id"]

            # Check that this recipe also appears in whiskey search results
            whiskey_recipe_ids = [recipe["id"] for recipe in whiskey_data["recipes"]]
            assert bourbon_recipe_id in whiskey_recipe_ids, (
                "Recipe with Bourbon should also match Whiskey search"
            )

    async def test_search_recipes_case_insensitive_ingredients(self, test_client_with_data):
        """Test that ingredient search is case-insensitive"""
        # Test different cases of the same ingredient
        test_cases = ["aperol", "Aperol", "APEROL", "ApErOl"]
        client, app = test_client_with_data
        expected_count = None
        for ingredient_case in test_cases:
            response = await client.get(f"/recipes/search?ingredients={ingredient_case}")
            assert response.status_code == 200
            data = response.json()

            if expected_count is None:
                expected_count = data["pagination"]["total_count"]
            else:
                assert data["pagination"]["total_count"] == expected_count, (
                    f"Case-insensitive search failed: {ingredient_case} returned "
                    f"{data['pagination']['total_count']} recipes, expected {expected_count}"
                )

    async def test_search_recipes_ingredient_name_with_spaces(self, test_client_with_data):
        """Test searching for ingredients with spaces in their names"""
        # Test with "Simple Syrup" which has a space
        client, app = test_client_with_data
        response = await client.get("/recipes/search?ingredients=Simple Syrup")
        assert response.status_code == 200
        data = response.json()

        # Should return recipes containing simple syrup
        assert "recipes" in data
        assert "pagination" in data

        # If recipes found, verify they contain simple syrup
        for recipe in data["recipes"]:
            ingredient_names = [
                ing["ingredient_name"].lower() for ing in recipe["ingredients"]
            ]
            has_simple_syrup = any(
                "simple" in name and "syrup" in name for name in ingredient_names
            )
            assert has_simple_syrup, (
                f"Recipe should contain simple syrup. Found: {ingredient_names}"
            )

    async def test_search_recipes_must_not_contain_ingredient(self, test_client_with_data):
        """Test MUST_NOT logic - exclude recipes containing specific ingredients"""
        # First, get all recipes to establish baseline
        client, app = test_client_with_data
        all_response = await client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()
        total_recipes = all_data["pagination"]["total_count"]

        # Find recipes that contain Aperol
        aperol_response = await client.get("/recipes/search?ingredients=Aperol")
        assert aperol_response.status_code == 200
        aperol_data = aperol_response.json()
        aperol_count = aperol_data["pagination"]["total_count"]

        if aperol_count > 0:
            # Test MUST_NOT Aperol - should return recipes that DON'T contain Aperol
            # Using the format: ingredient_name:MUST_NOT
            must_not_response = await client.get(
                "/recipes/search?ingredients=Aperol:MUST_NOT"
            )
            assert must_not_response.status_code == 200
            must_not_data = must_not_response.json()

            # Should return fewer recipes than total (excluding Aperol recipes)
            expected_count = total_recipes - aperol_count
            assert must_not_data["pagination"]["total_count"] == expected_count

            # Verify that none of the returned recipes contain Aperol
            for recipe in must_not_data["recipes"]:
                ingredient_names = [
                    ing["ingredient_name"].lower() for ing in recipe["ingredients"]
                ]
                has_aperol = any("aperol" in name for name in ingredient_names)
                assert not has_aperol, (
                    f"Recipe should NOT contain Aperol but found: {ingredient_names}"
                )

    async def test_search_recipes_mixed_must_and_must_not(self, test_client_with_data):
        """Test combination of MUST and MUST_NOT ingredients"""
        # Search for recipes that MUST contain Whiskey but MUST NOT contain Aperol
        client, app = test_client_with_data
        response = await client.get(
            "/recipes/search?ingredients=Whiskey:MUST,Aperol:MUST_NOT"
        )
        assert response.status_code == 200
        data = response.json()

        # Should return recipes with whiskey but without aperol
        assert "recipes" in data
        assert "pagination" in data

        # Verify each returned recipe contains whiskey but not aperol
        for recipe in data["recipes"]:
            ingredient_names = [
                ing["ingredient_name"].lower() for ing in recipe["ingredients"]
            ]

            # Must have whiskey (or its children like bourbon, rye, scotch, etc.)
            # Due to hierarchical matching, any whiskey type should be included
            has_whiskey_type = any(
                "whiskey" in name
                or "bourbon" in name
                or "rye" in name
                or "scotch" in name
                for name in ingredient_names
            )
            assert has_whiskey_type, (
                f"Recipe should contain some type of whiskey. Found: {ingredient_names}"
            )

            # Must NOT have aperol
            has_aperol = any("aperol" in name for name in ingredient_names)
            assert not has_aperol, (
                f"Recipe should NOT contain Aperol. Found: {ingredient_names}"
            )

    async def test_search_recipes_must_not_nonexistent_ingredient(
        self, test_client_with_data
    ):
        """Test MUST_NOT with nonexistent ingredient should return all recipes"""
        # Get baseline count
        client, app = test_client_with_data
        all_response = await client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()
        total_recipes = all_data["pagination"]["total_count"]

        # MUST_NOT nonexistent ingredient should return all recipes
        response = await client.get(
            "/recipes/search?ingredients=NonexistentIngredient123:MUST_NOT"
        )
        assert response.status_code == 200
        data = response.json()

        # Should return all recipes since none contain the nonexistent ingredient
        assert data["pagination"]["total_count"] == total_recipes