"""
Integration tests for CocktailDB API using production data
Tests end-to-end functionality with realistic data scenarios and production data validation
"""

import pytest
from fastapi import status
from conftest import (
    assert_ingredient_structure, 
    assert_recipe_structure, 
    assert_unit_structure,
    assert_valid_response_structure
)


class TestProductionDataValidation:
    """Test that production data is valid and well-structured"""
    
    def test_ingredients_production_data_integrity(self, test_client_production_readonly):
        """Test ingredients production data structure and relationships"""
        response = test_client_production_readonly.get("/api/v1/ingredients")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert isinstance(data, list)
        
        if data:
            # Test structure of ingredients
            for ingredient in data[:10]:  # Test first 10 ingredients
                assert_ingredient_structure(ingredient)
            
            # Test hierarchy relationships
            children = [ing for ing in data if ing.get("parent_id")]
            parents = [ing for ing in data if not ing.get("parent_id")]
            
            assert len(parents) > 0, "Should have root-level ingredients"
            
            # Verify parent-child relationships
            for child in children[:5]:  # Test first 5 children
                parent_id = child["parent_id"]
                parent = next((ing for ing in data if ing["ingredient_id"] == parent_id), None)
                assert parent is not None, f"Parent {parent_id} not found for child {child['name']}"
    
    def test_recipes_production_data_integrity(self, test_client_production_readonly):
        """Test recipes production data structure and completeness"""
        response = test_client_production_readonly.get("/api/v1/recipes")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert "recipes" in data
        recipes = data["recipes"]
        
        if recipes:
            # Test detailed recipe structure
            recipe_id = recipes[0]["recipe_id"]
            detail_response = test_client_production_readonly.get(f"/api/v1/recipes/{recipe_id}")
            assert detail_response.status_code == status.HTTP_200_OK
            
            recipe_detail = detail_response.json()
            assert_recipe_structure(recipe_detail)
            
            # Verify ingredients are properly structured
            if recipe_detail.get("ingredients"):
                ingredient = recipe_detail["ingredients"][0]
                expected_keys = ["ingredient_id", "ingredient_name", "quantity", "unit_name"]
                assert_valid_response_structure(ingredient, expected_keys)
    
    def test_units_production_data_completeness(self, test_client_production_readonly):
        """Test that essential cocktail units exist in production data"""
        response = test_client_production_readonly.get("/api/v1/units")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert "units" in data
        units = data["units"]
        assert len(units) > 0, "Should have units in production database"
        
        # Test unit structure and validate conversion factors
        unit_names = [unit["name"].lower() for unit in units]
        unit_abbrevs = [unit["abbreviation"].lower() for unit in units]
        
        # Essential cocktail units
        expected_units = ["ounce", "ml", "dash"]
        expected_abbrevs = ["oz", "ml"]
        
        for unit in expected_units:
            assert any(unit in name for name in unit_names), f"Essential unit '{unit}' not found"
        
        for abbrev in expected_abbrevs:
            assert any(abbrev in ab for ab in unit_abbrevs), f"Essential abbreviation '{abbrev}' not found"
        
        # Validate conversion factors
        for unit in units:
            assert_unit_structure(unit)
            assert unit["conversion_to_ml"] > 0, f"Invalid conversion factor for {unit['name']}"


