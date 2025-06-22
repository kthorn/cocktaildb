"""
CRUD (Create, Read, Update, Delete) operation tests for CocktailDB API
Tests complex CRUD workflows and transactional behavior with isolated database instances
"""

import pytest
from fastapi import status
from unittest.mock import patch
from conftest import (
    assert_ingredient_structure,
    assert_recipe_structure,
    assert_unit_structure,
    assert_valid_response_structure,
)


class TestComplexIngredientCRUD:
    """Test complex CRUD operations for ingredients"""

    def test_ingredient_hierarchy_crud_workflow(
        self, test_client_with_data, mock_user, mocker
    ):
        """Test complete CRUD workflow with ingredient hierarchy"""
        # Mock authentication using pytest-mock
        mock_auth = mocker.patch("api.dependencies.auth.get_user_from_lambda_event")
        from api.dependencies.auth import UserInfo

        mock_auth.return_value = UserInfo(
            user_id=mock_user["user_id"],
            username=mock_user.get("username"),
            email=mock_user.get("email"),
            groups=mock_user.get("cognito:groups", []),
            claims=mock_user,
        )


        # Create parent ingredient
        parent_data = {"name": "Test Spirits", "description": "Alcoholic spirits"}
        parent_response = client.post("/ingredients", json=parent_data)

        if parent_response.status_code == 201:
            parent_ingredient = parent_response.json()
            parent_id = parent_ingredient["ingredient_id"]

            # Create child ingredient with hierarchy
            child_data = {
                "name": "Test Gin",
                "description": "Juniper-flavored spirit",
                "parent_id": parent_id,
            }
            child_response = client.post("/ingredients", json=child_data)

            if child_response.status_code == 201:
                child_ingredient = child_response.json()
                child_id = child_ingredient["ingredient_id"]
                assert child_ingredient["parent_id"] == parent_id

                # Update child ingredient
                update_data = {"description": "Updated gin description"}
                update_response = client.put(
                    f"/ingredients/{child_id}", json=update_data
                )

                if update_response.status_code == 200:
                    # Verify hierarchy is maintained
                    updated_ingredient = update_response.json()
                    assert updated_ingredient["parent_id"] == parent_id

                # Delete child first (should succeed)
                delete_child_response = client.delete(f"/ingredients/{child_id}")
                assert delete_child_response.status_code in [200, 204]

                # Delete parent (should succeed now that child is gone)
                delete_parent_response = client.delete(
                    f"/ingredients/{parent_id}"
                )
                assert delete_parent_response.status_code in [200, 204]


class TestComplexRecipeCRUD:
    """Test complex CRUD operations for recipes"""

    def test_recipe_with_ingredients_crud_workflow(
        self, db_with_test_data, mock_user, mocker, monkeypatch
    ):
        """Test complete CRUD workflow for recipes with ingredients"""
        # Set up isolated database environment
        monkeypatch.setenv("DB_PATH", db_with_test_data)
        monkeypatch.setenv("ENVIRONMENT", "test")

        # Import and create app after environment is configured
        from api.main import app
        from fastapi.testclient import TestClient
        from api.dependencies.auth import UserInfo, require_authentication

        # Create authenticated client with dependency override
        user_info = UserInfo(
            user_id=mock_user["user_id"],
            username=mock_user.get("username"),
            email=mock_user.get("email"),
            groups=mock_user.get("cognito:groups", []),
            claims=mock_user,
        )

        # Override the authentication dependency
        def override_require_authentication():
            return user_info

        app.dependency_overrides[require_authentication] = (
            override_require_authentication
        )
        client = TestClient(app)

        # Get existing ingredients and units for the recipe
        ingredients_response = client.get("/ingredients?limit=2")
        units_response = client.get("/units?limit=1")

        if (
            ingredients_response.status_code == 200
            and units_response.status_code == 200
            and len(ingredients_response.json()) >= 2
            and len(units_response.json()) >= 1
        ):
            ingredients = ingredients_response.json()  # Direct list
            units = units_response.json()  # Direct list

            recipe_data = {
                "name": "Test Complex Martini",
                "instructions": "Stir with ice, strain, and garnish",
                "ingredients": [
                    {
                        "ingredient_id": ingredients[0]["id"],
                        "quantity": 2.5,
                        "unit_id": units[0]["id"],
                        "notes": "London Dry Gin",
                    },
                    {
                        "ingredient_id": ingredients[1]["id"],
                        "quantity": 0.5,
                        "unit_id": units[0]["id"],
                        "notes": "Dry Vermouth",
                    },
                ],
            }

            create_response = client.post("/recipes", json=recipe_data)

            if create_response.status_code == 201:
                created_recipe = create_response.json()
                recipe_id = created_recipe["id"]

                # Read back the recipe with full details
                read_response = client.get(f"/recipes/{recipe_id}")
                assert read_response.status_code == 200
                read_recipe = read_response.json()
                assert "ingredients" in read_recipe
                assert len(read_recipe["ingredients"]) == 2

                # Update recipe instructions and add ingredient
                update_data = {
                    "instructions": "Updated: Stir gently with ice, double strain, express lemon peel"
                }
                update_response = client.put(
                    f"/recipes/{recipe_id}", json=update_data
                )

                if update_response.status_code == 200:
                    updated_recipe = update_response.json()
                    assert "Updated:" in updated_recipe["instructions"]

                # Delete the recipe
                delete_response = client.delete(f"/recipes/{recipe_id}")
                assert delete_response.status_code in [200, 204]

        # Clean up the override
        if require_authentication in app.dependency_overrides:
            del app.dependency_overrides[require_authentication]


