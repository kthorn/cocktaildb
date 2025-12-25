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
    assert_valid_response_structure,
)


class TestDataValidation:
    """Test that database data is valid and well-structured"""

    def test_ingredients_data_integrity(self, test_client_with_data):
        """Test ingredients data structure and relationships"""
        client, app = test_client_with_data
        response = client.get("/ingredients")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert isinstance(data, list)

        if data:
            # Test structure of ingredients
            for ingredient in data[:10]:  # Test first 10 ingredients
                assert_ingredient_structure(ingredient)

            # Test hierarchy relationships - should have both parent and child ingredients
            children = [ing for ing in data if ing.get("parent_id")]
            parents = [ing for ing in data if not ing.get("parent_id")]

            assert len(parents) > 0, "Should have root-level ingredients"
            assert len(children) > 0, "Should have child ingredients"

            # Verify parent-child relationships
            for child in children[:5]:  # Test first 5 children
                parent_id = child["parent_id"]
                parent = next((ing for ing in data if ing["id"] == parent_id), None)
                assert parent is not None, (
                    f"Parent {parent_id} not found for child {child['name']}"
                )

    def test_recipes_data_integrity(self, test_client_with_data):
        """Test recipes data structure and completeness"""
        client, app = test_client_with_data
        response = client.get("/recipes/search")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        recipes = data if isinstance(data, list) else data.get("recipes", [])

        assert len(recipes) > 0, "Should have test recipes"

        # Test detailed recipe structure
        recipe_id = recipes[0]["id"]
        detail_response = client.get(f"/recipes/{recipe_id}")
        assert detail_response.status_code == status.HTTP_200_OK

        recipe_detail = detail_response.json()
        assert_recipe_structure(recipe_detail)

        # Verify ingredients are properly structured
        if recipe_detail.get("ingredients"):
            ingredient = recipe_detail["ingredients"][0]
            expected_keys = [
                "ingredient_id",
                "ingredient_name",
                "unit_name",
            ]
            assert_valid_response_structure(ingredient, expected_keys)
            # Check that amount is present
            assert "amount" in ingredient, "Ingredient should have 'amount' field"

    def test_units_data_completeness(self, test_client_with_data):
        """Test that essential cocktail units exist in test data"""
        client, app = test_client_with_data
        response = client.get("/units")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        # Handle both possible response formats: direct list or dict with "units" key
        units = data if isinstance(data, list) else data.get("units", [])
        assert len(units) > 0, "Should have units in test database"

        # Test unit structure and validate conversion factors
        unit_names = [unit["name"].lower() for unit in units]
        unit_abbrevs = [
            unit["abbreviation"].lower() for unit in units if unit.get("abbreviation")
        ]

        # Essential cocktail units that should exist from schema
        expected_units = ["ounce", "dash", "tablespoon", "teaspoon"]
        expected_abbrevs = ["oz", "dash", "tbsp", "tsp"]

        for unit in expected_units:
            assert any(unit in name for name in unit_names), (
                f"Essential unit '{unit}' not found"
            )

        for abbrev in expected_abbrevs:
            assert any(abbrev in ab for ab in unit_abbrevs), (
                f"Essential abbreviation '{abbrev}' not found"
            )

        # Validate conversion factors
        for unit in units:
            assert_unit_structure(unit)
            # Only check conversion factor if it's not None (some units like "Each" may not have conversion)
            if unit.get("conversion_to_ml") is not None:
                assert unit["conversion_to_ml"] > 0, (
                    f"Invalid conversion factor for {unit['name']}"
                )


class TestSearchAndPaginationFunctionality:
    """Test search and pagination with test data"""

    def test_ingredients_endpoint_functionality(self, test_client_with_data):
        """Test ingredients endpoint returns all ingredients (no search functionality)"""
        client, app = test_client_with_data
        # Test basic ingredients endpoint
        response = client.get("/ingredients")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert isinstance(data, list), "Ingredients endpoint should return a list"
        assert len(data) > 0, "Should have test ingredients"

        # Verify ingredient structure
        ingredient = data[0]
        expected_keys = ["id", "name"]
        assert_valid_response_structure(ingredient, expected_keys)

        # Verify that adding search parameters doesn't change results
        # (since search is not implemented for ingredients)
        search_response = client.get("/ingredients?search=gin")
        assert search_response.status_code == status.HTTP_200_OK
        search_data = search_response.json()

        # Should return the same results as without search parameter
        assert len(search_data) == len(data), (
            "Search parameter should be ignored for ingredients endpoint"
        )


