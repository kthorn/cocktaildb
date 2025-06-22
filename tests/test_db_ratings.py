"""
Rating System Testing
Comprehensive tests for rating CRUD operations, aggregation calculations,
and user-specific constraints
"""

import pytest
import sqlite3
import os
from typing import Dict, Any, List
from unittest.mock import patch

from api.db.db_core import Database


class TestRatingCRUD:
    """Test basic CRUD operations for ratings"""

    def test_set_rating_new(self, memory_db_with_schema):
        """Test setting a new rating for a recipe"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipe
            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            # Set rating
            rating_data = {
                "cognito_user_id": "user123",
                "cognito_username": "testuser",
                "recipe_id": recipe["id"],
                "rating": 4,
            }

            result = db.set_rating(rating_data)

            assert result["id"] is not None
            assert result["cognito_user_id"] == "user123"
            assert result["cognito_username"] == "testuser"
            assert result["recipe_id"] == recipe["id"]
            assert result["rating"] == 4
            assert result["avg_rating"] == 4.0
            assert result["rating_count"] == 1

    def test_set_rating_update_existing(self, memory_db_with_schema):
        """Test updating an existing rating"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipe
            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            # Set initial rating
            rating_data = {
                "cognito_user_id": "user123",
                "cognito_username": "testuser",
                "recipe_id": recipe["id"],
                "rating": 3,
            }
            initial_result = db.set_rating(rating_data)

            # Update rating
            rating_data["rating"] = 5
            updated_result = db.set_rating(rating_data)

            # Should be same rating ID (updated, not new)
            assert updated_result["id"] == initial_result["id"]
            assert updated_result["rating"] == 5
            assert updated_result["avg_rating"] == 5.0
            assert updated_result["rating_count"] == 1

    def test_set_rating_multiple_users(self, memory_db_with_schema):
        """Test multiple users rating the same recipe"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipe
            recipe = db.create_recipe(
                {"name": "Popular Recipe", "instructions": "Test"}
            )

            # User 1 rates 4
            rating1_data = {
                "cognito_user_id": "user1",
                "cognito_username": "user1",
                "recipe_id": recipe["id"],
                "rating": 4,
            }
            result1 = db.set_rating(rating1_data)

            # User 2 rates 2
            rating2_data = {
                "cognito_user_id": "user2",
                "cognito_username": "user2",
                "recipe_id": recipe["id"],
                "rating": 2,
            }
            result2 = db.set_rating(rating2_data)

            # Check aggregated results
            assert result2["avg_rating"] == 3.0  # (4 + 2) / 2
            assert result2["rating_count"] == 2

    def test_set_rating_validation_missing_user_id(self, memory_db_with_schema):
        """Test rating validation with missing user ID"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            rating_data = {
                "cognito_username": "testuser",
                "recipe_id": recipe["id"],
                "rating": 4,
            }

            with pytest.raises(ValueError, match="User ID is required"):
                db.set_rating(rating_data)

    def test_set_rating_validation_missing_username(self, memory_db_with_schema):
        """Test rating validation with missing username"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            rating_data = {
                "cognito_user_id": "user123",
                "recipe_id": recipe["id"],
                "rating": 4,
            }

            with pytest.raises(ValueError, match="Username is required"):
                db.set_rating(rating_data)

    def test_set_rating_validation_missing_recipe_id(self, memory_db_with_schema):
        """Test rating validation with missing recipe ID"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            rating_data = {
                "cognito_user_id": "user123",
                "cognito_username": "testuser",
                "rating": 4,
            }

            with pytest.raises(ValueError, match="Recipe ID is required"):
                db.set_rating(rating_data)

    def test_set_rating_validation_invalid_rating_low(self, memory_db_with_schema):
        """Test rating validation with rating too low"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            rating_data = {
                "cognito_user_id": "user123",
                "cognito_username": "testuser",
                "recipe_id": recipe["id"],
                "rating": 0,  # Too low
            }

            with pytest.raises(ValueError, match="Rating must be between 1 and 5"):
                db.set_rating(rating_data)

    def test_set_rating_validation_invalid_rating_high(self, memory_db_with_schema):
        """Test rating validation with rating too high"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            rating_data = {
                "cognito_user_id": "user123",
                "cognito_username": "testuser",
                "recipe_id": recipe["id"],
                "rating": 6,  # Too high
            }

            with pytest.raises(ValueError, match="Rating must be between 1 and 5"):
                db.set_rating(rating_data)

    def test_set_rating_nonexistent_recipe(self, memory_db_with_schema):
        """Test setting rating for non-existent recipe"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            rating_data = {
                "cognito_user_id": "user123",
                "cognito_username": "testuser",
                "recipe_id": 999,  # Non-existent recipe
                "rating": 4,
            }

            with pytest.raises(ValueError, match="Recipe with ID 999 does not exist"):
                db.set_rating(rating_data)

    def test_get_user_rating(self, memory_db_with_schema):
        """Test retrieving a user's rating for a recipe"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipe and rating
            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})
            rating_data = {
                "cognito_user_id": "user123",
                "cognito_username": "testuser",
                "recipe_id": recipe["id"],
                "rating": 4,
            }
            db.set_rating(rating_data)

            # Retrieve user rating
            result = db.get_user_rating(recipe["id"], "user123")

            assert result is not None
            assert result["cognito_user_id"] == "user123"
            assert result["recipe_id"] == recipe["id"]
            assert result["rating"] == 4

    def test_get_user_rating_nonexistent(self, memory_db_with_schema):
        """Test retrieving non-existent user rating"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            result = db.get_user_rating(recipe["id"], "nonexistent_user")
            assert result is None

    def test_get_recipe_ratings(self, memory_db_with_schema):
        """Test retrieving all ratings for a recipe"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipe
            recipe = db.create_recipe(
                {"name": "Popular Recipe", "instructions": "Test"}
            )

            # Create multiple ratings
            users_and_ratings = [
                ("user1", "User One", 5),
                ("user2", "User Two", 3),
                ("user3", "User Three", 4),
            ]

            for user_id, username, rating in users_and_ratings:
                rating_data = {
                    "cognito_user_id": user_id,
                    "cognito_username": username,
                    "recipe_id": recipe["id"],
                    "rating": rating,
                }
                db.set_rating(rating_data)

            # Get all ratings
            result = db.get_recipe_ratings(recipe["id"])

            assert len(result) == 3

            # Verify all ratings are present
            user_ids = {r["cognito_user_id"] for r in result}
            assert user_ids == {"user1", "user2", "user3"}

            ratings = {r["rating"] for r in result}
            assert ratings == {3, 4, 5}


