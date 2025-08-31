"""
Search and Pagination Testing
Comprehensive tests for recipe search functionality, pagination,
and complex query scenarios
"""

import pytest
import sqlite3
import os
from typing import Dict, Any, List
from unittest.mock import patch

from api.db.db_core import Database


class TestBasicRecipeSearch:
    """Test basic recipe search functionality"""

    def test_search_recipes_by_name(self, memory_db_with_schema):
        """Test searching recipes by name"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create test recipes
            recipes = [
                {"name": "Classic Martini", "instructions": "Gin and vermouth"},
                {"name": "Manhattan", "instructions": "Whiskey and vermouth"},
                {
                    "name": "Dirty Martini",
                    "instructions": "Gin, vermouth, and olive brine",
                },
            ]

            for recipe_data in recipes:
                db.create_recipe(recipe_data)

            # Search for "martini"
            search_params = {"name": "martini"}
            results = db.search_recipes(search_params)

            assert len(results) == 2
            result_names = {recipe["name"] for recipe in results}
            assert "Classic Martini" in result_names
            assert "Dirty Martini" in result_names
            assert "Manhattan" not in result_names

    def test_search_recipes_case_insensitive(self, memory_db_with_schema):
        """Test that name search is case insensitive"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            db.create_recipe({"name": "Piña Colada", "instructions": "Tropical drink"})

            # Test various cases
            for search_term in ["pina", "PINA", "Pina", "colada", "COLADA"]:
                search_params = {"name": search_term}
                results = db.search_recipes(search_params)

                assert len(results) == 1
                assert results[0]["name"] == "Piña Colada"

    def test_search_recipes_partial_match(self, memory_db_with_schema):
        """Test that name search supports partial matches"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            db.create_recipe(
                {"name": "Old Fashioned", "instructions": "Whiskey cocktail"}
            )

            # Test partial matches
            partial_searches = ["old", "fashion", "fashioned", "Old F"]

            for search_term in partial_searches:
                search_params = {"name": search_term}
                results = db.search_recipes(search_params)

                assert len(results) == 1
                assert results[0]["name"] == "Old Fashioned"

    def test_search_recipes_no_results(self, memory_db_with_schema):
        """Test search with no matching results"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            db.create_recipe({"name": "Martini", "instructions": "Classic cocktail"})

            search_params = {"name": "nonexistent"}
            results = db.search_recipes(search_params)

            assert len(results) == 0


