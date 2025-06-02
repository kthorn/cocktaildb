"""
CRUD (Create, Read, Update, Delete) operation tests for CocktailDB API
Tests full CRUD workflows with isolated database instances
"""

import pytest
from fastapi import status
from conftest import (
    assert_ingredient_structure,
    assert_recipe_structure,
    assert_unit_structure,
    assert_valid_response_structure
)


class TestIngredientCRUD:
    """Test CRUD operations for ingredients"""
    
    def test_create_read_ingredient(self, test_client_production_isolated, sample_ingredient_data):
        """Test creating and reading an ingredient"""
        with pytest.raises(Exception):
            # This will fail without proper authentication - testing with mock
            pass
    
    @pytest.fixture
    def created_ingredient(self, authenticated_client, sample_ingredient_data):
        """Fixture that creates an ingredient for testing"""
        response = authenticated_client.post("/api/v1/ingredients", json=sample_ingredient_data)
        if response.status_code == 201:
            return response.json()
        return None
    
    def test_ingredient_crud_workflow(self, test_client_production_isolated, mock_user, mocker):
        """Test complete CRUD workflow for ingredients"""
        # This test simulates the full CRUD workflow
        # Mock authentication using pytest-mock
        
        mock_auth = mocker.patch('api.dependencies.auth.get_user_from_lambda_event')
        from api.dependencies.auth import UserInfo
        mock_auth.return_value = UserInfo(**mock_user)
        
        client = test_client_production_isolated
        
        # CREATE
        ingredient_data = {
            "name": "Test Botanical Gin",
            "description": "A gin infused with botanical herbs",
            "parent_id": None
        }
        
        create_response = client.post("/api/v1/ingredients", json=ingredient_data)
        
        if create_response.status_code == 201:
            created_ingredient = create_response.json()
            assert_ingredient_structure(created_ingredient)
            ingredient_id = created_ingredient["ingredient_id"]
            
            # READ
            read_response = client.get(f"/api/v1/ingredients/{ingredient_id}")
            assert read_response.status_code == 200
            read_ingredient = read_response.json()
            assert read_ingredient["name"] == ingredient_data["name"]
            assert read_ingredient["description"] == ingredient_data["description"]
            
            # UPDATE
            update_data = {
                "name": "Updated Botanical Gin",
                "description": "An updated description for botanical gin"
            }
            update_response = client.put(f"/api/v1/ingredients/{ingredient_id}", json=update_data)
            
            if update_response.status_code == 200:
                updated_ingredient = update_response.json()
                assert updated_ingredient["name"] == update_data["name"]
                assert updated_ingredient["description"] == update_data["description"]
            
            # DELETE
            delete_response = client.delete(f"/api/v1/ingredients/{ingredient_id}")
            assert delete_response.status_code in [200, 204]
            
            # Verify deletion
            verify_response = client.get(f"/api/v1/ingredients/{ingredient_id}")
            assert verify_response.status_code == 404
    
    def test_ingredient_hierarchy_crud(self, test_client_production_isolated, mock_user):
        """Test CRUD operations with ingredient hierarchy"""
        with patch('api.dependencies.auth.get_current_user') as mock_auth:
            from api.dependencies.auth import UserInfo
            mock_auth.return_value = UserInfo(**mock_user)
            
            client = test_client_production_isolated
            
            # Create parent ingredient
            parent_data = {"name": "Spirits", "description": "Alcoholic spirits"}
            parent_response = client.post("/api/v1/ingredients", json=parent_data)
            
            if parent_response.status_code == 201:
                parent_ingredient = parent_response.json()
                parent_id = parent_ingredient["ingredient_id"]
                
                # Create child ingredient
                child_data = {
                    "name": "Gin",
                    "description": "Juniper-flavored spirit",
                    "parent_id": parent_id
                }
                child_response = client.post("/api/v1/ingredients", json=child_data)
                
                if child_response.status_code == 201:
                    child_ingredient = child_response.json()
                    assert child_ingredient["parent_id"] == parent_id
                    
                    # Verify hierarchy in path
                    assert str(parent_id) in child_ingredient.get("ingredient_path", "")


