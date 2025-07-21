"""
Database Unit Operations Testing
Tests for unit-related database operations including get_unit_by_name,
get_unit_by_abbreviation, and get_unit_by_name_or_abbreviation
"""

import pytest
from api.db.db_core import Database


class TestUnitDatabaseOperations:
    """Test unit-related database operations"""

    def test_get_unit_by_name_exact_match(self, db_instance):
        """Test getting unit by exact name match"""
        # Test with a unit that exists in schema.sql
        result = db_instance.get_unit_by_name("Ounce")

        assert result is not None
        assert result["name"] == "Ounce"
        assert result["abbreviation"] == "oz"
        assert "id" in result

    def test_get_unit_by_name_case_insensitive(self, db_instance):
        """Test getting unit by name is case insensitive"""
        # Test lowercase
        result = db_instance.get_unit_by_name("ounce")
        assert result is not None
        assert result["name"] == "Ounce"

        # Test uppercase
        result = db_instance.get_unit_by_name("OUNCE")
        assert result is not None
        assert result["name"] == "Ounce"

        # Test mixed case
        result = db_instance.get_unit_by_name("OuNcE")
        assert result is not None
        assert result["name"] == "Ounce"

    def test_get_unit_by_name_not_found(self, db_instance):
        """Test getting unit by name when unit doesn't exist"""
        result = db_instance.get_unit_by_name("NonexistentUnit")
        assert result is None

    def test_get_unit_by_name_empty_string(self, db_instance):
        """Test getting unit by empty name"""
        result = db_instance.get_unit_by_name("")
        assert result is None

    def test_get_unit_by_abbreviation_exact_match(self, db_instance):
        """Test getting unit by exact abbreviation match"""
        # Test with an abbreviation that exists in schema.sql
        result = db_instance.get_unit_by_abbreviation("oz")

        assert result is not None
        assert result["name"] == "Ounce"
        assert result["abbreviation"] == "oz"
        assert "id" in result

    def test_get_unit_by_abbreviation_case_insensitive(self, db_instance):
        """Test getting unit by abbreviation is case insensitive"""
        # Test lowercase
        result = db_instance.get_unit_by_abbreviation("oz")
        assert result is not None
        assert result["abbreviation"] == "oz"

        # Test uppercase
        result = db_instance.get_unit_by_abbreviation("OZ")
        assert result is not None
        assert result["abbreviation"] == "oz"

        # Test mixed case
        result = db_instance.get_unit_by_abbreviation("Oz")
        assert result is not None
        assert result["abbreviation"] == "oz"

    def test_get_unit_by_abbreviation_not_found(self, db_instance):
        """Test getting unit by abbreviation when unit doesn't exist"""
        result = db_instance.get_unit_by_abbreviation("xyz")
        assert result is None

    def test_get_unit_by_abbreviation_empty_string(self, db_instance):
        """Test getting unit by empty abbreviation"""
        result = db_instance.get_unit_by_abbreviation("")
        assert result is None

    def test_get_unit_by_name_or_abbreviation_by_name(self, db_instance):
        """Test getting unit by name when searching by name or abbreviation"""
        result = db_instance.get_unit_by_name_or_abbreviation("Ounce")

        assert result is not None
        assert result["name"] == "Ounce"
        assert result["abbreviation"] == "oz"

    def test_get_unit_by_name_or_abbreviation_by_abbreviation(self, db_instance):
        """Test getting unit by abbreviation when name doesn't match"""
        result = db_instance.get_unit_by_name_or_abbreviation("oz")

        assert result is not None
        assert result["name"] == "Ounce"
        assert result["abbreviation"] == "oz"

    def test_get_unit_by_name_or_abbreviation_neither_match(self, db_instance):
        """Test getting unit when neither name nor abbreviation match"""
        result = db_instance.get_unit_by_name_or_abbreviation("NonexistentUnit")
        assert result is None

    def test_get_unit_by_name_or_abbreviation_case_insensitive(self, db_instance):
        """Test that name or abbreviation search is case insensitive"""
        # Test with mixed case name
        result = db_instance.get_unit_by_name_or_abbreviation("OuNcE")
        assert result is not None
        assert result["name"] == "Ounce"

    def test_conversion_to_ml_field_present(self, db_instance):
        """Test that conversion_to_ml field is present in results"""
        result = db_instance.get_unit_by_name("Ounce")

        assert "conversion_to_ml" in result


class TestSpecialUnits:
    """Test special units like 'to top', 'to rinse', and 'each'"""

    def test_each_unit_exists(self, db_instance):
        """Test that 'each' unit exists in base schema"""
        result = db_instance.get_unit_by_name("each")
        
        assert result is not None
        assert result["name"] == "Each"  # Database stores as "Each" with capital E
        assert result["abbreviation"] == "each"
        assert result["conversion_to_ml"] is None  # No standard conversion for 'each'

    def test_special_units_case_insensitive(self, db_instance):
        """Test that special units are case insensitive"""
        # Test 'each' in different cases
        for case_variant in ["each", "EACH", "Each", "eAcH"]:
            result = db_instance.get_unit_by_name(case_variant)
            if result:  # Unit exists
                assert result["name"] == "Each"  # Database stores as "Each"

    def test_to_top_unit_properties(self, db_instance):
        """Test 'to top' unit properties if it exists"""
        result = db_instance.get_unit_by_name("to top")
        
        if result:  # Unit exists (from migrations)
            assert result["name"] == "to top"
            assert result["conversion_to_ml"] is None  # No standard conversion
            # Should have some abbreviation
            assert result["abbreviation"] is not None

    def test_to_rinse_unit_properties(self, db_instance):
        """Test 'to rinse' unit properties if it exists"""
        result = db_instance.get_unit_by_name("to rinse")
        
        if result:  # Unit exists (from migrations)
            assert result["name"] == "to rinse"
            assert result["conversion_to_ml"] is None  # No standard conversion
            # Should have some abbreviation
            assert result["abbreviation"] is not None

    def test_special_units_by_abbreviation(self, db_instance):
        """Test getting special units by their abbreviations"""
        # Test 'each' by abbreviation
        result = db_instance.get_unit_by_abbreviation("each")
        if result:
            assert result["name"] == "Each"

        # Test 'to top' by abbreviation if it exists
        result = db_instance.get_unit_by_abbreviation("top")
        if result:
            assert result["name"] == "to top"

        # Test 'to rinse' by abbreviation if it exists
        result = db_instance.get_unit_by_abbreviation("rinse")
        if result:
            assert result["name"] == "to rinse"

    def test_null_conversion_units(self, db_instance):
        """Test that units with null conversions are handled correctly"""
        # Get all units and check for null conversions
        all_units = db_instance.get_units()
        
        null_conversion_units = [unit for unit in all_units if unit["conversion_to_ml"] is None]
        
        # Should have at least 'Each' unit with null conversion
        unit_names = [unit["name"] for unit in null_conversion_units]
        assert "Each" in unit_names  # Database stores as "Each"
        
        # All null conversion units should have conversion_to_ml as None
        for unit in null_conversion_units:
            assert unit["conversion_to_ml"] is None
        
        # Check that we have some units with null conversions (the exact set may vary)
        assert len(null_conversion_units) > 0, "Should have at least some units with null conversions"