class TestRatingDeletion:
    """Test rating deletion operations"""

    def test_delete_rating(self, memory_db_with_schema):
        """Test deleting a user's rating"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipe and rating
            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})
            rating_data = {
                "cognito_user_id": "user123",
                "cognito_username": "testuser",
                "recipe_id": recipe["id"],
                "rating": 4,
            }
            db.set_rating(rating_data)

            # Verify rating exists
            assert db.get_user_rating(recipe["id"], "user123") is not None

            # Delete rating
            result = db.delete_rating(recipe["id"], "user123")
            assert result is True

            # Verify rating is deleted
            assert db.get_user_rating(recipe["id"], "user123") is None

    def test_delete_rating_nonexistent(self, memory_db_with_schema):
        """Test deleting non-existent rating"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            with pytest.raises(
                ValueError, match="Rating not found for this user and recipe"
            ):
                db.delete_rating(recipe["id"], "nonexistent_user")

    def test_delete_rating_updates_aggregates(self, memory_db_with_schema):
        """Test that deleting rating updates recipe aggregates"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipe
            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            # Add multiple ratings
            db.set_rating(
                {
                    "cognito_user_id": "user1",
                    "cognito_username": "user1",
                    "recipe_id": recipe["id"],
                    "rating": 5,
                }
            )
            db.set_rating(
                {
                    "cognito_user_id": "user2",
                    "cognito_username": "user2",
                    "recipe_id": recipe["id"],
                    "rating": 3,
                }
            )

            # Verify initial aggregates (5 + 3) / 2 = 4.0
            recipe_before = db.get_recipe(recipe["id"])
            assert recipe_before["avg_rating"] == 4.0
            assert recipe_before["rating_count"] == 2

            # Delete one rating
            db.delete_rating(recipe["id"], "user1")

            # Verify updated aggregates (only 3 remaining)
            recipe_after = db.get_recipe(recipe["id"])
            assert recipe_after["avg_rating"] == 3.0
            assert recipe_after["rating_count"] == 1


class TestRatingAggregation:
    """Test rating aggregation and calculation logic"""

    def test_rating_aggregation_single_rating(self, memory_db_with_schema):
        """Test aggregation with single rating"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            db.set_rating(
                {
                    "cognito_user_id": "user1",
                    "cognito_username": "user1",
                    "recipe_id": recipe["id"],
                    "rating": 4,
                }
            )

            recipe_result = db.get_recipe(recipe["id"])
            assert recipe_result["avg_rating"] == 4.0
            assert recipe_result["rating_count"] == 1

    def test_rating_aggregation_multiple_ratings(self, memory_db_with_schema):
        """Test aggregation with multiple ratings"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            # Add ratings: 1, 2, 3, 4, 5 (average = 3.0)
            for i, rating in enumerate([1, 2, 3, 4, 5], 1):
                db.set_rating(
                    {
                        "cognito_user_id": f"user{i}",
                        "cognito_username": f"user{i}",
                        "recipe_id": recipe["id"],
                        "rating": rating,
                    }
                )

            recipe_result = db.get_recipe(recipe["id"])
            assert recipe_result["avg_rating"] == 3.0
            assert recipe_result["rating_count"] == 5

    def test_rating_aggregation_decimal_average(self, memory_db_with_schema):
        """Test aggregation with decimal average"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            # Add ratings: 4, 5 (average = 4.5)
            db.set_rating(
                {
                    "cognito_user_id": "user1",
                    "cognito_username": "user1",
                    "recipe_id": recipe["id"],
                    "rating": 4,
                }
            )
            db.set_rating(
                {
                    "cognito_user_id": "user2",
                    "cognito_username": "user2",
                    "recipe_id": recipe["id"],
                    "rating": 5,
                }
            )

            recipe_result = db.get_recipe(recipe["id"])
            assert recipe_result["avg_rating"] == 4.5
            assert recipe_result["rating_count"] == 2

    def test_rating_aggregation_update_existing(self, memory_db_with_schema):
        """Test that aggregation updates correctly when rating is changed"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            # Initial rating: 2
            db.set_rating(
                {
                    "cognito_user_id": "user1",
                    "cognito_username": "user1",
                    "recipe_id": recipe["id"],
                    "rating": 2,
                }
            )

            recipe_after_first = db.get_recipe(recipe["id"])
            assert recipe_after_first["avg_rating"] == 2.0
            assert recipe_after_first["rating_count"] == 1

            # Update rating: 2 -> 5
            db.set_rating(
                {
                    "cognito_user_id": "user1",
                    "cognito_username": "user1",
                    "recipe_id": recipe["id"],
                    "rating": 5,
                }
            )

            recipe_after_update = db.get_recipe(recipe["id"])
            assert recipe_after_update["avg_rating"] == 5.0
            assert (
                recipe_after_update["rating_count"] == 1
            )  # Still 1 rating, just updated

    def test_rating_aggregation_after_deletion(self, memory_db_with_schema):
        """Test aggregation after rating deletion"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            # Add three ratings: 2, 4, 6 (wait, 6 is invalid... let's use 2, 4, 5)
            ratings = [2, 4, 5]  # average = 11/3 ≈ 3.67
            for i, rating in enumerate(ratings, 1):
                db.set_rating(
                    {
                        "cognito_user_id": f"user{i}",
                        "cognito_username": f"user{i}",
                        "recipe_id": recipe["id"],
                        "rating": rating,
                    }
                )

            # Verify initial aggregation
            recipe_before = db.get_recipe(recipe["id"])
            expected_avg = sum(ratings) / len(ratings)
            assert abs(recipe_before["avg_rating"] - expected_avg) < 0.01
            assert recipe_before["rating_count"] == 3

            # Delete middle rating (4)
            db.delete_rating(recipe["id"], "user2")

            # Verify updated aggregation (2, 5 remaining, avg = 3.5)
            recipe_after = db.get_recipe(recipe["id"])
            assert recipe_after["avg_rating"] == 3.5
            assert recipe_after["rating_count"] == 2

    def test_rating_aggregation_all_deleted(self, memory_db_with_schema):
        """Test aggregation when all ratings are deleted"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            # Add rating
            db.set_rating(
                {
                    "cognito_user_id": "user1",
                    "cognito_username": "user1",
                    "recipe_id": recipe["id"],
                    "rating": 4,
                }
            )

            # Verify rating exists
            recipe_with_rating = db.get_recipe(recipe["id"])
            assert recipe_with_rating["avg_rating"] == 4.0
            assert recipe_with_rating["rating_count"] == 1

            # Delete the rating
            db.delete_rating(recipe["id"], "user1")

            # Verify aggregates reset to defaults
            recipe_no_ratings = db.get_recipe(recipe["id"])
            assert recipe_no_ratings["avg_rating"] == 0
            assert recipe_no_ratings["rating_count"] == 0


class TestRatingConstraints:
    """Test rating constraints and database integrity"""

    def test_rating_unique_constraint(self, memory_db_with_schema):
        """Test that user can only have one rating per recipe (enforced by update)"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            # Set initial rating
            rating_data = {
                "cognito_user_id": "user1",
                "cognito_username": "user1",
                "recipe_id": recipe["id"],
                "rating": 3,
            }
            first_result = db.set_rating(rating_data)

            # "Set" rating again (should update, not create new)
            rating_data["rating"] = 5
            second_result = db.set_rating(rating_data)

            # Should be same rating ID (updated)
            assert second_result["id"] == first_result["id"]

            # Verify only one rating exists
            all_ratings = db.get_recipe_ratings(recipe["id"])
            assert len(all_ratings) == 1
            assert all_ratings[0]["rating"] == 5

    def test_rating_recipe_foreign_key(self, memory_db_with_schema):
        """Test rating foreign key constraint to recipes"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Try to rate non-existent recipe
            rating_data = {
                "cognito_user_id": "user1",
                "cognito_username": "user1",
                "recipe_id": 999,  # Non-existent
                "rating": 4,
            }

            with pytest.raises(ValueError, match="Recipe with ID 999 does not exist"):
                db.set_rating(rating_data)

    def test_rating_cascade_delete_with_recipe(self, memory_db_with_schema):
        """Test that ratings are deleted when recipe is deleted (cascade)"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipe and rating
            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})
            db.set_rating(
                {
                    "cognito_user_id": "user1",
                    "cognito_username": "user1",
                    "recipe_id": recipe["id"],
                    "rating": 4,
                }
            )

            # Verify rating exists
            assert db.get_user_rating(recipe["id"], "user1") is not None

            # Delete recipe
            db.delete_recipe(recipe["id"])

            # Verify rating was cascade deleted
            ratings_after = db.execute_query(
                "SELECT COUNT(*) as count FROM ratings WHERE recipe_id = ?",
                (recipe["id"],),
            )
            assert ratings_after[0]["count"] == 0