class TestDataConsistencyAndIntegrity:
    """Test data consistency and integrity with test data"""

    def test_database_referential_integrity(
        self, test_client_with_data, db_with_test_data
    ):
        """Test referential integrity across all tables"""
        cursor = db_with_test_data.cursor()

        # Test ingredient parent references
        cursor.execute("""
            SELECT i1.id, i1.name, i1.parent_id 
            FROM ingredients i1 
            LEFT JOIN ingredients i2 ON i1.parent_id = i2.id 
            WHERE i1.parent_id IS NOT NULL AND i2.id IS NULL
            LIMIT 5
        """)
        orphaned_ingredients = cursor.fetchall()
        assert len(orphaned_ingredients) == 0, (
            f"Found orphaned ingredient references: {orphaned_ingredients}"
        )

        # Test recipe-ingredient references
        cursor.execute("""
            SELECT ri.recipe_id, ri.ingredient_id 
            FROM recipe_ingredients ri 
            LEFT JOIN ingredients i ON ri.ingredient_id = i.id 
            WHERE i.id IS NULL
            LIMIT 5
        """)
        invalid_recipe_ingredients = cursor.fetchall()
        assert len(invalid_recipe_ingredients) == 0, (
            f"Found invalid ingredient references: {invalid_recipe_ingredients}"
        )

        # Test recipe-unit references
        cursor.execute("""
            SELECT ri.recipe_id, ri.unit_id 
            FROM recipe_ingredients ri 
            LEFT JOIN units u ON ri.unit_id = u.id 
            WHERE ri.unit_id IS NOT NULL AND u.id IS NULL
            LIMIT 5
        """)
        invalid_unit_refs = cursor.fetchall()
        assert len(invalid_unit_refs) == 0, (
            f"Found invalid unit references: {invalid_unit_refs}"
        )

    def test_data_quality_constraints(self, test_client_with_data, db_with_test_data):
        """Test data quality and business rule constraints"""
        cursor = db_with_test_data.cursor()

        # Test rating value constraints
        cursor.execute(
            "SELECT id, rating FROM ratings WHERE rating < 1 OR rating > 5 LIMIT 5"
        )
        invalid_ratings = cursor.fetchall()
        assert len(invalid_ratings) == 0, (
            f"Found ratings outside valid range (1-5): {invalid_ratings}"
        )

        # Test required fields are not empty
        cursor.execute(
            "SELECT id FROM ingredients WHERE name IS NULL OR name = '' LIMIT 5"
        )
        empty_ingredient_names = cursor.fetchall()
        assert len(empty_ingredient_names) == 0, (
            f"Found ingredients with empty names: {empty_ingredient_names}"
        )

        cursor.execute("SELECT id FROM recipes WHERE name IS NULL OR name = '' LIMIT 5")
        empty_recipe_names = cursor.fetchall()
        assert len(empty_recipe_names) == 0, (
            f"Found recipes with empty names: {empty_recipe_names}"
        )

    def test_schema_completeness(self, test_client_with_data, db_with_test_data):
        """Test that database schema has all expected tables"""
        cursor = db_with_test_data.cursor()

        # Use PostgreSQL information_schema instead of sqlite_master
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        tables = [row[0] for row in cursor.fetchall()]

        expected_tables = [
            "ingredients",
            "recipes",
            "recipe_ingredients",
            "units",
            "ratings",
            "tags",
            "recipe_tags",
        ]

        for table in expected_tables:
            assert table in tables, f"Expected table '{table}' not found in database"


