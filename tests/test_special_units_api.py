"""
Special Units API Testing
Tests for recipes containing special units like "to top", "to rinse", and "each"
"""

from typing import Dict, Any

from api.db.db_core import Database


class TestSpecialUnitsInRecipes:
    """Test recipes containing special units"""

    def setup_test_data(self, db: Database) -> Dict[str, Any]:
        """Set up test data with ingredients and special units"""
        # Use existing ingredients or create new ones with unique names
        all_ingredients = db.get_ingredients()

        # Find existing ingredients or create new ones for testing
        gin = None
        champagne = None
        absinthe = None
        cherry = None

        # Look for suitable existing ingredients
        for ingredient in all_ingredients:
            if not gin and "gin" in ingredient.get("name", "").lower():
                gin = ingredient
            elif not champagne and any(
                word in ingredient.get("name", "").lower()
                for word in ["champagne", "sparkling"]
            ):
                champagne = ingredient
            elif not absinthe and "absinthe" in ingredient.get("name", "").lower():
                absinthe = ingredient
            elif not cherry and any(
                word in ingredient.get("name", "").lower()
                for word in ["cherry", "garnish"]
            ):
                cherry = ingredient

        # Create new ingredients if none found, with unique names
        if not gin:
            gin_data = {"name": "Test Gin", "description": "Test juniper-based spirit"}
            gin = db.create_ingredient(gin_data)

        if not champagne:
            champagne_data = {
                "name": "Test Champagne",
                "description": "Test sparkling wine",
            }
            champagne = db.create_ingredient(champagne_data)

        if not absinthe:
            absinthe_data = {
                "name": "Test Absinthe",
                "description": "Test high-proof spirit",
            }
            absinthe = db.create_ingredient(absinthe_data)

        if not cherry:
            cherry_data = {
                "name": "Test Cherry",
                "description": "Test cocktail garnish",
            }
            cherry = db.create_ingredient(cherry_data)

        return {
            "gin": gin,
            "champagne": champagne,
            "absinthe": absinthe,
            "cherry": cherry,
        }

    def test_recipe_with_to_top_unit(self, db_instance):
        """Test recipe with 'to top' unit and null amount"""
        db = db_instance
        ingredients = self.setup_test_data(db)

        # Get the 'to top' unit (should exist from migrations)
        to_top_unit = db.get_unit_by_name("to top")
        if not to_top_unit:
            # If unit doesn't exist, create it for the test
            conn = db._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO units (name, abbreviation, conversion_to_ml) VALUES (%s, %s, %s)",
                ("to top", "top", None),
            )
            conn.commit()
            to_top_unit = db.get_unit_by_name("to top")

        # Create recipe with 'to top' ingredient
        recipe_data = {
            "name": "French 75",
            "instructions": "Shake gin and lemon, strain, top with champagne",
            "description": "Classic champagne cocktail",
            "ingredients": [
                {
                    "ingredient_id": ingredients["gin"]["id"],
                    "amount": 1.0,
                    "unit_id": db.get_unit_by_name("Ounce")["id"],
                },
                {
                    "ingredient_id": ingredients["champagne"]["id"],
                    "amount": None,  # Null amount for 'to top'
                    "unit_id": to_top_unit["id"],
                },
            ],
        }

        recipe = db.create_recipe(recipe_data)
        retrieved_recipe = db.get_recipe(recipe["id"])

        # Find the champagne ingredient
        champagne_ingredient = None
        for ing in retrieved_recipe["ingredients"]:
            if ing["ingredient_id"] == ingredients["champagne"]["id"]:
                champagne_ingredient = ing
                break

        assert champagne_ingredient is not None
        assert champagne_ingredient["amount"] is None
        assert champagne_ingredient["unit_name"] == "to top"

    def test_recipe_with_to_rinse_unit(self, db_instance):
        """Test recipe with 'to rinse' unit and null amount"""
        db = db_instance
        ingredients = self.setup_test_data(db)

        # Get the 'to rinse' unit (should exist from migrations)
        to_rinse_unit = db.get_unit_by_name("to rinse")
        if not to_rinse_unit:
            # If unit doesn't exist, create it for the test
            conn = db._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO units (name, abbreviation, conversion_to_ml) VALUES (%s, %s, %s)",
                ("to rinse", "rinse", None),
            )
            conn.commit()
            to_rinse_unit = db.get_unit_by_name("to rinse")

        # Create recipe with 'to rinse' ingredient
        recipe_data = {
            "name": "Sazerac",
            "instructions": "Rinse glass with absinthe, add other ingredients",
            "description": "Classic New Orleans cocktail",
            "ingredients": [
                {
                    "ingredient_id": ingredients["absinthe"]["id"],
                    "amount": None,  # Null amount for 'to rinse'
                    "unit_id": to_rinse_unit["id"],
                }
            ],
        }

        recipe = db.create_recipe(recipe_data)
        retrieved_recipe = db.get_recipe(recipe["id"])

        # Find the absinthe ingredient
        absinthe_ingredient = None
        for ing in retrieved_recipe["ingredients"]:
            if ing["ingredient_id"] == ingredients["absinthe"]["id"]:
                absinthe_ingredient = ing
                break

        assert absinthe_ingredient is not None
        assert absinthe_ingredient["amount"] is None
        assert absinthe_ingredient["unit_name"] == "to rinse"

    def test_recipe_with_each_unit(self, db_instance):
        """Test recipe with 'each' unit"""
        db = db_instance
        ingredients = self.setup_test_data(db)

        # Get the 'each' unit (should exist in base schema)
        each_unit = db.get_unit_by_name("each")
        assert each_unit is not None, "'each' unit should exist in base schema"

        # Create recipe with 'each' ingredient
        recipe_data = {
            "name": "Manhattan",
            "instructions": "Stir ingredients, strain, garnish",
            "description": "Classic whiskey cocktail",
            "ingredients": [
                {
                    "ingredient_id": ingredients["cherry"]["id"],
                    "amount": 1.0,
                    "unit_id": each_unit["id"],
                }
            ],
        }

        recipe = db.create_recipe(recipe_data)
        retrieved_recipe = db.get_recipe(recipe["id"])

        # Find the cherry ingredient
        cherry_ingredient = None
        for ing in retrieved_recipe["ingredients"]:
            if ing["ingredient_id"] == ingredients["cherry"]["id"]:
                cherry_ingredient = ing
                break

        assert cherry_ingredient is not None
        assert cherry_ingredient["amount"] == 1.0
        assert cherry_ingredient["unit_name"] == "each"

    def test_multiple_special_units_in_recipe(self, db_instance):
        """Test recipe containing multiple special units"""
        db = db_instance
        ingredients = self.setup_test_data(db)

        # Ensure special units exist
        special_units = {}
        for unit_name in ["to top", "to rinse", "each"]:
            unit = db.get_unit_by_name(unit_name)
            if not unit and unit_name in ["to top", "to rinse"]:
                conn = db._get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO units (name, abbreviation, conversion_to_ml) VALUES (%s, %s, %s)",
                    (
                        unit_name,
                        unit_name.split()[1] if " " in unit_name else unit_name,
                        None,
                    ),
                )
                conn.commit()
                unit = db.get_unit_by_name(unit_name)
            special_units[unit_name] = unit

        # Create complex recipe with multiple special units
        recipe_data = {
            "name": "Complex Cocktail",
            "instructions": "Mix and garnish",
            "description": "Test cocktail with special units",
            "ingredients": [
                {
                    "ingredient_id": ingredients["gin"]["id"],
                    "amount": 2.0,
                    "unit_id": db.get_unit_by_name("Ounce")["id"],
                },
                {
                    "ingredient_id": ingredients["champagne"]["id"],
                    "amount": None,
                    "unit_id": special_units["to top"]["id"],
                },
                {
                    "ingredient_id": ingredients["absinthe"]["id"],
                    "amount": None,
                    "unit_id": special_units["to rinse"]["id"],
                },
                {
                    "ingredient_id": ingredients["cherry"]["id"],
                    "amount": 2.0,
                    "unit_id": special_units["each"]["id"],
                },
            ],
        }

        recipe = db.create_recipe(recipe_data)
        retrieved_recipe = db.get_recipe(recipe["id"])

        # Verify all ingredients have correct structure
        assert len(retrieved_recipe["ingredients"]) == 4

        # Check each ingredient type
        ingredient_checks = {
            ingredients["gin"]["id"]: {"amount": 2.0, "unit_name": "ounce"},
            ingredients["champagne"]["id"]: {"amount": None, "unit_name": "to top"},
            ingredients["absinthe"]["id"]: {
                "amount": None,
                "unit_name": "to rinse",
            },
            ingredients["cherry"]["id"]: {"amount": 2.0, "unit_name": "each"},
        }

        for ing in retrieved_recipe["ingredients"]:
            expected = ingredient_checks[ing["ingredient_id"]]
            assert ing["amount"] == expected["amount"]
            assert ing["unit_name"] == expected["unit_name"]


class TestSpecialUnitsValidation:
    """Test validation of special units"""

    def test_special_units_null_conversion(self, db_instance):
        """Test that special units have null conversion_to_ml"""
        db = db_instance

        # Check that special units have null conversions
        special_unit_names = ["to top", "to rinse", "each"]

        for unit_name in special_unit_names:
            unit = db.get_unit_by_name(unit_name)
            if unit:  # Unit exists
                # Special units should have null conversion
                if unit_name in ["to top", "to rinse"]:
                    assert unit["conversion_to_ml"] is None
                # 'each' should also have null conversion (no standard conversion)
                elif unit_name == "each":
                    assert unit["conversion_to_ml"] is None
