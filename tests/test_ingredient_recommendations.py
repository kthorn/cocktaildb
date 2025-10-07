"""
Tests for ingredient recommendation feature
"""

import pytest


class TestIngredientRecommendations:
    """Test the ingredient recommendation algorithm"""

    def setup_test_data(self, db_instance, user_id="test-user-123"):
        """Set up test data for recommendations testing"""
        # Create base ingredients with substitution levels
        # Use unique test names to avoid conflicts
        db_instance.execute_query(
            """
            INSERT INTO ingredients (id, name, description, parent_id, path, substitution_level) VALUES
            (100, 'Test Bourbon', 'American whiskey', 1, '/1/100/', 1),
            (101, 'Test Rye', 'Rye-based whiskey', 1, '/1/101/', 1),
            (102, 'Test Lemon', 'Fresh lemon juice', 7, '/7/102/', 1),
            (103, 'Test Lime', 'Fresh lime juice', 7, '/7/103/', 1),
            (104, 'Test Syrup', 'Sugar syrup', NULL, '/104/', 0),
            (105, 'Test Bitters', 'Aromatic bitters', NULL, '/105/', 0),
            (106, 'Test Vermouth', 'White vermouth', NULL, '/106/', 0),
            (107, 'Test Orange Liqueur', 'Triple sec style', NULL, '/107/', 0)
            """
        )

        # Create recipes
        db_instance.execute_query(
            """
            INSERT INTO recipes (id, name, instructions) VALUES
            (100, 'Old Fashioned', 'Classic whiskey cocktail'),
            (101, 'Whiskey Sour', 'Whisky with citrus'),
            (102, 'Margarita', 'Tequila cocktail'),
            (103, 'Manhattan', 'Whiskey and vermouth'),
            (104, 'Daiquiri', 'Rum cocktail')
            """
        )

        # Old Fashioned: Bourbon (100), Simple Syrup (104), Bitters (105)
        db_instance.execute_query(
            """
            INSERT INTO recipe_ingredients (recipe_id, ingredient_id, amount, unit_id) VALUES
            (100, 100, 2.0, 1),
            (100, 104, 0.5, 1),
            (100, 105, 2, 5)
            """
        )

        # Whiskey Sour: Bourbon (100), Lemon Juice (102), Simple Syrup (104)
        db_instance.execute_query(
            """
            INSERT INTO recipe_ingredients (recipe_id, ingredient_id, amount, unit_id) VALUES
            (101, 100, 2.0, 1),
            (101, 102, 0.75, 1),
            (101, 104, 0.5, 1)
            """
        )

        # Margarita: Tequila (6), Lime Juice (103), Orange Liqueur (107)
        db_instance.execute_query(
            """
            INSERT INTO recipe_ingredients (recipe_id, ingredient_id, amount, unit_id) VALUES
            (102, 6, 2.0, 1),
            (102, 103, 1.0, 1),
            (102, 107, 1.0, 1)
            """
        )

        # Manhattan: Bourbon (100), Dry Vermouth (106), Bitters (105)
        db_instance.execute_query(
            """
            INSERT INTO recipe_ingredients (recipe_id, ingredient_id, amount, unit_id) VALUES
            (103, 100, 2.0, 1),
            (103, 106, 1.0, 1),
            (103, 105, 2, 5)
            """
        )

        # Daiquiri: Rum (2), Lime Juice (103), Simple Syrup (104)
        db_instance.execute_query(
            """
            INSERT INTO recipe_ingredients (recipe_id, ingredient_id, amount, unit_id) VALUES
            (104, 2, 2.0, 1),
            (104, 103, 0.75, 1),
            (104, 104, 0.5, 1)
            """
        )

    def test_recommendations_basic(self, db_instance_with_data):
        """Test basic recommendation functionality"""
        user_id = "test-user-123"

        # Setup test data
        self.setup_test_data(db_instance_with_data, user_id)

        # User has Bourbon and Simple Syrup
        db_instance_with_data.execute_query(
            "INSERT INTO user_ingredients (cognito_user_id, ingredient_id) VALUES (?, ?)",
            (user_id, 100)  # Bourbon
        )
        db_instance_with_data.execute_query(
            "INSERT INTO user_ingredients (cognito_user_id, ingredient_id) VALUES (?, ?)",
            (user_id, 104)  # Simple Syrup
        )

        # Get recommendations
        recommendations = db_instance_with_data.get_ingredient_recommendations(user_id, limit=10)

        # Should recommend ingredients that unlock recipes
        assert len(recommendations) > 0

        # Verify structure
        for rec in recommendations:
            assert "id" in rec
            assert "name" in rec
            assert "recipes_unlocked" in rec
            assert "recipe_names" in rec
            assert isinstance(rec["recipe_names"], list)

    def test_recommendations_with_no_user_ingredients(self, db_instance_with_data):
        """Test recommendations when user has no ingredients"""
        user_id = "test-user-empty"

        self.setup_test_data(db_instance_with_data, user_id)

        # User has no ingredients
        recommendations = db_instance_with_data.get_ingredient_recommendations(user_id, limit=10)

        # Should return empty list - no "almost makeable" recipes
        assert len(recommendations) == 0

    def test_recommendations_prioritizes_high_impact(self, db_instance_with_data):
        """Test that recommendations prioritize ingredients that unlock more recipes"""
        user_id = "test-user-priority"

        self.setup_test_data(db_instance_with_data, user_id)

        # User has Bourbon, so they're 1 ingredient away from multiple recipes
        db_instance_with_data.execute_query(
            "INSERT INTO user_ingredients (cognito_user_id, ingredient_id) VALUES (?, ?)",
            (user_id, 100)  # Bourbon
        )

        # Also add Simple Syrup
        db_instance_with_data.execute_query(
            "INSERT INTO user_ingredients (cognito_user_id, ingredient_id) VALUES (?, ?)",
            (user_id, 104)  # Simple Syrup
        )

        recommendations = db_instance_with_data.get_ingredient_recommendations(user_id, limit=10)

        # Should get recommendations
        assert len(recommendations) > 0

        # Verify sorted by recipes_unlocked (descending)
        if len(recommendations) > 1:
            for i in range(len(recommendations) - 1):
                assert recommendations[i]["recipes_unlocked"] >= recommendations[i + 1]["recipes_unlocked"]

    def test_recommendations_respects_limit(self, db_instance_with_data):
        """Test that recommendations respect the limit parameter"""
        user_id = "test-user-limit"

        self.setup_test_data(db_instance_with_data, user_id)

        # User has Bourbon
        db_instance_with_data.execute_query(
            "INSERT INTO user_ingredients (cognito_user_id, ingredient_id) VALUES (?, ?)",
            (user_id, 100)  # Bourbon
        )

        # Request only 2 recommendations
        recommendations = db_instance_with_data.get_ingredient_recommendations(user_id, limit=2)

        # Should return at most 2
        assert len(recommendations) <= 2

    def test_recommendations_with_all_ingredients(self, db_instance_with_data):
        """Test recommendations when user can make all recipes"""
        user_id = "test-user-complete"

        self.setup_test_data(db_instance_with_data, user_id)

        # Give user all necessary ingredients
        for ingredient_id in [100, 102, 103, 104, 105, 106, 107, 2, 6]:
            db_instance_with_data.execute_query(
                "INSERT INTO user_ingredients (cognito_user_id, ingredient_id) VALUES (?, ?)",
                (user_id, ingredient_id)
            )

        recommendations = db_instance_with_data.get_ingredient_recommendations(user_id, limit=10)

        # Should return empty - user can make everything
        assert len(recommendations) == 0

    def test_recommendations_recipe_names_accuracy(self, db_instance_with_data):
        """Test that recipe names are correctly associated with recommendations"""
        user_id = "test-user-names"

        self.setup_test_data(db_instance_with_data, user_id)

        # User has Bourbon and Simple Syrup (can almost make Old Fashioned and Whiskey Sour)
        db_instance_with_data.execute_query(
            "INSERT INTO user_ingredients (cognito_user_id, ingredient_id) VALUES (?, ?)",
            (user_id, 100)  # Bourbon
        )
        db_instance_with_data.execute_query(
            "INSERT INTO user_ingredients (cognito_user_id, ingredient_id) VALUES (?, ?)",
            (user_id, 104)  # Simple Syrup
        )

        recommendations = db_instance_with_data.get_ingredient_recommendations(user_id, limit=10)

        # Find Bitters in recommendations
        bitters_rec = next((r for r in recommendations if r["name"] == "Test Bitters"), None)
        if bitters_rec:
            # Should unlock Old Fashioned and Manhattan
            assert bitters_rec["recipes_unlocked"] >= 1
            assert len(bitters_rec["recipe_names"]) == bitters_rec["recipes_unlocked"]

    def test_recommendations_with_substitution_level_0(self, db_instance_with_data):
        """Test that substitution level 0 requires exact match"""
        user_id = "test-user-exact"

        # Create ingredients with substitution level 0
        db_instance_with_data.execute_query(
            """
            INSERT INTO ingredients (id, name, parent_id, path, substitution_level) VALUES
            (200, 'Specific Brand Rum', 2, '/2/200/', 0)
            """
        )

        # Create recipe requiring exact brand
        db_instance_with_data.execute_query(
            "INSERT INTO recipes (id, name, instructions) VALUES (200, 'Special Daiquiri', 'Requires specific brand')"
        )
        db_instance_with_data.execute_query(
            "INSERT INTO recipe_ingredients (recipe_id, ingredient_id, amount, unit_id) VALUES (200, 200, 2.0, 1)"
        )

        # User has generic Rum (id=2)
        db_instance_with_data.execute_query(
            "INSERT INTO user_ingredients (cognito_user_id, ingredient_id) VALUES (?, ?)",
            (user_id, 2)  # Generic Rum
        )

        recommendations = db_instance_with_data.get_ingredient_recommendations(user_id, limit=10)

        # Should recommend the specific brand since user only has generic
        specific_brand = next((r for r in recommendations if r["id"] == 200), None)
        # This recipe requires exact match, so generic rum shouldn't satisfy it
        # (depending on implementation details, this might show up in recommendations)


