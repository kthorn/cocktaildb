"""
Integration tests for CocktailDB API using production data
Tests end-to-end functionality with realistic data scenarios
"""

import pytest
from fastapi import status
from conftest import (
    assert_ingredient_structure, 
    assert_recipe_structure, 
    assert_unit_structure,
    assert_valid_response_structure
)


class TestIngredientsIntegration:
    """Integration tests for ingredients with production data"""
    
    def test_get_ingredients_with_production_data(self, test_client_production_readonly):
        """Test getting ingredients returns valid production data"""
        response = test_client_production_readonly.get("/api/v1/ingredients")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert isinstance(data, list)
        
        # Test structure of first ingredient if any exist
        if data:
            first_ingredient = data[0]
            assert_ingredient_structure(first_ingredient)
    
    def test_ingredients_search_functionality(self, test_client_production_readonly):
        """Test ingredient search with production data"""
        # Search for common ingredients
        search_terms = ["gin", "vodka", "rum", "whiskey", "lime"]
        
        for term in search_terms:
            response = test_client_production_readonly.get(f"/api/v1/ingredients?search={term}")
            assert response.status_code == status.HTTP_200_OK
            
            data = response.json()
            assert "ingredients" in data
            
            # If results found, verify they contain the search term
            if data["ingredients"]:
                for ingredient in data["ingredients"][:5]:  # Check first 5 results
                    assert_ingredient_structure(ingredient)
                    # Name or description should contain search term (case insensitive)
                    name_match = term.lower() in ingredient["name"].lower()
                    desc_match = ingredient.get("description", "") and term.lower() in ingredient["description"].lower()
                    assert name_match or desc_match, f"Search term '{term}' not found in ingredient: {ingredient['name']}"
    
    def test_ingredients_hierarchy(self, test_client_production_readonly):
        """Test ingredient hierarchy functionality"""
        response = test_client_production_readonly.get("/api/v1/ingredients")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        ingredients = data["ingredients"]
        
        # Find ingredients with parent relationships
        children = [ing for ing in ingredients if ing.get("parent_id")]
        parents = [ing for ing in ingredients if not ing.get("parent_id")]
        
        assert len(parents) > 0, "Should have root-level ingredients"
        
        # Test parent-child relationships
        for child in children[:10]:  # Test first 10 children
            parent_id = child["parent_id"]
            parent = next((ing for ing in ingredients if ing["ingredient_id"] == parent_id), None)
            assert parent is not None, f"Parent {parent_id} not found for child {child['name']}"
    
    def test_ingredient_full_names(self, test_client_production_readonly):
        """Test that ingredient full names include hierarchy"""
        response = test_client_production_readonly.get("/api/v1/ingredients")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        ingredients = data["ingredients"]
        
        # Find ingredients with paths
        ingredients_with_paths = [ing for ing in ingredients if ing.get("ingredient_path") and "/" in ing["ingredient_path"]]
        
        if ingredients_with_paths:
            for ingredient in ingredients_with_paths[:5]:
                full_name = ingredient.get("full_name", "")
                # Full name should include the base name
                assert ingredient["name"] in full_name
                # If it has ancestors, full name should be longer than just the name
                path_parts = ingredient["ingredient_path"].strip("/").split("/")
                if len(path_parts) > 1:
                    assert len(full_name) > len(ingredient["name"])


