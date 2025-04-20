import pytest
from src.database.cocktail_db import Database, Cocktail, Ingredient, Unit, UnitType
import os


@pytest.fixture
def db():
    # Use a test database URL
    os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test_db"
    return Database()


@pytest.fixture
def standard_units(db):
    # Create standard units for testing
    units = [
        {
            "name": "ounce",
            "abbreviation": "oz",
            "type": UnitType.VOLUME,
            "conversion_factor": 29.5735,  # to ml
            "description": "Fluid ounce",
        },
        {
            "name": "milliliter",
            "abbreviation": "ml",
            "type": UnitType.VOLUME,
            "conversion_factor": 1.0,  # base unit
            "description": "Milliliter",
        },
        {
            "name": "count",
            "abbreviation": "cnt",
            "type": UnitType.COUNT,
            "conversion_factor": 1.0,
            "description": "Count of items",
        },
    ]

    created_units = []
    for unit_data in units:
        unit = db.create_unit(unit_data)
        created_units.append(unit)

    return created_units


def test_create_cocktail(db):
    cocktail_data = {
        "name": "Test Cocktail",
        "description": "A test cocktail",
        "ingredients": {"vodka": "2 oz", "orange juice": "4 oz"},
        "instructions": "Mix and serve",
        "category": "test",
    }

    cocktail = db.create_cocktail(cocktail_data)
    assert cocktail.name == "Test Cocktail"
    assert cocktail.description == "A test cocktail"
    assert cocktail.ingredients == {"vodka": "2 oz", "orange juice": "4 oz"}


def test_get_cocktail(db):
    # First create a cocktail
    cocktail_data = {
        "name": "Test Get Cocktail",
        "description": "For testing get",
        "ingredients": {"gin": "1 oz"},
        "instructions": "Test instructions",
        "category": "test",
    }
    created = db.create_cocktail(cocktail_data)

    # Then retrieve it
    retrieved = db.get_cocktail(created.id)
    assert retrieved.name == "Test Get Cocktail"
    assert retrieved.description == "For testing get"


def test_update_cocktail(db):
    # Create initial cocktail
    cocktail_data = {
        "name": "Original Name",
        "description": "Original description",
        "ingredients": {"rum": "2 oz"},
        "instructions": "Original instructions",
        "category": "test",
    }
    created = db.create_cocktail(cocktail_data)

    # Update it
    update_data = {"name": "Updated Name", "description": "Updated description"}
    updated = db.update_cocktail(created.id, update_data)

    assert updated.name == "Updated Name"
    assert updated.description == "Updated description"
    assert updated.ingredients == {"rum": "2 oz"}  # Should remain unchanged


def test_delete_cocktail(db):
    # Create a cocktail to delete
    cocktail_data = {
        "name": "To Be Deleted",
        "description": "Will be deleted",
        "ingredients": {"tequila": "1 oz"},
        "instructions": "Delete me",
        "category": "test",
    }
    created = db.create_cocktail(cocktail_data)

    # Delete it
    result = db.delete_cocktail(created.id)
    assert result is True

    # Verify it's gone
    deleted = db.get_cocktail(created.id)
    assert deleted is None


def test_create_cocktail_with_ingredients(db):
    # First create some ingredients
    vodka = db.create_ingredient(
        {"name": "Vodka", "category": "spirit", "description": "Clear distilled spirit"}
    )

    orange_juice = db.create_ingredient(
        {
            "name": "Orange Juice",
            "category": "mixer",
            "description": "Fresh squeezed orange juice",
        }
    )

    # Create a cocktail with ingredients
    cocktail_data = {
        "name": "Screwdriver",
        "description": "A classic vodka and orange juice cocktail",
        "instructions": "Mix vodka and orange juice over ice",
        "category": "classic",
        "ingredients": [
            {"name": "Vodka", "amount": 2.0, "unit": "oz"},
            {"name": "Orange Juice", "amount": 4.0, "unit": "oz"},
        ],
    }

    cocktail = db.create_cocktail(cocktail_data)
    assert cocktail.name == "Screwdriver"
    assert len(cocktail.ingredients) == 2

    # Verify ingredient amounts
    for ingredient in cocktail.ingredients:
        if ingredient.name == "Vodka":
            assert ingredient.cocktails[0].amount == 2.0
            assert ingredient.cocktails[0].unit == "oz"
        elif ingredient.name == "Orange Juice":
            assert ingredient.cocktails[0].amount == 4.0
            assert ingredient.cocktails[0].unit == "oz"


def test_update_cocktail_ingredients(db):
    # Create initial cocktail
    cocktail_data = {
        "name": "Test Cocktail",
        "description": "Test description",
        "instructions": "Test instructions",
        "category": "test",
        "ingredients": [{"name": "Gin", "amount": 2.0, "unit": "oz"}],
    }
    created = db.create_cocktail(cocktail_data)

    # Update with new ingredients
    update_data = {
        "name": "Updated Name",
        "ingredients": [
            {"name": "Gin", "amount": 1.5, "unit": "oz"},
            {"name": "Tonic Water", "amount": 4.0, "unit": "oz"},
        ],
    }

    updated = db.update_cocktail(created.id, update_data)
    assert updated.name == "Updated Name"
    assert len(updated.ingredients) == 2

    # Verify ingredient amounts
    for ingredient in updated.ingredients:
        if ingredient.name == "Gin":
            assert ingredient.cocktails[0].amount == 1.5
        elif ingredient.name == "Tonic Water":
            assert ingredient.cocktails[0].amount == 4.0


