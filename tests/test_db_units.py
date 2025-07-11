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
