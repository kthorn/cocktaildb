"""
Tests for bulk ingredient upload functionality
"""

import pytest


class TestBulkIngredientUploadDatabaseLayer:
    """Test database layer functionality for bulk ingredient upload"""

    def test_check_ingredient_names_batch(self, db_instance):
        """Test batch checking of ingredient names for duplicates"""
        # Add test ingredients with unique names
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (%s, %s)",
            ("Test Gin", "Premium test gin"),
        )
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (%s, %s)",
            ("Test Vodka", "Premium test vodka"),
        )

        # Test batch checking
        ingredient_names = ["Test Gin", "Test Vodka", "Test Rum", "Test Whiskey"]
        results = db_instance.check_ingredient_names_batch(ingredient_names)

        # Should return mapping of names to exists status
        assert isinstance(results, dict)
        assert len(results) == 4

        # Existing ingredients should be marked as True
        assert results["Test Gin"] is True
        assert results["Test Vodka"] is True

        # Non-existing ingredients should be marked as False
        assert results["Test Rum"] is False
        assert results["Test Whiskey"] is False

    def test_search_ingredients_batch(self, db_instance):
        """Test batch searching for ingredients by name"""
        # Add test ingredients with unique names
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (%s, %s)",
            ("Test Spirits", "Spirits category"),
        )
        spirits_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = %s",
            ("Test Spirits",),
        )
        spirits_id = spirits_result[0]["id"]

        db_instance.execute_query(
            "INSERT INTO ingredients (name, description, parent_id) VALUES (%s, %s, %s)",
            ("Test Gin", "Premium test gin", spirits_id),
        )
        gin_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = %s",
            ("Test Gin",),
        )
        gin_id = gin_result[0]["id"]

        # Test batch searching
        ingredient_names = ["Test Spirits", "Test Gin", "Non-existent Ingredient"]
        results = db_instance.search_ingredients_batch(ingredient_names)

        # Should return mapping of names to ingredient data
        assert isinstance(results, dict)
        assert len(results) == 2  # Only existing ingredients

        # Existing ingredients should be in results
        assert "Test Spirits" in results
        assert "Test Gin" in results
        assert "Non-existent Ingredient" not in results

        # Check ingredient data structure
        spirits_data = results["Test Spirits"]
        assert spirits_data["id"] == spirits_id
        assert spirits_data["name"] == "Test Spirits"
        assert spirits_data["parent_id"] is None

        gin_data = results["Test Gin"]
        assert gin_data["id"] == gin_id
        assert gin_data["name"] == "Test Gin"
        assert gin_data["parent_id"] == spirits_id

    def test_database_ingredient_hierarchy_validation(self, db_instance):
        """Test ingredient hierarchy validation for bulk upload"""
        # Add test ingredients with hierarchy
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (%s, %s)",
            ("Test Spirits Category", "Spirits category"),
        )
        spirits_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = %s",
            ("Test Spirits Category",),
        )
        spirits_id = spirits_result[0]["id"]

        # Test batch searching for parent ingredients
        parent_names = ["Test Spirits Category", "Non-existent Parent"]
        results = db_instance.search_ingredients_batch(parent_names)

        # Should find existing parent
        assert "Test Spirits Category" in results
        assert "Non-existent Parent" not in results

        # Parent data should be valid
        parent_data = results["Test Spirits Category"]
        assert parent_data["id"] == spirits_id
        assert parent_data["name"] == "Test Spirits Category"


