"""
Core Database Class Testing
Tests for the main Database class including connection management, transactions, and retry logic
"""

import os
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from api.db.db_core import Database, retry_on_db_locked


class TestDatabaseConnection:
    """Test database connection and initialization"""

    def test_database_initialization_success(self, memory_db_with_schema):
        """Test successful database initialization"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            assert db.db_path == memory_db_with_schema

    def test_database_initialization_with_missing_file(self):
        """Test database initialization with missing database file"""
        missing_path = "/tmp/nonexistent_test.db"
        with patch.dict(os.environ, {"DB_PATH": missing_path}):
            # Should not raise exception during init, but during connection test
            with pytest.raises(Exception):
                Database()

    def test_database_path_from_environment(self):
        """Test that database path is read from environment variable"""
        test_path = "/test/path/db.sqlite"
        with patch.dict(os.environ, {"DB_PATH": test_path}):
            with patch.object(Database, "_test_connection"):
                db = Database()
                assert db.db_path == test_path

    def test_database_path_default(self):
        """Test default database path when environment variable not set"""
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(Database, "_test_connection"):
                db = Database()
                assert db.db_path == "/mnt/efs/cocktaildb.db"

    def test_connection_retry_mechanism(self, memory_db_with_schema):
        """Test connection retry mechanism with temporary failures"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            # Mock _get_connection to fail twice then succeed
            with patch.object(Database, "_get_connection") as mock_conn:
                mock_conn.side_effect = [
                    sqlite3.OperationalError("database is locked"),
                    sqlite3.OperationalError("database is locked"),
                    MagicMock(),  # Success on third try
                ]

                with patch("time.sleep"):  # Speed up test
                    db = Database()
                    # Should succeed after retries
                    assert mock_conn.call_count == 3

    def test_connection_max_retries_exceeded(self, memory_db_with_schema):
        """Test behavior when max retries are exceeded"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            with patch.object(Database, "_get_connection") as mock_conn:
                mock_conn.side_effect = sqlite3.OperationalError("database is locked")

                with patch("time.sleep"):  # Speed up test
                    with pytest.raises(sqlite3.OperationalError):
                        Database()


class TestDatabaseConnectionManagement:
    """Test database connection configuration and settings"""

    def test_get_connection_settings(self, memory_db_with_schema):
        """Test that connection has proper SQLite settings"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            conn = db._get_connection()

            # Verify row factory is set
            assert conn.row_factory == sqlite3.Row

            # Verify timeout and journal mode
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode")
            journal_mode = cursor.fetchone()[0]
            assert journal_mode == "delete"

            conn.close()


class TestRetryDecorator:
    """Test the retry_on_db_locked decorator"""

    def test_retry_decorator_success_first_try(self):
        """Test decorator when function succeeds on first try"""

        @retry_on_db_locked(max_retries=3)
        def test_function():
            return "success"

        result = test_function()
        assert result == "success"

    def test_retry_decorator_success_after_retries(self):
        """Test decorator when function succeeds after retries"""
        call_count = 0

        @retry_on_db_locked(max_retries=3, initial_backoff=0.01)
        def test_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise sqlite3.OperationalError("database is locked")
            return "success"

        with patch("time.sleep"):  # Speed up test
            result = test_function()
            assert result == "success"
            assert call_count == 3

    def test_retry_decorator_max_retries_exceeded(self):
        """Test decorator when max retries are exceeded"""

        @retry_on_db_locked(max_retries=2, initial_backoff=0.01)
        def test_function():
            raise sqlite3.OperationalError("database is locked")

        with patch("time.sleep"):  # Speed up test
            with pytest.raises(sqlite3.OperationalError):
                test_function()

    def test_retry_decorator_non_lock_error(self):
        """Test decorator doesn't retry non-lock errors"""

        @retry_on_db_locked(max_retries=3)
        def test_function():
            raise sqlite3.OperationalError("syntax error")

        with pytest.raises(sqlite3.OperationalError) as exc_info:
            test_function()
        assert "syntax error" in str(exc_info.value)

    def test_retry_decorator_exponential_backoff(self):
        """Test that decorator uses exponential backoff"""
        call_count = 0
        sleep_times = []

        @retry_on_db_locked(max_retries=3, initial_backoff=0.1)
        def test_function():
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                raise sqlite3.OperationalError("database is locked")
            return "success"

        def mock_sleep(duration):
            sleep_times.append(duration)

        with patch("time.sleep", side_effect=mock_sleep):
            with pytest.raises(sqlite3.OperationalError):
                test_function()

        # Verify exponential backoff: 0.1, 0.2, 0.4
        assert len(sleep_times) == 3
        assert sleep_times[0] == 0.1
        assert sleep_times[1] == 0.2
        assert sleep_times[2] == 0.4