class TestRatingBasedSearch:
    """Test searching recipes by rating"""

    def test_search_recipes_by_min_rating(self, memory_db_with_schema):
        """Test searching recipes by minimum rating"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipes
            recipe1 = db.create_recipe({"name": "Great Recipe", "instructions": "Test"})
            recipe2 = db.create_recipe({"name": "Good Recipe", "instructions": "Test"})
            recipe3 = db.create_recipe({"name": "Poor Recipe", "instructions": "Test"})

            # Add ratings
            db.set_rating(
                {
                    "cognito_user_id": "user1",
                    "cognito_username": "user1",
                    "recipe_id": recipe1["id"],
                    "rating": 5,
                }
            )
            db.set_rating(
                {
                    "cognito_user_id": "user1",
                    "cognito_username": "user1",
                    "recipe_id": recipe2["id"],
                    "rating": 3,
                }
            )
            db.set_rating(
                {
                    "cognito_user_id": "user1",
                    "cognito_username": "user1",
                    "recipe_id": recipe3["id"],
                    "rating": 2,
                }
            )

            # Search for recipes with rating >= 4
            search_params = {"min_rating": 4.0}
            results = db.search_recipes(search_params)

            assert len(results) == 1
            assert results[0]["name"] == "Great Recipe"
            assert results[0]["avg_rating"] == 5.0

    def test_search_recipes_by_exact_rating(self, memory_db_with_schema):
        """Test searching recipes by exact minimum rating"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipe with specific rating
            recipe = db.create_recipe(
                {"name": "Three Star Recipe", "instructions": "Test"}
            )
            db.set_rating(
                {
                    "cognito_user_id": "user1",
                    "cognito_username": "user1",
                    "recipe_id": recipe["id"],
                    "rating": 3,
                }
            )

            # Search for exactly 3.0 rating
            search_params = {"min_rating": 3.0}
            results = db.search_recipes(search_params)

            assert len(results) == 1
            assert results[0]["avg_rating"] == 3.0

            # Search for 3.1 rating (should find nothing)
            search_params = {"min_rating": 3.1}
            results = db.search_recipes(search_params)

            assert len(results) == 0

    def test_search_recipes_unrated_excluded(self, memory_db_with_schema):
        """Test that unrated recipes are excluded from rating searches"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create rated and unrated recipes
            rated_recipe = db.create_recipe(
                {"name": "Rated Recipe", "instructions": "Test"}
            )
            unrated_recipe = db.create_recipe(
                {"name": "Unrated Recipe", "instructions": "Test"}
            )

            # Rate only one recipe
            db.set_rating(
                {
                    "cognito_user_id": "user1",
                    "cognito_username": "user1",
                    "recipe_id": rated_recipe["id"],
                    "rating": 4,
                }
            )

            # Search with minimum rating
            search_params = {"min_rating": 1.0}
            results = db.search_recipes(search_params)

            assert len(results) == 1
            assert results[0]["name"] == "Rated Recipe"


class TestTagBasedSearch:
    """Test searching recipes by tags"""

    def test_search_recipes_by_single_tag(self, memory_db_with_schema):
        """Test searching recipes by a single tag"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipes and tags
            recipe1 = db.create_recipe(
                {"name": "Classic Martini", "instructions": "Test"}
            )
            recipe2 = db.create_recipe({"name": "Manhattan", "instructions": "Test"})
            recipe3 = db.create_recipe({"name": "Margarita", "instructions": "Test"})

            classic_tag = db.create_public_tag("classic")
            strong_tag = db.create_public_tag("strong")

            # Tag recipes
            db.add_public_tag_to_recipe(recipe1["id"], classic_tag["id"])
            db.add_public_tag_to_recipe(recipe2["id"], classic_tag["id"])
            db.add_public_tag_to_recipe(recipe2["id"], strong_tag["id"])
            db.add_public_tag_to_recipe(recipe3["id"], strong_tag["id"])

            # Search by "classic" tag
            search_params = {"tags": ["classic"]}
            results = db.search_recipes(search_params)

            assert len(results) == 2
            result_names = {recipe["name"] for recipe in results}
            assert "Classic Martini" in result_names
            assert "Manhattan" in result_names
            assert "Margarita" not in result_names

    def test_search_recipes_by_nonexistent_tag(self, memory_db_with_schema):
        """Test searching by non-existent tag"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            search_params = {"tags": ["nonexistent"]}
            results = db.search_recipes(search_params)

            assert len(results) == 0


class TestIngredientBasedSearch:
    """Test searching recipes by ingredients"""

    def test_search_recipes_by_ingredient_must(self, memory_db_with_schema):
        """Test searching recipes that MUST contain specific ingredients"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create ingredients
            gin = db.create_ingredient(
                {"name": "Gin1", "description": "Gin1", "parent_id": None}
            )
            vodka = db.create_ingredient(
                {"name": "Vodka1", "description": "Vodka1", "parent_id": None}
            )
            vermouth = db.create_ingredient(
                {"name": "Vermouth", "description": "Vermouth", "parent_id": None}
            )

            # Create recipes
            martini = db.create_recipe(
                {
                    "name": "Gin Martini",
                    "instructions": "Test",
                    "ingredients": [
                        {"ingredient_id": gin["id"], "amount": 2.0},
                        {"ingredient_id": vermouth["id"], "amount": 0.5},
                    ],
                }
            )

            vodka_martini = db.create_recipe(
                {
                    "name": "Vodka Martini",
                    "instructions": "Test",
                    "ingredients": [
                        {"ingredient_id": vodka["id"], "amount": 2.0},
                        {"ingredient_id": vermouth["id"], "amount": 0.5},
                    ],
                }
            )

            gin_tonic = db.create_recipe(
                {
                    "name": "Gin and Tonic",
                    "instructions": "Test",
                    "ingredients": [{"ingredient_id": gin["id"], "amount": 2.0}],
                }
            )

            # Search for recipes that MUST contain gin
            search_params = {"ingredients": [{"id": gin["id"], "operator": "MUST"}]}
            results = db.search_recipes(search_params)

            assert len(results) == 2
            result_names = {recipe["name"] for recipe in results}
            assert "Gin Martini" in result_names
            assert "Gin and Tonic" in result_names
            assert "Vodka Martini" not in result_names

    def test_search_recipes_by_ingredient_must_not(self, memory_db_with_schema):
        """Test searching recipes that MUST NOT contain specific ingredients"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create ingredients
            gin = db.create_ingredient(
                {"name": "Gin1", "description": "Gin1", "parent_id": None}
            )
            vodka = db.create_ingredient(
                {"name": "Vodka1", "description": "Vodka1", "parent_id": None}
            )
            rum = db.create_ingredient(
                {"name": "Rum1", "description": "Rum1", "parent_id": None}
            )

            # Create recipes
            gin_drink = db.create_recipe(
                {
                    "name": "Gin Drink",
                    "instructions": "Test",
                    "ingredients": [{"ingredient_id": gin["id"], "amount": 2.0}],
                }
            )

            vodka_drink = db.create_recipe(
                {
                    "name": "Vodka Drink",
                    "instructions": "Test",
                    "ingredients": [{"ingredient_id": vodka["id"], "amount": 2.0}],
                }
            )

            rum_drink = db.create_recipe(
                {
                    "name": "Rum Drink",
                    "instructions": "Test",
                    "ingredients": [{"ingredient_id": rum["id"], "amount": 2.0}],
                }
            )

            # Search for recipes that MUST NOT contain gin
            search_params = {"ingredients": [{"id": gin["id"], "operator": "MUST_NOT"}]}
            results = db.search_recipes(search_params)

            assert len(results) == 2
            result_names = {recipe["name"] for recipe in results}
            assert "Vodka Drink" in result_names
            assert "Rum Drink" in result_names
            assert "Gin Drink" not in result_names

    def test_search_recipes_by_ingredient_hierarchy(self, memory_db_with_schema):
        """Test searching recipes using ingredient hierarchy (path-based)"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create ingredient hierarchy
            spirits = db.create_ingredient(
                {"name": "Spirits", "description": "Spirits", "parent_id": None}
            )
            gin = db.create_ingredient(
                {"name": "Gin1", "description": "Gin1", "parent_id": spirits["id"]}
            )
            london_gin = db.create_ingredient(
                {
                    "name": "London Dry Gin",
                    "description": "London Gin",
                    "parent_id": gin["id"],
                }
            )
            vodka = db.create_ingredient(
                {"name": "Vodka1", "description": "Vodka1", "parent_id": spirits["id"]}
            )

            # Create recipes with specific gin types
            recipe1 = db.create_recipe(
                {
                    "name": "Premium Martini",
                    "instructions": "Test",
                    "ingredients": [{"ingredient_id": london_gin["id"], "amount": 2.0}],
                }
            )

            recipe2 = db.create_recipe(
                {
                    "name": "Standard Martini",
                    "instructions": "Test",
                    "ingredients": [{"ingredient_id": gin["id"], "amount": 2.0}],
                }
            )

            recipe3 = db.create_recipe(
                {
                    "name": "Vodka Drink",
                    "instructions": "Test",
                    "ingredients": [{"ingredient_id": vodka["id"], "amount": 2.0}],
                }
            )

            # Search for recipes containing "Gin" (should find both gin types)
            search_params = {"ingredients": [{"id": gin["id"], "operator": "MUST"}]}
            results = db.search_recipes(search_params)

            assert len(results) == 2
            result_names = {recipe["name"] for recipe in results}
            assert "Premium Martini" in result_names  # London Dry Gin is a child of Gin
            assert "Standard Martini" in result_names
            assert "Vodka Drink" not in result_names

            # Search for recipes containing "Spirits" (should find all)
            search_params = {"ingredients": [{"id": spirits["id"], "operator": "MUST"}]}
            results = db.search_recipes(search_params)

            assert len(results) == 3  # All recipes contain some type of spirit

    def test_search_recipes_by_multiple_ingredient_constraints(
        self, memory_db_with_schema
    ):
        """Test searching with multiple ingredient constraints"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create ingredients
            gin = db.create_ingredient(
                {"name": "Gin1", "description": "Gin1", "parent_id": None}
            )
            vodka = db.create_ingredient(
                {"name": "Vodka1", "description": "Vodka1", "parent_id": None}
            )
            vermouth = db.create_ingredient(
                {"name": "Vermouth", "description": "Vermouth", "parent_id": None}
            )
            olive = db.create_ingredient(
                {"name": "Olive", "description": "Olive", "parent_id": None}
            )

            # Create recipes
            gin_martini = db.create_recipe(
                {
                    "name": "Gin Martini",
                    "instructions": "Test",
                    "ingredients": [
                        {"ingredient_id": gin["id"], "amount": 2.0},
                        {"ingredient_id": vermouth["id"], "amount": 0.5},
                    ],
                }
            )

            dirty_martini = db.create_recipe(
                {
                    "name": "Dirty Martini",
                    "instructions": "Test",
                    "ingredients": [
                        {"ingredient_id": gin["id"], "amount": 2.0},
                        {"ingredient_id": vermouth["id"], "amount": 0.5},
                        {"ingredient_id": olive["id"], "amount": 1.0},
                    ],
                }
            )

            vodka_martini = db.create_recipe(
                {
                    "name": "Vodka Martini",
                    "instructions": "Test",
                    "ingredients": [
                        {"ingredient_id": vodka["id"], "amount": 2.0},
                        {"ingredient_id": vermouth["id"], "amount": 0.5},
                    ],
                }
            )

            # Search for recipes that MUST have gin AND vermouth but MUST NOT have olive
            search_params = {
                "ingredients": [
                    {"id": gin["id"], "operator": "MUST"},
                    {"id": vermouth["id"], "operator": "MUST"},
                    {"id": olive["id"], "operator": "MUST_NOT"},
                ]
            }
            results = db.search_recipes(search_params)

            assert len(results) == 1
            assert results[0]["name"] == "Gin Martini"


class TestCombinedSearch:
    """Test combined search criteria"""

    def test_search_recipes_name_and_rating(self, memory_db_with_schema):
        """Test searching by both name and rating"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipes
            martini1 = db.create_recipe(
                {"name": "Classic Martini", "instructions": "Test"}
            )
            martini2 = db.create_recipe(
                {"name": "Dirty Martini", "instructions": "Test"}
            )
            manhattan = db.create_recipe({"name": "Manhattan", "instructions": "Test"})

            # Add ratings
            db.set_rating(
                {
                    "cognito_user_id": "user1",
                    "cognito_username": "user1",
                    "recipe_id": martini1["id"],
                    "rating": 5,
                }
            )
            db.set_rating(
                {
                    "cognito_user_id": "user1",
                    "cognito_username": "user1",
                    "recipe_id": martini2["id"],
                    "rating": 2,
                }
            )
            db.set_rating(
                {
                    "cognito_user_id": "user1",
                    "cognito_username": "user1",
                    "recipe_id": manhattan["id"],
                    "rating": 5,
                }
            )

            # Search for "martini" recipes with rating >= 4
            search_params = {"name": "martini", "min_rating": 4.0}
            results = db.search_recipes(search_params)

            assert len(results) == 1
            assert results[0]["name"] == "Classic Martini"

    def test_search_recipes_all_criteria(self, memory_db_with_schema):
        """Test searching with all criteria combined"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create ingredients
            gin = db.create_ingredient(
                {"name": "Gin1", "description": "Gin1", "parent_id": None}
            )
            vermouth = db.create_ingredient(
                {"name": "Vermouth1", "description": "Vermouth", "parent_id": None}
            )

            # Create recipes
            classic_martini = db.create_recipe(
                {
                    "name": "Classic Martini",
                    "instructions": "Test",
                    "ingredients": [
                        {"ingredient_id": gin["id"], "amount": 2.0},
                        {"ingredient_id": vermouth["id"], "amount": 0.5},
                    ],
                }
            )

            other_martini = db.create_recipe(
                {
                    "name": "Other Martini",
                    "instructions": "Test",
                    "ingredients": [{"ingredient_id": gin["id"], "amount": 2.0}],
                }
            )

            # Add tags and ratings
            classic_tag = db.create_public_tag("classic")
            db.add_public_tag_to_recipe(classic_martini["id"], classic_tag["id"])

            db.set_rating(
                {
                    "cognito_user_id": "user1",
                    "cognito_username": "user1",
                    "recipe_id": classic_martini["id"],
                    "rating": 5,
                }
            )
            db.set_rating(
                {
                    "cognito_user_id": "user1",
                    "cognito_username": "user1",
                    "recipe_id": other_martini["id"],
                    "rating": 3,
                }
            )

            # Search with all criteria
            search_params = {
                "name": "martini",
                "min_rating": 4.0,
                "tags": ["classic"],
                "ingredients": [{"id": gin["id"], "operator": "MUST"}],
            }
            results = db.search_recipes(search_params)

            assert len(results) == 1
            assert results[0]["name"] == "Classic Martini"


class TestSearchResultStructure:
    """Test search result structure and data completeness"""

    def test_search_results_include_ingredient_count(self, memory_db_with_schema):
        """Test that search results include ingredient counts"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create ingredients
            gin = db.create_ingredient(
                {"name": "Gin1", "description": "Gin1", "parent_id": None}
            )
            vermouth = db.create_ingredient(
                {"name": "Vermouth1", "description": "Vermouth", "parent_id": None}
            )
            olive = db.create_ingredient(
                {"name": "Olive", "description": "Olive", "parent_id": None}
            )

            # Create recipe with multiple ingredients
            recipe = db.create_recipe(
                {
                    "name": "Complex Martini",
                    "instructions": "Test",
                    "ingredients": [
                        {"ingredient_id": gin["id"], "amount": 2.0},
                        {"ingredient_id": vermouth["id"], "amount": 0.5},
                        {"ingredient_id": olive["id"], "amount": 1.0},
                    ],
                }
            )

            # Search and verify ingredient count
            search_params = {"name": "martini"}
            results = db.search_recipes(search_params)

            assert len(results) == 1
            assert "ingredient_count" in results[0]
            assert results[0]["ingredient_count"] == 3

    def test_search_results_rating_order(self, memory_db_with_schema):
        """Test that search results are ordered by rating (descending)"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipes
            recipe1 = db.create_recipe({"name": "Low Rated", "instructions": "Test"})
            recipe2 = db.create_recipe({"name": "High Rated", "instructions": "Test"})
            recipe3 = db.create_recipe({"name": "Medium Rated", "instructions": "Test"})

            # Add ratings in non-sequential order
            db.set_rating(
                {
                    "cognito_user_id": "user1",
                    "cognito_username": "user1",
                    "recipe_id": recipe1["id"],
                    "rating": 2,
                }
            )
            db.set_rating(
                {
                    "cognito_user_id": "user1",
                    "cognito_username": "user1",
                    "recipe_id": recipe2["id"],
                    "rating": 5,
                }
            )
            db.set_rating(
                {
                    "cognito_user_id": "user1",
                    "cognito_username": "user1",
                    "recipe_id": recipe3["id"],
                    "rating": 3,
                }
            )

            # Search all recipes
            search_params = {}
            results = db.search_recipes(search_params)

            # Should be ordered by rating descending
            assert len(results) == 3
            assert results[0]["name"] == "High Rated"
            assert results[0]["avg_rating"] == 5.0
            assert results[1]["name"] == "Medium Rated"
            assert results[1]["avg_rating"] == 3.0
            assert results[2]["name"] == "Low Rated"
            assert results[2]["avg_rating"] == 2.0


class TestPaginationOperations:
    """Test pagination functionality"""

    def test_get_recipes_paginated_basic(self, memory_db_with_schema):
        """Test basic paginated recipe retrieval"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create test recipes
            recipe_names = [f"Recipe {i:02d}" for i in range(10)]
            for name in recipe_names:
                db.create_recipe({"name": name, "instructions": "Test"})

            # Test first page
            page1 = db.search_recipes_paginated(
                search_params={}, limit=3, offset=0, sort_by="name", sort_order="asc"
            )
            assert len(page1) == 3
            assert page1[0]["name"] == "Recipe 00"
            assert page1[1]["name"] == "Recipe 01"
            assert page1[2]["name"] == "Recipe 02"

            # Test second page
            page2 = db.search_recipes_paginated(
                search_params={}, limit=3, offset=3, sort_by="name", sort_order="asc"
            )
            assert len(page2) == 3
            assert page2[0]["name"] == "Recipe 03"
            assert page2[1]["name"] == "Recipe 04"
            assert page2[2]["name"] == "Recipe 05"

    def test_get_recipes_paginated_with_ingredients(self, memory_db_with_schema):
        """Test that paginated recipes include full ingredient details"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create ingredient and recipe
            gin = db.create_ingredient(
                {"name": "Gin1", "description": "Gin1", "parent_id": None}
            )
            recipe = db.create_recipe(
                {
                    "name": "Test Recipe",
                    "instructions": "Test",
                    "ingredients": [{"ingredient_id": gin["id"], "amount": 2.0}],
                }
            )

            results = db.search_recipes_paginated(search_params={}, limit=10, offset=0)

            assert len(results) == 1
            recipe_result = results[0]

            # Should include full ingredient details
            assert "ingredients" in recipe_result
            assert len(recipe_result["ingredients"]) == 1

            ingredient = recipe_result["ingredients"][0]
            assert ingredient["ingredient_id"] == gin["id"]
            assert ingredient["ingredient_name"] == "Gin1"
            assert ingredient["amount"] == 2.0

    def test_search_recipes_paginated(self, memory_db_with_schema):
        """Test paginated search functionality"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create test recipes
            martini_names = [f"Martini {i:02d}" for i in range(10)]
            other_names = [f"Other {i:02d}" for i in range(5)]

            for name in martini_names + other_names:
                db.create_recipe({"name": name, "instructions": "Test"})

            # Search with pagination
            search_params = {"q": "martini"}
            results = db.search_recipes_paginated(
                search_params, limit=3, offset=0, sort_by="name", sort_order="asc"
            )

            assert len(results) == 3  # First page of 3
            assert all("Martini" in recipe["name"] for recipe in results)

            # Check first page results
            assert results[0]["name"] == "Martini 00"
            assert results[1]["name"] == "Martini 01"
            assert results[2]["name"] == "Martini 02"

            # Get second page
            results_page2 = db.search_recipes_paginated(
                search_params, limit=3, offset=3, sort_by="name", sort_order="asc"
            )

            assert len(results_page2) == 3
            assert results_page2[0]["name"] == "Martini 03"

    def test_search_recipes_paginated_empty_results(self, memory_db_with_schema):
        """Test paginated search with no results"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            search_params = {"q": "nonexistent"}
            results = db.search_recipes_paginated(search_params, limit=10, offset=0)

            assert len(results) == 0


class TestSortingFunctionality:
    """Test recipe sorting functionality"""

    def test_search_recipes_sort_by_name_asc(self, memory_db_with_schema):
        """Test sorting recipes by name in ascending order"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipes in non-alphabetical order
            recipe_names = ["Zebra Cocktail", "Apple Martini", "Manhattan", "Bloody Mary"]
            for name in recipe_names:
                db.create_recipe({"name": name, "instructions": "Test"})

            # Search with name sorting ascending
            results = db.search_recipes_paginated(
                search_params={}, limit=10, offset=0, sort_by="name", sort_order="asc"
            )

            assert len(results) == 4
            # Should be in alphabetical order
            assert results[0]["name"] == "Apple Martini"
            assert results[1]["name"] == "Bloody Mary"
            assert results[2]["name"] == "Manhattan"
            assert results[3]["name"] == "Zebra Cocktail"

    def test_search_recipes_sort_by_name_desc(self, memory_db_with_schema):
        """Test sorting recipes by name in descending order"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipes in non-alphabetical order
            recipe_names = ["Apple Martini", "Zebra Cocktail", "Manhattan", "Bloody Mary"]
            for name in recipe_names:
                db.create_recipe({"name": name, "instructions": "Test"})

            # Search with name sorting descending
            results = db.search_recipes_paginated(
                search_params={}, limit=10, offset=0, sort_by="name", sort_order="desc"
            )

            assert len(results) == 4
            # Should be in reverse alphabetical order
            assert results[0]["name"] == "Zebra Cocktail"
            assert results[1]["name"] == "Manhattan"
            assert results[2]["name"] == "Bloody Mary"
            assert results[3]["name"] == "Apple Martini"

    def test_search_recipes_sort_by_rating_asc(self, memory_db_with_schema):
        """Test sorting recipes by rating in ascending order"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipes
            recipe1 = db.create_recipe({"name": "High Rated", "instructions": "Test"})
            recipe2 = db.create_recipe({"name": "Low Rated", "instructions": "Test"})
            recipe3 = db.create_recipe({"name": "Medium Rated", "instructions": "Test"})
            recipe4 = db.create_recipe({"name": "Unrated", "instructions": "Test"})

            # Add ratings
            db.set_rating({"cognito_user_id": "user1", "cognito_username": "user1", 
                          "recipe_id": recipe1["id"], "rating": 5})
            db.set_rating({"cognito_user_id": "user1", "cognito_username": "user1", 
                          "recipe_id": recipe2["id"], "rating": 2})
            db.set_rating({"cognito_user_id": "user1", "cognito_username": "user1", 
                          "recipe_id": recipe3["id"], "rating": 3})
            # recipe4 remains unrated (avg_rating = 0)

            # Search with rating sorting ascending
            results = db.search_recipes_paginated(
                search_params={}, limit=10, offset=0, sort_by="avg_rating", sort_order="asc"
            )

            assert len(results) == 4
            # Should be ordered by rating ascending (unrated/0 first)
            assert results[0]["name"] == "Unrated"
            assert results[0]["avg_rating"] is None or results[0]["avg_rating"] == 0
            assert results[1]["name"] == "Low Rated"
            assert results[1]["avg_rating"] == 2.0
            assert results[2]["name"] == "Medium Rated"
            assert results[2]["avg_rating"] == 3.0
            assert results[3]["name"] == "High Rated"
            assert results[3]["avg_rating"] == 5.0

    def test_search_recipes_sort_by_rating_desc(self, memory_db_with_schema):
        """Test sorting recipes by rating in descending order"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipes
            recipe1 = db.create_recipe({"name": "High Rated", "instructions": "Test"})
            recipe2 = db.create_recipe({"name": "Low Rated", "instructions": "Test"})
            recipe3 = db.create_recipe({"name": "Medium Rated", "instructions": "Test"})

            # Add ratings
            db.set_rating({"cognito_user_id": "user1", "cognito_username": "user1", 
                          "recipe_id": recipe1["id"], "rating": 5})
            db.set_rating({"cognito_user_id": "user1", "cognito_username": "user1", 
                          "recipe_id": recipe2["id"], "rating": 2})
            db.set_rating({"cognito_user_id": "user1", "cognito_username": "user1", 
                          "recipe_id": recipe3["id"], "rating": 3})

            # Search with rating sorting descending
            results = db.search_recipes_paginated(
                search_params={}, limit=10, offset=0, sort_by="avg_rating", sort_order="desc"
            )

            assert len(results) == 3
            # Should be ordered by rating descending
            assert results[0]["name"] == "High Rated"
            assert results[0]["avg_rating"] == 5.0
            assert results[1]["name"] == "Medium Rated"
            assert results[1]["avg_rating"] == 3.0
            assert results[2]["name"] == "Low Rated"
            assert results[2]["avg_rating"] == 2.0

    def test_search_recipes_sort_by_created_at_asc(self, memory_db_with_schema):
        """Test sorting recipes by creation time (ID) in ascending order"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipes - IDs should be sequential
            recipe1 = db.create_recipe({"name": "First Recipe", "instructions": "Test"})
            recipe2 = db.create_recipe({"name": "Second Recipe", "instructions": "Test"})
            recipe3 = db.create_recipe({"name": "Third Recipe", "instructions": "Test"})

            # Search with creation time sorting ascending
            results = db.search_recipes_paginated(
                search_params={}, limit=10, offset=0, sort_by="created_at", sort_order="asc"
            )

            assert len(results) == 3
            # Should be ordered by creation time (ID) ascending
            assert results[0]["name"] == "First Recipe"
            assert results[0]["id"] == recipe1["id"]
            assert results[1]["name"] == "Second Recipe"
            assert results[1]["id"] == recipe2["id"]
            assert results[2]["name"] == "Third Recipe"
            assert results[2]["id"] == recipe3["id"]

    def test_search_recipes_sort_by_created_at_desc(self, memory_db_with_schema):
        """Test sorting recipes by creation time (ID) in descending order"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipes - IDs should be sequential
            recipe1 = db.create_recipe({"name": "First Recipe", "instructions": "Test"})
            recipe2 = db.create_recipe({"name": "Second Recipe", "instructions": "Test"})
            recipe3 = db.create_recipe({"name": "Third Recipe", "instructions": "Test"})

            # Search with creation time sorting descending
            results = db.search_recipes_paginated(
                search_params={}, limit=10, offset=0, sort_by="created_at", sort_order="desc"
            )

            assert len(results) == 3
            # Should be ordered by creation time (ID) descending
            assert results[0]["name"] == "Third Recipe"
            assert results[0]["id"] == recipe3["id"]
            assert results[1]["name"] == "Second Recipe"
            assert results[1]["id"] == recipe2["id"]
            assert results[2]["name"] == "First Recipe"
            assert results[2]["id"] == recipe1["id"]

    def test_search_recipes_sort_with_search_criteria(self, memory_db_with_schema):
        """Test that sorting works correctly with search criteria"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipes with search term in different orders
            recipe_names = ["Zebra Martini", "Apple Martini", "Classic Martini"]
            recipes = []
            for name in recipe_names:
                recipe = db.create_recipe({"name": name, "instructions": "Test"})
                recipes.append(recipe)

            # Add ratings to make sorting more interesting
            db.set_rating({"cognito_user_id": "user1", "cognito_username": "user1", 
                          "recipe_id": recipes[0]["id"], "rating": 2})  # Zebra Martini
            db.set_rating({"cognito_user_id": "user1", "cognito_username": "user1", 
                          "recipe_id": recipes[1]["id"], "rating": 5})  # Apple Martini
            db.set_rating({"cognito_user_id": "user1", "cognito_username": "user1", 
                          "recipe_id": recipes[2]["id"], "rating": 3})  # Classic Martini

            # Search for "martini" and sort by name ascending
            results = db.search_recipes_paginated(
                search_params={"name": "martini"}, limit=10, offset=0, 
                sort_by="name", sort_order="asc"
            )

            assert len(results) == 3
            assert results[0]["name"] == "Apple Martini"
            assert results[1]["name"] == "Classic Martini"
            assert results[2]["name"] == "Zebra Martini"

            # Same search but sort by rating descending
            results = db.search_recipes_paginated(
                search_params={"name": "martini"}, limit=10, offset=0, 
                sort_by="avg_rating", sort_order="desc"
            )

            assert len(results) == 3
            assert results[0]["name"] == "Apple Martini"  # Rating 5
            assert results[1]["name"] == "Classic Martini"  # Rating 3
            assert results[2]["name"] == "Zebra Martini"  # Rating 2

    def test_search_recipes_sort_case_sensitive(self, memory_db_with_schema):
        """Test that name sorting follows SQLite's default case-sensitive collation"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipes with different cases
            recipe_names = ["apple martini", "BANANA DAIQUIRI", "Cherry Bomb", "dragon fruit"]
            for name in recipe_names:
                db.create_recipe({"name": name, "instructions": "Test"})

            # Search with name sorting ascending
            results = db.search_recipes_paginated(
                search_params={}, limit=10, offset=0, sort_by="name", sort_order="asc"
            )

            assert len(results) == 4
            # SQLite default collation: uppercase letters come before lowercase letters
            # Expected order: BANANA DAIQUIRI, Cherry Bomb, apple martini, dragon fruit
            assert results[0]["name"] == "BANANA DAIQUIRI"
            assert results[1]["name"] == "Cherry Bomb"
            assert results[2]["name"] == "apple martini"
            assert results[3]["name"] == "dragon fruit"


class TestSearchEdgeCases:
    """Test edge cases and error conditions"""

    def test_search_empty_database(self, memory_db_with_schema):
        """Test searching in empty database"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            search_params = {"name": "anything"}
            results = db.search_recipes(search_params)

            assert len(results) == 0

    def test_search_with_empty_criteria(self, memory_db_with_schema):
        """Test search with empty search criteria"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create test recipes
            for i in range(3):
                db.create_recipe({"name": f"Recipe {i}", "instructions": "Test"})

            # Empty search should return all recipes
            search_params = {}
            results = db.search_recipes(search_params)

            assert len(results) == 3

    def test_search_with_very_long_name(self, memory_db_with_schema):
        """Test search with very long recipe name"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            long_name = "A" + "a" * 999
            db.create_recipe({"name": long_name, "instructions": "Test"})

            # Search for part of the long name
            search_params = {"name": "A" * 50}
            results = db.search_recipes(search_params)

            assert len(results) == 1
            assert results[0]["name"] == long_name

    def test_search_with_unicode_content(self, memory_db_with_schema):
        """Test search with unicode content"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            unicode_name = "Piña Colada 🍹"
            db.create_recipe({"name": unicode_name, "instructions": "Test"})

            # Search for unicode content
            search_params = {"name": "Piña"}
            results = db.search_recipes(search_params)

            assert len(results) == 1
            assert results[0]["name"] == unicode_name

    def test_search_ingredient_with_invalid_id(self, memory_db_with_schema):
        """Test ingredient search with invalid ingredient ID"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            # Search with non-existent ingredient ID
            search_params = {"ingredients": [{"id": 999, "operator": "MUST"}]}
            results = db.search_recipes(search_params)

            # Should return no results for non-existent ingredient
            assert len(results) == 0

    def test_pagination_beyond_available_results(self, memory_db_with_schema):
        """Test pagination beyond available results"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create only 3 recipes
            for i in range(3):
                db.create_recipe({"name": f"Recipe {i}", "instructions": "Test"})

            # Request page beyond available data
            results = db.search_recipes_paginated(search_params={}, limit=5, offset=10)

            assert len(results) == 0

    def test_pagination_with_zero_limit(self, memory_db_with_schema):
        """Test pagination with zero limit"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            # Zero limit should return empty results
            results = db.search_recipes_paginated(search_params={}, limit=0, offset=0)

            assert len(results) == 0
