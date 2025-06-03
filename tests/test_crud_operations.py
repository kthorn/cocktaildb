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
    assert_valid_response_structure
)


class TestComplexIngredientCRUD:
    """Test complex CRUD operations for ingredients"""
    
    def test_ingredient_hierarchy_crud_workflow(self, test_client_production_isolated, mock_user, mocker):
        """Test complete CRUD workflow with ingredient hierarchy"""
        # Mock authentication using pytest-mock
        mock_auth = mocker.patch('api.dependencies.auth.get_user_from_lambda_event')
        from api.dependencies.auth import UserInfo
        mock_auth.return_value = UserInfo(**mock_user)
        
        client = test_client_production_isolated
        
        # Create parent ingredient
        parent_data = {"name": "Test Spirits", "description": "Alcoholic spirits"}
        parent_response = client.post("/api/v1/ingredients", json=parent_data)
        
        if parent_response.status_code == 201:
            parent_ingredient = parent_response.json()
            parent_id = parent_ingredient["ingredient_id"]
            
            # Create child ingredient with hierarchy
            child_data = {
                "name": "Test Gin",
                "description": "Juniper-flavored spirit",
                "parent_id": parent_id
            }
            child_response = client.post("/api/v1/ingredients", json=child_data)
            
            if child_response.status_code == 201:
                child_ingredient = child_response.json()
                child_id = child_ingredient["ingredient_id"]
                assert child_ingredient["parent_id"] == parent_id
                
                # Update child ingredient
                update_data = {"description": "Updated gin description"}
                update_response = client.put(f"/api/v1/ingredients/{child_id}", json=update_data)
                
                if update_response.status_code == 200:
                    # Verify hierarchy is maintained
                    updated_ingredient = update_response.json()
                    assert updated_ingredient["parent_id"] == parent_id
                
                # Delete child first (should succeed)
                delete_child_response = client.delete(f"/api/v1/ingredients/{child_id}")
                assert delete_child_response.status_code in [200, 204]
                
                # Delete parent (should succeed now that child is gone)
                delete_parent_response = client.delete(f"/api/v1/ingredients/{parent_id}")
                assert delete_parent_response.status_code in [200, 204]


class TestComplexRecipeCRUD:
    """Test complex CRUD operations for recipes"""
    
    def test_recipe_with_ingredients_crud_workflow(self, test_client_production_isolated, mock_user, mocker):
        """Test complete CRUD workflow for recipes with ingredients"""
        mock_auth = mocker.patch('api.dependencies.auth.get_user_from_lambda_event')
        from api.dependencies.auth import UserInfo
        mock_auth.return_value = UserInfo(**mock_user)
        
        client = test_client_production_isolated
        
        # Get existing ingredients and units for the recipe
        ingredients_response = client.get("/api/v1/ingredients?limit=2")
        units_response = client.get("/api/v1/units?limit=1")
        
        if (ingredients_response.status_code == 200 and units_response.status_code == 200 and
            len(ingredients_response.json().get("ingredients", [])) >= 2 and
            len(units_response.json().get("units", [])) >= 1):
            
            ingredients = ingredients_response.json()["ingredients"]
            units = units_response.json()["units"]
            
            recipe_data = {
                "name": "Test Complex Martini",
                "instructions": "Stir with ice, strain, and garnish",
                "ingredients": [
                    {
                        "ingredient_id": ingredients[0]["ingredient_id"],
                        "quantity": 2.5,
                        "unit_id": units[0]["unit_id"],
                        "notes": "London Dry Gin"
                    },
                    {
                        "ingredient_id": ingredients[1]["ingredient_id"],
                        "quantity": 0.5,
                        "unit_id": units[0]["unit_id"],
                        "notes": "Dry Vermouth"
                    }
                ]
            }
            
            create_response = client.post("/api/v1/recipes", json=recipe_data)
            
            if create_response.status_code == 201:
                created_recipe = create_response.json()
                recipe_id = created_recipe["recipe_id"]
                
                # Read back the recipe with full details
                read_response = client.get(f"/api/v1/recipes/{recipe_id}")
                assert read_response.status_code == 200
                read_recipe = read_response.json()
                assert "ingredients" in read_recipe
                assert len(read_recipe["ingredients"]) == 2
                
                # Update recipe instructions and add ingredient
                update_data = {
                    "instructions": "Updated: Stir gently with ice, double strain, express lemon peel"
                }
                update_response = client.put(f"/api/v1/recipes/{recipe_id}", json=update_data)
                
                if update_response.status_code == 200:
                    updated_recipe = update_response.json()
                    assert "Updated:" in updated_recipe["instructions"]
                
                # Delete the recipe
                delete_response = client.delete(f"/api/v1/recipes/{recipe_id}")
                assert delete_response.status_code in [200, 204]