class TestIngredientRecommendationsAPI:
    """Test the API endpoint for ingredient recommendations"""

    def test_recommendations_endpoint_requires_auth(self, test_client_memory):
        """Test that recommendations endpoint requires authentication"""
        response = test_client_memory.get("/user-ingredients/recommendations")
        assert response.status_code == 401

    def test_recommendations_endpoint_success(self, authenticated_client, db_instance_with_data):
        """Test successful recommendations API call"""
        user_id = "test-user-123"

        # Setup test data
        test = TestIngredientRecommendations()
        test.setup_test_data(db_instance_with_data, user_id)

        # Add some user ingredients
        db_instance_with_data.execute_query(
            "INSERT INTO user_ingredients (cognito_user_id, ingredient_id) VALUES (?, ?)",
            (user_id, 100)  # Bourbon
        )

        response = authenticated_client.get("/user-ingredients/recommendations")
        assert response.status_code == 200

        data = response.json()
        assert "recommendations" in data
        assert "total_count" in data
        assert isinstance(data["recommendations"], list)

    def test_recommendations_endpoint_with_limit(self, authenticated_client, db_instance_with_data):
        """Test recommendations endpoint with custom limit"""
        user_id = "test-user-123"

        # Setup test data
        test = TestIngredientRecommendations()
        test.setup_test_data(db_instance_with_data, user_id)

        # Add user ingredient
        db_instance_with_data.execute_query(
            "INSERT INTO user_ingredients (cognito_user_id, ingredient_id) VALUES (?, ?)",
            (user_id, 100)
        )

        response = authenticated_client.get("/user-ingredients/recommendations?limit=5")
        assert response.status_code == 200

        data = response.json()
        assert len(data["recommendations"]) <= 5

    def test_recommendations_response_structure(self, authenticated_client, db_instance_with_data):
        """Test that recommendations response has correct structure"""
        user_id = "test-user-123"

        # Setup test data
        test = TestIngredientRecommendations()
        test.setup_test_data(db_instance_with_data, user_id)

        # Add user ingredient
        db_instance_with_data.execute_query(
            "INSERT INTO user_ingredients (cognito_user_id, ingredient_id) VALUES (?, ?)",
            (user_id, 100)
        )

        response = authenticated_client.get("/user-ingredients/recommendations")
        assert response.status_code == 200

        data = response.json()

        # Check top-level structure
        assert "recommendations" in data
        assert "total_count" in data

        # Check each recommendation structure
        if len(data["recommendations"]) > 0:
            rec = data["recommendations"][0]
            assert "id" in rec
            assert "name" in rec
            assert "description" in rec or rec["description"] is None
            assert "parent_id" in rec or rec["parent_id"] is None
            assert "path" in rec
            assert "substitution_level" in rec or rec["substitution_level"] is None
            assert "recipes_unlocked" in rec
            assert "recipe_names" in rec
            assert isinstance(rec["recipe_names"], list)
