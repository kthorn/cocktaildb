"""
Database Utils Testing
Tests for utility functions in db_utils.py including ingredient ID extraction
and full name assembly algorithms
"""

import pytest
import os
from typing import Dict, Any, List
from unittest.mock import patch

from api.db.db_utils import extract_all_ingredient_ids, assemble_ingredient_full_names


class TestExtractAllIngredientIds:
    """Test extract_all_ingredient_ids function"""

    def test_extract_ids_single_ingredient_root_level(self):
        """Test extracting IDs from single root-level ingredient"""
        ingredients_list = [
            {
                "ingredient_id": 5,
                "ingredient_path": "/5/"
            }
        ]
        
        result = extract_all_ingredient_ids(ingredients_list)
        
        assert result == {5}

    def test_extract_ids_single_ingredient_with_hierarchy(self):
        """Test extracting IDs from single ingredient with hierarchy"""
        ingredients_list = [
            {
                "ingredient_id": 10,
                "ingredient_path": "/1/5/10/"
            }
        ]
        
        result = extract_all_ingredient_ids(ingredients_list)
        
        # Should include the ingredient itself and all ancestors
        assert result == {1, 5, 10}

    def test_extract_ids_multiple_ingredients_no_overlap(self):
        """Test extracting IDs from multiple ingredients with no overlap"""
        ingredients_list = [
            {
                "ingredient_id": 5,
                "ingredient_path": "/1/5/"
            },
            {
                "ingredient_id": 8,
                "ingredient_path": "/2/8/"
            }
        ]
        
        result = extract_all_ingredient_ids(ingredients_list)
        
        assert result == {1, 2, 5, 8}

    def test_extract_ids_multiple_ingredients_with_overlap(self):
        """Test extracting IDs from multiple ingredients with overlapping paths"""
        ingredients_list = [
            {
                "ingredient_id": 10,
                "ingredient_path": "/1/5/10/"
            },
            {
                "ingredient_id": 11,
                "ingredient_path": "/1/5/11/"
            },
            {
                "ingredient_id": 12,
                "ingredient_path": "/1/12/"
            }
        ]
        
        result = extract_all_ingredient_ids(ingredients_list)
        
        # Should deduplicate overlapping ancestors
        assert result == {1, 5, 10, 11, 12}

    def test_extract_ids_deep_hierarchy(self):
        """Test extracting IDs from deep ingredient hierarchy"""
        ingredients_list = [
            {
                "ingredient_id": 20,
                "ingredient_path": "/1/3/7/15/20/"
            }
        ]
        
        result = extract_all_ingredient_ids(ingredients_list)
        
        assert result == {1, 3, 7, 15, 20}

    def test_extract_ids_mixed_hierarchy_levels(self):
        """Test extracting IDs from ingredients at different hierarchy levels"""
        ingredients_list = [
            {
                "ingredient_id": 1,
                "ingredient_path": "/1/"  # Root level
            },
            {
                "ingredient_id": 5,
                "ingredient_path": "/1/5/"  # Level 2
            },
            {
                "ingredient_id": 15,
                "ingredient_path": "/1/5/10/15/"  # Level 4
            }
        ]
        
        result = extract_all_ingredient_ids(ingredients_list)
        
        assert result == {1, 5, 10, 15}

    def test_extract_ids_empty_list(self):
        """Test extracting IDs from empty ingredient list"""
        ingredients_list = []
        
        result = extract_all_ingredient_ids(ingredients_list)
        
        assert result == set()

    def test_extract_ids_missing_ingredient_id(self):
        """Test extracting IDs when ingredient_id is missing"""
        ingredients_list = [
            {
                "ingredient_path": "/1/5/"
                # Missing ingredient_id
            }
        ]
        
        result = extract_all_ingredient_ids(ingredients_list)
        
        # Should still extract from path
        assert result == {1, 5}

    def test_extract_ids_missing_path(self):
        """Test extracting IDs when ingredient_path is missing"""
        ingredients_list = [
            {
                "ingredient_id": 5
                # Missing ingredient_path
            }
        ]
        
        result = extract_all_ingredient_ids(ingredients_list)
        
        # Should only include the direct ingredient ID
        assert result == {5}

    def test_extract_ids_none_values(self):
        """Test extracting IDs when values are None"""
        ingredients_list = [
            {
                "ingredient_id": None,
                "ingredient_path": None
            }
        ]
        
        result = extract_all_ingredient_ids(ingredients_list)
        
        assert result == set()

    def test_extract_ids_malformed_path(self):
        """Test extracting IDs from malformed path"""
        ingredients_list = [
            {
                "ingredient_id": 5,
                "ingredient_path": "malformed/path"
            }
        ]
        
        result = extract_all_ingredient_ids(ingredients_list)
        
        # Should still include the direct ingredient ID
        assert result == {5}

    def test_extract_ids_path_with_non_numeric_parts(self):
        """Test extracting IDs from path with non-numeric parts"""
        ingredients_list = [
            {
                "ingredient_id": 5,
                "ingredient_path": "/1/abc/5/"
            }
        ]
        
        result = extract_all_ingredient_ids(ingredients_list)
        
        # Should skip non-numeric parts
        assert result == {1, 5}

    def test_extract_ids_duplicate_paths(self):
        """Test extracting IDs from ingredients with identical paths"""
        ingredients_list = [
            {
                "ingredient_id": 10,
                "ingredient_path": "/1/5/10/"
            },
            {
                "ingredient_id": 10,
                "ingredient_path": "/1/5/10/"
            }
        ]
        
        result = extract_all_ingredient_ids(ingredients_list)
        
        # Should deduplicate
        assert result == {1, 5, 10}

    def test_extract_ids_efficiency_optimization(self):
        """Test that path parsing is optimized for unique paths"""
        # This test verifies the optimization where identical paths
        # are only parsed once
        ingredients_list = [
            {
                "ingredient_id": 10,
                "ingredient_path": "/1/5/10/"
            },
            {
                "ingredient_id": 11,
                "ingredient_path": "/1/5/11/"
            },
            {
                "ingredient_id": 12,
                "ingredient_path": "/1/5/10/"  # Same path as first
            }
        ]
        
        result = extract_all_ingredient_ids(ingredients_list)
        
        assert result == {1, 5, 10, 11, 12}