class TestRecipesIntegration:
    """Integration tests for recipes with production data"""
    
    def test_get_recipes_with_production_data(self, test_client_production_readonly):
        """Test getting recipes returns valid production data"""
        response = test_client_production_readonly.get("/api/v1/recipes")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert "recipes" in data
        assert isinstance(data["recipes"], list)
        
        # Test structure of first recipe if any exist
        if data["recipes"]:
            first_recipe = data["recipes"][0]
            assert_recipe_structure(first_recipe)
    
    def test_recipes_pagination(self, test_client_production_readonly):
        """Test recipe pagination with production data"""
        # Test first page
        response1 = test_client_production_readonly.get("/api/v1/recipes?limit=5&offset=0")
        assert response1.status_code == status.HTTP_200_OK
        data1 = response1.json()
        
        # Test second page
        response2 = test_client_production_readonly.get("/api/v1/recipes?limit=5&offset=5")
        assert response2.status_code == status.HTTP_200_OK
        data2 = response2.json()
        
        # Should have different recipes (if enough exist)
        if len(data1["recipes"]) == 5 and len(data2["recipes"]) > 0:
            recipe_ids_1 = {r["recipe_id"] for r in data1["recipes"]}
            recipe_ids_2 = {r["recipe_id"] for r in data2["recipes"]}
            assert recipe_ids_1.isdisjoint(recipe_ids_2), "Pagination should return different recipes"
    
    def test_recipes_search(self, test_client_production_readonly):
        """Test recipe search functionality"""
        search_terms = ["martini", "mojito", "manhattan", "daiquiri", "cocktail"]
        
        for term in search_terms:
            response = test_client_production_readonly.get(f"/api/v1/recipes?search={term}")
            assert response.status_code == status.HTTP_200_OK
            
            data = response.json()
            assert "recipes" in data
            
            # If results found, verify they contain the search term
            if data["recipes"]:
                for recipe in data["recipes"][:3]:  # Check first 3 results
                    assert_recipe_structure(recipe)
                    # Name or instructions should contain search term (case insensitive)
                    name_match = term.lower() in recipe["name"].lower()
                    inst_match = recipe.get("instructions", "") and term.lower() in recipe["instructions"].lower()
                    assert name_match or inst_match, f"Search term '{term}' not found in recipe: {recipe['name']}"
    
    def test_get_recipe_details(self, test_client_production_readonly):
        """Test getting detailed recipe information"""
        # First get a list of recipes
        response = test_client_production_readonly.get("/api/v1/recipes?limit=1")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        if not data["recipes"]:
            pytest.skip("No recipes in database for testing")
        
        recipe_id = data["recipes"][0]["recipe_id"]
        
        # Get detailed recipe
        detail_response = test_client_production_readonly.get(f"/api/v1/recipes/{recipe_id}")
        assert detail_response.status_code == status.HTTP_200_OK
        
        recipe_detail = detail_response.json()
        assert_recipe_structure(recipe_detail)
        assert recipe_detail["recipe_id"] == recipe_id
        
        # Should have ingredients list
        assert "ingredients" in recipe_detail
        assert isinstance(recipe_detail["ingredients"], list)
        
        # Test ingredient structure in recipe
        if recipe_detail["ingredients"]:
            ingredient = recipe_detail["ingredients"][0]
            expected_keys = ["ingredient_id", "ingredient_name", "quantity", "unit_name"]
            assert_valid_response_structure(ingredient, expected_keys)
    
    def test_recipe_ratings_integration(self, test_client_production_readonly):
        """Test recipe ratings integration"""
        # Get a recipe to test ratings
        response = test_client_production_readonly.get("/api/v1/recipes?limit=1")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        if not data["recipes"]:
            pytest.skip("No recipes in database for testing")
        
        recipe_id = data["recipes"][0]["recipe_id"]
        
        # Get ratings for this recipe
        ratings_response = test_client_production_readonly.get(f"/api/v1/recipes/{recipe_id}/ratings")
        assert ratings_response.status_code == status.HTTP_200_OK
        
        ratings_data = ratings_response.json()
        assert "ratings" in ratings_data
        assert isinstance(ratings_data["ratings"], list)
        
        # Test rating structure if any exist
        if ratings_data["ratings"]:
            rating = ratings_data["ratings"][0]
            expected_keys = ["rating_id", "rating", "notes", "created_at", "user_id"]
            assert_valid_response_structure(rating, expected_keys)
            assert 1 <= rating["rating"] <= 10


class TestUnitsIntegration:
    """Integration tests for units with production data"""
    
    def test_get_units_with_production_data(self, test_client_production_readonly):
        """Test getting units returns valid production data"""
        response = test_client_production_readonly.get("/api/v1/units")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert "units" in data
        assert isinstance(data["units"], list)
        assert len(data["units"]) > 0, "Should have units in production database"
        
        # Test structure of units
        for unit in data["units"]:
            assert_unit_structure(unit)
            # Conversion factor should be positive
            assert unit["conversion_to_ml"] > 0
    
    def test_common_units_exist(self, test_client_production_readonly):
        """Test that common cocktail units exist in production data"""
        response = test_client_production_readonly.get("/api/v1/units")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        unit_names = [unit["name"].lower() for unit in data["units"]]
        unit_abbrevs = [unit["abbreviation"].lower() for unit in data["units"]]
        
        # Common cocktail units
        expected_units = ["ounce", "ml", "dash", "splash", "drop"]
        expected_abbrevs = ["oz", "ml"]
        
        for unit in expected_units:
            assert any(unit in name for name in unit_names), f"Unit '{unit}' not found in production data"
        
        for abbrev in expected_abbrevs:
            assert any(abbrev in ab for ab in unit_abbrevs), f"Abbreviation '{abbrev}' not found in production data"


