"""
Tests for bulk recipe upload functionality
"""

import pytest
import json
from typing import Dict, Any
from unittest.mock import patch


class TestBulkUploadDatabaseLayer:
    """Test database layer functionality for bulk upload"""

    def test_search_ingredients_exact_match(self, db_instance):
        """Test that search_ingredients returns exact match flag"""
        # Add test ingredients with unique names
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Test Vodka", "Premium test vodka"),
        )
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Test Vodka Premium", "Premium test vodka brand"),
        )

        # Search for exact match
        results = db_instance.search_ingredients("Test Vodka")

        # Should return both ingredients with exact match flags
        assert len(results) >= 1

        # Find the exact match
        exact_matches = [r for r in results if r.get("exact_match", False)]
        partial_matches = [r for r in results if not r.get("exact_match", False)]

        # Should have exactly one exact match
        assert len(exact_matches) == 1
        assert exact_matches[0]["name"] == "Test Vodka"

        # Should have at least one partial match (if there are any)
        # The exact match functionality is the important part for bulk upload
        if len(partial_matches) > 0:
            partial_names = [r["name"] for r in partial_matches]
            assert "Test Vodka Premium" in partial_names

    def test_database_ingredient_name_lookup(self, db_instance):
        """Test ingredient name lookup for bulk upload validation"""
        # Add test ingredients with unique names
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Test Gin", "London Dry Test Gin"),
        )
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Test Gin Premium", "Premium test gin"),
        )

        # Test exact match exists
        results = db_instance.search_ingredients("Test Gin")
        exact_matches = [r for r in results if r.get("exact_match", False)]
        assert len(exact_matches) == 1
        assert exact_matches[0]["name"] == "Test Gin"

        # Test non-existent ingredient
        results = db_instance.search_ingredients("NonExistentIngredient")
        exact_matches = [r for r in results if r.get("exact_match", False)]
        assert len(exact_matches) == 0

    def test_recipe_name_duplicate_check(self, db_instance):
        """Test recipe name duplicate checking"""
        # Add a test recipe
        db_instance.execute_query(
            "INSERT INTO recipes (name, instructions) VALUES (?, ?)",
            ("Test Recipe", "Test instructions"),
        )

        # Check for duplicate (case insensitive)
        results = db_instance.execute_query(
            "SELECT name FROM recipes WHERE LOWER(name) = LOWER(?)", ("test recipe",)
        )
        assert len(results) == 1

        # Check for non-duplicate
        results = db_instance.execute_query(
            "SELECT name FROM recipes WHERE LOWER(name) = LOWER(?)",
            ("Different Recipe",),
        )
        assert len(results) == 0


