"""
Integration and Transaction Testing
Tests for cross-system integration scenarios, transaction consistency,
and complex database operations spanning multiple tables
"""

import pytest
import sqlite3
import os
from typing import Dict, Any, List
from unittest.mock import patch
import concurrent.futures
import threading
import time

from api.db.db_core import Database


class TestTransactionConsistency:
    """Test transaction consistency across multiple tables"""

    def test_recipe_creation_transaction_rollback(self, memory_db_with_schema):
        """Test that recipe creation is properly rolled back on error"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create a valid ingredient
            gin = db.create_ingredient(
                {"name": "Test", "description": "Test", "parent_id": None}
            )

            # Attempt to create recipe with both valid and invalid ingredients
            recipe_data = {
                "name": "Test Recipe",
                "instructions": "Test instructions",
                "ingredients": [
                    {"ingredient_id": gin["id"], "amount": 2.0},
                    {"ingredient_id": 999, "amount": 1.0},  # Invalid ingredient
                ],
            }

            # Should fail due to invalid ingredient
            with pytest.raises(sqlite3.IntegrityError):
                db.create_recipe(recipe_data)

            # Verify no recipe was created (transaction rolled back)
            recipes = db.search_recipes(search_params={})
            assert len(recipes) == 0

            # Verify no recipe_ingredients were created
            ingredients_count = db.execute_query(
                "SELECT COUNT(*) as count FROM recipe_ingredients"
            )
            assert ingredients_count[0]["count"] == 0

    def test_recipe_update_transaction_consistency(self, memory_db_with_schema):
        """Test transaction consistency during recipe updates"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create ingredients and recipe
            gin = db.create_ingredient(
                {"name": "Test", "description": "Test", "parent_id": None}
            )
            vermouth = db.create_ingredient(
                {"name": "Vermouth", "description": "Vermouth", "parent_id": None}
            )

            recipe = db.create_recipe(
                {
                    "name": "Original Recipe",
                    "instructions": "Original instructions",
                    "ingredients": [{"ingredient_id": gin["id"], "amount": 2.0}],
                }
            )

            # Store original state
            original_recipe = db.get_recipe(recipe["id"])

            # Attempt update with invalid ingredient (should fail and rollback)
            update_data = {
                "name": "Updated Recipe",
                "ingredients": [
                    {"ingredient_id": gin["id"], "amount": 2.5},
                    {"ingredient_id": 999, "amount": 1.0},  # Invalid
                ],
            }

            with pytest.raises(sqlite3.IntegrityError):
                db.update_recipe(recipe["id"], update_data)

            # Verify recipe remains unchanged
            current_recipe = db.get_recipe(recipe["id"])
            assert current_recipe["name"] == original_recipe["name"]
            assert len(current_recipe["ingredients"]) == len(
                original_recipe["ingredients"]
            )

    def test_ingredient_hierarchy_update_transaction(self, memory_db_with_schema):
        """Test transaction consistency when updating ingredient hierarchy"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create hierarchy: Spirits -> Gin -> London Gin
            spirits = db.create_ingredient(
                {"name": "Spirits", "description": "Spirits", "parent_id": None}
            )
            gin = db.create_ingredient(
                {"name": "Test", "description": "Test", "parent_id": spirits["id"]}
            )
            london_gin = db.create_ingredient(
                {
                    "name": "New Test Gin",
                    "description": "London Gin",
                    "parent_id": gin["id"],
                }
            )

            # Store original paths
            original_gin_path = gin["path"]
            original_london_gin_path = london_gin["path"]

            # Create another parent to move gin to
            whiskey = db.create_ingredient(
                {
                    "name": "New Test Whiskey",
                    "description": "Whiskey",
                    "parent_id": spirits["id"],
                }
            )

            # Move gin under whiskey (this should update all descendant paths)
            updated_gin = db.update_ingredient(gin["id"], {"parent_id": whiskey["id"]})

            # Verify gin's path was updated
            assert updated_gin["path"] != original_gin_path
            assert str(whiskey["id"]) in updated_gin["path"].split("/")

            # Verify london_gin's path was also updated (cascade)
            updated_london_gin = db.get_ingredient(london_gin["id"])
            assert updated_london_gin["path"] != original_london_gin_path
            assert updated_london_gin["path"].startswith(updated_gin["path"])

    def test_rating_aggregation_transaction_consistency(self, memory_db_with_schema):
        """Test that rating aggregation updates are transactionally consistent"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipe
            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            # Add multiple ratings simultaneously using direct SQL to test triggers
            conn = sqlite3.connect(db.db_path)
            try:
                # Begin transaction
                conn.execute("BEGIN")

                # Insert multiple ratings
                ratings_data = [
                    ("user1", "user1", recipe["id"], 5),
                    ("user2", "user2", recipe["id"], 3),
                    ("user3", "user3", recipe["id"], 4),
                ]

                for user_id, username, recipe_id, rating in ratings_data:
                    conn.execute(
                        "INSERT INTO ratings (cognito_user_id, cognito_username, recipe_id, rating) VALUES (?, ?, ?, ?)",
                        (user_id, username, recipe_id, rating),
                    )

                # Commit all at once
                conn.commit()
            finally:
                conn.close()

            # Verify aggregated values are correct
            updated_recipe = db.get_recipe(recipe["id"])
            assert updated_recipe["rating_count"] == 3
            assert updated_recipe["avg_rating"] == 4.0  # (5 + 3 + 4) / 3