class TestTagsIntegration:
    """Integration tests for tags with production data"""
    
    def test_get_tags_with_production_data(self, test_client_production_readonly):
        """Test getting tags returns valid production data"""
        response = test_client_production_readonly.get("/api/v1/tags")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert "tags" in data
        assert isinstance(data["tags"], list)
        
        # Test structure of tags if any exist
        if data["tags"]:
            tag = data["tags"][0]
            expected_keys = ["tag_id", "name", "description", "is_public"]
            assert_valid_response_structure(tag, expected_keys)
    
    def test_recipe_tags_integration(self, test_client_production_readonly):
        """Test recipe-tag relationships"""
        # Get recipes
        response = test_client_production_readonly.get("/api/v1/recipes?limit=5")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        if not data["recipes"]:
            pytest.skip("No recipes in database for testing")
        
        # Check if any recipes have tags
        for recipe in data["recipes"]:
            recipe_id = recipe["recipe_id"]
            tags_response = test_client_production_readonly.get(f"/api/v1/recipes/{recipe_id}/tags")
            assert tags_response.status_code == status.HTTP_200_OK
            
            tags_data = tags_response.json()
            assert "tags" in tags_data
            assert isinstance(tags_data["tags"], list)


class TestDataConsistency:
    """Test data consistency and integrity with production data"""
    
    def test_ingredient_references_valid(self, test_client_production_readonly, db_connection):
        """Test that ingredient parent references are valid"""
        cursor = db_connection.cursor()
        
        # Check for orphaned ingredient references
        cursor.execute("""
            SELECT i1.ingredient_id, i1.name, i1.parent_id 
            FROM ingredients i1 
            LEFT JOIN ingredients i2 ON i1.parent_id = i2.ingredient_id 
            WHERE i1.parent_id IS NOT NULL AND i2.ingredient_id IS NULL
        """)
        
        orphaned = cursor.fetchall()
        assert len(orphaned) == 0, f"Found orphaned ingredient references: {orphaned}"
    
    def test_recipe_ingredient_references_valid(self, test_client_production_readonly, db_connection):
        """Test that recipe-ingredient references are valid"""
        cursor = db_connection.cursor()
        
        # Check for invalid ingredient references in recipes
        cursor.execute("""
            SELECT ri.recipe_id, ri.ingredient_id 
            FROM recipe_ingredients ri 
            LEFT JOIN ingredients i ON ri.ingredient_id = i.ingredient_id 
            WHERE i.ingredient_id IS NULL
            LIMIT 10
        """)
        
        invalid_refs = cursor.fetchall()
        assert len(invalid_refs) == 0, f"Found invalid ingredient references in recipes: {invalid_refs}"
    
    def test_recipe_unit_references_valid(self, test_client_production_readonly, db_connection):
        """Test that recipe-unit references are valid"""
        cursor = db_connection.cursor()
        
        # Check for invalid unit references in recipes
        cursor.execute("""
            SELECT ri.recipe_id, ri.unit_id 
            FROM recipe_ingredients ri 
            LEFT JOIN units u ON ri.unit_id = u.unit_id 
            WHERE ri.unit_id IS NOT NULL AND u.unit_id IS NULL
            LIMIT 10
        """)
        
        invalid_refs = cursor.fetchall()
        assert len(invalid_refs) == 0, f"Found invalid unit references in recipes: {invalid_refs}"
    
    def test_rating_ranges_valid(self, test_client_production_readonly, db_connection):
        """Test that all ratings are within valid range"""
        cursor = db_connection.cursor()
        
        cursor.execute("SELECT rating_id, rating FROM ratings WHERE rating < 1 OR rating > 10")
        invalid_ratings = cursor.fetchall()
        
        assert len(invalid_ratings) == 0, f"Found ratings outside valid range (1-10): {invalid_ratings}"
    
    def test_database_schema_integrity(self, test_client_production_readonly, db_connection):
        """Test that database schema has expected tables and structure"""
        cursor = db_connection.cursor()
        
        # Check that all expected tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        expected_tables = [
            "ingredients", "recipes", "recipe_ingredients", 
            "units", "ratings", "tags", "recipe_tags"
        ]
        
        for table in expected_tables:
            assert table in tables, f"Expected table '{table}' not found in database"


class TestPerformance:
    """Performance tests with production data"""
    
    def test_ingredients_response_time(self, test_client_production_readonly):
        """Test that ingredients endpoint responds within reasonable time"""
        import time
        
        start_time = time.time()
        response = test_client_production_readonly.get("/api/v1/ingredients")
        end_time = time.time()
        
        assert response.status_code == status.HTTP_200_OK
        response_time = end_time - start_time
        assert response_time < 5.0, f"Ingredients endpoint took {response_time:.2f}s, should be under 5s"
    
    def test_recipes_response_time(self, test_client_production_readonly):
        """Test that recipes endpoint responds within reasonable time"""
        import time
        
        start_time = time.time()
        response = test_client_production_readonly.get("/api/v1/recipes?limit=50")
        end_time = time.time()
        
        assert response.status_code == status.HTTP_200_OK
        response_time = end_time - start_time
        assert response_time < 5.0, f"Recipes endpoint took {response_time:.2f}s, should be under 5s"