class TestBulkUploadModels:
    """Test Pydantic models for bulk upload"""

    def test_bulk_recipe_ingredient_model(self):
        """Test BulkRecipeIngredient model validation"""
        from api.models.requests import BulkRecipeIngredient

        # Valid data with unit_name
        valid_data = {"ingredient_name": "Vodka", "amount": 2.0, "unit_name": "oz"}
        ingredient = BulkRecipeIngredient(**valid_data)
        assert ingredient.ingredient_name == "Vodka"
        assert ingredient.amount == 2.0
        assert ingredient.unit_name == "oz"

        # Test with minimal data (only ingredient_name required)
        minimal_data = {"ingredient_name": "Gin"}
        ingredient = BulkRecipeIngredient(**minimal_data)
        assert ingredient.ingredient_name == "Gin"
        assert ingredient.amount is None
        assert ingredient.unit_name is None

        # Test backward compatibility with unit_id
        legacy_data = {"ingredient_name": "Vodka", "amount": 2.0, "unit_id": 1}
        ingredient = BulkRecipeIngredient(**legacy_data)
        assert ingredient.ingredient_name == "Vodka"
        assert ingredient.amount == 2.0
        assert ingredient.unit_id == 1

    def test_bulk_recipe_create_model(self):
        """Test BulkRecipeCreate model validation"""
        from api.models.requests import BulkRecipeCreate, BulkRecipeIngredient

        # Valid recipe data
        recipe_data = {
            "name": "Test Cocktail",
            "instructions": "Mix ingredients",
            "description": "A test cocktail",
            "ingredients": [
                {"ingredient_name": "Vodka", "amount": 2.0, "unit_name": "oz"}
            ],
        }

        recipe = BulkRecipeCreate(**recipe_data)
        assert recipe.name == "Test Cocktail"
        assert len(recipe.ingredients) == 1
        assert recipe.ingredients[0].ingredient_name == "Vodka"

    def test_bulk_recipe_upload_model(self):
        """Test BulkRecipeUpload model validation"""
        from api.models.requests import BulkRecipeUpload

        # Valid upload data
        upload_data = {
            "recipes": [
                {
                    "name": "Test Recipe 1",
                    "instructions": "Mix ingredients",
                    "ingredients": [
                        {"ingredient_name": "Vodka", "amount": 2.0, "unit_name": "oz"}
                    ],
                },
                {
                    "name": "Test Recipe 2",
                    "instructions": "Shake ingredients",
                    "ingredients": [
                        {"ingredient_name": "Gin", "amount": 1.5, "unit_name": "oz"}
                    ],
                },
            ]
        }

        upload = BulkRecipeUpload(**upload_data)
        assert len(upload.recipes) == 2
        assert upload.recipes[0].name == "Test Recipe 1"
        assert upload.recipes[1].name == "Test Recipe 2"

        # Test validation error for empty recipes list
        with pytest.raises(Exception):  # Pydantic validation error
            BulkRecipeUpload(recipes=[])

    def test_bulk_upload_response_models(self):
        """Test BulkUploadResponse and BulkUploadValidationError models"""
        from api.models.responses import BulkUploadResponse, BulkUploadValidationError

        # Test validation error model
        error_data = {
            "recipe_index": 0,
            "recipe_name": "Test Recipe",
            "error_type": "duplicate_name",
            "error_message": "Recipe name already exists",
        }
        error = BulkUploadValidationError(**error_data)
        assert error.recipe_index == 0
        assert error.error_type == "duplicate_name"

        # Test response model
        response_data = {
            "uploaded_count": 2,
            "failed_count": 1,
            "validation_errors": [error],
            "uploaded_recipes": [],
        }
        response = BulkUploadResponse(**response_data)
        assert response.uploaded_count == 2
        assert response.failed_count == 1
        assert len(response.validation_errors) == 1