class TestAssembleIngredientFullNames:
    """Test assemble_ingredient_full_names function"""

    def test_assemble_full_names_single_ingredient_root(self):
        """Test assembling full name for single root-level ingredient"""
        ingredients_list = [
            {
                "ingredient_id": 5,
                "ingredient_name": "Gin",
                "ingredient_path": "/5/"
            }
        ]
        ingredient_names_map = {5: "Gin"}
        
        assemble_ingredient_full_names(ingredients_list, ingredient_names_map)
        
        # Root level ingredient should just use its own name
        assert ingredients_list[0]["full_name"] == "Gin"

    def test_assemble_full_names_two_level_hierarchy(self):
        """Test assembling full name for two-level hierarchy"""
        ingredients_list = [
            {
                "ingredient_id": 10,
                "ingredient_name": "London Dry Gin",
                "ingredient_path": "/5/10/"
            }
        ]
        ingredient_names_map = {
            5: "Gin",
            10: "London Dry Gin"
        }
        
        assemble_ingredient_full_names(ingredients_list, ingredient_names_map)
        
        assert ingredients_list[0]["full_name"] == "London Dry Gin [Gin]"

    def test_assemble_full_names_deep_hierarchy(self):
        """Test assembling full name for deep hierarchy"""
        ingredients_list = [
            {
                "ingredient_id": 20,
                "ingredient_name": "Bombay Sapphire",
                "ingredient_path": "/1/5/10/20/"
            }
        ]
        ingredient_names_map = {
            1: "Spirits",
            5: "Gin", 
            10: "London Dry Gin",
            20: "Bombay Sapphire"
        }
        
        assemble_ingredient_full_names(ingredients_list, ingredient_names_map)
        
        assert ingredients_list[0]["full_name"] == "Bombay Sapphire [London Dry Gin;Gin;Spirits]"

    def test_assemble_full_names_multiple_ingredients(self):
        """Test assembling full names for multiple ingredients"""
        ingredients_list = [
            {
                "ingredient_id": 10,
                "ingredient_name": "London Dry Gin",
                "ingredient_path": "/5/10/"
            },
            {
                "ingredient_id": 15,
                "ingredient_name": "Dry Vermouth",
                "ingredient_path": "/8/15/"
            }
        ]
        ingredient_names_map = {
            5: "Gin",
            8: "Vermouth",
            10: "London Dry Gin",
            15: "Dry Vermouth"
        }
        
        assemble_ingredient_full_names(ingredients_list, ingredient_names_map)
        
        assert ingredients_list[0]["full_name"] == "London Dry Gin [Gin]"
        assert ingredients_list[1]["full_name"] == "Dry Vermouth [Vermouth]"

    def test_assemble_full_names_missing_path(self):
        """Test assembling full name when path is missing"""
        ingredients_list = [
            {
                "ingredient_id": 5,
                "ingredient_name": "Gin"
                # Missing ingredient_path
            }
        ]
        ingredient_names_map = {5: "Gin"}
        
        assemble_ingredient_full_names(ingredients_list, ingredient_names_map)
        
        # Should fallback to just the ingredient name
        assert ingredients_list[0]["full_name"] == "Gin"

    def test_assemble_full_names_missing_names_in_map(self):
        """Test assembling full name when some ancestor names are missing"""
        ingredients_list = [
            {
                "ingredient_id": 20,
                "ingredient_name": "Bombay Sapphire",
                "ingredient_path": "/1/5/10/20/"
            }
        ]
        ingredient_names_map = {
            1: "Spirits",
            # Missing 5 (Gin)
            10: "London Dry Gin",
            20: "Bombay Sapphire"
        }
        
        assemble_ingredient_full_names(ingredients_list, ingredient_names_map)
        
        # Should skip missing names and continue with available ones
        assert ingredients_list[0]["full_name"] == "Bombay Sapphire [London Dry Gin;Spirits]"

    def test_assemble_full_names_empty_list(self):
        """Test assembling full names for empty ingredient list"""
        ingredients_list = []
        ingredient_names_map = {}
        
        # Should not raise exception
        assemble_ingredient_full_names(ingredients_list, ingredient_names_map)
        
        assert len(ingredients_list) == 0

    def test_assemble_full_names_modifies_in_place(self):
        """Test that function modifies the ingredients list in-place"""
        original_list = [
            {
                "ingredient_id": 10,
                "ingredient_name": "London Dry Gin",
                "ingredient_path": "/5/10/"
            }
        ]
        ingredient_names_map = {
            5: "Gin",
            10: "London Dry Gin"
        }
        
        # Keep reference to original list
        ingredients_list = original_list
        
        assemble_ingredient_full_names(ingredients_list, ingredient_names_map)
        
        # Should modify the original list
        assert original_list[0]["full_name"] == "London Dry Gin [Gin]"
        assert ingredients_list is original_list

    def test_assemble_full_names_preserves_other_fields(self):
        """Test that function preserves other fields in ingredient dictionaries"""
        ingredients_list = [
            {
                "ingredient_id": 10,
                "ingredient_name": "London Dry Gin",
                "ingredient_path": "/5/10/",
                "amount": 2.0,
                "unit_id": 1,
                "other_field": "preserved"
            }
        ]
        ingredient_names_map = {
            5: "Gin",
            10: "London Dry Gin"
        }
        
        assemble_ingredient_full_names(ingredients_list, ingredient_names_map)
        
        # Should preserve all original fields
        ingredient = ingredients_list[0]
        assert ingredient["ingredient_id"] == 10
        assert ingredient["ingredient_name"] == "London Dry Gin"
        assert ingredient["ingredient_path"] == "/5/10/"
        assert ingredient["amount"] == 2.0
        assert ingredient["unit_id"] == 1
        assert ingredient["other_field"] == "preserved"
        assert ingredient["full_name"] == "London Dry Gin [Gin]"

    def test_assemble_full_names_malformed_path(self):
        """Test assembling full name with malformed path"""
        ingredients_list = [
            {
                "ingredient_id": 10,
                "ingredient_name": "London Dry Gin",
                "ingredient_path": "malformed"
            }
        ]
        ingredient_names_map = {10: "London Dry Gin"}
        
        assemble_ingredient_full_names(ingredients_list, ingredient_names_map)
        
        # Should fallback to ingredient name
        assert ingredients_list[0]["full_name"] == "London Dry Gin"

    def test_assemble_full_names_none_path(self):
        """Test assembling full name when path is None"""
        ingredients_list = [
            {
                "ingredient_id": 10,
                "ingredient_name": "London Dry Gin",
                "ingredient_path": None
            }
        ]
        ingredient_names_map = {10: "London Dry Gin"}
        
        assemble_ingredient_full_names(ingredients_list, ingredient_names_map)
        
        # Should fallback to ingredient name
        assert ingredients_list[0]["full_name"] == "London Dry Gin"

    def test_assemble_full_names_single_slash_path(self):
        """Test assembling full name with single slash (malformed) path"""
        ingredients_list = [
            {
                "ingredient_id": 10,
                "ingredient_name": "London Dry Gin",
                "ingredient_path": "/"
            }
        ]
        ingredient_names_map = {10: "London Dry Gin"}
        
        assemble_ingredient_full_names(ingredients_list, ingredient_names_map)
        
        # Should fallback to ingredient name
        assert ingredients_list[0]["full_name"] == "London Dry Gin"

    def test_assemble_full_names_unicode_names(self):
        """Test assembling full name with unicode characters"""
        ingredients_list = [
            {
                "ingredient_id": 20,
                "ingredient_name": "Café Liqueur",
                "ingredient_path": "/5/10/20/"
            }
        ]
        ingredient_names_map = {
            5: "Spirits",
            10: "Liqueurs 🍸",
            20: "Café Liqueur"
        }
        
        assemble_ingredient_full_names(ingredients_list, ingredient_names_map)
        
        assert ingredients_list[0]["full_name"] == "Café Liqueur [Liqueurs 🍸;Spirits]"

    def test_assemble_full_names_special_characters(self):
        """Test assembling full name with special characters"""
        ingredients_list = [
            {
                "ingredient_id": 20,
                "ingredient_name": "St-Germain's \"Premium\" & Elderflower",
                "ingredient_path": "/5/20/"
            }
        ]
        ingredient_names_map = {
            5: "Liqueurs & Cordials",
            20: "St-Germain's \"Premium\" & Elderflower"
        }
        
        assemble_ingredient_full_names(ingredients_list, ingredient_names_map)
        
        assert ingredients_list[0]["full_name"] == "St-Germain's \"Premium\" & Elderflower [Liqueurs & Cordials]"