class TestTransactionalBehavior:
    """Test transactional behavior and data integrity"""
    
    def test_recipe_creation_with_invalid_ingredient_rollback(self, test_client_production_isolated, mock_user, mocker):
        """Test that recipe creation fails gracefully with invalid ingredient references"""
        mock_auth = mocker.patch('api.dependencies.auth.get_user_from_lambda_event')
        from api.dependencies.auth import UserInfo
        mock_auth.return_value = UserInfo(**mock_user)
        
        client = test_client_production_isolated
        
        # Try to create recipe with non-existent ingredient
        recipe_data = {
            "name": "Test Invalid Recipe",
            "instructions": "This should fail",
            "ingredients": [
                {
                    "ingredient_id": 99999,  # Non-existent ingredient
                    "quantity": 1.0,
                    "unit_id": 1,
                    "notes": "This should cause a failure"
                }
            ]
        }
        
        create_response = client.post("/api/v1/recipes", json=recipe_data)
        # Should fail due to foreign key constraint
        assert create_response.status_code in [400, 422, 500]
        
        # Verify recipe was not created
        recipes_response = client.get("/api/v1/recipes?search=Test Invalid Recipe")
        if recipes_response.status_code == 200:
            recipes = recipes_response.json().get("recipes", [])
            invalid_recipes = [r for r in recipes if r["name"] == "Test Invalid Recipe"]
            assert len(invalid_recipes) == 0
    
    def test_rating_constraints_validation(self, test_client_production_isolated, mock_user, mocker):
        """Test rating validation and constraints"""
        mock_auth = mocker.patch('api.dependencies.auth.get_user_from_lambda_event')
        from api.dependencies.auth import UserInfo
        mock_auth.return_value = UserInfo(**mock_user)
        
        client = test_client_production_isolated
        
        # Get a recipe to rate
        recipes_response = client.get("/api/v1/recipes?limit=1")
        if (recipes_response.status_code == 200 and 
            recipes_response.json().get("recipes")):
            
            recipe_id = recipes_response.json()["recipes"][0]["recipe_id"]
            
            # Test invalid rating values
            invalid_ratings = [
                {"rating": 0, "notes": "Too low"},      # Below minimum
                {"rating": 11, "notes": "Too high"},    # Above maximum
                {"rating": -1, "notes": "Negative"},    # Negative
                {"rating": "five", "notes": "Not a number"}  # Wrong type
            ]
            
            for invalid_data in invalid_ratings:
                response = client.post(f"/api/v1/recipes/{recipe_id}/ratings", json=invalid_data)
                assert response.status_code == 422, f"Should reject invalid rating: {invalid_data}"
            
            # Test valid rating
            valid_rating = {"rating": 8, "notes": "Great cocktail!"}
            valid_response = client.post(f"/api/v1/recipes/{recipe_id}/ratings", json=valid_rating)
            
            if valid_response.status_code == 201:
                # Try to rate the same recipe again (should handle duplicate user ratings)
                duplicate_response = client.post(f"/api/v1/recipes/{recipe_id}/ratings", json=valid_rating)
                # Should either update existing rating or reject duplicate
                assert duplicate_response.status_code in [200, 201, 409, 422]