class TestDatabaseQueryExecution:
    """Test database query execution methods"""

    def test_execute_query_select(self, memory_db_with_schema):
        """Test executing SELECT queries"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Insert test data
            db.execute_query(
                "INSERT INTO ingredients (name, description) VALUES (?, ?)",
                ("Test Ingredient", "Test Description"),
            )

            # Test SELECT query
            result = db.execute_query(
                "SELECT * FROM ingredients WHERE name = ?", ("Test Ingredient",)
            )
            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]["name"] == "Test Ingredient"

    def test_execute_query_insert(self, memory_db_with_schema):
        """Test executing INSERT queries"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            result = db.execute_query(
                "INSERT INTO ingredients (name, description) VALUES (?, ?)",
                ("Test Ingredient", "Test Description"),
            )
            assert isinstance(result, dict)
            assert "rowCount" in result
            assert result["rowCount"] == 1

    def test_execute_query_update(self, memory_db_with_schema):
        """Test executing UPDATE queries"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Insert test data
            db.execute_query(
                "INSERT INTO ingredients (name, description) VALUES (?, ?)",
                ("Test Ingredient", "Test Description"),
            )

            # Update data
            result = db.execute_query(
                "UPDATE ingredients SET description = ? WHERE name = ?",
                ("Updated Description", "Test Ingredient"),
            )
            assert result["rowCount"] == 1

    def test_execute_query_delete(self, memory_db_with_schema):
        """Test executing DELETE queries"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Insert test data
            db.execute_query(
                "INSERT INTO ingredients (name, description) VALUES (?, ?)",
                ("Test Ingredient", "Test Description"),
            )

            # Delete data
            result = db.execute_query(
                "DELETE FROM ingredients WHERE name = ?", ("Test Ingredient",)
            )
            assert result["rowCount"] == 1

    def test_execute_query_with_named_parameters(self, memory_db_with_schema):
        """Test executing queries with named parameters"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            result = db.execute_query(
                "INSERT INTO ingredients (name, description) VALUES (:name, :description)",
                {"name": "Test Ingredient", "description": "Test Description"},
            )
            assert result["rowCount"] == 1

    def test_execute_query_error_handling(self, memory_db_with_schema):
        """Test error handling in query execution"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Test SQL syntax error
            with pytest.raises(sqlite3.Error):
                db.execute_query("INVALID SQL STATEMENT")

    def test_execute_query_with_rollback(self, memory_db_with_schema):
        """Test that transactions are rolled back on error"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Insert valid data first
            db.execute_query(
                "INSERT INTO ingredients (name, description) VALUES (?, ?)",
                ("Valid Ingredient", "Valid Description"),
            )

            # Attempt invalid operation that should trigger rollback
            with pytest.raises(sqlite3.Error):
                with patch.object(db, "_get_connection") as mock_conn:
                    mock_connection = MagicMock()
                    mock_cursor = MagicMock()
                    mock_connection.cursor.return_value = mock_cursor
                    mock_cursor.execute.side_effect = sqlite3.Error("Test error")
                    mock_conn.return_value = mock_connection

                    db.execute_query("SELECT * FROM ingredients")

            # Verify rollback was called
            mock_connection.rollback.assert_called_once()


class TestSmartTitleCase:
    """Test the smart_title_case utility function"""

    def test_smart_title_case_basic(self):
        """Test basic title casing"""
        from api.db.db_core import smart_title_case

        assert smart_title_case("hello world") == "Hello World"
        assert smart_title_case("gin") == "Gin"
        assert smart_title_case("london dry gin") == "London Dry Gin"

    def test_smart_title_case_apostrophes(self):
        """Test title casing with apostrophes"""
        from api.db.db_core import smart_title_case

        # Single apostrophe cases
        assert smart_title_case("st-germain's") == "St-Germain's"
        assert smart_title_case("ST-GERMAIN'S") == "St-Germain's"
        assert smart_title_case("o'reilly") == "O'reilly"
        assert smart_title_case("don't") == "Don't"
        assert smart_title_case("won't") == "Won't"
        assert smart_title_case("can't") == "Can't"

    def test_smart_title_case_complex_apostrophes(self):
        """Test title casing with complex apostrophe cases"""
        from api.db.db_core import smart_title_case

        # The original failing test case
        special_name = 'St-Germain\'s "Premium" Elderflower & Herbs (100%)'
        result = smart_title_case(special_name.lower())
        assert result == 'St-Germain\'s "Premium" Elderflower & Herbs (100%)'

        # Multiple apostrophes
        assert smart_title_case("o'reilly's bar") == "O'reilly's Bar"

    def test_smart_title_case_special_characters(self):
        """Test title casing with special characters"""
        from api.db.db_core import smart_title_case

        assert smart_title_case("jack & jill") == "Jack & Jill"
        assert smart_title_case("salt-n-pepper") == "Salt-N-Pepper"
        assert smart_title_case("café (french)") == "Café (French)"
        assert smart_title_case("100% proof") == "100% Proof"
        assert smart_title_case("whiskey #1") == "Whiskey #1"

    def test_smart_title_case_unicode(self):
        """Test title casing with unicode characters"""
        from api.db.db_core import smart_title_case

        assert smart_title_case("café liqueur") == "Café Liqueur"
        assert smart_title_case("mezcal añejo") == "Mezcal Añejo"
        assert smart_title_case("cocktail 🍸") == "Cocktail 🍸"

    def test_smart_title_case_edge_cases(self):
        """Test title casing edge cases"""
        from api.db.db_core import smart_title_case

        # Empty and None cases
        assert smart_title_case("") is None
        assert smart_title_case(None) is None

        # Single character
        assert smart_title_case("a") == "A"
        assert smart_title_case("'") == "'"

        # Already properly cased
        assert smart_title_case("London Dry Gin") == "London Dry Gin"

        # All caps
        assert smart_title_case("VODKA") == "Vodka"

        # Mixed case with apostrophe
        assert smart_title_case("mCdOnAlD's") == "Mcdonald's"

    def test_smart_title_case_whitespace(self):
        """Test title casing with various whitespace"""
        from api.db.db_core import smart_title_case

        assert smart_title_case("  hello world  ") == "  Hello World  "
        assert smart_title_case("hello\tworld") == "Hello\tWorld"
        assert smart_title_case("hello\nworld") == "Hello\nWorld"
        assert smart_title_case("hello  world") == "Hello  World"

    def test_smart_title_case_numbers_and_punctuation(self):
        """Test title casing with numbers and punctuation"""
        from api.db.db_core import smart_title_case

        assert smart_title_case("recipe #1: gin & tonic") == "Recipe #1: Gin & Tonic"
        assert smart_title_case("50/50 split") == "50/50 Split"
        assert smart_title_case("brand-new recipe") == "Brand-New Recipe"
        assert smart_title_case("old-fashioned cocktail") == "Old-Fashioned Cocktail"