def test_ingredient_management(db):
    # Create an ingredient
    ingredient_data = {
        "name": "Rum",
        "category": "spirit",
        "description": "Distilled sugarcane spirit",
    }
    ingredient = db.create_ingredient(ingredient_data)
    assert ingredient.name == "Rum"
    assert ingredient.category == "spirit"

    # Update the ingredient
    updated_ingredient = db.update_ingredient(
        ingredient.id, {"description": "Updated description"}
    )
    assert updated_ingredient.description == "Updated description"

    # Delete the ingredient
    result = db.delete_ingredient(ingredient.id)
    assert result is True
    assert db.get_ingredient(ingredient.id) is None


def test_cocktail_with_existing_ingredients(db):
    # Create an ingredient first
    db.create_ingredient({"name": "Vermouth", "category": "fortified wine"})

    # Create a cocktail using the existing ingredient
    cocktail_data = {
        "name": "Martini",
        "description": "Classic martini",
        "instructions": "Stir with ice and strain",
        "category": "classic",
        "ingredients": [{"name": "Vermouth", "amount": 0.5, "unit": "oz"}],
    }

    cocktail = db.create_cocktail(cocktail_data)
    assert len(cocktail.ingredients) == 1
    assert cocktail.ingredients[0].name == "Vermouth"


def test_unit_management(db):
    # Create a unit
    unit_data = {
        "name": "teaspoon",
        "abbreviation": "tsp",
        "type": UnitType.VOLUME,
        "conversion_factor": 4.92892,  # to ml
        "description": "Teaspoon",
    }
    unit = db.create_unit(unit_data)
    assert unit.name == "teaspoon"
    assert unit.abbreviation == "tsp"
    assert unit.type == UnitType.VOLUME

    # Update the unit
    updated_unit = db.update_unit(unit.id, {"description": "Updated description"})
    assert updated_unit.description == "Updated description"

    # Delete the unit
    result = db.delete_unit(unit.id)
    assert result is True
    assert db.get_unit(unit.id) is None


def test_unit_conversion(db, standard_units):
    # Get the units
    ounce = db.get_units_by_type(UnitType.VOLUME)[0]
    ml = db.get_units_by_type(UnitType.VOLUME)[1]

    # Test conversion
    assert db.convert_amount(1.0, ounce, ml) == pytest.approx(29.5735)
    assert db.convert_amount(29.5735, ml, ounce) == pytest.approx(1.0)


def test_cocktail_with_standardized_units(db, standard_units):
    # Create a cocktail with standardized units
    cocktail_data = {
        "name": "Test Cocktail",
        "description": "Test description",
        "instructions": "Test instructions",
        "category": "test",
        "ingredients": [
            {"name": "Vodka", "amount": 2.0, "unit": "ounce"},
            {"name": "Orange Juice", "amount": 60.0, "unit": "milliliter"},
        ],
    }

    cocktail = db.create_cocktail(cocktail_data)
    assert cocktail.name == "Test Cocktail"
    assert len(cocktail.ingredients) == 2

    # Verify units are properly set
    for ingredient in cocktail.ingredients:
        if ingredient.name == "Vodka":
            assert ingredient.cocktails[0].amount == 2.0
            assert db.get_unit(ingredient.cocktails[0].unit_id).name == "ounce"
        elif ingredient.name == "Orange Juice":
            assert ingredient.cocktails[0].amount == 60.0
            assert db.get_unit(ingredient.cocktails[0].unit_id).name == "milliliter"


def test_invalid_unit(db):
    # Try to create a cocktail with an invalid unit
    cocktail_data = {
        "name": "Invalid Cocktail",
        "description": "Should fail",
        "instructions": "Test",
        "category": "test",
        "ingredients": [{"name": "Vodka", "amount": 2.0, "unit": "invalid_unit"}],
    }

    with pytest.raises(ValueError) as exc_info:
        db.create_cocktail(cocktail_data)
    assert "Unit 'invalid_unit' not found" in str(exc_info.value)


def test_unit_type_validation(db, standard_units):
    # Create a weight unit
    weight_unit = db.create_unit(
        {
            "name": "gram",
            "abbreviation": "g",
            "type": UnitType.WEIGHT,
            "conversion_factor": 1.0,
            "description": "Gram",
        }
    )

    # Try to convert between different unit types
    volume_unit = db.get_units_by_type(UnitType.VOLUME)[0]

    with pytest.raises(ValueError) as exc_info:
        db.convert_amount(1.0, weight_unit, volume_unit)
    assert "Cannot convert between different unit types" in str(exc_info.value)


def test_get_units_by_type(db, standard_units):
    # Test getting units by type
    volume_units = db.get_units_by_type(UnitType.VOLUME)
    assert len(volume_units) == 2  # ounce and milliliter

    count_units = db.get_units_by_type(UnitType.COUNT)
    assert len(count_units) == 1  # count

    weight_units = db.get_units_by_type(UnitType.WEIGHT)
    assert len(weight_units) == 0  # no weight units yet