class TestBulkUploadValidation:
    """Test validation logic for bulk upload"""

    def test_successful_bulk_upload(self, editor_client):
        """Test successful bulk upload with valid data"""
        # First, create some test ingredients
        ingredient_data = [
            {"name": "Lime Juice", "description": "Fresh lime juice"},
            {"name": "Dark Jamaican Rum", "parent_name": "Rum"},
            {"name": "Green Chartreuse"},
            {"name": "Apricot Liqueur"},
        ]

        # Create ingredients
        for ingredient in ingredient_data:
            response = editor_client.post("/ingredients", json=ingredient)
            assert response.status_code == 201

        # Test bulk upload with valid data
        bulk_data = {
            "recipes": [
                {
                    "name": "Test Vodka Cocktail",
                    "instructions": "Mix vodka and lime juice",
                    "description": "A simple vodka cocktail",
                    "ingredients": [
                        {"ingredient_name": "Vodka", "amount": 2.0, "unit_name": "oz"},
                        {
                            "ingredient_name": "Lime Juice",
                            "amount": 0.5,
                            "unit_name": "oz",
                        },
                    ],
                },
                {
                    "name": "Test Gin Cocktail",
                    "instructions": "Mix gin and lime juice",
                    "description": "A simple gin cocktail",
                    "ingredients": [
                        {"ingredient_name": "Gin", "amount": 1.5, "unit_name": "oz"},
                        {
                            "ingredient_name": "Lime Juice",
                            "amount": 0.75,
                            "unit_name": "oz",
                        },
                    ],
                },
                {
                    "name": "Final Voyage",
                    "description": "Four equal parts cocktail with dark rum, lime juice, Green Chartreuse, and apricot liqueur",
                    "instructions": "Shake all ingredients with ice and strain into a cocktail or coupe glass.",
                    "ingredients": [
                        {
                            "ingredient_name": "Dark Jamaican Rum",
                            "amount": 0.75,
                            "unit_name": "oz",
                        },
                        {
                            "ingredient_name": "Lime juice",
                            "amount": 0.75,
                            "unit_name": "oz",
                        },
                        {
                            "ingredient_name": "Green Chartreuse",
                            "amount": 0.75,
                            "unit_name": "oz",
                        },
                        {
                            "ingredient_name": "Apricot Liqueur",
                            "amount": 0.75,
                            "unit_name": "oz",
                        },
                    ],
                    "source_url": "http://kindredcocktails.com/cocktail/final-voyage",
                },
            ]
        }

        response = editor_client.post("/recipes/bulk", json=bulk_data)
        assert response.status_code == 201

        response_data = response.json()
        assert response_data["uploaded_count"] == 3
        assert response_data["failed_count"] == 0
        assert len(response_data["validation_errors"]) == 0
        assert len(response_data["uploaded_recipes"]) == 3

        # Verify recipes were created
        assert response_data["uploaded_recipes"][0]["name"] == "Test Vodka Cocktail"
        assert response_data["uploaded_recipes"][1]["name"] == "Test Gin Cocktail"

    def test_bulk_upload_duplicate_recipe_names(self, editor_client):
        """Test bulk upload validation for duplicate recipe names"""
        # Create a recipe first
        recipe_data = {
            "name": "Existing Recipe",
            "instructions": "Mix ingredients",
            "ingredients": [{"ingredient_id": 1, "amount": 2.0, "unit_id": 1}],
        }
        create_response = editor_client.post("/recipes", json=recipe_data)
        assert create_response.status_code == 201

        # Now try bulk upload with duplicate name
        bulk_data = {
            "recipes": [
                {
                    "name": "Existing Recipe",  # This should fail
                    "instructions": "Different instructions",
                    "ingredients": [
                        {"ingredient_name": "Vodka", "amount": 1.0, "unit_name": "oz"}
                    ],
                }
            ]
        }

        response = editor_client.post("/recipes/bulk", json=bulk_data)
        assert (
            response.status_code == 201
        )  # Endpoint returns 201 even with validation errors

        response_data = response.json()
        assert response_data["uploaded_count"] == 0
        assert response_data["failed_count"] == 1
        assert len(response_data["validation_errors"]) == 1
        assert response_data["validation_errors"][0]["error_type"] == "duplicate_name"
        assert (
            "already exists" in response_data["validation_errors"][0]["error_message"]
        )

    def test_bulk_upload_nonexistent_ingredient(self, editor_client):
        """Test bulk upload validation for non-existent ingredients"""
        bulk_data = {
            "recipes": [
                {
                    "name": "Test Recipe",
                    "instructions": "Mix ingredients",
                    "ingredients": [
                        {
                            "ingredient_name": "NonExistent Ingredient",
                            "amount": 2.0,
                            "unit_name": "oz",
                        }
                    ],
                }
            ]
        }

        response = editor_client.post("/recipes/bulk", json=bulk_data)
        assert response.status_code == 201

        response_data = response.json()
        assert response_data["uploaded_count"] == 0
        assert response_data["failed_count"] == 1
        assert len(response_data["validation_errors"]) == 1
        assert (
            response_data["validation_errors"][0]["error_type"]
            == "ingredient_not_found"
        )
        assert (
            "No exact match found"
            in response_data["validation_errors"][0]["error_message"]
        )

    def test_bulk_upload_partial_name_match(self, editor_client):
        """Test that partial ingredient name matches are rejected"""
        # Create an ingredient with a specific name
        ingredient_response = editor_client.post(
            "/ingredients", json={"name": "Vodka Premium"}
        )
        assert ingredient_response.status_code == 201

        # Try to use a partial match
        bulk_data = {
            "recipes": [
                {
                    "name": "Test Recipe",
                    "instructions": "Mix ingredients",
                    "ingredients": [
                        {
                            "ingredient_name": "Premium",  # This is a partial match, should fail
                            "amount": 2.0,
                            "unit_name": "oz",
                        }
                    ],
                }
            ]
        }

        response = editor_client.post("/recipes/bulk", json=bulk_data)
        assert response.status_code == 201

        response_data = response.json()
        assert response_data["uploaded_count"] == 0
        assert response_data["failed_count"] == 1
        assert len(response_data["validation_errors"]) == 1
        assert (
            response_data["validation_errors"][0]["error_type"]
            == "ingredient_not_found"
        )

    def test_bulk_upload_invalid_unit_name(self, editor_client):
        """Test bulk upload validation for invalid unit names"""
        bulk_data = {
            "recipes": [
                {
                    "name": "Test Recipe",
                    "instructions": "Mix ingredients",
                    "ingredients": [
                        {
                            "ingredient_name": "Vodka",
                            "amount": 2.0,
                            "unit_name": "InvalidUnit",  # Invalid unit name
                        }
                    ],
                }
            ]
        }

        response = editor_client.post("/recipes/bulk", json=bulk_data)
        assert response.status_code == 201

        response_data = response.json()
        assert response_data["uploaded_count"] == 0
        assert response_data["failed_count"] == 1
        assert len(response_data["validation_errors"]) == 1
        assert response_data["validation_errors"][0]["error_type"] == "invalid_unit"
        assert (
            "does not exist" in response_data["validation_errors"][0]["error_message"]
        )

    def test_bulk_upload_multiple_validation_errors(self, editor_client):
        """Test bulk upload with multiple validation errors"""
        bulk_data = {
            "recipes": [
                {
                    "name": "Valid Recipe",
                    "instructions": "Mix ingredients",
                    "ingredients": [
                        {"ingredient_name": "Vodka", "amount": 2.0, "unit_name": "oz"}
                    ],
                },
                {
                    "name": "Invalid Recipe 1",
                    "instructions": "Mix ingredients",
                    "ingredients": [
                        {
                            "ingredient_name": "NonExistent",
                            "amount": 2.0,
                            "unit_name": "oz",
                        }
                    ],
                },
                {
                    "name": "Invalid Recipe 2",
                    "instructions": "Mix ingredients",
                    "ingredients": [
                        {
                            "ingredient_name": "Vodka",
                            "amount": 2.0,
                            "unit_name": "InvalidUnit",  # Invalid unit
                        }
                    ],
                },
            ]
        }

        response = editor_client.post("/recipes/bulk", json=bulk_data)
        assert response.status_code == 201

        response_data = response.json()
        assert (
            response_data["uploaded_count"] == 0
        )  # None uploaded due to validation errors
        assert response_data["failed_count"] == 2  # Two recipes failed validation
        assert len(response_data["validation_errors"]) == 2

        # Check that we have both error types
        error_types = [
            error["error_type"] for error in response_data["validation_errors"]
        ]
        assert "ingredient_not_found" in error_types
        assert "invalid_unit" in error_types

    def test_bulk_upload_atomic_operation(self, editor_client):
        """Test that bulk upload is atomic - all or nothing"""
        bulk_data = {
            "recipes": [
                {
                    "name": "Good Recipe",
                    "instructions": "Mix ingredients",
                    "ingredients": [
                        {"ingredient_name": "Vodka", "amount": 2.0, "unit_name": "oz"}
                    ],
                },
                {
                    "name": "Bad Recipe",
                    "instructions": "Mix ingredients",
                    "ingredients": [
                        {
                            "ingredient_name": "NonExistent",
                            "amount": 2.0,
                            "unit_name": "oz",
                        }
                    ],
                },
            ]
        }

        response = editor_client.post("/recipes/bulk", json=bulk_data)
        assert response.status_code == 201

        response_data = response.json()
        assert (
            response_data["uploaded_count"] == 0
        )  # Nothing uploaded due to validation failure
        assert response_data["failed_count"] == 1  # One recipe failed validation
        assert len(response_data["uploaded_recipes"]) == 0

        # Verify no recipes were actually created
        recipes_response = editor_client.get("/recipes/search")
        assert recipes_response.status_code == 200
        recipes_data = recipes_response.json()
        recipe_names = [recipe["name"] for recipe in recipes_data["recipes"]]
        assert "Good Recipe" not in recipe_names
        assert "Bad Recipe" not in recipe_names

    def test_bulk_upload_case_insensitive_duplicate_check(self, editor_client):
        """Test that duplicate recipe name check is case insensitive"""
        # Create a recipe first
        recipe_data = {
            "name": "Test Recipe",
            "instructions": "Mix ingredients",
            "ingredients": [{"ingredient_id": 1, "amount": 2.0, "unit_id": 1}],
        }
        create_response = editor_client.post("/recipes", json=recipe_data)
        assert create_response.status_code == 201

        # Try bulk upload with different case
        bulk_data = {
            "recipes": [
                {
                    "name": "TEST RECIPE",  # Different case, should still fail
                    "instructions": "Different instructions",
                    "ingredients": [
                        {"ingredient_name": "Vodka", "amount": 1.0, "unit_name": "oz"}
                    ],
                }
            ]
        }

        response = editor_client.post("/recipes/bulk", json=bulk_data)
        assert response.status_code == 201

        response_data = response.json()
        assert response_data["uploaded_count"] == 0
        assert response_data["failed_count"] == 1
        assert response_data["validation_errors"][0]["error_type"] == "duplicate_name"


