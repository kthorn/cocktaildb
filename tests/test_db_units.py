"""
Database Unit Operations Testing
Tests for unit-related database operations including get_unit_by_name,
get_unit_by_abbreviation, and get_unit_by_name_or_abbreviation
"""

import pytest
from api.db.db_core import Database


class TestUnitDatabaseOperations:
    """Test unit-related database operations"""

    def test_get_unit_by_name_exact_match(self, db_instance_with_data):
        """Test getting unit by exact name match"""
        db = db_instance_with_data
        # Test with a unit that exists in test data (lowercase)
        result = db.get_unit_by_name("ounce")

        assert result is not None
        assert result["name"] == "ounce"
        assert result["abbreviation"] == "oz"
        assert "id" in result

    def test_get_unit_by_name_case_insensitive(self, db_instance_with_data):
        """Test getting unit by name is case insensitive"""
        db = db_instance_with_data
        # Test lowercase
        result = db.get_unit_by_name("ounce")
        assert result is not None
        assert result["name"] == "ounce"

        # Test uppercase
        result = db.get_unit_by_name("OUNCE")
        assert result is not None
        assert result["name"] == "ounce"

        # Test mixed case
        result = db.get_unit_by_name("OuNcE")
        assert result is not None
        assert result["name"] == "ounce"

    def test_get_unit_by_name_not_found(self, db_instance_with_data):
        """Test getting unit by name when unit doesn't exist"""
        db = db_instance_with_data
        result = db.get_unit_by_name("NonexistentUnit")
        assert result is None

    def test_get_unit_by_name_empty_string(self, db_instance_with_data):
        """Test getting unit by empty name"""
        db = db_instance_with_data
        result = db.get_unit_by_name("")
        assert result is None

    def test_get_unit_by_abbreviation_exact_match(self, db_instance_with_data):
        """Test getting unit by exact abbreviation match"""
        db = db_instance_with_data
        # Test with an abbreviation that exists in test data
        result = db.get_unit_by_abbreviation("oz")

        assert result is not None
        assert result["name"] == "ounce"
        assert result["abbreviation"] == "oz"
        assert "id" in result

    def test_get_unit_by_abbreviation_case_insensitive(self, db_instance_with_data):
        """Test getting unit by abbreviation is case insensitive"""
        db = db_instance_with_data
        # Test lowercase
        result = db.get_unit_by_abbreviation("oz")
        assert result is not None
        assert result["abbreviation"] == "oz"

        # Test uppercase
        result = db.get_unit_by_abbreviation("OZ")
        assert result is not None
        assert result["abbreviation"] == "oz"

        # Test mixed case
        result = db.get_unit_by_abbreviation("Oz")
        assert result is not None
        assert result["abbreviation"] == "oz"

    def test_get_unit_by_abbreviation_not_found(self, db_instance_with_data):
        """Test getting unit by abbreviation when unit doesn't exist"""
        db = db_instance_with_data
        result = db.get_unit_by_abbreviation("xyz")
        assert result is None

    def test_get_unit_by_abbreviation_empty_string(self, db_instance_with_data):
        """Test getting unit by empty abbreviation"""
        db = db_instance_with_data
        result = db.get_unit_by_abbreviation("")
        assert result is None

    def test_get_unit_by_name_or_abbreviation_by_name(self, db_instance_with_data):
        """Test getting unit by name when searching by name or abbreviation"""
        db = db_instance_with_data
        result = db.get_unit_by_name_or_abbreviation("ounce")

        assert result is not None
        assert result["name"] == "ounce"
        assert result["abbreviation"] == "oz"

    def test_get_unit_by_name_or_abbreviation_by_abbreviation(self, db_instance_with_data):
        """Test getting unit by abbreviation when name doesn't match"""
        db = db_instance_with_data
        result = db.get_unit_by_name_or_abbreviation("oz")

        assert result is not None
        assert result["name"] == "ounce"
        assert result["abbreviation"] == "oz"

    def test_get_unit_by_name_or_abbreviation_neither_match(self, db_instance_with_data):
        """Test getting unit when neither name nor abbreviation match"""
        db = db_instance_with_data
        result = db.get_unit_by_name_or_abbreviation("NonexistentUnit")
        assert result is None

    def test_get_unit_by_name_or_abbreviation_case_insensitive(self, db_instance_with_data):
        """Test that name or abbreviation search is case insensitive"""
        db = db_instance_with_data
        # Test with mixed case name
        result = db.get_unit_by_name_or_abbreviation("OuNcE")
        assert result is not None
        assert result["name"] == "ounce"

    def test_conversion_to_ml_field_present(self, db_instance_with_data):
        """Test that conversion_to_ml field is present in results"""
        db = db_instance_with_data
        result = db.get_unit_by_name("ounce")

        assert "conversion_to_ml" in result


class TestSpecialUnits:
    """Test special units like 'to top', 'to rinse', and 'each'"""

    def test_dash_unit_exists(self, db_instance_with_data):
        """Test that 'dash' unit exists in test data"""
        db = db_instance_with_data
        result = db.get_unit_by_name("dash")

        assert result is not None
        assert result["name"] == "dash"
        assert result["abbreviation"] == "dash"

    def test_special_units_case_insensitive(self, db_instance_with_data):
        """Test that units are case insensitive"""
        db = db_instance_with_data
        # Test 'dash' in different cases
        for case_variant in ["dash", "DASH", "Dash", "dAsH"]:
            result = db.get_unit_by_name(case_variant)
            assert result is not None
            assert result["name"] == "dash"

    def test_teaspoon_unit_properties(self, db_instance_with_data):
        """Test 'teaspoon' unit properties"""
        db = db_instance_with_data
        result = db.get_unit_by_name("teaspoon")

        assert result is not None
        assert result["name"] == "teaspoon"
        assert result["abbreviation"] == "tsp"
        assert result["conversion_to_ml"] is not None

    def test_tablespoon_unit_properties(self, db_instance_with_data):
        """Test 'tablespoon' unit properties"""
        db = db_instance_with_data
        result = db.get_unit_by_name("tablespoon")

        assert result is not None
        assert result["name"] == "tablespoon"
        assert result["abbreviation"] == "tbsp"
        assert result["conversion_to_ml"] is not None

    def test_special_units_by_abbreviation(self, db_instance_with_data):
        """Test getting units by their abbreviations"""
        db = db_instance_with_data
        # Test 'ml' by abbreviation
        result = db.get_unit_by_abbreviation("ml")
        assert result is not None
        assert result["name"] == "milliliter"

        # Test 'tsp' by abbreviation
        result = db.get_unit_by_abbreviation("tsp")
        assert result is not None
        assert result["name"] == "teaspoon"

        # Test 'tbsp' by abbreviation
        result = db.get_unit_by_abbreviation("tbsp")
        assert result is not None
        assert result["name"] == "tablespoon"

    def test_units_with_conversion(self, db_instance_with_data):
        """Test that units with conversions are handled correctly"""
        db = db_instance_with_data
        # Get all units and check for conversions
        all_units = db.get_units()

        # Should have units with valid conversion values
        assert len(all_units) > 0

        # Check that ounce has a conversion
        ounce = next((u for u in all_units if u["name"] == "ounce"), None)
        assert ounce is not None
        assert ounce["conversion_to_ml"] is not None
        assert ounce["conversion_to_ml"] > 0