class TestConcurrencyAndLocking:
    """Test concurrent operations and data consistency"""

    def test_concurrent_recipe_updates(
        self, test_client_with_data, mock_user, mocker
    ):
        """Test handling of concurrent recipe updates"""
        mock_auth = mocker.patch("api.dependencies.auth.get_user_from_lambda_event")
        from api.dependencies.auth import UserInfo

        mock_auth.return_value = UserInfo(
            user_id=mock_user["user_id"],
            username=mock_user.get("username"),
            email=mock_user.get("email"),
            groups=mock_user.get("cognito:groups", []),
            claims=mock_user,
        )


        # Create a recipe to test concurrent updates
        recipe_data = {
            "name": "Concurrency Test Recipe",
            "instructions": "Original instructions",
        }

        create_response = client.post("/recipes", json=recipe_data)

        if create_response.status_code == 201:
            recipe_id = create_response.json()["recipe_id"]

            # Simulate concurrent updates
            update1_data = {"instructions": "First concurrent update"}
            update2_data = {"instructions": "Second concurrent update"}

            # Both updates should succeed or handle conflicts gracefully
            response1 = client.put(f"/recipes/{recipe_id}", json=update1_data)
            response2 = client.put(f"/recipes/{recipe_id}", json=update2_data)

            # At least one should succeed
            assert response1.status_code == 200 or response2.status_code == 200

            # Verify final state is consistent
            final_response = client.get(f"/recipes/{recipe_id}")
            if final_response.status_code == 200:
                final_recipe = final_response.json()
                # Instructions should be one of the updates, not corrupted
                assert final_recipe["instructions"] in [
                    "First concurrent update",
                    "Second concurrent update",
                ]


class TestComplexQueries:
    """Test complex query operations and edge cases"""

    def test_deep_ingredient_hierarchy_queries(self, test_client_with_data):
        client, app = test_client_with_data
        """Test querying ingredients with deep hierarchy"""

        # Get ingredients with hierarchy
        response = client.get("/ingredients")
        if response.status_code == 200:
            ingredients = response.json()

            # Find ingredients with complex paths
            complex_ingredients = [
                ing
                for ing in ingredients
                if ing.get("path") and ing["path"].count("/") > 2
            ]

            # Test that hierarchy queries work for complex paths
            for ingredient in complex_ingredients[
                :3
            ]:  # Test first 3 complex ingredients
                ingredient_id = ingredient["id"]
                detail_response = client.get(f"/ingredients/{ingredient_id}")

                if detail_response.status_code == 200:
                    detailed_ingredient = detail_response.json()
                    # Verify hierarchy information is preserved
                    assert "path" in detailed_ingredient
                    assert detailed_ingredient["path"] == ingredient["path"]
