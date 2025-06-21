"""
Recipe Management Testing
Comprehensive tests for recipe CRUD operations, ingredient relationships,
and complex query scenarios
"""

import pytest
import sqlite3
import os
from typing import Dict, Any, List
from unittest.mock import patch

from api.db.db_core import Database


class TestRecipeCRUD:
    """Test basic CRUD operations for recipes"""

    def test_create_recipe_simple(self, memory_db_with_schema):
        """Test creating a simple recipe without ingredients"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            recipe_data = {
                "name": "simple martini",
                "instructions": "Stir with ice and strain",
                "description": "A classic martini",
                "image_url": "http://example.com/martini.jpg",
                "source": "Classic Cocktails",
                "source_url": "http://example.com/recipe"
            }
            
            result = db.create_recipe(recipe_data)
            
            assert result["id"] is not None
            assert result["name"] == "Simple Martini"  # Should be title-cased
            assert result["instructions"] == "Stir with ice and strain"
            assert result["description"] == "A classic martini"
            assert result["image_url"] == "http://example.com/martini.jpg"
            assert result["source"] == "Classic Cocktails"
            assert result["source_url"] == "http://example.com/recipe"
            assert result["avg_rating"] == 0
            assert result["rating_count"] == 0

    def test_create_recipe_with_ingredients(self, memory_db_with_schema):
        """Test creating a recipe with ingredients"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            # Create ingredients first
            gin = db.create_ingredient({"name": "Gin", "description": "Gin", "parent_id": None})
            vermouth = db.create_ingredient({"name": "Dry Vermouth", "description": "Vermouth", "parent_id": None})
            
            # Create units
            db.execute_query("INSERT INTO units (name, abbreviation) VALUES (?, ?)", ("Ounce", "oz"))
            unit_result = db.execute_query("SELECT id FROM units WHERE name = ?", ("Ounce",))
            unit_id = unit_result[0]["id"]
            
            recipe_data = {
                "name": "Classic Martini",
                "instructions": "Stir with ice and strain",
                "ingredients": [
                    {"ingredient_id": gin["id"], "unit_id": unit_id, "amount": 2.5},
                    {"ingredient_id": vermouth["id"], "unit_id": unit_id, "amount": 0.5}
                ]
            }
            
            result = db.create_recipe(recipe_data)
            
            assert result["id"] is not None
            assert result["name"] == "Classic Martini"
            assert len(result["ingredients"]) == 2
            
            # Verify ingredient details
            gin_ingredient = next(ing for ing in result["ingredients"] if ing["ingredient_id"] == gin["id"])
            assert gin_ingredient["amount"] == 2.5
            assert gin_ingredient["unit_id"] == unit_id

    def test_create_recipe_duplicate_name(self, memory_db_with_schema):
        """Test that duplicate recipe names are handled"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            recipe_data = {
                "name": "Martini",
                "instructions": "First recipe"
            }
            
            # Create first recipe
            db.create_recipe(recipe_data)
            
            # Attempt to create duplicate
            with pytest.raises(sqlite3.IntegrityError):
                db.create_recipe(recipe_data)

    def test_create_recipe_invalid_ingredient(self, memory_db_with_schema):
        """Test creating recipe with non-existent ingredient"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            recipe_data = {
                "name": "Invalid Recipe",
                "instructions": "Test recipe",
                "ingredients": [
                    {"ingredient_id": 999, "amount": 1.0}  # Non-existent ingredient
                ]
            }
            
            with pytest.raises(sqlite3.IntegrityError):
                db.create_recipe(recipe_data)

    def test_get_recipe_by_id(self, memory_db_with_schema):
        """Test retrieving recipe by ID"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            # Create recipe
            recipe_data = {"name": "Test Recipe", "instructions": "Test instructions"}
            created = db.create_recipe(recipe_data)
            
            # Retrieve by ID
            result = db.get_recipe(created["id"])
            
            assert result is not None
            assert result["id"] == created["id"]
            assert result["name"] == "Test Recipe"
            assert result["instructions"] == "Test instructions"

    def test_get_recipe_nonexistent(self, memory_db_with_schema):
        """Test retrieving non-existent recipe"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            result = db.get_recipe(999)
            assert result is None

    def test_get_recipes_empty(self, memory_db_with_schema):
        """Test getting recipes when database is empty"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            result = db.get_recipes()
            assert isinstance(result, list)
            assert len(result) == 0

    def test_get_recipes_multiple(self, memory_db_with_schema):
        """Test getting multiple recipes"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            # Create multiple recipes
            recipes = [
                {"name": "Martini", "instructions": "Martini instructions"},
                {"name": "Manhattan", "instructions": "Manhattan instructions"}
            ]
            
            for recipe_data in recipes:
                db.create_recipe(recipe_data)
            
            result = db.get_recipes()
            assert len(result) == 2
            
            names = {recipe["name"] for recipe in result}
            assert names == {"Martini", "Manhattan"}