class TestCascadeOperations:
    """Test cascade delete and update operations"""

    def test_recipe_deletion_cascades(self, memory_db_with_schema):
        """Test that recipe deletion cascades to all related tables"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipe with ingredients, ratings, and tags
            gin = db.create_ingredient(
                {"name": "Test", "description": "Test", "parent_id": None}
            )
            recipe = db.create_recipe(
                {
                    "name": "Complex Recipe",
                    "instructions": "Test",
                    "ingredients": [{"ingredient_id": gin["id"], "amount": 2.0}],
                }
            )

            # Add rating
            db.set_rating(
                {
                    "cognito_user_id": "user1",
                    "cognito_username": "user1",
                    "recipe_id": recipe["id"],
                    "rating": 4,
                }
            )

            # Add tags
            public_tag = db.create_public_tag("classic")
            private_tag = db.create_private_tag("favorites", "user1")
            db.add_public_tag_to_recipe(recipe["id"], public_tag["id"])
            db.add_private_tag_to_recipe(recipe["id"], private_tag["id"])

            # Verify all associations exist
            assert len(db.get_recipe_ratings(recipe["id"])) == 1
            recipe_tags = db.execute_query(
                "SELECT COUNT(*) as count FROM recipe_tags WHERE recipe_id = ?",
                (recipe["id"],),
            )
            assert recipe_tags[0]["count"] == 2

            ingredients_before = db.execute_query(
                "SELECT COUNT(*) as count FROM recipe_ingredients WHERE recipe_id = ?",
                (recipe["id"],),
            )
            assert ingredients_before[0]["count"] == 1

            # Delete recipe
            db.delete_recipe(recipe["id"])

            # Verify all associations were cascade deleted
            ratings_after = db.execute_query(
                "SELECT COUNT(*) as count FROM ratings WHERE recipe_id = ?",
                (recipe["id"],),
            )
            assert ratings_after[0]["count"] == 0

            tags_after = db.execute_query(
                "SELECT COUNT(*) as count FROM recipe_tags WHERE recipe_id = ?",
                (recipe["id"],),
            )
            assert tags_after[0]["count"] == 0

            ingredients_after = db.execute_query(
                "SELECT COUNT(*) as count FROM recipe_ingredients WHERE recipe_id = ?",
                (recipe["id"],),
            )
            assert ingredients_after[0]["count"] == 0

            # Verify that ingredients and tags themselves still exist
            assert db.get_ingredient(gin["id"]) is not None
            assert db.get_public_tag_by_name("classic") is not None
            assert db.get_private_tag_by_name_and_user("favorites", "user1") is not None

    def test_ingredient_deletion_restriction(self, memory_db_with_schema):
        """Test that ingredients used in recipes cannot be deleted"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create ingredient and recipe using it
            gin = db.create_ingredient(
                {"name": "Test", "description": "Test", "parent_id": None}
            )
            recipe = db.create_recipe(
                {
                    "name": "Gin Recipe",
                    "instructions": "Test",
                    "ingredients": [{"ingredient_id": gin["id"], "amount": 2.0}],
                }
            )

            # Try to delete ingredient (should fail)
            with pytest.raises(
                ValueError, match="Cannot delete ingredient used in recipes"
            ):
                db.delete_ingredient(gin["id"])

            # Verify ingredient still exists
            assert db.get_ingredient(gin["id"]) is not None

            # Delete recipe first
            db.delete_recipe(recipe["id"])

            # Now ingredient deletion should succeed
            result = db.delete_ingredient(gin["id"])
            assert result is True
            assert db.get_ingredient(gin["id"]) is None