class TestComplexIntegrationScenarios:
    """Test complex integration scenarios that span multiple endpoints"""

    def test_recipe_with_ingredients_and_ratings_flow(self, test_client_with_data):
        """Test complete recipe workflow with ingredients and ratings"""
        client, app = test_client_with_data

        # Get a recipe with detailed information
        recipes_response = client.get("/recipes/search?limit=1")
        assert recipes_response.status_code == status.HTTP_200_OK

        recipes_data = recipes_response.json()
        # Handle both possible response formats: direct list or dict with "recipes" key
        recipes = (
            recipes_data
            if isinstance(recipes_data, list)
            else recipes_data.get("recipes", [])
        )
        assert len(recipes) > 0, "Should have test recipes available"

        recipe_id = recipes[0]["id"]

        # Get detailed recipe with ingredients
        recipe_detail_response = client.get(f"/recipes/{recipe_id}")
        assert recipe_detail_response.status_code == status.HTTP_200_OK
        recipe_detail = recipe_detail_response.json()

        # Verify recipe has ingredients
        assert "ingredients" in recipe_detail
        if recipe_detail["ingredients"]:
            # Verify ingredient details are complete
            for ingredient in recipe_detail["ingredients"][:3]:  # Check first 3
                assert "ingredient_name" in ingredient
                assert "amount" in ingredient
                amount = ingredient.get("amount", 0)
                assert amount > 0
                if ingredient.get("unit_name"):
                    assert len(ingredient["unit_name"]) > 0

        # Get ratings for this recipe (correct endpoint is /ratings/recipes/{id})
        ratings_response = client.get(f"/ratings/recipes/{recipe_id}")
        assert ratings_response.status_code == status.HTTP_200_OK

        ratings_data = ratings_response.json()
        # The ratings endpoint returns a summary format, not individual ratings
        assert "recipe_id" in ratings_data
        assert "rating_count" in ratings_data
        assert "avg_rating" in ratings_data
        assert ratings_data["recipe_id"] == recipe_id

        # Verify rating summary structure
        assert isinstance(ratings_data["rating_count"], int)
        assert ratings_data["rating_count"] >= 0

        # avg_rating can be None if no ratings exist
        if ratings_data["avg_rating"] is not None:
            assert 0 <= ratings_data["avg_rating"] <= 5

        # If user_rating exists, verify its structure
        if ratings_data.get("user_rating"):
            user_rating = ratings_data["user_rating"]
            assert 1 <= user_rating["rating"] <= 5
            assert "user_id" in user_rating
            assert "recipe_id" in user_rating

    def test_ingredient_hierarchy_navigation(self, test_client_with_data):
        """Test navigating ingredient hierarchies"""
        client, app = test_client_with_data
        response = client.get("/ingredients")
        assert response.status_code == status.HTTP_200_OK

        ingredients = response.json()

        # Find ingredients with complex hierarchy paths
        hierarchical_ingredients = [
            ing
            for ing in ingredients
            if ing.get("path")
            and ing["path"].count("/") > 2  # More than just root level
        ]

        assert len(hierarchical_ingredients) > 0, (
            "Should have hierarchical ingredients in test data"
        )

        for ingredient in hierarchical_ingredients[:3]:  # Test first 3
            # Verify path structure
            assert ingredient["path"].startswith("/"), "Path should start with /"
            assert ingredient["path"].endswith("/"), "Path should end with /"

            # If it has a parent, verify parent exists
            if ingredient.get("parent_id"):
                parent = next(
                    (
                        ing
                        for ing in ingredients
                        if ing["id"] == ingredient["parent_id"]
                    ),
                    None,
                )
                assert parent is not None, f"Parent {ingredient['parent_id']} not found"