class TestRecipeIngredientRelationships:
    """Test complex recipe-ingredient relationships"""

    def test_recipe_with_hierarchical_ingredients(self, memory_db_with_schema):
        """Test recipe using hierarchical ingredients"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            # Create ingredient hierarchy
            spirits = db.create_ingredient({"name": "Spirits", "description": "Spirits", "parent_id": None})
            gin = db.create_ingredient({"name": "Gin", "description": "Gin", "parent_id": spirits["id"]})
            london_gin = db.create_ingredient({"name": "London Dry Gin", "description": "London Gin", "parent_id": gin["id"]})
            
            # Create recipe using specific gin type
            recipe_data = {
                "name": "Premium Martini",
                "instructions": "Use premium gin",
                "ingredients": [
                    {"ingredient_id": london_gin["id"], "amount": 2.0}
                ]
            }
            
            result = db.create_recipe(recipe_data)
            
            # Verify ingredient includes full hierarchy info
            ingredient = result["ingredients"][0]
            assert ingredient["ingredient_id"] == london_gin["id"]
            assert "Gin" in ingredient["full_name"]  # Should include parent names

    def test_recipe_ingredient_full_names(self, memory_db_with_schema):
        """Test that recipe ingredients include full hierarchical names"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            # Create hierarchy: Spirits -> Gin -> London Dry Gin
            spirits = db.create_ingredient({"name": "Spirits", "description": "Spirits", "parent_id": None})
            gin = db.create_ingredient({"name": "Gin", "description": "Gin", "parent_id": spirits["id"]})
            london_gin = db.create_ingredient({"name": "London Dry Gin", "description": "London Gin", "parent_id": gin["id"]})
            
            recipe_data = {
                "name": "Gin Martini",
                "instructions": "Use London Dry Gin",
                "ingredients": [{"ingredient_id": london_gin["id"], "amount": 2.0}]
            }
            
            recipe = db.create_recipe(recipe_data)
            ingredient = recipe["ingredients"][0]
            
            # The full_name should include the hierarchy
            assert "full_name" in ingredient
            assert "Spirits" in ingredient["full_name"]
            assert "Gin" in ingredient["full_name"]
            assert "London Dry Gin" in ingredient["full_name"]

    def test_recipe_with_units(self, memory_db_with_schema):
        """Test recipe with ingredient units"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            # Create ingredient and unit
            gin = db.create_ingredient({"name": "Gin", "description": "Gin", "parent_id": None})
            db.execute_query(
                "INSERT INTO units (name, abbreviation, conversion_to_ml) VALUES (?, ?, ?)",
                ("Ounce", "oz", 29.5735)
            )
            unit_result = db.execute_query("SELECT id FROM units WHERE name = ?", ("Ounce",))
            unit_id = unit_result[0]["id"]
            
            recipe_data = {
                "name": "Measured Martini",
                "instructions": "Measure carefully",
                "ingredients": [
                    {"ingredient_id": gin["id"], "unit_id": unit_id, "amount": 2.0}
                ]
            }
            
            recipe = db.create_recipe(recipe_data)
            ingredient = recipe["ingredients"][0]
            
            assert ingredient["unit_id"] == unit_id
            assert ingredient["unit_name"] == "Ounce"
            assert ingredient["unit_abbreviation"] == "oz"

    def test_recipe_without_units(self, memory_db_with_schema):
        """Test recipe with ingredients that don't specify units"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            gin = db.create_ingredient({"name": "Gin", "description": "Gin", "parent_id": None})
            
            recipe_data = {
                "name": "Flexible Martini",
                "instructions": "Add gin to taste",
                "ingredients": [
                    {"ingredient_id": gin["id"], "amount": None}  # No specific amount
                ]
            }
            
            recipe = db.create_recipe(recipe_data)
            ingredient = recipe["ingredients"][0]
            
            assert ingredient["unit_id"] is None
            assert ingredient["unit_name"] is None
            assert ingredient["amount"] is None


