"""
Integration and Transaction Testing
Tests for cross-system integration scenarios, transaction consistency,
and complex database operations spanning multiple tables
"""

import pytest
import psycopg2
import psycopg2.errors
import os
from typing import Dict, Any, List
from unittest.mock import patch
import concurrent.futures
import threading
import time

from api.db.db_core import Database


class TestTransactionConsistency:
    """Test transaction consistency across multiple tables"""

    def test_recipe_update_transaction_consistency(self, db_instance):
        """Test transaction consistency during recipe updates"""
        db = db_instance

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

        with pytest.raises(psycopg2.errors.ForeignKeyViolation):
            db.update_recipe(recipe["id"], update_data)

        # Verify recipe remains unchanged
        current_recipe = db.get_recipe(recipe["id"])
        assert current_recipe["name"] == original_recipe["name"]
        assert len(current_recipe["ingredients"]) == len(
            original_recipe["ingredients"]
        )

    def test_ingredient_hierarchy_update_transaction(self, db_instance):
        """Test transaction consistency when updating ingredient hierarchy"""
        db = db_instance

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

    def test_rating_aggregation_transaction_consistency(self, db_instance, pg_db_with_schema):
        """Test that rating aggregation updates are transactionally consistent"""
        db = db_instance

        # Create recipe
        recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

        # Add multiple ratings using direct SQL to test triggers
        conn = psycopg2.connect(**pg_db_with_schema)
        try:
            cursor = conn.cursor()

            # Insert multiple ratings
            ratings_data = [
                ("user1", recipe["id"], 5),
                ("user2", recipe["id"], 3),
                ("user3", recipe["id"], 4),
            ]

            for user_id, recipe_id, rating in ratings_data:
                cursor.execute(
                    "INSERT INTO ratings (cognito_user_id, recipe_id, rating) VALUES (%s, %s, %s)",
                    (user_id, recipe_id, rating),
                )

            # Commit all at once
            conn.commit()
            cursor.close()
        finally:
            conn.close()

        # Verify aggregated values are correct
        updated_recipe = db.get_recipe(recipe["id"])
        assert updated_recipe["rating_count"] == 3
        assert updated_recipe["avg_rating"] == 4.0  # (5 + 3 + 4) / 3


class TestCascadeOperations:
    """Test cascade delete and update operations"""

    def test_recipe_deletion_cascades(self, db_instance):
        """Test that recipe deletion cascades to all related tables"""
        db = db_instance

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
            "SELECT COUNT(*) as count FROM recipe_tags WHERE recipe_id = %s",
            (recipe["id"],),
        )
        assert recipe_tags[0]["count"] == 2

        ingredients_before = db.execute_query(
            "SELECT COUNT(*) as count FROM recipe_ingredients WHERE recipe_id = %s",
            (recipe["id"],),
        )
        assert ingredients_before[0]["count"] == 1

        # Delete recipe
        db.delete_recipe(recipe["id"])

        # Verify all associations were cascade deleted
        ratings_after = db.execute_query(
            "SELECT COUNT(*) as count FROM ratings WHERE recipe_id = %s",
            (recipe["id"],),
        )
        assert ratings_after[0]["count"] == 0

        tags_after = db.execute_query(
            "SELECT COUNT(*) as count FROM recipe_tags WHERE recipe_id = %s",
            (recipe["id"],),
        )
        assert tags_after[0]["count"] == 0

        ingredients_after = db.execute_query(
            "SELECT COUNT(*) as count FROM recipe_ingredients WHERE recipe_id = %s",
            (recipe["id"],),
        )
        assert ingredients_after[0]["count"] == 0

        # Verify that ingredients and tags themselves still exist
        assert db.get_ingredient(gin["id"]) is not None
        assert db.get_public_tag_by_name("classic") is not None
        assert db.get_private_tag_by_name_and_user("favorites", "user1") is not None

    def test_ingredient_deletion_restriction(self, db_instance):
        """Test that ingredients used in recipes cannot be deleted"""
        db = db_instance

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

    def test_concurrent_rating_updates(self, db_instance):
        """Test concurrent rating updates on the same recipe"""
        db = db_instance
        recipe = db.create_recipe(
            {"name": "Popular Recipe", "instructions": "Test"}
        )

        def add_rating(user_num, rating_value):
            db_new = Database()
            try:
                result = db_new.set_rating(
                    {
                        "cognito_user_id": f"user{user_num}",
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

    def test_concurrent_ingredient_hierarchy_updates(self, db_instance):
        """Test concurrent ingredient hierarchy updates"""
        db = db_instance

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
            db_new = Database()
            try:
                result = db_new.update_ingredient(
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

    def test_recipe_ingredients_foreign_key_enforcement(self, db_instance):
        """Test that recipe_ingredients enforces foreign key constraints"""
        db = db_instance

        # Create recipe
        recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

        # Try to add ingredient that doesn't exist directly to database
        with pytest.raises(psycopg2.errors.ForeignKeyViolation):
            db.execute_query(
                "INSERT INTO recipe_ingredients (recipe_id, ingredient_id, amount) VALUES (%s, %s, %s)",
                (recipe["id"], 999, 1.0),
            )

    def test_ratings_foreign_key_enforcement(self, db_instance):
        """Test that ratings enforces foreign key constraints"""
        db = db_instance

        # Try to add rating for non-existent recipe
        with pytest.raises(psycopg2.errors.ForeignKeyViolation):
            db.execute_query(
                "INSERT INTO ratings (cognito_user_id, recipe_id, rating) VALUES (%s, %s, %s)",
                ("user1", 999, 4),
            )

    def test_tag_associations_foreign_key_enforcement(self, db_instance):
        """Test that tag associations enforce foreign key constraints"""
        db = db_instance

        # Create recipe and tag
        recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})
        tag = db.create_public_tag("test")

        # Try to associate with non-existent recipe
        with pytest.raises(psycopg2.errors.ForeignKeyViolation):
            db.execute_query(
                "INSERT INTO recipe_tags (recipe_id, tag_id) VALUES (%s, %s)",
                (999, tag["id"]),
            )

        # Try to associate with non-existent tag
        with pytest.raises(psycopg2.errors.ForeignKeyViolation):
            db.execute_query(
                "INSERT INTO recipe_tags (recipe_id, tag_id) VALUES (%s, %s)",
                (recipe["id"], 999),
            )