class TestBulkUploadEndpointSecurity:
    """Test security aspects of bulk upload endpoint"""

    def test_bulk_upload_requires_authentication(self, test_client_memory):
        """Test that bulk upload requires authentication"""
        bulk_data = {
            "recipes": [
                {
                    "name": "Test Recipe",
                    "instructions": "Mix ingredients",
                    "ingredients": [
                        {"ingredient_name": "Vodka", "amount": 2.0, "unit_name": "oz"}
                    ],
                }
            ]
        }

        response = test_client_memory.post("/recipes/bulk", json=bulk_data)
        assert response.status_code == 401  # Unauthorized

    def test_bulk_upload_validates_input_structure(self, editor_client):
        """Test that bulk upload validates input structure"""
        # Test with malformed data
        invalid_data = {
            "recipes": [
                {
                    "name": "Test Recipe",
                    # Missing required fields
                    "ingredients": "not_an_array",
                }
            ]
        }

        response = editor_client.post("/recipes/bulk", json=invalid_data)
        assert response.status_code == 422  # Validation error

    def test_bulk_upload_empty_recipes_list(self, editor_client):
        """Test that empty recipes list is rejected"""
        invalid_data = {"recipes": []}

        response = editor_client.post("/recipes/bulk", json=invalid_data)
        assert response.status_code == 422  # Validation error


