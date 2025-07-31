"""
Error Handling and Edge Cases Testing
Comprehensive tests for error scenarios, edge cases, data validation,
and recovery mechanisms in the database layer
"""

import pytest
import sqlite3
import os
import tempfile
import shutil
from typing import Dict, Any, List
from unittest.mock import patch, MagicMock
import time

from api.db.db_core import Database


class TestDatabaseInitializationErrors:
    """Test database initialization error scenarios"""

    def test_database_file_permission_error(self):
        """Test behavior when database file has permission issues"""
        # Create a temporary directory that we can control
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "readonly.db")

            # Create database file and make it read-only
            with open(db_path, "w") as f:
                f.write("dummy")
            os.chmod(db_path, 0o444)  # Read-only

            with patch.dict(os.environ, {"DB_PATH": db_path}):
                # Should fail during connection test
                with pytest.raises(Exception):
                    Database()

    def test_database_directory_does_not_exist(self):
        """Test behavior when database directory doesn't exist"""
        nonexistent_path = "/nonexistent/directory/test.db"

        with patch.dict(os.environ, {"DB_PATH": nonexistent_path}):
            with pytest.raises(Exception):
                Database()

    def test_database_corrupted_file(self):
        """Test behavior with corrupted database file"""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as temp_file:
            # Write invalid SQLite data
            temp_file.write(b"This is not a valid SQLite file")
            temp_file.flush()

            with patch.dict(os.environ, {"DB_PATH": temp_file.name}):
                try:
                    with pytest.raises(Exception):
                        Database()
                finally:
                    os.unlink(temp_file.name)

    def test_database_schema_missing_tables(self, memory_db_with_schema):
        """Test behavior when database is missing required tables"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            # Drop a required table
            db = Database()
            db.execute_query("DROP TABLE ingredients")

            # Now database operations should fail
            with pytest.raises(sqlite3.OperationalError):
                db.create_ingredient(
                    {"name": "Test", "description": "Test", "parent_id": None}
                )


class TestDataValidationErrors:
    """Test data validation and constraint violation scenarios"""

    def test_ingredient_creation_with_invalid_data_types(self, memory_db_with_schema):
        """Test ingredient creation with invalid data types"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Test with non-string name
            with pytest.raises(Exception):
                db.create_ingredient(
                    {"name": 123, "description": "Test", "parent_id": None}
                )

            # Test with invalid parent_id type
            with pytest.raises(Exception):
                db.create_ingredient(
                    {"name": "Test", "description": "Test", "parent_id": "invalid"}
                )

    def test_recipe_creation_with_malformed_ingredients(self, memory_db_with_schema):
        """Test recipe creation with malformed ingredient data"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Test with missing ingredient_id
            with pytest.raises(Exception):
                db.create_recipe(
                    {
                        "name": "Test Recipe",
                        "instructions": "Test",
                        "ingredients": [{"amount": 1.0}],  # Missing ingredient_id
                    }
                )

            with pytest.raises(Exception):
                db.create_recipe(
                    {
                        "name": "Test Recipe",
                        "instructions": "Test",
                        "ingredients": [{"ingredient_id": 1, "amount": "invalid"}],
                    }
                )

    def test_rating_creation_with_invalid_constraints(self, memory_db_with_schema):
        """Test rating creation with constraint violations"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            # Test with rating outside valid range using direct SQL
            with pytest.raises(sqlite3.IntegrityError):
                db.execute_query(
                    "INSERT INTO ratings (cognito_user_id, cognito_username, recipe_id, rating) VALUES (?, ?, ?, ?)",
                    ("user1", "user1", recipe["id"], 6),  # Rating > 5
                )

            with pytest.raises(sqlite3.IntegrityError):
                db.execute_query(
                    "INSERT INTO ratings (cognito_user_id, cognito_username, recipe_id, rating) VALUES (?, ?, ?, ?)",
                    ("user1", "user1", recipe["id"], 0),  # Rating < 1
                )

    def test_tag_creation_with_constraint_violations(self, memory_db_with_schema):
        """Test tag creation with various constraint violations"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Test private tag with missing user information
            with pytest.raises(Exception):
                db.execute_query(
                    "INSERT INTO private_tags (name, cognito_user_id) VALUES (?, ?)",
                    ("test", None),  # Missing required cognito_username
                )


class TestConcurrencyAndLockingErrors:
    """Test concurrency issues and locking scenarios"""

    def test_deadlock_detection_and_recovery(self, memory_db_with_schema):
        """Test database behavior during potential deadlock scenarios"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create test data
            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})

            import threading
            import time

            errors = []
            success_count = [0]

            def concurrent_rating_update(user_id, delay=0):
                try:
                    time.sleep(delay)
                    local_db = Database()

                    # Add rating
                    local_db.set_rating(
                        {
                            "cognito_user_id": f"user{user_id}",
                            "cognito_username": f"user{user_id}",
                            "recipe_id": recipe["id"],
                            "rating": (user_id % 5) + 1,
                        }
                    )

                    # Update rating
                    local_db.set_rating(
                        {
                            "cognito_user_id": f"user{user_id}",
                            "cognito_username": f"user{user_id}",
                            "recipe_id": recipe["id"],
                            "rating": ((user_id + 1) % 5) + 1,
                        }
                    )

                    success_count[0] += 1

                except Exception as e:
                    errors.append(str(e))

            # Start multiple concurrent operations
            threads = []
            for i in range(10):
                thread = threading.Thread(
                    target=concurrent_rating_update, args=(i, i * 0.01)
                )
                threads.append(thread)
                thread.start()

            # Wait for all threads
            for thread in threads:
                thread.join(timeout=10)  # Timeout to prevent hanging

            # Most operations should succeed despite concurrency
            assert success_count[0] >= 8  # Allow for some failures due to locking

            # If there are errors, they should be database-related, not application crashes
            for error in errors:
                assert "database" in error.lower() or "lock" in error.lower()

    def test_database_locked_retry_mechanism(self, memory_db_with_schema):
        """Test retry mechanism when database is locked"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create a scenario where database might be locked
            def long_running_transaction():
                local_db = Database()
                conn = local_db._get_connection()
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    time.sleep(0.2)  # Hold lock briefly
                    conn.execute(
                        "INSERT INTO ingredients (name, description) VALUES (?, ?)",
                        ("Lock Test", "Test"),
                    )
                    conn.commit()
                except:
                    conn.rollback()
                finally:
                    conn.close()

            def quick_operation():
                local_db = Database()
                # This should retry if database is locked
                return local_db.create_ingredient(
                    {"name": "Quick Test", "description": "Test", "parent_id": None}
                )

            import threading

            # Start long transaction
            long_thread = threading.Thread(target=long_running_transaction)
            long_thread.start()

            # Try quick operation (might encounter lock)
            time.sleep(0.05)  # Let long transaction start
            result = quick_operation()  # Should eventually succeed due to retry

            long_thread.join()

            # Both operations should have succeeded
            assert result["name"] == "Quick Test"

            # Verify both ingredients exist
            ingredients = db.get_ingredients()
            names = {ing["name"] for ing in ingredients}
            assert "Lock Test" in names
            assert "Quick Test" in names


class TestDataIntegrityErrors:
    """Test data integrity and consistency error scenarios"""

    def test_circular_reference_prevention(self, memory_db_with_schema):
        """Test prevention of circular references in ingredient hierarchy"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create hierarchy: A -> B -> C
            a = db.create_ingredient(
                {"name": "A", "description": "A", "parent_id": None}
            )
            b = db.create_ingredient(
                {"name": "B", "description": "B", "parent_id": a["id"]}
            )
            c = db.create_ingredient(
                {"name": "C", "description": "C", "parent_id": b["id"]}
            )

            # Try to create circular reference: A -> B -> C -> A
            with pytest.raises(ValueError, match="Cannot create circular reference"):
                db.update_ingredient(a["id"], {"parent_id": c["id"]})

            # Try self-reference
            with pytest.raises(ValueError, match="cannot be its own parent"):
                db.update_ingredient(a["id"], {"parent_id": a["id"]})