class TestRecipeUpdate:
    """Test recipe update operations"""

    def test_update_recipe_basic_fields(self, memory_db_with_schema):
        """Test updating basic recipe fields"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            # Create recipe
            original = db.create_recipe({
                "name": "Original Martini",
                "instructions": "Original instructions",
                "description": "Original description"
            })
            
            # Update recipe
            update_data = {
                "name": "Updated Martini",
                "instructions": "Updated instructions",
                "description": "Updated description"
            }
            
            updated = db.update_recipe(original["id"], update_data)
            
            assert updated is not None
            assert updated["name"] == "Updated Martini"
            assert updated["instructions"] == "Updated instructions"
            assert updated["description"] == "Updated description"

    def test_update_recipe_ingredients(self, memory_db_with_schema):
        """Test updating recipe ingredients"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            # Create ingredients
            gin = db.create_ingredient({"name": "Gin", "description": "Gin", "parent_id": None})
            vermouth = db.create_ingredient({"name": "Vermouth", "description": "Vermouth", "parent_id": None})
            olive = db.create_ingredient({"name": "Olive", "description": "Olive", "parent_id": None})
            
            # Create recipe with original ingredients
            original = db.create_recipe({
                "name": "Martini",
                "instructions": "Stir and strain",
                "ingredients": [
                    {"ingredient_id": gin["id"], "amount": 2.0},
                    {"ingredient_id": vermouth["id"], "amount": 0.5}
                ]
            })
            
            # Update with different ingredients
            update_data = {
                "ingredients": [
                    {"ingredient_id": gin["id"], "amount": 2.5},  # Updated amount
                    {"ingredient_id": olive["id"], "amount": 1.0}  # New ingredient, vermouth removed
                ]
            }
            
            updated = db.update_recipe(original["id"], update_data)
            
            assert len(updated["ingredients"]) == 2
            
            # Verify gin amount was updated
            gin_ingredient = next(ing for ing in updated["ingredients"] if ing["ingredient_id"] == gin["id"])
            assert gin_ingredient["amount"] == 2.5
            
            # Verify olive was added
            olive_ingredient = next(ing for ing in updated["ingredients"] if ing["ingredient_id"] == olive["id"])
            assert olive_ingredient["amount"] == 1.0
            
            # Verify vermouth was removed
            vermouth_ingredients = [ing for ing in updated["ingredients"] if ing["ingredient_id"] == vermouth["id"]]
            assert len(vermouth_ingredients) == 0

    def test_update_recipe_partial_fields(self, memory_db_with_schema):
        """Test updating only some recipe fields"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            original = db.create_recipe({
                "name": "Original Name",
                "instructions": "Original instructions",
                "description": "Original description",
                "source": "Original source"
            })
            
            # Update only instructions
            update_data = {"instructions": "New instructions"}
            
            updated = db.update_recipe(original["id"], update_data)
            
            assert updated["name"] == "Original Name"  # Unchanged
            assert updated["instructions"] == "New instructions"  # Changed
            assert updated["description"] == "Original description"  # Unchanged
            assert updated["source"] == "Original source"  # Unchanged

    def test_update_recipe_nonexistent(self, memory_db_with_schema):
        """Test updating non-existent recipe"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            result = db.update_recipe(999, {"name": "New Name"})
            assert result is None