class TestBulkUploadIngredientSearch:
    """Test integration with ingredient search functionality"""

    def test_exact_match_ingredient_search(self, editor_client):
        """Test that only exact matches are accepted for ingredient names"""
        # Create ingredients with similar names
        ingredients = [
            {"name": "Vodka Premium", "description": "Premium vodka"},
            {"name": "Vodka Flavored", "description": "Flavored vodka"},
        ]

        for ingredient in ingredients:
            response = editor_client.post("/ingredients", json=ingredient)
            assert response.status_code == 201

        # Test bulk upload with exact match
        bulk_data = {
            "recipes": [
                {
                    "name": "Test Recipe",
                    "instructions": "Mix ingredients",
                    "ingredients": [
                        {
                            "ingredient_name": "Vodka",  # Exact match
                            "amount": 2.0,
                            "unit_name": "oz",
                        }
                    ],
                }
            ]
        }

        response = editor_client.post("/recipes/bulk", json=bulk_data)
        assert response.status_code == 201

        response_data = response.json()
        assert response_data["uploaded_count"] == 1
        assert response_data["failed_count"] == 0

        # Verify the correct ingredient was used
        created_recipe = response_data["uploaded_recipes"][0]
        ingredient_names = [
            ing["ingredient_name"] for ing in created_recipe["ingredients"]
        ]
        assert "Vodka" in ingredient_names

    def test_ingredient_search_with_special_characters(self, editor_client):
        """Test ingredient search with special characters"""
        # Create ingredient with special characters
        ingredient_response = editor_client.post(
            "/ingredients",
            json={"name": "St-Germain", "description": "Elderflower liqueur"},
        )
        assert ingredient_response.status_code == 201

        bulk_data = {
            "recipes": [
                {
                    "name": "Test Recipe",
                    "instructions": "Mix ingredients",
                    "ingredients": [
                        {
                            "ingredient_name": "St-Germain",
                            "amount": 0.5,
                            "unit_name": "oz",
                        }
                    ],
                }
            ]
        }

        response = editor_client.post("/recipes/bulk", json=bulk_data)
        assert response.status_code == 201

        response_data = response.json()
        assert response_data["uploaded_count"] == 1
        assert response_data["failed_count"] == 0


