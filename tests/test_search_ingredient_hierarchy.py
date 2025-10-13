"""
Tests for ingredient hierarchy fields in search results

These tests verify that search_recipes_paginated() returns ingredients with
both 'full_name' and 'hierarchy' fields, which are essential for frontend tooltips.
"""

import pytest
import os
from unittest.mock import patch
from api.db.db_core import Database


class TestSearchIngredientHierarchy:
    """Test that search results include ingredient hierarchy data"""

    def test_search_returns_full_name_for_root_ingredient(self, memory_db_with_schema):
        """Test that search results include full_name for root-level ingredients"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create root ingredient with unique name
            gin = db.create_ingredient(
                {"name": "TestGin001", "description": "Gin", "parent_id": None}
            )

            # Create recipe with root ingredient
            recipe_data = {
                "name": "Simple Test Gin Cocktail 001",
                "instructions": "Mix gin",
                "ingredients": [{"ingredient_id": gin["id"], "amount": 2.0}],
            }
            db.create_recipe(recipe_data)

            # Search for recipes by recipe name (not ingredient)
            results = db.search_recipes_paginated(
                search_params={"q": "Simple Test Gin Cocktail 001"}, limit=10, offset=0
            )

            assert len(results) == 1
            assert len(results[0]["ingredients"]) == 1

            ingredient = results[0]["ingredients"][0]

            # Verify full_name exists and is correct for root ingredient
            assert "full_name" in ingredient
            assert ingredient["full_name"] == "TestGin001"

    def test_search_returns_hierarchy_for_root_ingredient(self, memory_db_with_schema):
        """Test that search results include hierarchy array for root-level ingredients"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create root ingredient
            vodka = db.create_ingredient(
                {"name": "TestVodka002", "description": "Vodka", "parent_id": None}
            )

            # Create recipe
            recipe_data = {
                "name": "Test Vodka Martini 002",
                "instructions": "Mix vodka",
                "ingredients": [{"ingredient_id": vodka["id"], "amount": 2.0}],
            }
            db.create_recipe(recipe_data)

            # Search for recipes
            results = db.search_recipes_paginated(
                search_params={}, limit=10, offset=0
            )

            assert len(results) >= 1

            # Find our recipe
            recipe = next(r for r in results if r["name"] == "Test Vodka Martini 002")
            ingredient = recipe["ingredients"][0]

            # Verify hierarchy exists and is correct for root ingredient
            assert "hierarchy" in ingredient
            assert ingredient["hierarchy"] == ["TestVodka002"]

    def test_search_returns_full_name_for_nested_ingredient(self, memory_db_with_schema):
        """Test that search results include full_name with parent info for nested ingredients"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create hierarchy: TestSpirits003 -> TestGin003 -> TestLondonGin003
            spirits = db.create_ingredient(
                {"name": "TestSpirits003", "description": "Spirits", "parent_id": None}
            )
            gin = db.create_ingredient(
                {"name": "TestGin003", "description": "Gin", "parent_id": spirits["id"]}
            )
            london_gin = db.create_ingredient(
                {
                    "name": "TestLondonGin003",
                    "description": "London Gin",
                    "parent_id": gin["id"],
                }
            )

            # Create recipe with nested ingredient
            recipe_data = {
                "name": "Test London Martini 003",
                "instructions": "Use London Dry Gin",
                "ingredients": [{"ingredient_id": london_gin["id"], "amount": 2.0}],
            }
            db.create_recipe(recipe_data)

            # Search for recipes
            results = db.search_recipes_paginated(
                search_params={"q": "London Martini 003"}, limit=10, offset=0
            )

            assert len(results) == 1
            ingredient = results[0]["ingredients"][0]

            # Verify full_name includes parent hierarchy
            assert "full_name" in ingredient
            assert "TestLondonGin003" in ingredient["full_name"]
            assert "TestGin003" in ingredient["full_name"]
            assert "TestSpirits003" in ingredient["full_name"]
            # Format should be: "TestLondonGin003 [TestGin003;TestSpirits003]"
            assert ingredient["full_name"] == "TestLondonGin003 [TestGin003;TestSpirits003]"

    def test_search_returns_hierarchy_array_for_nested_ingredient(self, memory_db_with_schema):
        """Test that search results include hierarchy array for nested ingredients"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create hierarchy: TestSpirits004 -> TestWhiskey004 -> TestBourbon004
            spirits = db.create_ingredient(
                {"name": "TestSpirits004", "description": "Spirits", "parent_id": None}
            )
            whiskey = db.create_ingredient(
                {"name": "TestWhiskey004", "description": "Whiskey", "parent_id": spirits["id"]}
            )
            bourbon = db.create_ingredient(
                {
                    "name": "TestBourbon004",
                    "description": "Bourbon",
                    "parent_id": whiskey["id"],
                }
            )

            # Create recipe
            recipe_data = {
                "name": "Test Old Fashioned 004",
                "instructions": "Use bourbon",
                "ingredients": [{"ingredient_id": bourbon["id"], "amount": 2.0}],
            }
            db.create_recipe(recipe_data)

            # Search for recipes
            results = db.search_recipes_paginated(
                search_params={}, limit=10, offset=0
            )

            # Find our recipe
            recipe = next(r for r in results if r["name"] == "Test Old Fashioned 004")
            ingredient = recipe["ingredients"][0]

            # Verify hierarchy array is in root-to-leaf order
            assert "hierarchy" in ingredient
            assert ingredient["hierarchy"] == ["TestSpirits004", "TestWhiskey004", "TestBourbon004"]

    def test_search_returns_hierarchy_for_deep_nesting(self, memory_db_with_schema):
        """Test hierarchy fields for deeply nested ingredients (4 levels)"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create deep hierarchy: TestSpirits005 -> TestWhiskey005 -> TestBourbon005 -> TestMakers005
            spirits = db.create_ingredient(
                {"name": "TestSpirits005", "description": "Spirits", "parent_id": None}
            )
            whiskey = db.create_ingredient(
                {"name": "TestWhiskey005", "description": "Whiskey", "parent_id": spirits["id"]}
            )
            bourbon = db.create_ingredient(
                {"name": "TestBourbon005", "description": "Bourbon", "parent_id": whiskey["id"]}
            )
            makers = db.create_ingredient(
                {
                    "name": "TestMakers005",
                    "description": "Bourbon brand",
                    "parent_id": bourbon["id"],
                }
            )

            # Create recipe
            recipe_data = {
                "name": "Test Premium Bourbon 005",
                "instructions": "Use Maker's Mark",
                "ingredients": [{"ingredient_id": makers["id"], "amount": 2.0}],
            }
            db.create_recipe(recipe_data)

            # Search for recipes
            results = db.search_recipes_paginated(
                search_params={"q": "Premium Bourbon 005"}, limit=10, offset=0
            )

            assert len(results) == 1
            ingredient = results[0]["ingredients"][0]

            # Verify full_name
            assert "full_name" in ingredient
            assert ingredient["full_name"] == "TestMakers005 [TestBourbon005;TestWhiskey005;TestSpirits005]"

            # Verify hierarchy array
            assert "hierarchy" in ingredient
            assert ingredient["hierarchy"] == ["TestSpirits005", "TestWhiskey005", "TestBourbon005", "TestMakers005"]

    def test_search_multiple_ingredients_with_mixed_hierarchy(self, memory_db_with_schema):
        """Test that search handles recipes with multiple ingredients at different hierarchy levels"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create hierarchy
            spirits = db.create_ingredient(
                {"name": "TestSpirits006", "description": "Spirits", "parent_id": None}
            )
            gin = db.create_ingredient(
                {"name": "TestGin006", "description": "Gin", "parent_id": spirits["id"]}
            )

            # Create root-level ingredient
            lime = db.create_ingredient(
                {"name": "TestLime006", "description": "Lime", "parent_id": None}
            )

            # Create recipe with both nested and root ingredients
            recipe_data = {
                "name": "Test Gimlet 006",
                "instructions": "Mix gin and lime",
                "ingredients": [
                    {"ingredient_id": gin["id"], "amount": 2.0},
                    {"ingredient_id": lime["id"], "amount": 0.75},
                ],
            }
            db.create_recipe(recipe_data)

            # Search for recipes
            results = db.search_recipes_paginated(
                search_params={"q": "Gimlet 006"}, limit=10, offset=0
            )

            assert len(results) == 1
            assert len(results[0]["ingredients"]) == 2

            # Check nested ingredient (Gin)
            gin_ingredient = next(
                i for i in results[0]["ingredients"] if i["ingredient_id"] == gin["id"]
            )
            assert "full_name" in gin_ingredient
            assert gin_ingredient["full_name"] == "TestGin006 [TestSpirits006]"
            assert "hierarchy" in gin_ingredient
            assert gin_ingredient["hierarchy"] == ["TestSpirits006", "TestGin006"]

            # Check root ingredient (Lime)
            lime_ingredient = next(
                i for i in results[0]["ingredients"] if i["ingredient_id"] == lime["id"]
            )
            assert "full_name" in lime_ingredient
            assert lime_ingredient["full_name"] == "TestLime006"
            assert "hierarchy" in lime_ingredient
            assert lime_ingredient["hierarchy"] == ["TestLime006"]

    def test_search_empty_results_does_not_crash(self, memory_db_with_schema):
        """Test that searching with no results doesn't crash when processing ingredients"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Search for non-existent recipe
            results = db.search_recipes_paginated(
                search_params={"q": "NonexistentRecipeXYZ12345"}, limit=10, offset=0
            )

            # Should return empty list, not crash
            assert results == []

    def test_search_with_ingredient_filter_includes_hierarchy(self, memory_db_with_schema):
        """Test that ingredient filtering in search still returns hierarchy fields"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create hierarchy
            spirits = db.create_ingredient(
                {"name": "TestSpirits007", "description": "Spirits", "parent_id": None}
            )
            rum = db.create_ingredient(
                {"name": "TestRum007", "description": "Rum", "parent_id": spirits["id"]}
            )
            dark_rum = db.create_ingredient(
                {"name": "TestDarkRum007", "description": "Dark Rum", "parent_id": rum["id"]}
            )

            # Create recipe
            recipe_data = {
                "name": "Test Dark Stormy 007",
                "instructions": "Use dark rum",
                "ingredients": [{"ingredient_id": dark_rum["id"], "amount": 2.0}],
            }
            db.create_recipe(recipe_data)

            # Search with ingredient filter
            results = db.search_recipes_paginated(
                search_params={"ingredients": ["TestRum007"]}, limit=10, offset=0
            )

            assert len(results) >= 1

            # Find our recipe
            recipe = next(r for r in results if r["name"] == "Test Dark Stormy 007")
            ingredient = recipe["ingredients"][0]

            # Verify hierarchy fields are present even with ingredient filtering
            assert "full_name" in ingredient
            assert ingredient["full_name"] == "TestDarkRum007 [TestRum007;TestSpirits007]"
            assert "hierarchy" in ingredient
            assert ingredient["hierarchy"] == ["TestSpirits007", "TestRum007", "TestDarkRum007"]

    def test_search_pagination_preserves_hierarchy(self, memory_db_with_schema):
        """Test that pagination doesn't affect hierarchy field generation"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create hierarchy
            spirits = db.create_ingredient(
                {"name": "TestSpirits008", "description": "Spirits", "parent_id": None}
            )
            tequila = db.create_ingredient(
                {"name": "TestTequila008", "description": "Tequila", "parent_id": spirits["id"]}
            )

            # Create multiple recipes
            for i in range(3):
                recipe_data = {
                    "name": f"Test Tequila Cocktail 008-{i}",
                    "instructions": f"Recipe {i}",
                    "ingredients": [{"ingredient_id": tequila["id"], "amount": 2.0}],
                }
                db.create_recipe(recipe_data)

            # Search with pagination (page 1)
            results_page1 = db.search_recipes_paginated(
                search_params={"q": "Tequila Cocktail 008"}, limit=2, offset=0
            )

            # Search with pagination (page 2)
            results_page2 = db.search_recipes_paginated(
                search_params={"q": "Tequila Cocktail 008"}, limit=2, offset=2
            )

            # Verify all results have hierarchy fields
            all_results = results_page1 + results_page2
            for recipe in all_results:
                if recipe["ingredients"]:
                    ingredient = recipe["ingredients"][0]
                    assert "full_name" in ingredient
                    assert ingredient["full_name"] == "TestTequila008 [TestSpirits008]"
                    assert "hierarchy" in ingredient
                    assert ingredient["hierarchy"] == ["TestSpirits008", "TestTequila008"]

    def test_search_with_user_context_includes_hierarchy(self, memory_db_with_schema):
        """Test that searching with user context still returns hierarchy fields"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create ingredient
            vodka = db.create_ingredient(
                {"name": "TestVodka009", "description": "Vodka", "parent_id": None}
            )

            # Create recipe
            recipe_data = {
                "name": "Test User Vodka Martini 009",
                "instructions": "Mix vodka",
                "ingredients": [{"ingredient_id": vodka["id"], "amount": 2.0}],
            }
            db.create_recipe(recipe_data)

            # Search with user context
            results = db.search_recipes_paginated(
                search_params={}, limit=10, offset=0, user_id="test-user-123"
            )

            recipe = next(r for r in results if r["name"] == "Test User Vodka Martini 009")
            ingredient = recipe["ingredients"][0]

            # Verify hierarchy fields present even with user context
            assert "full_name" in ingredient
            assert ingredient["full_name"] == "TestVodka009"
            assert "hierarchy" in ingredient
            assert ingredient["hierarchy"] == ["TestVodka009"]