class TestSpecialUnitsIntegration:
    """Integration tests for special units in recipe creation and retrieval"""

    def test_create_and_retrieve_recipe_with_to_top(self, editor_client_with_data):
        """Test creating and retrieving recipe with 'to top' unit"""
        client = editor_client_with_data

        # First get ingredients and units for the test
        ingredients_response = client.get("/ingredients")
        assert ingredients_response.status_code == status.HTTP_200_OK
        ingredients = ingredients_response.json()

        units_response = client.get("/units")
        assert units_response.status_code == status.HTTP_200_OK
        units = units_response.json()

        # Find a suitable ingredient and 'to top' unit
        test_ingredient = ingredients[0] if ingredients else None
        to_top_unit = next((unit for unit in units if unit["name"] == "to top"), None)

        assert test_ingredient is not None, "Need at least one ingredient for test"

        # Create recipe with 'to top' unit and null amount
        recipe_data = {
            "name": "Test To Top Recipe",
            "instructions": "Test instructions",
            "description": "Test recipe with to top unit",
            "ingredients": [
                {
                    "ingredient_id": test_ingredient["id"],
                    "amount": None,  # Null amount for 'to top'
                    "unit_id": to_top_unit["id"],
                }
            ],
        }

        # Create the recipe
        create_response = client.post("/recipes", json=recipe_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        created_recipe = create_response.json()

        # Retrieve the recipe and verify structure
        get_response = client.get(f"/recipes/{created_recipe['id']}")
        assert get_response.status_code == status.HTTP_200_OK
        retrieved_recipe = get_response.json()

        # Verify the ingredient with 'to top' unit
        assert len(retrieved_recipe["ingredients"]) == 1
        ingredient = retrieved_recipe["ingredients"][0]

        assert ingredient["amount"] is None
        assert ingredient["unit_name"] == "to top"
        assert ingredient["ingredient_id"] == test_ingredient["id"]

    def test_create_and_retrieve_recipe_with_to_rinse(self, editor_client_with_data):
        """Test creating and retrieving recipe with 'to rinse' unit"""
        client = editor_client_with_data

        # Get ingredients and units
        ingredients_response = client.get("/ingredients")
        assert ingredients_response.status_code == status.HTTP_200_OK
        ingredients = ingredients_response.json()

        units_response = client.get("/units")
        assert units_response.status_code == status.HTTP_200_OK
        units = units_response.json()

        # Find suitable ingredient and 'to rinse' unit
        test_ingredient = ingredients[0] if ingredients else None
        to_rinse_unit = next(
            (unit for unit in units if unit["name"] == "to rinse"), None
        )

        assert test_ingredient is not None, "Need at least one ingredient for test"

        # Create recipe with 'to rinse' unit
        recipe_data = {
            "name": "Test To Rinse Recipe",
            "instructions": "Test instructions with rinse",
            "description": "Test recipe with to rinse unit",
            "ingredients": [
                {
                    "ingredient_id": test_ingredient["id"],
                    "amount": None,  # Null amount for 'to rinse'
                    "unit_id": to_rinse_unit["id"],
                }
            ],
        }

        # Create and retrieve recipe
        create_response = client.post("/recipes", json=recipe_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        created_recipe = create_response.json()

        get_response = client.get(f"/recipes/{created_recipe['id']}")
        assert get_response.status_code == status.HTTP_200_OK
        retrieved_recipe = get_response.json()

        # Verify the ingredient with 'to rinse' unit
        assert len(retrieved_recipe["ingredients"]) == 1
        ingredient = retrieved_recipe["ingredients"][0]

        assert ingredient["amount"] is None
        assert ingredient["unit_name"] == "to rinse"
        assert ingredient["ingredient_id"] == test_ingredient["id"]

    def test_create_and_retrieve_recipe_with_each_unit(self, editor_client_with_data):
        """Test creating and retrieving recipe with 'each' unit"""
        client = editor_client_with_data

        # Get ingredients and units
        ingredients_response = client.get("/ingredients")
        assert ingredients_response.status_code == status.HTTP_200_OK
        ingredients = ingredients_response.json()

        units_response = client.get("/units")
        assert units_response.status_code == status.HTTP_200_OK
        units = units_response.json()

        # Find suitable ingredient and 'each' unit
        test_ingredient = ingredients[0] if ingredients else None
        each_unit = next((unit for unit in units if unit["name"] == "Each"), None)

        assert each_unit is not None, "'Each' unit should exist in base schema"
        assert test_ingredient is not None, "Need at least one ingredient for test"

        # Create recipe with 'each' unit
        recipe_data = {
            "name": "Test Each Recipe",
            "instructions": "Test instructions with each unit",
            "description": "Test recipe with each unit",
            "ingredients": [
                {
                    "ingredient_id": test_ingredient["id"],
                    "amount": 2.0,  # 2 items
                    "unit_id": each_unit["id"],
                }
            ],
        }

        # Create and retrieve recipe
        create_response = client.post("/recipes", json=recipe_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        created_recipe = create_response.json()

        get_response = client.get(f"/recipes/{created_recipe['id']}")
        assert get_response.status_code == status.HTTP_200_OK
        retrieved_recipe = get_response.json()

        # Verify the ingredient with 'each' unit
        assert len(retrieved_recipe["ingredients"]) == 1
        ingredient = retrieved_recipe["ingredients"][0]

        assert ingredient["amount"] == 2.0
        assert ingredient["unit_name"] == "Each"
        assert ingredient["ingredient_id"] == test_ingredient["id"]
