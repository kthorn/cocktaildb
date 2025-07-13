"""
Database Layer Tests for User Ingredients functionality
Tests the Database class methods for user ingredient inventory management
"""

import pytest
from unittest.mock import patch
from api.db.db_core import Database


class TestDatabaseUserIngredients:
    """Test user ingredients database operations"""

    def test_add_user_ingredient_success(self, db_instance):
        """Test successfully adding an ingredient to user's inventory"""
        # First insert a test ingredient
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Test Ingredient", "Test Description")
        )
        
        # Get the ingredient ID
        ingredient_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = ?",
            ("Test Ingredient",)
        )
        ingredient_id = ingredient_result[0]["id"]
        
        # Add ingredient to user's inventory
        user_id = "test-user-123"
        result = db_instance.add_user_ingredient(user_id, ingredient_id)
        
        assert result["ingredient_id"] == ingredient_id
        assert result["ingredient_name"] == "Test Ingredient"
        assert "added_at" in result
        
        # Verify ingredient was added to database
        check_result = db_instance.execute_query(
            "SELECT * FROM user_ingredients WHERE cognito_user_id = ? AND ingredient_id = ?",
            (user_id, ingredient_id)
        )
        assert len(check_result) == 1
        assert check_result[0]["cognito_user_id"] == user_id
        assert check_result[0]["ingredient_id"] == ingredient_id

    def test_add_user_ingredient_already_exists(self, db_instance):
        """Test adding an ingredient that already exists in user's inventory"""
        # Insert test ingredient
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Test Ingredient", "Test Description")
        )
        
        ingredient_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = ?",
            ("Test Ingredient",)
        )
        ingredient_id = ingredient_result[0]["id"]
        
        user_id = "test-user-123"
        
        # Add ingredient first time
        db_instance.add_user_ingredient(user_id, ingredient_id)
        
        # Add the same ingredient again - should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            db_instance.add_user_ingredient(user_id, ingredient_id)
        
        assert "already exists" in str(exc_info.value)

    def test_add_user_ingredient_nonexistent_ingredient(self, db_instance):
        """Test adding a nonexistent ingredient to user's inventory"""
        user_id = "test-user-123"
        nonexistent_id = 999999
        
        with pytest.raises(ValueError) as exc_info:
            db_instance.add_user_ingredient(user_id, nonexistent_id)
        
        assert "does not exist" in str(exc_info.value)

    def test_remove_user_ingredient_success(self, db_instance):
        """Test successfully removing an ingredient from user's inventory"""
        # Insert test ingredient
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Test Ingredient", "Test Description")
        )
        
        ingredient_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = ?",
            ("Test Ingredient",)
        )
        ingredient_id = ingredient_result[0]["id"]
        
        user_id = "test-user-123"
        
        # Add ingredient to user's inventory
        db_instance.add_user_ingredient(user_id, ingredient_id)
        
        # Remove ingredient from user's inventory
        result = db_instance.remove_user_ingredient(user_id, ingredient_id)
        
        assert result is True
        
        # Verify ingredient was removed from database
        check_result = db_instance.execute_query(
            "SELECT * FROM user_ingredients WHERE cognito_user_id = ? AND ingredient_id = ?",
            (user_id, ingredient_id)
        )
        assert len(check_result) == 0

    def test_remove_user_ingredient_not_found(self, db_instance):
        """Test removing an ingredient that doesn't exist in user's inventory"""
        # Insert test ingredient
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Test Ingredient", "Test Description")
        )
        
        ingredient_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = ?",
            ("Test Ingredient",)
        )
        ingredient_id = ingredient_result[0]["id"]
        
        user_id = "test-user-123"
        
        # Try to remove ingredient that was never added
        result = db_instance.remove_user_ingredient(user_id, ingredient_id)
        
        assert result is False

    def test_get_user_ingredients_success(self, db_instance):
        """Test getting all ingredients for a user"""
        # Insert test ingredients
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Test Ingredient 1", "Test Description 1")
        )
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Test Ingredient 2", "Test Description 2")
        )
        
        ingredient1_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = ?",
            ("Test Ingredient 1",)
        )
        ingredient2_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = ?",
            ("Test Ingredient 2",)
        )
        
        ingredient1_id = ingredient1_result[0]["id"]
        ingredient2_id = ingredient2_result[0]["id"]
        
        user_id = "test-user-123"
        
        # Add ingredients to user's inventory
        db_instance.add_user_ingredient(user_id, ingredient1_id)
        db_instance.add_user_ingredient(user_id, ingredient2_id)
        
        # Get all user ingredients
        result = db_instance.get_user_ingredients(user_id)
        
        assert len(result) == 2
        
        # Check that both ingredients are returned with correct structure
        ingredient_names = [ingredient["name"] for ingredient in result]
        assert "Test Ingredient 1" in ingredient_names
        assert "Test Ingredient 2" in ingredient_names
        
        # Check structure of returned ingredients
        for ingredient in result:
            assert "ingredient_id" in ingredient
            assert "name" in ingredient
            assert "description" in ingredient
            assert "parent_id" in ingredient
            assert "path" in ingredient
            assert "added_at" in ingredient

    def test_get_user_ingredients_empty(self, db_instance):
        """Test getting ingredients for a user with no ingredients"""
        user_id = "test-user-123"
        
        result = db_instance.get_user_ingredients(user_id)
        
        assert result == []

    def test_add_user_ingredients_bulk_success(self, db_instance):
        """Test successfully adding multiple ingredients to user's inventory"""
        # Insert test ingredients
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Test Ingredient 1", "Test Description 1")
        )
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Test Ingredient 2", "Test Description 2")
        )
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Test Ingredient 3", "Test Description 3")
        )
        
        # Get ingredient IDs
        ingredient1_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = ?",
            ("Test Ingredient 1",)
        )
        ingredient2_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = ?",
            ("Test Ingredient 2",)
        )
        ingredient3_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = ?",
            ("Test Ingredient 3",)
        )
        
        ingredient_ids = [
            ingredient1_result[0]["id"],
            ingredient2_result[0]["id"],
            ingredient3_result[0]["id"]
        ]
        
        user_id = "test-user-123"
        
        # Add ingredients in bulk
        result = db_instance.add_user_ingredients_bulk(user_id, ingredient_ids)
        
        assert result["added_count"] == 3
        assert result["already_exists_count"] == 0
        assert result["failed_count"] == 0
        assert result["errors"] == []
        
        # Verify all ingredients were added
        for ingredient_id in ingredient_ids:
            check_result = db_instance.execute_query(
                "SELECT * FROM user_ingredients WHERE cognito_user_id = ? AND ingredient_id = ?",
                (user_id, ingredient_id)
            )
            assert len(check_result) == 1

    def test_add_user_ingredients_bulk_mixed_results(self, db_instance):
        """Test bulk adding ingredients with mixed success/failure results"""
        # Insert test ingredients
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Test Ingredient 1", "Test Description 1")
        )
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Test Ingredient 2", "Test Description 2")
        )
        
        ingredient1_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = ?",
            ("Test Ingredient 1",)
        )
        ingredient2_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = ?",
            ("Test Ingredient 2",)
        )
        
        ingredient1_id = ingredient1_result[0]["id"]
        ingredient2_id = ingredient2_result[0]["id"]
        nonexistent_id = 999999
        
        user_id = "test-user-123"
        
        # Add one ingredient first
        db_instance.add_user_ingredient(user_id, ingredient1_id)
        
        # Bulk add: one already exists, one new, one nonexistent
        ingredient_ids = [ingredient1_id, ingredient2_id, nonexistent_id]
        result = db_instance.add_user_ingredients_bulk(user_id, ingredient_ids)
        
        assert result["added_count"] == 1  # ingredient2 added
        assert result["already_exists_count"] == 1  # ingredient1 already exists
        assert result["failed_count"] == 1  # nonexistent ingredient failed
        assert len(result["errors"]) == 1
        assert "999999" in result["errors"][0]

    def test_remove_user_ingredients_bulk_success(self, db_instance):
        """Test successfully removing multiple ingredients from user's inventory"""
        # Insert test ingredients
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Test Ingredient 1", "Test Description 1")
        )
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Test Ingredient 2", "Test Description 2")
        )
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Test Ingredient 3", "Test Description 3")
        )
        
        # Get ingredient IDs
        ingredient1_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = ?",
            ("Test Ingredient 1",)
        )
        ingredient2_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = ?",
            ("Test Ingredient 2",)
        )
        ingredient3_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = ?",
            ("Test Ingredient 3",)
        )
        
        ingredient_ids = [
            ingredient1_result[0]["id"],
            ingredient2_result[0]["id"],
            ingredient3_result[0]["id"]
        ]
        
        user_id = "test-user-123"
        
        # Add ingredients to user's inventory
        for ingredient_id in ingredient_ids:
            db_instance.add_user_ingredient(user_id, ingredient_id)
        
        # Remove ingredients in bulk
        result = db_instance.remove_user_ingredients_bulk(user_id, ingredient_ids)
        
        assert result["removed_count"] == 3
        assert result["not_found_count"] == 0
        
        # Verify all ingredients were removed
        for ingredient_id in ingredient_ids:
            check_result = db_instance.execute_query(
                "SELECT * FROM user_ingredients WHERE cognito_user_id = ? AND ingredient_id = ?",
                (user_id, ingredient_id)
            )
            assert len(check_result) == 0

    def test_remove_user_ingredients_bulk_mixed_results(self, db_instance):
        """Test bulk removing ingredients with mixed success/failure results"""
        # Insert test ingredients
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Test Ingredient 1", "Test Description 1")
        )
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Test Ingredient 2", "Test Description 2")
        )
        
        ingredient1_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = ?",
            ("Test Ingredient 1",)
        )
        ingredient2_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = ?",
            ("Test Ingredient 2",)
        )
        
        ingredient1_id = ingredient1_result[0]["id"]
        ingredient2_id = ingredient2_result[0]["id"]
        nonexistent_id = 999999
        
        user_id = "test-user-123"
        
        # Add only one ingredient to user's inventory
        db_instance.add_user_ingredient(user_id, ingredient1_id)
        
        # Bulk remove: one exists, one doesn't exist in user's inventory, one nonexistent ingredient
        ingredient_ids = [ingredient1_id, ingredient2_id, nonexistent_id]
        result = db_instance.remove_user_ingredients_bulk(user_id, ingredient_ids)
        
        assert result["removed_count"] == 1  # ingredient1 removed
        assert result["not_found_count"] == 2  # ingredient2 and nonexistent not found

    def test_user_ingredients_isolation(self, db_instance):
        """Test that user ingredients are properly isolated between users"""
        # Insert test ingredient
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Test Ingredient", "Test Description")
        )
        
        ingredient_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = ?",
            ("Test Ingredient",)
        )
        ingredient_id = ingredient_result[0]["id"]
        
        user1_id = "test-user-123"
        user2_id = "test-user-456"
        
        # Add ingredient to user1's inventory
        db_instance.add_user_ingredient(user1_id, ingredient_id)
        
        # Check user1 has the ingredient
        user1_ingredients = db_instance.get_user_ingredients(user1_id)
        assert len(user1_ingredients) == 1
        assert user1_ingredients[0]["ingredient_id"] == ingredient_id
        
        # Check user2 doesn't have the ingredient
        user2_ingredients = db_instance.get_user_ingredients(user2_id)
        assert len(user2_ingredients) == 0
        
        # Add ingredient to user2's inventory
        db_instance.add_user_ingredient(user2_id, ingredient_id)
        
        # Check both users have the ingredient independently
        user1_ingredients = db_instance.get_user_ingredients(user1_id)
        user2_ingredients = db_instance.get_user_ingredients(user2_id)
        
        assert len(user1_ingredients) == 1
        assert len(user2_ingredients) == 1
        assert user1_ingredients[0]["ingredient_id"] == ingredient_id
        assert user2_ingredients[0]["ingredient_id"] == ingredient_id
        
        # Remove ingredient from user1's inventory
        db_instance.remove_user_ingredient(user1_id, ingredient_id)
        
        # Check user1 doesn't have it but user2 still does
        user1_ingredients = db_instance.get_user_ingredients(user1_id)
        user2_ingredients = db_instance.get_user_ingredients(user2_id)
        
        assert len(user1_ingredients) == 0
        assert len(user2_ingredients) == 1

    def test_user_ingredients_with_hierarchical_ingredients(self, db_instance):
        """Test user ingredients with hierarchical ingredient structure"""
        # Insert hierarchical ingredients
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description, parent_id, path) VALUES (?, ?, ?, ?)",
            ("Test Spirits", "Alcoholic beverages", None, "/1/")
        )
        
        # Get the spirits ID for the parent reference
        spirits_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = ?",
            ("Test Spirits",)
        )
        spirits_id = spirits_result[0]["id"]
        
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description, parent_id, path) VALUES (?, ?, ?, ?)",
            ("Test Gin", "Juniper-flavored spirit", spirits_id, f"/{spirits_id}/2/")
        )
        
        gin_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = ?",
            ("Test Gin",)
        )
        
        gin_id = gin_result[0]["id"]
        
        user_id = "test-user-123"
        
        # Add gin to user's inventory
        db_instance.add_user_ingredient(user_id, gin_id)
        
        # Get user ingredients
        user_ingredients = db_instance.get_user_ingredients(user_id)
        
        assert len(user_ingredients) == 1
        gin_ingredient = user_ingredients[0]
        assert gin_ingredient["name"] == "Test Gin"
        assert gin_ingredient["parent_id"] == spirits_id
        assert gin_ingredient["path"] == f"/{spirits_id}/2/"

    def test_get_user_ingredients_sorted_by_name(self, db_instance):
        """Test that get_user_ingredients returns ingredients sorted by name"""
        # Insert test ingredients in non-alphabetical order
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Zucchini", "Green vegetable")
        )
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Apple", "Red fruit")
        )
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Banana", "Yellow fruit")
        )
        
        # Get ingredient IDs
        zucchini_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = ?",
            ("Zucchini",)
        )
        apple_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = ?",
            ("Apple",)
        )
        banana_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = ?",
            ("Banana",)
        )
        
        ingredient_ids = [
            zucchini_result[0]["id"],
            apple_result[0]["id"],
            banana_result[0]["id"]
        ]
        
        user_id = "test-user-123"
        
        # Add ingredients to user's inventory
        for ingredient_id in ingredient_ids:
            db_instance.add_user_ingredient(user_id, ingredient_id)
        
        # Get user ingredients
        user_ingredients = db_instance.get_user_ingredients(user_id)
        
        assert len(user_ingredients) == 3
        
        # Check that ingredients are sorted by name
        ingredient_names = [ingredient["name"] for ingredient in user_ingredients]
        assert ingredient_names == ["Apple", "Banana", "Zucchini"]