class TestConcurrentAccess:
    """Test concurrent database access scenarios"""

    def test_concurrent_recipe_creation(self, memory_db_with_schema):
        """Test concurrent recipe creation doesn't cause conflicts"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            # Create shared ingredient
            db = Database()
            gin = db.create_ingredient(
                {"name": "Test", "description": "Test", "parent_id": None}
            )

            def create_recipe(recipe_name):
                db_instance = Database()
                try:
                    recipe = db_instance.create_recipe(
                        {
                            "name": recipe_name,
                            "instructions": f"Instructions for {recipe_name}",
                            "ingredients": [
                                {"ingredient_id": gin["id"], "amount": 2.0}
                            ],
                        }
                    )
                    return recipe["id"]
                except sqlite3.IntegrityError:
                    # Expected for duplicate names
                    return None

            # Create multiple recipes concurrently
            recipe_names = [f"Recipe {i}" for i in range(10)]

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [
                    executor.submit(create_recipe, name) for name in recipe_names
                ]
                results = [
                    future.result()
                    for future in concurrent.futures.as_completed(futures)
                ]

            # Filter out None results (duplicates)
            successful_ids = [r for r in results if r is not None]

            # Verify all recipes were created successfully
            assert len(successful_ids) == 10

            # Verify in database
            final_db = Database()
            all_recipes = final_db.search_recipes(search_params={})
            assert len(all_recipes) == 10

    def test_concurrent_rating_updates(self, memory_db_with_schema):
        """Test concurrent rating updates on the same recipe"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            recipe = db.create_recipe(
                {"name": "Popular Recipe", "instructions": "Test"}
            )

            def add_rating(user_num, rating_value):
                db_instance = Database()
                try:
                    result = db_instance.set_rating(
                        {
                            "cognito_user_id": f"user{user_num}",
                            "cognito_username": f"user{user_num}",
                            "recipe_id": recipe["id"],
                            "rating": rating_value,
                        }
                    )
                    return result["rating"]
                except Exception as e:
                    print(f"Error adding rating for user{user_num}: {e}")
                    return None

            # Add ratings concurrently
            rating_data = [(i, (i % 5) + 1) for i in range(20)]  # 20 users, ratings 1-5

            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [
                    executor.submit(add_rating, user_num, rating)
                    for user_num, rating in rating_data
                ]
                results = [
                    future.result()
                    for future in concurrent.futures.as_completed(futures)
                ]

            # Verify all ratings were added
            successful_ratings = [r for r in results if r is not None]
            assert len(successful_ratings) == 20

            # Verify final aggregation is correct
            final_recipe = db.get_recipe(recipe["id"])
            assert final_recipe["rating_count"] == 20

            # Calculate expected average
            expected_avg = sum(rating for _, rating in rating_data) / len(rating_data)
            assert abs(final_recipe["avg_rating"] - expected_avg) < 0.01

    def test_concurrent_ingredient_hierarchy_updates(self, memory_db_with_schema):
        """Test concurrent ingredient hierarchy updates"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create base hierarchy
            spirits = db.create_ingredient(
                {"name": "Spirits", "description": "Spirits", "parent_id": None}
            )
            categories = []

            # Create multiple categories under spirits
            for i in range(5):
                category = db.create_ingredient(
                    {
                        "name": f"Category {i}",
                        "description": f"Category {i}",
                        "parent_id": spirits["id"],
                    }
                )
                categories.append(category)

            def move_ingredient_to_category(ingredient_id, category_id):
                db_instance = Database()
                try:
                    result = db_instance.update_ingredient(
                        ingredient_id, {"parent_id": category_id}
                    )
                    return result["id"] if result else None
                except Exception as e:
                    print(f"Error moving ingredient {ingredient_id}: {e}")
                    return None

            # Create child ingredients and move them concurrently
            child_ingredients = []
            for i in range(10):
                child = db.create_ingredient(
                    {
                        "name": f"Child {i}",
                        "description": f"Child {i}",
                        "parent_id": spirits["id"],
                    }
                )
                child_ingredients.append(child)

            # Move children to different categories concurrently
            moves = [
                (child["id"], categories[i % len(categories)]["id"])
                for i, child in enumerate(child_ingredients)
            ]

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [
                    executor.submit(move_ingredient_to_category, child_id, cat_id)
                    for child_id, cat_id in moves
                ]
                results = [
                    future.result()
                    for future in concurrent.futures.as_completed(futures)
                ]

            # Verify all moves succeeded
            successful_moves = [r for r in results if r is not None]
            assert len(successful_moves) == 10

            # Verify final hierarchy is correct
            for i, child in enumerate(child_ingredients):
                updated_child = db.get_ingredient(child["id"])
                expected_parent = categories[i % len(categories)]["id"]
                assert updated_child["parent_id"] == expected_parent


class TestForeignKeyConstraints:
    """Test foreign key constraint enforcement"""

    def test_recipe_ingredients_foreign_key_enforcement(self, memory_db_with_schema):
        """Test that recipe_ingredients enforces foreign key constraints"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipe
            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            # Try to add ingredient that doesn't exist directly to database
            with pytest.raises(sqlite3.IntegrityError):
                db.execute_query(
                    "INSERT INTO recipe_ingredients (recipe_id, ingredient_id, amount) VALUES (?, ?, ?)",
                    (recipe["id"], 999, 1.0),
                )

    def test_ratings_foreign_key_enforcement(self, memory_db_with_schema):
        """Test that ratings enforces foreign key constraints"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Try to add rating for non-existent recipe
            with pytest.raises(sqlite3.IntegrityError):
                db.execute_query(
                    "INSERT INTO ratings (cognito_user_id, cognito_username, recipe_id, rating) VALUES (?, ?, ?, ?)",
                    ("user1", "user1", 999, 4),
                )

    def test_tag_associations_foreign_key_enforcement(self, memory_db_with_schema):
        """Test that tag associations enforce foreign key constraints"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipe and tag
            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})
            tag = db.create_public_tag("test")

            # Try to associate with non-existent recipe
            with pytest.raises(sqlite3.IntegrityError):
                db.execute_query(
                    "INSERT INTO recipe_tags (recipe_id, tag_id) VALUES (?, ?)",
                    (999, tag["id"]),
                )

            # Try to associate with non-existent tag
            with pytest.raises(sqlite3.IntegrityError):
                db.execute_query(
                    "INSERT INTO recipe_tags (recipe_id, tag_id) VALUES (?, ?)",
                    (recipe["id"], 999),
                )