class TestSearchAndPaginationFunctionality:
    """Test search and pagination with production data"""
    
    def test_ingredient_search_relevance(self, test_client_production_readonly):
        """Test ingredient search returns relevant results"""
        search_terms = ["gin", "vodka", "rum", "whiskey"]
        
        for term in search_terms:
            response = test_client_production_readonly.get(f"/api/v1/ingredients?search={term}")
            assert response.status_code == status.HTTP_200_OK
            
            data = response.json()
            assert "ingredients" in data
            
            # Verify search relevance
            if data["ingredients"]:
                for ingredient in data["ingredients"][:3]:  # Check first 3 results
                    name_match = term.lower() in ingredient["name"].lower()
                    desc_match = ingredient.get("description", "") and term.lower() in ingredient["description"].lower()
                    assert name_match or desc_match, f"Search term '{term}' not found in result: {ingredient['name']}"
    
    def test_recipe_search_and_pagination(self, test_client_production_readonly):
        """Test recipe search and pagination functionality"""
        # Test pagination consistency
        page1_response = test_client_production_readonly.get("/api/v1/recipes?limit=5&offset=0")
        page2_response = test_client_production_readonly.get("/api/v1/recipes?limit=5&offset=5")
        
        assert page1_response.status_code == status.HTTP_200_OK
        assert page2_response.status_code == status.HTTP_200_OK
        
        page1_data = page1_response.json()
        page2_data = page2_response.json()
        
        # Should have different recipes (if enough exist)
        if len(page1_data["recipes"]) == 5 and len(page2_data["recipes"]) > 0:
            page1_ids = {r["recipe_id"] for r in page1_data["recipes"]}
            page2_ids = {r["recipe_id"] for r in page2_data["recipes"]}
            assert page1_ids.isdisjoint(page2_ids), "Pagination should return different recipes"
        
        # Test search functionality
        search_terms = ["martini", "mojito", "cocktail"]
        for term in search_terms:
            search_response = test_client_production_readonly.get(f"/api/v1/recipes?search={term}")
            assert search_response.status_code == status.HTTP_200_OK
            
            search_data = search_response.json()
            if search_data["recipes"]:
                for recipe in search_data["recipes"][:2]:  # Check first 2 results
                    name_match = term.lower() in recipe["name"].lower()
                    inst_match = recipe.get("instructions", "") and term.lower() in recipe["instructions"].lower()
                    assert name_match or inst_match, f"Search term '{term}' not found in recipe: {recipe['name']}"


class TestDataConsistencyAndIntegrity:
    """Test data consistency and integrity with production data"""
    
    def test_database_referential_integrity(self, test_client_production_readonly, db_connection):
        """Test referential integrity across all tables"""
        cursor = db_connection.cursor()
        
        # Test ingredient parent references
        cursor.execute("""
            SELECT i1.ingredient_id, i1.name, i1.parent_id 
            FROM ingredients i1 
            LEFT JOIN ingredients i2 ON i1.parent_id = i2.ingredient_id 
            WHERE i1.parent_id IS NOT NULL AND i2.ingredient_id IS NULL
            LIMIT 5
        """)
        orphaned_ingredients = cursor.fetchall()
        assert len(orphaned_ingredients) == 0, f"Found orphaned ingredient references: {orphaned_ingredients}"
        
        # Test recipe-ingredient references
        cursor.execute("""
            SELECT ri.recipe_id, ri.ingredient_id 
            FROM recipe_ingredients ri 
            LEFT JOIN ingredients i ON ri.ingredient_id = i.ingredient_id 
            WHERE i.ingredient_id IS NULL
            LIMIT 5
        """)
        invalid_recipe_ingredients = cursor.fetchall()
        assert len(invalid_recipe_ingredients) == 0, f"Found invalid ingredient references: {invalid_recipe_ingredients}"
        
        # Test recipe-unit references
        cursor.execute("""
            SELECT ri.recipe_id, ri.unit_id 
            FROM recipe_ingredients ri 
            LEFT JOIN units u ON ri.unit_id = u.unit_id 
            WHERE ri.unit_id IS NOT NULL AND u.unit_id IS NULL
            LIMIT 5
        """)
        invalid_unit_refs = cursor.fetchall()
        assert len(invalid_unit_refs) == 0, f"Found invalid unit references: {invalid_unit_refs}"
    
    def test_data_quality_constraints(self, test_client_production_readonly, db_connection):
        """Test data quality and business rule constraints"""
        cursor = db_connection.cursor()
        
        # Test rating value constraints
        cursor.execute("SELECT rating_id, rating FROM ratings WHERE rating < 1 OR rating > 10 LIMIT 5")
        invalid_ratings = cursor.fetchall()
        assert len(invalid_ratings) == 0, f"Found ratings outside valid range (1-10): {invalid_ratings}"
        
        # Test required fields are not empty
        cursor.execute("SELECT ingredient_id FROM ingredients WHERE name IS NULL OR name = '' LIMIT 5")
        empty_ingredient_names = cursor.fetchall()
        assert len(empty_ingredient_names) == 0, f"Found ingredients with empty names: {empty_ingredient_names}"
        
        cursor.execute("SELECT recipe_id FROM recipes WHERE name IS NULL OR name = '' LIMIT 5")
        empty_recipe_names = cursor.fetchall()
        assert len(empty_recipe_names) == 0, f"Found recipes with empty names: {empty_recipe_names}"
    
    def test_schema_completeness(self, test_client_production_readonly, db_connection):
        """Test that database schema has all expected tables"""
        cursor = db_connection.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        expected_tables = [
            "ingredients", "recipes", "recipe_ingredients", 
            "units", "ratings", "tags", "recipe_tags"
        ]
        
        for table in expected_tables:
            assert table in tables, f"Expected table '{table}' not found in database"