class TestRatingEdgeCases:
    """Test edge cases and error conditions"""

    def test_rating_boundary_values(self, memory_db_with_schema):
        """Test rating boundary values (1 and 5)"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            # Test minimum rating (1)
            min_rating = db.set_rating(
                {
                    "cognito_user_id": "user1",
                    "cognito_username": "user1",
                    "recipe_id": recipe["id"],
                    "rating": 1,
                }
            )
            assert min_rating["rating"] == 1

            # Test maximum rating (5)
            max_rating = db.set_rating(
                {
                    "cognito_user_id": "user2",
                    "cognito_username": "user2",
                    "recipe_id": recipe["id"],
                    "rating": 5,
                }
            )
            assert max_rating["rating"] == 5

    def test_rating_with_special_user_ids(self, memory_db_with_schema):
        """Test ratings with special characters in user IDs"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            # Test with UUID-like user ID
            uuid_user_id = "550e8400-e29b-41d4-a716-446655440000"
            result = db.set_rating(
                {
                    "cognito_user_id": uuid_user_id,
                    "cognito_username": "uuid_user",
                    "recipe_id": recipe["id"],
                    "rating": 4,
                }
            )
            assert result["cognito_user_id"] == uuid_user_id

    def test_rating_with_unicode_username(self, memory_db_with_schema):
        """Test ratings with unicode usernames"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            unicode_username = "用户名🍸"
            result = db.set_rating(
                {
                    "cognito_user_id": "user1",
                    "cognito_username": unicode_username,
                    "recipe_id": recipe["id"],
                    "rating": 4,
                }
            )
            assert result["cognito_username"] == unicode_username

    def test_rating_extreme_aggregation_scenarios(self, memory_db_with_schema):
        """Test aggregation with many ratings"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe(
                {"name": "Popular Recipe", "instructions": "Test"}
            )

            # Add 100 ratings (50 fives, 50 ones) - should average to 3.0
            for i in range(100):
                rating = 5 if i < 50 else 1
                db.set_rating(
                    {
                        "cognito_user_id": f"user{i}",
                        "cognito_username": f"user{i}",
                        "recipe_id": recipe["id"],
                        "rating": rating,
                    }
                )

            recipe_result = db.get_recipe(recipe["id"])
            assert recipe_result["avg_rating"] == 3.0
            assert recipe_result["rating_count"] == 100