class TestComplexIntegrationScenarios:
    """Test complex scenarios involving multiple database components"""

    def test_full_recipe_lifecycle_with_all_components(self, memory_db_with_schema):
        """Test complete recipe lifecycle involving all database components"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # 1. Create ingredient hierarchy
            spirits = db.create_ingredient(
                {
                    "name": "Spirits",
                    "description": "Alcoholic spirits",
                    "parent_id": None,
                }
            )
            gin = db.create_ingredient(
                {
                    "name": "Test",
                    "description": "Juniper spirit",
                    "parent_id": spirits["id"],
                }
            )
            london_gin = db.create_ingredient(
                {
                    "name": "London Dry Gin",
                    "description": "Specific gin type",
                    "parent_id": gin["id"],
                }
            )
            vermouth = db.create_ingredient(
                {"name": "Vermouth", "description": "Fortified wine", "parent_id": None}
            )

            # 2. Create units
            db.execute_query(
                "INSERT INTO units (name, abbreviation, conversion_to_ml) VALUES (?, ?, ?)",
                ("New Test Unit", "ntu", 29.5735),
            )
            unit_result = db.execute_query(
                "SELECT id FROM units WHERE name = ?", ("Ounce",)
            )
            unit_id = unit_result[0]["id"]

            # 3. Create recipe with complex ingredients
            recipe = db.create_recipe(
                {
                    "name": "Premium Martini",
                    "instructions": "Stir with ice and strain into chilled glass",
                    "description": "A premium martini using London Dry Gin",
                    "ingredients": [
                        {
                            "ingredient_id": london_gin["id"],
                            "unit_id": unit_id,
                            "amount": 2.5,
                        },
                        {
                            "ingredient_id": vermouth["id"],
                            "unit_id": unit_id,
                            "amount": 0.5,
                        },
                    ],
                }
            )

            # 4. Add tags
            novel_tag = db.create_public_tag("novel")
            strong_tag = db.create_public_tag("strong")
            favorites_tag = db.create_private_tag("favorites", "user1")

            db.add_public_tag_to_recipe(recipe["id"], novel_tag["id"])
            db.add_public_tag_to_recipe(recipe["id"], strong_tag["id"])
            db.add_private_tag_to_recipe(recipe["id"], favorites_tag["id"])

            # 5. Add ratings from multiple users
            users_and_ratings = [
                ("user1", "testuser", 5),
                ("user2", "user2", 4),
                ("user3", "user3", 5),
            ]

            for user_id, username, rating in users_and_ratings:
                db.set_rating(
                    {
                        "cognito_user_id": user_id,
                        "cognito_username": username,
                        "recipe_id": recipe["id"],
                        "rating": rating,
                    }
                )

            # 6. Retrieve complete recipe and verify all components
            complete_recipe = db.get_recipe(recipe["id"], "user1")

            # Verify basic recipe data
            assert complete_recipe["name"] == "Premium Martini"
            assert (
                complete_recipe["description"]
                == "A premium martini using London Dry Gin"
            )

            # Verify ingredients with hierarchy
            assert len(complete_recipe["ingredients"]) == 2
            london_gin_ingredient = next(
                ing
                for ing in complete_recipe["ingredients"]
                if ing["ingredient_id"] == london_gin["id"]
            )
            assert "full_name" in london_gin_ingredient
            assert "Spirits" in london_gin_ingredient["full_name"]
            assert "Test" in london_gin_ingredient["full_name"]
            assert "London Dry Gin" in london_gin_ingredient["full_name"]

            # Verify units
            assert london_gin_ingredient["unit_name"] == "Ounce"
            assert london_gin_ingredient["unit_abbreviation"] == "oz"

            # Verify tags
            public_tag_names = {
                tag["name"]
                for tag in complete_recipe["tags"]
                if tag["type"] == "public"
            }
            private_tag_names = {
                tag["name"]
                for tag in complete_recipe["tags"]
                if tag["type"] == "private"
            }
            assert public_tag_names == {"novel", "strong"}
            assert private_tag_names == {"favorites"}

            # Verify ratings
            assert complete_recipe["avg_rating"] == 14 / 3  # (5+4+5)/3 ≈ 4.67
            assert complete_recipe["rating_count"] == 3
            assert complete_recipe["user_rating"] == 5  # user1's rating

            # 7. Test search functionality finds this recipe
            search_results = db.search_recipes(
                {
                    "name": "martini",
                    "min_rating": 4.0,
                    "tags": ["novel"],
                    "ingredients": [{"id": gin["id"], "operator": "MUST"}],
                }
            )

            assert len(search_results) == 1
            assert search_results[0]["name"] == "Premium Martini"

            # 8. Test pagination includes this recipe
            paginated_results = db.get_recipes_paginated(
                limit=10, offset=0, sort_by="avg_rating", sort_order="desc"
            )
            assert len(paginated_results) == 1
            assert paginated_results[0]["name"] == "Premium Martini"

    def test_bulk_operations_consistency(self, memory_db_with_schema):
        """Test consistency during bulk operations"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create base ingredients
            base_ingredients = []
            for i in range(10):
                ingredient = db.create_ingredient(
                    {
                        "name": f"Ingredient {i}",
                        "description": f"Test ingredient {i}",
                        "parent_id": None,
                    }
                )
                base_ingredients.append(ingredient)

            # Create multiple recipes using these ingredients
            recipes = []
            for i in range(20):
                # Each recipe uses 2-3 random ingredients
                recipe_ingredients = []
                for j in range(2 + (i % 2)):  # 2 or 3 ingredients
                    ingredient_idx = (i + j) % len(base_ingredients)
                    recipe_ingredients.append(
                        {
                            "ingredient_id": base_ingredients[ingredient_idx]["id"],
                            "amount": 1.0 + j,
                        }
                    )

                recipe = db.create_recipe(
                    {
                        "name": f"Recipe {i:02d}",
                        "instructions": f"Instructions for recipe {i}",
                        "ingredients": recipe_ingredients,
                    }
                )
                recipes.append(recipe)

            # Add ratings to all recipes
            for i, recipe in enumerate(recipes):
                rating = (i % 5) + 1  # Ratings 1-5
                db.set_rating(
                    {
                        "cognito_user_id": f"user{i}",
                        "cognito_username": f"user{i}",
                        "recipe_id": recipe["id"],
                        "rating": rating,
                    }
                )

            # Verify data consistency
            all_recipes = db.search_recipes(search_params={})
            assert len(all_recipes) == 20

            # Verify all recipes have correct ingredient counts
            for recipe in all_recipes:
                assert "ingredient_count" in recipe
                assert recipe["ingredient_count"] >= 2
                assert recipe["ingredient_count"] <= 3

            # Verify search across all recipes works
            search_results = db.search_recipes({"min_rating": 3.0})
            high_rated_recipes = [r for r in all_recipes if r["avg_rating"] >= 3.0]
            assert len(search_results) == len(high_rated_recipes)

            # Verify pagination works correctly
            page1 = db.get_recipes_paginated(
                limit=10, offset=0, sort_by="name", sort_order="asc"
            )
            page2 = db.get_recipes_paginated(
                limit=10, offset=10, sort_by="name", sort_order="asc"
            )

            assert len(page1) == 10
            assert len(page2) == 10

            # Verify no overlap between pages
            page1_names = {recipe["name"] for recipe in page1}
            page2_names = {recipe["name"] for recipe in page2}
            assert len(page1_names.intersection(page2_names)) == 0