class TestRecipeDeletion:
    """Test recipe deletion operations"""

    def test_delete_recipe_simple(self, memory_db_with_schema):
        """Test deleting a simple recipe"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})
            
            result = db.delete_recipe(recipe["id"])
            assert result is True
            
            # Verify deletion
            assert db.get_recipe(recipe["id"]) is None

    def test_delete_recipe_with_ingredients(self, memory_db_with_schema):
        """Test deleting recipe with ingredients (cascade delete)"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            # Create ingredient and recipe
            gin = db.create_ingredient({"name": "Gin", "description": "Gin", "parent_id": None})
            recipe = db.create_recipe({
                "name": "Gin Martini",
                "instructions": "Add gin",
                "ingredients": [{"ingredient_id": gin["id"], "amount": 2.0}]
            })
            
            # Verify recipe_ingredients were created
            ingredients_before = db.execute_query(
                "SELECT COUNT(*) as count FROM recipe_ingredients WHERE recipe_id = ?",
                (recipe["id"],)
            )
            assert ingredients_before[0]["count"] == 1
            
            # Delete recipe
            result = db.delete_recipe(recipe["id"])
            assert result is True
            
            # Verify recipe_ingredients were also deleted (cascade)
            ingredients_after = db.execute_query(
                "SELECT COUNT(*) as count FROM recipe_ingredients WHERE recipe_id = ?",
                (recipe["id"],)
            )
            assert ingredients_after[0]["count"] == 0
            
            # Verify ingredient itself still exists
            assert db.get_ingredient(gin["id"]) is not None

    def test_delete_recipe_nonexistent(self, memory_db_with_schema):
        """Test deleting non-existent recipe"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            result = db.delete_recipe(999)
            assert result is False


class TestRecipeWithTags:
    """Test recipe operations with tags"""

    def test_get_recipe_with_tags(self, memory_db_with_schema):
        """Test retrieving recipe with associated tags"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            # Create recipe
            recipe = db.create_recipe({"name": "Tagged Recipe", "instructions": "Test"})
            
            # Create and associate public tag
            public_tag = db.create_public_tag("classic")
            db.add_public_tag_to_recipe(recipe["id"], public_tag["id"])
            
            # Create and associate private tag
            private_tag = db.create_private_tag("personal", "user123", "testuser")
            db.add_private_tag_to_recipe(recipe["id"], private_tag["id"])
            
            # Retrieve recipe with user context
            result = db.get_recipe(recipe["id"], "user123")
            
            assert "tags" in result
            assert len(result["tags"]) == 2
            
            # Verify tag types
            public_tags = [tag for tag in result["tags"] if tag["type"] == "public"]
            private_tags = [tag for tag in result["tags"] if tag["type"] == "private"]
            
            assert len(public_tags) == 1
            assert len(private_tags) == 1
            assert public_tags[0]["name"] == "classic"
            assert private_tags[0]["name"] == "personal"

    def test_get_recipe_tags_without_user_context(self, memory_db_with_schema):
        """Test retrieving recipe tags without user context (only public tags)"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            # Create recipe
            recipe = db.create_recipe({"name": "Tagged Recipe", "instructions": "Test"})
            
            # Create and associate public and private tags
            public_tag = db.create_public_tag("classic")
            db.add_public_tag_to_recipe(recipe["id"], public_tag["id"])
            
            private_tag = db.create_private_tag("personal", "user123", "testuser")
            db.add_private_tag_to_recipe(recipe["id"], private_tag["id"])
            
            # Retrieve recipe without user context
            result = db.get_recipe(recipe["id"], None)
            
            # Should only get public tags
            public_tags = [tag for tag in result["tags"] if tag["type"] == "public"]
            private_tags = [tag for tag in result["tags"] if tag["type"] == "private"]
            
            assert len(public_tags) == 1
            assert len(private_tags) == 0


class TestRecipeWithRatings:
    """Test recipe operations with ratings"""

    def test_get_recipe_with_user_rating(self, memory_db_with_schema):
        """Test retrieving recipe with user's rating"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            # Create recipe
            recipe = db.create_recipe({"name": "Rated Recipe", "instructions": "Test"})
            
            # Add user rating
            rating_data = {
                "cognito_user_id": "user123",
                "cognito_username": "testuser",
                "recipe_id": recipe["id"],
                "rating": 4
            }
            db.set_rating(rating_data)
            
            # Retrieve recipe with user context
            result = db.get_recipe(recipe["id"], "user123")
            
            assert result["user_rating"] == 4
            assert result["avg_rating"] == 4.0
            assert result["rating_count"] == 1

    def test_get_recipe_without_user_rating(self, memory_db_with_schema):
        """Test retrieving recipe without user's rating"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            # Create recipe
            recipe = db.create_recipe({"name": "Unrated Recipe", "instructions": "Test"})
            
            # Retrieve recipe without user context
            result = db.get_recipe(recipe["id"], None)
            
            assert result["user_rating"] is None
            assert result["avg_rating"] == 0
            assert result["rating_count"] == 0


class TestRecipePerformance:
    """Test recipe performance optimizations"""

    def test_get_recipes_optimized(self, memory_db_with_schema):
        """Test that get_recipes is optimized for list view"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            # Create ingredients
            gin = db.create_ingredient({"name": "Gin", "description": "Gin", "parent_id": None})
            vermouth = db.create_ingredient({"name": "Vermouth", "description": "Vermouth", "parent_id": None})
            
            # Create recipe with ingredients
            recipe = db.create_recipe({
                "name": "Performance Test Recipe",
                "instructions": "Test performance",
                "ingredients": [
                    {"ingredient_id": gin["id"], "amount": 2.0},
                    {"ingredient_id": vermouth["id"], "amount": 0.5}
                ]
            })
            
            # get_recipes should return ingredient_count but not full ingredient details
            result = db.get_recipes()
            
            assert len(result) == 1
            test_recipe = result[0]
            
            # Should have ingredient count for list view
            assert "ingredient_count" in test_recipe
            assert test_recipe["ingredient_count"] == 2
            
            # Should NOT have full ingredient details in list view
            assert "ingredients" not in test_recipe

    def test_get_recipes_with_ingredients_detailed(self, memory_db_with_schema):
        """Test that get_recipes_with_ingredients returns full details"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            # Create ingredients
            gin = db.create_ingredient({"name": "Gin", "description": "Gin", "parent_id": None})
            
            # Create recipe
            recipe = db.create_recipe({
                "name": "Detailed Test Recipe",
                "instructions": "Test detailed view",
                "ingredients": [{"ingredient_id": gin["id"], "amount": 2.0}]
            })
            
            # get_recipes_with_ingredients should return full ingredient details
            result = db.get_recipes_with_ingredients()
            
            assert len(result) == 1
            test_recipe = result[0]
            
            # Should have full ingredient details
            assert "ingredients" in test_recipe
            assert len(test_recipe["ingredients"]) == 1
            
            ingredient = test_recipe["ingredients"][0]
            assert ingredient["ingredient_id"] == gin["id"]
            assert ingredient["ingredient_name"] == "Gin"
            assert ingredient["amount"] == 2.0


class TestRecipeConstraints:
    """Test recipe constraints and validation"""

    def test_recipe_name_uniqueness(self, memory_db_with_schema):
        """Test that recipe names must be unique (case-insensitive)"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            # Create first recipe
            db.create_recipe({"name": "Martini", "instructions": "First martini"})
            
            # Try to create with same name (different case)
            with pytest.raises(sqlite3.IntegrityError):
                db.create_recipe({"name": "martini", "instructions": "Second martini"})

    def test_recipe_ingredient_foreign_key(self, memory_db_with_schema):
        """Test recipe_ingredients foreign key constraints"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            # Try to create recipe with non-existent ingredient
            with pytest.raises(sqlite3.IntegrityError):
                db.create_recipe({
                    "name": "Invalid Recipe",
                    "instructions": "Test",
                    "ingredients": [{"ingredient_id": 999, "amount": 1.0}]
                })


class TestRecipeEdgeCases:
    """Test edge cases and error conditions"""

    def test_recipe_empty_name(self, memory_db_with_schema):
        """Test creating recipe with empty name"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            with pytest.raises(Exception):
                db.create_recipe({"name": "", "instructions": "Test"})

    def test_recipe_none_name(self, memory_db_with_schema):
        """Test creating recipe with None name"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            with pytest.raises(Exception):
                db.create_recipe({"name": None, "instructions": "Test"})

    def test_recipe_very_long_name(self, memory_db_with_schema):
        """Test creating recipe with very long name"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            long_name = "A" * 1000
            result = db.create_recipe({
                "name": long_name,
                "instructions": "Test instructions"
            })
            
            assert result["name"] == long_name

    def test_recipe_unicode_content(self, memory_db_with_schema):
        """Test creating recipe with unicode content"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            unicode_data = {
                "name": "Piña Colada 🍹",
                "instructions": "Mix with piña and add 🥥",
                "description": "A tropical drink with piña (pineapple)"
            }
            
            result = db.create_recipe(unicode_data)
            
            assert result["name"] == "Piña Colada 🍹"
            assert result["instructions"] == "Mix with piña and add 🥥"
            assert result["description"] == "A tropical drink with piña (pineapple)"

    def test_recipe_with_zero_amount_ingredient(self, memory_db_with_schema):
        """Test recipe with zero amount ingredient"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            gin = db.create_ingredient({"name": "Gin", "description": "Gin", "parent_id": None})
            
            recipe_data = {
                "name": "Zero Amount Recipe",
                "instructions": "Add no gin",
                "ingredients": [{"ingredient_id": gin["id"], "amount": 0.0}]
            }
            
            result = db.create_recipe(recipe_data)
            
            ingredient = result["ingredients"][0]
            assert ingredient["amount"] == 0.0

    def test_recipe_with_negative_amount_ingredient(self, memory_db_with_schema):
        """Test recipe with negative amount ingredient"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            
            gin = db.create_ingredient({"name": "Gin", "description": "Gin", "parent_id": None})
            
            recipe_data = {
                "name": "Negative Amount Recipe",
                "instructions": "Somehow remove gin",
                "ingredients": [{"ingredient_id": gin["id"], "amount": -1.0}]
            }
            
            # Should allow negative amounts (might be useful for cocktail adjustments)
            result = db.create_recipe(recipe_data)
            
            ingredient = result["ingredients"][0]
            assert ingredient["amount"] == -1.0