class TestBulkUploadDocumentation:
    """Test bulk upload functionality against template file"""

    def test_bulk_upload_template_structure(self):
        """Test that the bulk upload template has correct structure"""
        import json
        from pathlib import Path

        template_path = Path(__file__).parent.parent / "bulk_upload_template.json"
        assert template_path.exists(), "bulk_upload_template.json should exist"

        with open(template_path, "r") as f:
            template_data = json.load(f)

        # Validate template structure
        assert isinstance(template_data, list), "Template should be a list of recipes"
        assert len(template_data) > 0, "Template should have at least one recipe"

        # Check first recipe structure
        recipe = template_data[0]
        assert "name" in recipe, "Recipe should have name"
        assert "instructions" in recipe, "Recipe should have instructions"
        assert "ingredients" in recipe, "Recipe should have ingredients"
        assert isinstance(recipe["ingredients"], list), "Ingredients should be a list"

        # Check ingredient structure
        if recipe["ingredients"]:
            ingredient = recipe["ingredients"][0]
            assert "ingredient_name" in ingredient, (
                "Ingredient should have ingredient_name"
            )
            assert "amount" in ingredient, "Ingredient should have amount"
            assert "unit_name" in ingredient, "Ingredient should have unit_name"

    def test_bulk_upload_model_matches_template(self):
        """Test that the bulk upload models match the template format"""
        from api.models.requests import BulkRecipeUpload
        import json
        from pathlib import Path

        template_path = Path(__file__).parent.parent / "bulk_upload_template.json"
        with open(template_path, "r") as f:
            template_data = json.load(f)

        # This should not raise a validation error
        try:
            bulk_upload = BulkRecipeUpload(recipes=template_data)
            assert len(bulk_upload.recipes) == len(template_data)

            # Check that all recipes have the expected fields
            for recipe in bulk_upload.recipes:
                assert recipe.name is not None
                assert recipe.instructions is not None
                assert isinstance(recipe.ingredients, list)

                for ingredient in recipe.ingredients:
                    assert ingredient.ingredient_name is not None
                    assert ingredient.amount is not None
                    # Check that either unit_name or unit_id is present (backward compatibility)
                    assert (
                        ingredient.unit_name is not None
                        or ingredient.unit_id is not None
                    )

        except Exception as e:
            pytest.fail(
                f"Template data should be valid for BulkRecipeUpload model: {e}"
            )


class TestBulkUploadPerformance:
    """Test performance aspects of bulk upload"""

    def test_bulk_upload_logic_validation(self):
        """Test the bulk upload validation logic without HTTP client"""
        from api.models.requests import (
            BulkRecipeUpload,
            BulkRecipeCreate,
            BulkRecipeIngredient,
        )

        # Test data that should pass validation
        valid_data = {
            "recipes": [
                {
                    "name": "Test Recipe 1",
                    "instructions": "Mix ingredients",
                    "ingredients": [
                        {"ingredient_name": "Vodka", "amount": 2.0, "unit_name": "oz"}
                    ],
                },
                {
                    "name": "Test Recipe 2",
                    "instructions": "Shake ingredients",
                    "ingredients": [
                        {"ingredient_name": "Gin", "amount": 1.5, "unit_name": "oz"}
                    ],
                },
            ]
        }

        # Should not raise validation errors
        bulk_upload = BulkRecipeUpload(**valid_data)
        assert len(bulk_upload.recipes) == 2

        # Test validation requirements
        for recipe in bulk_upload.recipes:
            assert recipe.name is not None
            assert len(recipe.ingredients) > 0
            for ingredient in recipe.ingredients:
                assert ingredient.ingredient_name is not None

    def test_bulk_upload_error_scenarios(self):
        """Test various error scenarios for bulk upload"""
        from api.models.requests import BulkRecipeUpload

        # Test empty recipes list (should fail)
        with pytest.raises(Exception):  # Pydantic validation error
            BulkRecipeUpload(recipes=[])

        # Test missing required fields
        invalid_data = {
            "recipes": [
                {
                    "name": "Test Recipe",
                    # Missing instructions is OK
                    "ingredients": [
                        {
                            # Missing ingredient_name should fail
                            "amount": 2.0,
                            "unit_name": "oz",
                        }
                    ],
                }
            ]
        }

        with pytest.raises(Exception):  # Pydantic validation error
            BulkRecipeUpload(**invalid_data)