class TestComplexIntegrationScenarios:
    """Test complex integration scenarios that span multiple endpoints"""
    
    def test_recipe_with_ingredients_and_ratings_flow(self, test_client_production_readonly):
        """Test complete recipe workflow with ingredients and ratings"""
        # Get a recipe with detailed information
        recipes_response = test_client_production_readonly.get("/api/v1/recipes?limit=1")
        assert recipes_response.status_code == status.HTTP_200_OK
        
        recipes_data = recipes_response.json()
        if not recipes_data["recipes"]:
            pytest.skip("No recipes available for integration test")
        
        recipe_id = recipes_data["recipes"][0]["recipe_id"]
        
        # Get detailed recipe with ingredients
        recipe_detail_response = test_client_production_readonly.get(f"/api/v1/recipes/{recipe_id}")
        assert recipe_detail_response.status_code == status.HTTP_200_OK
        recipe_detail = recipe_detail_response.json()
        
        # Verify recipe has ingredients
        assert "ingredients" in recipe_detail
        if recipe_detail["ingredients"]:
            # Verify ingredient details are complete
            for ingredient in recipe_detail["ingredients"][:3]:  # Check first 3
                assert "ingredient_name" in ingredient
                assert "quantity" in ingredient
                assert ingredient["quantity"] > 0
                if ingredient.get("unit_name"):
                    assert len(ingredient["unit_name"]) > 0
        
        # Get ratings for this recipe
        ratings_response = test_client_production_readonly.get(f"/api/v1/recipes/{recipe_id}/ratings")
        assert ratings_response.status_code == status.HTTP_200_OK
        
        ratings_data = ratings_response.json()
        assert "ratings" in ratings_data
        
        # Verify rating structure if any exist
        if ratings_data["ratings"]:
            rating = ratings_data["ratings"][0]
            assert 1 <= rating["rating"] <= 10
            assert "user_id" in rating
            assert "created_at" in rating
    
    def test_ingredient_hierarchy_navigation(self, test_client_production_readonly):
        """Test navigating ingredient hierarchies"""
        response = test_client_production_readonly.get("/api/v1/ingredients")
        assert response.status_code == status.HTTP_200_OK
        
        ingredients = response.json()
        
        # Find ingredients with complex hierarchy paths
        hierarchical_ingredients = [
            ing for ing in ingredients 
            if ing.get("ingredient_path") and ing["ingredient_path"].count("/") > 1
        ]
        
        if hierarchical_ingredients:
            for ingredient in hierarchical_ingredients[:3]:  # Test first 3
                # Verify full name includes hierarchy information
                if ingredient.get("full_name"):
                    assert ingredient["name"] in ingredient["full_name"]
                    
                    # If it has a parent, full name should be longer than just the name
                    if ingredient.get("parent_id"):
                        assert len(ingredient["full_name"]) > len(ingredient["name"])


class TestPerformanceWithProductionData:
    """Performance tests with production data volumes"""
    
    def test_endpoint_response_times(self, test_client_production_readonly):
        """Test that key endpoints respond within reasonable time limits"""
        import time
        
        endpoints_and_limits = [
            ("/api/v1/ingredients", 3.0),
            ("/api/v1/recipes?limit=50", 5.0),
            ("/api/v1/units", 2.0),
        ]
        
        for endpoint, time_limit in endpoints_and_limits:
            start_time = time.time()
            response = test_client_production_readonly.get(endpoint)
            end_time = time.time()
            
            assert response.status_code == status.HTTP_200_OK
            response_time = end_time - start_time
            assert response_time < time_limit, f"{endpoint} took {response_time:.2f}s, should be under {time_limit}s"