class TestBulkIngredientUploadIntegration:
    """Test the bulk ingredient upload endpoint integration"""

    def test_bulk_ingredient_upload_requires_authentication(self, test_client_memory):
        """Test that bulk ingredient upload requires authentication"""
        ingredients_data = {
            "ingredients": [
                {"name": "Test Gin", "description": "A test gin for bulk upload"}
            ]
        }

        response = test_client_memory.post("/ingredients/bulk", json=ingredients_data)
        assert response.status_code == 401

    def test_bulk_ingredient_upload_validation_errors(self, admin_client):
        """Test bulk ingredient upload validation errors"""
        # Test with empty ingredients list
        response = admin_client.post(
            "/ingredients/bulk",
            json={"ingredients": []},
        )
        assert response.status_code == 422

        # Test with invalid ingredient data
        response = admin_client.post(
            "/ingredients/bulk",
            json={"ingredients": [{"name": ""}]},  # Empty name
        )
        assert response.status_code == 422

    def test_bulk_ingredient_upload_duplicate_names(self, admin_client, db_instance):
        """Test bulk ingredient upload with duplicate names"""
        # Add an existing ingredient
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (%s, %s)",
            ("Existing Gin", "Already exists"),
        )

        ingredients_data = {
            "ingredients": [
                {"name": "Existing Gin", "description": "Duplicate gin"},
                {"name": "New Vodka", "description": "A new vodka"},
            ]
        }

        response = admin_client.post(
            "/ingredients/bulk",
            json=ingredients_data,
        )

        # Should return validation errors without creating any ingredients
        assert response.status_code == 201
        data = response.json()
        assert data["uploaded_count"] == 0
        assert data["failed_count"] == 1
        assert len(data["validation_errors"]) == 1
        assert data["validation_errors"][0]["error_type"] == "duplicate_name"

    def test_bulk_ingredient_upload_invalid_parent(self, admin_client):
        """Test bulk ingredient upload with invalid parent"""
        ingredients_data = {
            "ingredients": [
                {
                    "name": "Test Gin",
                    "description": "Test gin with invalid parent",
                    "parent_name": "Non-existent Parent",
                }
            ]
        }

        response = admin_client.post(
            "/ingredients/bulk",
            json=ingredients_data,
        )

        # Should return validation error
        assert response.status_code == 201
        data = response.json()
        assert data["uploaded_count"] == 0
        assert data["failed_count"] == 1
        assert len(data["validation_errors"]) == 1
        assert data["validation_errors"][0]["error_type"] == "parent_not_found"

    def test_bulk_ingredient_upload_success_simple(self, admin_client, db_instance):
        """Test successful bulk ingredient upload without parent relationships"""
        ingredients_data = {
            "ingredients": [
                {"name": "Bulk Test Gin", "description": "A test gin for bulk upload"},
                {
                    "name": "Bulk Test Vodka",
                    "description": "A test vodka for bulk upload",
                },
            ]
        }

        response = admin_client.post(
            "/ingredients/bulk",
            json=ingredients_data,
        )

        # Should succeed
        assert response.status_code == 201
        data = response.json()
        assert data["uploaded_count"] == 2
        assert data["failed_count"] == 0
        assert len(data["validation_errors"]) == 0
        assert len(data["uploaded_ingredients"]) == 2

        # Check that ingredients were created
        uploaded_names = [ing["name"] for ing in data["uploaded_ingredients"]]
        assert "Bulk Test Gin" in uploaded_names
        assert "Bulk Test Vodka" in uploaded_names

    def test_bulk_ingredient_upload_success_with_parent(
        self, admin_client, db_instance
    ):
        """Test successful bulk ingredient upload with parent relationships"""
        # First create a parent ingredient
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (%s, %s)",
            ("Bulk Test Spirits", "Spirits category for bulk test"),
        )
        parent_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = %s",
            ("Bulk Test Spirits",),
        )
        parent_id = parent_result[0]["id"]

        ingredients_data = {
            "ingredients": [
                {
                    "name": "Bulk Test London Gin",
                    "description": "London gin for bulk test",
                    "parent_name": "Bulk Test Spirits",
                },
                {
                    "name": "Bulk Test Premium Vodka",
                    "description": "Premium vodka for bulk test",
                    "parent_name": "Bulk Test Spirits",
                },
            ]
        }

        response = admin_client.post(
            "/ingredients/bulk",
            json=ingredients_data,
        )

        # Should succeed
        assert response.status_code == 201
        data = response.json()
        assert data["uploaded_count"] == 2
        assert data["failed_count"] == 0
        assert len(data["validation_errors"]) == 0
        assert len(data["uploaded_ingredients"]) == 2

        # Check that ingredients were created with correct parent
        for ingredient in data["uploaded_ingredients"]:
            assert ingredient["parent_id"] == parent_id
            assert ingredient["name"] in [
                "Bulk Test London Gin",
                "Bulk Test Premium Vodka",
            ]

    def test_bulk_ingredient_upload_legacy_parent_id(self, admin_client, db_instance):
        """Test bulk ingredient upload with legacy parent_id field"""
        # First create a parent ingredient
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (%s, %s)",
            ("Legacy Parent Spirits", "Spirits category for legacy test"),
        )
        parent_result = db_instance.execute_query(
            "SELECT id FROM ingredients WHERE name = %s",
            ("Legacy Parent Spirits",),
        )
        parent_id = parent_result[0]["id"]

        ingredients_data = {
            "ingredients": [
                {
                    "name": "Legacy Test Gin",
                    "description": "Gin for legacy parent_id test",
                    "parent_id": parent_id,
                }
            ]
        }

        response = admin_client.post(
            "/ingredients/bulk",
            json=ingredients_data,
        )

        # Should succeed
        assert response.status_code == 201
        data = response.json()
        assert data["uploaded_count"] == 1
        assert data["failed_count"] == 0
        assert len(data["validation_errors"]) == 0
        assert len(data["uploaded_ingredients"]) == 1

        # Check that ingredient was created with correct parent
        ingredient = data["uploaded_ingredients"][0]
        assert ingredient["parent_id"] == parent_id
        assert ingredient["name"] == "Legacy Test Gin"

    def test_bulk_ingredient_upload_mixed_success_failure(
        self, admin_client, db_instance
    ):
        """Test bulk ingredient upload with mixed success and failure"""
        # Add an existing ingredient
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (%s, %s)",
            ("Existing Mixed Test Gin", "Already exists"),
        )

        ingredients_data = {
            "ingredients": [
                {
                    "name": "Existing Mixed Test Gin",  # Should fail - duplicate
                    "description": "Duplicate gin",
                },
                {
                    "name": "Invalid Parent Gin",  # Should fail - invalid parent
                    "description": "Gin with invalid parent",
                    "parent_name": "Non-existent Parent",
                },
                {
                    "name": "Valid New Vodka",  # Should succeed
                    "description": "A new vodka",
                },
            ]
        }

        response = admin_client.post(
            "/ingredients/bulk",
            json=ingredients_data,
        )

        # Should return validation errors without creating any ingredients
        assert response.status_code == 201
        data = response.json()
        assert data["uploaded_count"] == 0  # All-or-nothing approach
        assert data["failed_count"] == 2
        assert len(data["validation_errors"]) == 2
        assert len(data["uploaded_ingredients"]) == 0

        # Check error types
        error_types = [err["error_type"] for err in data["validation_errors"]]
        assert "duplicate_name" in error_types
        assert "parent_not_found" in error_types