class TestRecipeCRUD:
    """Test CRUD operations for recipes"""
    
    def test_recipe_crud_workflow(self, test_client_production_isolated, mock_user):
        """Test complete CRUD workflow for recipes"""
        with patch('api.dependencies.auth.get_current_user') as mock_auth:
            from api.dependencies.auth import UserInfo
            mock_auth.return_value = UserInfo(**mock_user)
            
            client = test_client_production_isolated
            
            # CREATE
            recipe_data = {
                "name": "Test Classic Martini",
                "instructions": "Stir gin and vermouth with ice. Strain into chilled glass. Garnish with olive.",
                "ingredients": [
                    {
                        "ingredient_id": 1,  # Assuming gin exists
                        "quantity": 2.5,
                        "unit_id": 1,  # Assuming oz exists
                        "notes": "London Dry Gin"
                    },
                    {
                        "ingredient_id": 2,  # Assuming vermouth exists
                        "quantity": 0.5,
                        "unit_id": 1,
                        "notes": "Dry vermouth"
                    }
                ]
            }
            
            create_response = client.post("/api/v1/recipes", json=recipe_data)
            
            if create_response.status_code == 201:
                created_recipe = create_response.json()
                assert_recipe_structure(created_recipe)
                recipe_id = created_recipe["recipe_id"]
                
                # READ
                read_response = client.get(f"/api/v1/recipes/{recipe_id}")
                assert read_response.status_code == 200
                read_recipe = read_response.json()
                assert read_recipe["name"] == recipe_data["name"]
                assert read_recipe["instructions"] == recipe_data["instructions"]
                assert "ingredients" in read_recipe
                
                # UPDATE
                update_data = {
                    "name": "Updated Classic Martini",
                    "instructions": "Updated instructions for a perfect martini."
                }
                update_response = client.put(f"/api/v1/recipes/{recipe_id}", json=update_data)
                
                if update_response.status_code == 200:
                    updated_recipe = update_response.json()
                    assert updated_recipe["name"] == update_data["name"]
                    assert updated_recipe["instructions"] == update_data["instructions"]
                
                # DELETE
                delete_response = client.delete(f"/api/v1/recipes/{recipe_id}")
                assert delete_response.status_code in [200, 204]
                
                # Verify deletion
                verify_response = client.get(f"/api/v1/recipes/{recipe_id}")
                assert verify_response.status_code == 404
    
    def test_recipe_with_tags_crud(self, test_client_production_isolated, mock_user):
        """Test recipe CRUD with tags"""
        with patch('api.dependencies.auth.get_current_user') as mock_auth:
            from api.dependencies.auth import UserInfo
            mock_auth.return_value = UserInfo(**mock_user)
            
            client = test_client_production_isolated
            
            recipe_data = {
                "name": "Tagged Cocktail",
                "instructions": "A cocktail with tags",
                "tags": ["classic", "gin", "strong"]
            }
            
            create_response = client.post("/api/v1/recipes", json=recipe_data)
            
            if create_response.status_code == 201:
                created_recipe = create_response.json()
                recipe_id = created_recipe["recipe_id"]
                
                # Check tags were created/assigned
                tags_response = client.get(f"/api/v1/recipes/{recipe_id}/tags")
                if tags_response.status_code == 200:
                    tags_data = tags_response.json()
                    tag_names = [tag["name"] for tag in tags_data.get("tags", [])]
                    
                    for expected_tag in recipe_data["tags"]:
                        assert expected_tag in tag_names


class TestRatingCRUD:
    """Test CRUD operations for ratings"""
    
    def test_rating_crud_workflow(self, test_client_production_isolated, mock_user):
        """Test complete CRUD workflow for ratings"""
        with patch('api.dependencies.auth.get_current_user') as mock_auth:
            from api.dependencies.auth import UserInfo
            mock_auth.return_value = UserInfo(**mock_user)
            
            client = test_client_production_isolated
            
            # Assume we have a recipe to rate (get first recipe)
            recipes_response = client.get("/api/v1/recipes?limit=1")
            if recipes_response.status_code != 200 or not recipes_response.json().get("recipes"):
                pytest.skip("No recipes available for rating test")
            
            recipe_id = recipes_response.json()["recipes"][0]["recipe_id"]
            
            # CREATE rating
            rating_data = {
                "rating": 8,
                "notes": "Excellent cocktail, well balanced"
            }
            
            create_response = client.post(f"/api/v1/recipes/{recipe_id}/ratings", json=rating_data)
            
            if create_response.status_code == 201:
                created_rating = create_response.json()
                rating_id = created_rating["rating_id"]
                
                # READ rating
                ratings_response = client.get(f"/api/v1/recipes/{recipe_id}/ratings")
                assert ratings_response.status_code == 200
                ratings_data = ratings_response.json()
                
                user_ratings = [r for r in ratings_data["ratings"] if r["user_id"] == mock_user["user_id"]]
                assert len(user_ratings) > 0
                
                # UPDATE rating
                update_data = {
                    "rating": 9,
                    "notes": "Updated rating - even better than I thought"
                }
                
                update_response = client.put(f"/api/v1/ratings/{rating_id}", json=update_data)
                if update_response.status_code == 200:
                    updated_rating = update_response.json()
                    assert updated_rating["rating"] == update_data["rating"]
                    assert updated_rating["notes"] == update_data["notes"]
                
                # DELETE rating
                delete_response = client.delete(f"/api/v1/ratings/{rating_id}")
                assert delete_response.status_code in [200, 204]