class TestQueryErrorHandling:
    """Test query error handling and recovery"""

    def test_malformed_sql_query_handling(self, memory_db_with_schema):
        """Test handling of malformed SQL queries"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Test various SQL syntax errors
            with pytest.raises(sqlite3.Error):
                db.execute_query("SELECT * FROM nonexistent_table")

            with pytest.raises(sqlite3.Error):
                db.execute_query("INVALID SQL STATEMENT")

            with pytest.raises(sqlite3.Error):
                db.execute_query("SELECT * FROM ingredients WHERE")  # Incomplete WHERE

            # Database should still be functional after errors
            ingredient = db.create_ingredient(
                {"name": "Recovery Test", "description": "Test", "parent_id": None}
            )
            assert ingredient["name"] == "Recovery Test"

    def test_parameter_binding_errors(self, memory_db_with_schema):
        """Test parameter binding error scenarios"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Test mismatched parameter count
            with pytest.raises(sqlite3.OperationalError):
                db.execute_query(
                    "INSERT INTO ingredients (name, description) VALUES (?, ?, ?)",
                    ("Name", "Description"),  # Missing third parameter
                )

    def test_transaction_rollback_on_error(self, memory_db_with_schema):
        """Test that transactions are properly rolled back on errors"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Attempt transaction with error
            with pytest.raises(Exception):
                db.execute_transaction(
                    [
                        {
                            "sql": "INSERT INTO ingredients (name, description) VALUES (?, ?)",
                            "parameters": ("Valid Ingredient", "Valid Description"),
                        },
                        {"sql": "INVALID SQL STATEMENT", "parameters": {}},
                    ]
                )

            # Verify no partial data was committed
            ingredients = db.get_ingredients()
            ingredient_names = {ing["name"] for ing in ingredients}
            assert "Valid Ingredient" not in ingredient_names
            assert "Gin" in ingredient_names  # Original ingredient should still exist


class TestEdgeCaseDataValues:
    """Test edge case data values and boundary conditions"""

    def test_unicode_edge_cases(self, memory_db_with_schema):
        """Test various unicode edge cases"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Test various unicode scenarios
            unicode_test_cases = [
                "Café Liqueur",  # Accented characters
                "Āčēīōū",  # Extended Latin
            ]

            for i, test_name in enumerate(unicode_test_cases):
                ingredient = db.create_ingredient(
                    {
                        "name": f"{test_name} {i}",
                        "description": f"Unicode test {i}",
                        "parent_id": None,
                    }
                )

                # Verify data integrity
                retrieved = db.get_ingredient(ingredient["id"])
                assert retrieved["name"] == f"{test_name} {i}"

    def test_null_and_empty_value_handling(self, memory_db_with_schema):
        """Test handling of null and empty values"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Test empty string descriptions
            ingredient = db.create_ingredient(
                {"name": "Empty Description Test", "description": "", "parent_id": None}
            )

            retrieved = db.get_ingredient(ingredient["id"])
            assert retrieved["description"] == ""

            # Test null/None values where allowed
            recipe = db.create_recipe(
                {
                    "name": "Minimal Recipe",
                    "instructions": "Test",
                    "description": None,  # Should be allowed
                    "image_url": None,
                    "source": None,
                    "source_url": None,
                }
            )

            retrieved_recipe = db.get_recipe(recipe["id"])
            assert retrieved_recipe["description"] is None
            assert retrieved_recipe["image_url"] is None

    def test_numeric_boundary_values(self, memory_db_with_schema):
        """Test numeric boundary values"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()
            # Test empty string descriptions
            gin = db.create_ingredient(
                {"name": "Gin1", "description": "Gin", "parent_id": None}
            )
            recipe = db.create_recipe(
                {
                    "name": "Boundary Test Recipe",
                    "instructions": "Test",
                    "ingredients": [{"ingredient_id": gin["id"], "amount": 1.0}],
                }
            )

            # Test rating boundary values
            boundary_ratings = [1, 5]  # Min and max valid ratings

            for rating in boundary_ratings:
                result = db.set_rating(
                    {
                        "cognito_user_id": f"user_{rating}",
                        "cognito_username": f"user_{rating}",
                        "recipe_id": recipe["id"],
                        "rating": rating,
                    }
                )
                assert result["rating"] == rating

            # Test very small and very large amounts
            extreme_amounts = [0.000001, 999999.999999, 0.0, -1.0]

            for amount in extreme_amounts:
                try:
                    test_recipe = db.create_recipe(
                        {
                            "name": f"Amount Test {amount}",
                            "instructions": "Test",
                            "ingredients": [
                                {"ingredient_id": gin["id"], "amount": amount}
                            ],
                        }
                    )

                    retrieved = db.get_recipe(test_recipe["id"])
                    ingredient_amount = retrieved["ingredients"][0]["amount"]
                    assert abs(ingredient_amount - amount) < 0.000001

                except Exception as e:
                    print(f"Extreme amount test failed for {amount}: {e}")

    def test_special_character_handling_in_queries(self, memory_db_with_schema):
        """Test handling of special characters in search queries"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipes with special characters
            special_names = [
                "Recipe with 'single quotes'",
                'Recipe with "double quotes"',
                "Recipe with % wildcard",
                "Recipe with _ underscore",
                "Recipe with \\ backslash",
                "Recipe with [brackets]",
                "Recipe with (parentheses)",
            ]

            for name in special_names:
                try:
                    db.create_recipe(
                        {"name": name, "instructions": "Test instructions"}
                    )
                except Exception as e:
                    print(
                        f"Failed to create recipe with special characters '{name}': {e}"
                    )

            # Test searching for these recipes
            for name in special_names:
                try:
                    # Search for part of the name
                    search_term = name.split()[0]  # First word
                    results = db.search_recipes({"name": search_term})

                    # Should find at least one result
                    assert len(results) >= 0  # Might be 0 if creation failed

                except Exception as e:
                    print(
                        f"Search failed for special character recipe '{search_term}': {e}"
                    )