class TestConcurrencyAndLocking:
    """Test concurrent operations and data consistency"""
    
    def test_concurrent_recipe_updates(self, test_client_production_isolated, mock_user, mocker):
        """Test handling of concurrent recipe updates"""
        mock_auth = mocker.patch('api.dependencies.auth.get_user_from_lambda_event')
        from api.dependencies.auth import UserInfo
        mock_auth.return_value = UserInfo(**mock_user)
        
        client = test_client_production_isolated
        
        # Create a recipe to test concurrent updates
        recipe_data = {
            "name": "Concurrency Test Recipe",
            "instructions": "Original instructions"
        }
        
        create_response = client.post("/api/v1/recipes", json=recipe_data)
        
        if create_response.status_code == 201:
            recipe_id = create_response.json()["recipe_id"]
            
            # Simulate concurrent updates
            update1_data = {"instructions": "First concurrent update"}
            update2_data = {"instructions": "Second concurrent update"}
            
            # Both updates should succeed or handle conflicts gracefully
            response1 = client.put(f"/api/v1/recipes/{recipe_id}", json=update1_data)
            response2 = client.put(f"/api/v1/recipes/{recipe_id}", json=update2_data)
            
            # At least one should succeed
            assert (response1.status_code == 200 or response2.status_code == 200)
            
            # Verify final state is consistent
            final_response = client.get(f"/api/v1/recipes/{recipe_id}")
            if final_response.status_code == 200:
                final_recipe = final_response.json()
                # Instructions should be one of the updates, not corrupted
                assert final_recipe["instructions"] in [
                    "First concurrent update", 
                    "Second concurrent update"
                ]


class TestComplexQueries:
    """Test complex query operations and edge cases"""
    
    def test_deep_ingredient_hierarchy_queries(self, test_client_production_isolated):
        """Test querying ingredients with deep hierarchy"""
        client = test_client_production_isolated
        
        # Get ingredients with hierarchy
        response = client.get("/api/v1/ingredients")
        if response.status_code == 200:
            ingredients = response.json().get("ingredients", [])
            
            # Find ingredients with complex paths
            complex_ingredients = [
                ing for ing in ingredients 
                if ing.get("ingredient_path") and ing["ingredient_path"].count("/") > 2
            ]
            
            # Test that hierarchy queries work for complex paths
            for ingredient in complex_ingredients[:3]:  # Test first 3 complex ingredients
                ingredient_id = ingredient["ingredient_id"]
                detail_response = client.get(f"/api/v1/ingredients/{ingredient_id}")
                
                if detail_response.status_code == 200:
                    detailed_ingredient = detail_response.json()
                    # Verify hierarchy information is preserved
                    assert "ingredient_path" in detailed_ingredient
                    assert detailed_ingredient["ingredient_path"] == ingredient["ingredient_path"]
    
    def test_recipe_search_with_complex_criteria(self, test_client_production_isolated):
        """Test recipe search with multiple criteria"""
        client = test_client_production_isolated
        
        # Test search with various criteria
        search_params = [
            {"search": "martini", "limit": 5},
            {"search": "gin", "limit": 10, "offset": 5},
            {"limit": 3},  # Just limit
            {"offset": 10, "limit": 5}  # Pagination
        ]
        
        for params in search_params:
            query_string = "&".join(f"{k}={v}" for k, v in params.items())
            response = client.get(f"/api/v1/recipes?{query_string}")
            
            if response.status_code == 200:
                data = response.json()
                recipes = data.get("recipes", [])
                
                # Verify limit is respected
                if "limit" in params:
                    assert len(recipes) <= params["limit"]
                
                # Verify search results contain search term if specified
                if "search" in params:
                    search_term = params["search"].lower()
                    for recipe in recipes[:3]:  # Check first 3 results
                        name_match = search_term in recipe["name"].lower()
                        inst_match = (recipe.get("instructions", "") and 
                                    search_term in recipe["instructions"].lower())
                        assert name_match or inst_match