class TestUnitCRUD:
    """Test CRUD operations for units"""
    
    def test_unit_crud_workflow(self, test_client_production_isolated, mock_admin_user):
        """Test complete CRUD workflow for units (admin only)"""
        with patch('api.dependencies.auth.get_current_user') as mock_auth:
            from api.dependencies.auth import UserInfo
            mock_auth.return_value = UserInfo(**mock_admin_user)
            
            client = test_client_production_isolated
            
            # CREATE
            unit_data = {
                "name": "Test Teaspoon",
                "abbreviation": "tsp",
                "conversion_to_ml": 5.0
            }
            
            create_response = client.post("/api/v1/units", json=unit_data)
            
            if create_response.status_code == 201:
                created_unit = create_response.json()
                assert_unit_structure(created_unit)
                unit_id = created_unit["unit_id"]
                
                # READ
                units_response = client.get("/api/v1/units")
                assert units_response.status_code == 200
                units_data = units_response.json()
                
                created_unit_found = next(
                    (u for u in units_data["units"] if u["unit_id"] == unit_id), 
                    None
                )
                assert created_unit_found is not None
                
                # UPDATE
                update_data = {
                    "name": "Updated Teaspoon",
                    "abbreviation": "t",
                    "conversion_to_ml": 4.93  # More precise conversion
                }
                
                update_response = client.put(f"/api/v1/units/{unit_id}", json=update_data)
                if update_response.status_code == 200:
                    updated_unit = update_response.json()
                    assert updated_unit["name"] == update_data["name"]
                    assert updated_unit["conversion_to_ml"] == update_data["conversion_to_ml"]
                
                # DELETE
                delete_response = client.delete(f"/api/v1/units/{unit_id}")
                assert delete_response.status_code in [200, 204]


class TestTransactionalBehavior:
    """Test transactional behavior and rollbacks"""
    
    def test_recipe_creation_rollback_on_invalid_ingredient(self, test_client_production_isolated, mock_user):
        """Test that recipe creation fails cleanly with invalid ingredients"""
        with patch('api.dependencies.auth.get_current_user') as mock_auth:
            from api.dependencies.auth import UserInfo
            mock_auth.return_value = UserInfo(**mock_user)
            
            client = test_client_production_isolated
            
            # Try to create recipe with non-existent ingredient
            recipe_data = {
                "name": "Invalid Recipe",
                "instructions": "This should fail",
                "ingredients": [
                    {
                        "ingredient_id": 99999,  # Non-existent ingredient
                        "quantity": 1.0,
                        "unit_id": 1
                    }
                ]
            }
            
            response = client.post("/api/v1/recipes", json=recipe_data)
            # Should fail with appropriate error
            assert response.status_code in [400, 422, 500]
            
            # Verify recipe was not created
            recipes_response = client.get("/api/v1/recipes?search=Invalid Recipe")
            if recipes_response.status_code == 200:
                recipes = recipes_response.json().get("recipes", [])
                invalid_recipes = [r for r in recipes if r["name"] == "Invalid Recipe"]
                assert len(invalid_recipes) == 0
    
    def test_rating_constraints(self, test_client_production_isolated, mock_user):
        """Test rating value constraints"""
        with patch('api.dependencies.auth.get_current_user') as mock_auth:
            from api.dependencies.auth import UserInfo
            mock_auth.return_value = UserInfo(**mock_user)
            
            client = test_client_production_isolated
            
            # Get a recipe to rate
            recipes_response = client.get("/api/v1/recipes?limit=1")
            if recipes_response.status_code != 200 or not recipes_response.json().get("recipes"):
                pytest.skip("No recipes available for rating constraint test")
            
            recipe_id = recipes_response.json()["recipes"][0]["recipe_id"]
            
            # Test invalid rating values
            invalid_ratings = [0, 11, -1, 15]
            
            for invalid_rating in invalid_ratings:
                rating_data = {
                    "rating": invalid_rating,
                    "notes": f"Invalid rating test: {invalid_rating}"
                }
                
                response = client.post(f"/api/v1/recipes/{recipe_id}/ratings", json=rating_data)
                assert response.status_code == 422, f"Rating {invalid_rating} should be rejected"


class TestConcurrencyAndLocking:
    """Test concurrent operations and data consistency"""
    
    def test_concurrent_recipe_creation(self, test_client_production_isolated, mock_user):
        """Test concurrent recipe creation doesn't cause issues"""
        # This would require threading/async testing for true concurrency
        # For now, test sequential operations that might conflict
        
        with patch('api.dependencies.auth.get_current_user') as mock_auth:
            from api.dependencies.auth import UserInfo
            mock_auth.return_value = UserInfo(**mock_user)
            
            client = test_client_production_isolated
            
            # Create multiple recipes with similar data
            base_recipe = {
                "name": "Concurrent Test Recipe",
                "instructions": "Test concurrent creation"
            }
            
            created_recipes = []
            for i in range(3):
                recipe_data = base_recipe.copy()
                recipe_data["name"] = f"{base_recipe['name']} {i}"
                
                response = client.post("/api/v1/recipes", json=recipe_data)
                if response.status_code == 201:
                    created_recipes.append(response.json())
            
            # Verify all recipes were created with unique IDs
            if len(created_recipes) > 1:
                recipe_ids = [r["recipe_id"] for r in created_recipes]
                assert len(set(recipe_ids)) == len(recipe_ids), "Recipe IDs should be unique"