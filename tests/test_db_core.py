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

    def test_database_initialization_success(self, db_instance, memory_db_with_schema):
        """Test successful database initialization"""
        assert db_instance.db_path == memory_db_with_schema

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

    def test_connection_retry_mechanism(self, memory_db_with_schema, monkeypatch):
        """Test connection retry mechanism with temporary failures"""
        monkeypatch.setenv("DB_PATH", memory_db_with_schema)

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

    def test_connection_max_retries_exceeded(self, memory_db_with_schema, monkeypatch):
        """Test behavior when max retries are exceeded"""
        monkeypatch.setenv("DB_PATH", memory_db_with_schema)

        with patch.object(Database, "_get_connection") as mock_conn:
            mock_conn.side_effect = sqlite3.OperationalError("database is locked")

            with patch("time.sleep"):  # Speed up test
                with pytest.raises(sqlite3.OperationalError):
                    Database()


class TestDatabaseConnectionManagement:
    """Test database connection configuration and settings"""

    def test_get_connection_settings(self, db_instance):
        """Test that connection has proper SQLite settings"""
        conn = db_instance._get_connection()

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

    def test_execute_query_select(self, db_instance):
        """Test executing SELECT queries"""
        # Insert test data
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Test Ingredient", "Test Description"),
        )

        # Test SELECT query
        result = db_instance.execute_query(
            "SELECT * FROM ingredients WHERE name = ?", ("Test Ingredient",)
        )
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["name"] == "Test Ingredient"

    def test_execute_query_insert(self, db_instance):
        """Test executing INSERT queries"""
        result = db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Test Ingredient Insert", "Test Description"),
        )
        assert isinstance(result, dict)
        assert "rowCount" in result
        assert result["rowCount"] == 1

    def test_execute_query_update(self, db_instance):
        """Test executing UPDATE queries"""
        # Insert test data
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Test Ingredient Update", "Test Description"),
        )

        # Update data
        result = db_instance.execute_query(
            "UPDATE ingredients SET description = ? WHERE name = ?",
            ("Updated Description", "Test Ingredient Update"),
        )
        assert result["rowCount"] == 1

    def test_execute_query_delete(self, db_instance):
        """Test executing DELETE queries"""
        # Insert test data
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Test Ingredient Delete", "Test Description"),
        )

        # Delete data
        result = db_instance.execute_query(
            "DELETE FROM ingredients WHERE name = ?", ("Test Ingredient Delete",)
        )
        assert result["rowCount"] == 1

    def test_execute_query_with_named_parameters(self, db_instance):
        """Test executing queries with named parameters"""
        result = db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (:name, :description)",
            {"name": "Test Ingredient Named", "description": "Test Description"},
        )
        assert result["rowCount"] == 1

    def test_execute_query_error_handling(self, db_instance):
        """Test error handling in query execution"""
        # Test SQL syntax error
        with pytest.raises(sqlite3.Error):
            db_instance.execute_query("INVALID SQL STATEMENT")

    def test_execute_query_with_rollback(self, db_instance):
        """Test that transactions are rolled back on error"""
        # Insert valid data first
        db_instance.execute_query(
            "INSERT INTO ingredients (name, description) VALUES (?, ?)",
            ("Valid Ingredient", "Valid Description"),
        )

        # Attempt invalid operation that should trigger rollback
        with pytest.raises(sqlite3.Error):
            with patch.object(db_instance, "_get_connection") as mock_conn:
                mock_connection = MagicMock()
                mock_cursor = MagicMock()
                mock_connection.cursor.return_value = mock_cursor
                mock_cursor.execute.side_effect = sqlite3.Error("Test error")
                mock_conn.return_value = mock_connection

                db_instance.execute_query("SELECT * FROM ingredients")

        # Verify rollback was called
        mock_connection.rollback.assert_called_once()