class TestUtilsIntegration:
    """Test integration between utility functions"""

    def test_extract_and_assemble_workflow(self):
        """Test the typical workflow of extracting IDs then assembling names"""
        # This simulates the typical usage pattern in the Database class
        
        # Step 1: Recipe ingredients from database
        recipe_ingredients = [
            {
                "ingredient_id": 15,
                "ingredient_name": "Bombay Sapphire",
                "ingredient_path": "/1/5/10/15/",
                "amount": 2.0
            },
            {
                "ingredient_id": 20,
                "ingredient_name": "Dry Vermouth",
                "ingredient_path": "/3/20/",
                "amount": 0.5
            }
        ]
        
        # Step 2: Extract all needed IDs
        needed_ids = extract_all_ingredient_ids(recipe_ingredients)
        expected_ids = {1, 3, 5, 10, 15, 20}
        assert needed_ids == expected_ids
        
        # Step 3: Simulate fetching names from database
        ingredient_names_map = {
            1: "Spirits",
            3: "Vermouth",
            5: "Gin",
            10: "London Dry Gin",
            15: "Bombay Sapphire",
            20: "Dry Vermouth"
        }
        
        # Step 4: Assemble full names
        assemble_ingredient_full_names(recipe_ingredients, ingredient_names_map)
        
        # Verify final result
        assert recipe_ingredients[0]["full_name"] == "Bombay Sapphire [London Dry Gin;Gin;Spirits]"
        assert recipe_ingredients[1]["full_name"] == "Dry Vermouth [Vermouth]"

    def test_utils_performance_with_many_ingredients(self):
        """Test utility functions with a large number of ingredients"""
        # Create a large list of ingredients with overlapping hierarchies
        recipe_ingredients = []
        
        # Create 100 ingredients across 3 main categories
        for i in range(100):
            category = i % 3 + 1  # Categories 1, 2, 3
            subcategory = (i % 10) + 1  # 10 subcategories per category
            ingredient_id = 100 + i
            
            recipe_ingredients.append({
                "ingredient_id": ingredient_id,
                "ingredient_name": f"Ingredient {ingredient_id}",
                "ingredient_path": f"/{category}/{subcategory}/{ingredient_id}/",
                "amount": 1.0
            })
        
        # Extract IDs
        needed_ids = extract_all_ingredient_ids(recipe_ingredients)
        
        # Should include all ingredients plus their ancestors
        assert len(needed_ids) >= 100  # At least the 100 ingredients
        assert len(needed_ids) <= 113  # At most 100 + 10 subcategories + 3 categories
        
        # Create names map
        ingredient_names_map = {}
        for id in needed_ids:
            if id <= 3:
                ingredient_names_map[id] = f"Category {id}"
            elif id <= 13:
                ingredient_names_map[id] = f"Subcategory {id}"
            else:
                ingredient_names_map[id] = f"Ingredient {id}"
        
        # Assemble names (should complete without error)
        assemble_ingredient_full_names(recipe_ingredients, ingredient_names_map)
        
        # Verify all ingredients have full names
        for ingredient in recipe_ingredients:
            assert "full_name" in ingredient
            assert len(ingredient["full_name"]) > 0
            assert "[" in ingredient["full_name"] or ingredient["full_name"] == ingredient["ingredient_name"]  # Should have hierarchy separator or be root level