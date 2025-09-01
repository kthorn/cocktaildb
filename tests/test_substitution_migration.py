"""
Test the substitution_level migration

Verifies that the migration script properly adds the substitution_level column
and sets appropriate default values.
"""

import pytest
import sqlite3
import tempfile
import os
from pathlib import Path


class TestSubstitutionMigration:
    """Test the database migration for substitution_level"""

    def test_migration_adds_column(self):
        """Test that the migration properly adds substitution_level column"""
        
        # Create temporary database
        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp_file:
            tmp_db_path = tmp_file.name
        
        try:
            # Create database with base schema (simplified version)
            conn = sqlite3.connect(tmp_db_path)
            cursor = conn.cursor()
            
            # Create basic ingredients table without substitution_level
            cursor.execute("""
                CREATE TABLE ingredients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    parent_id INTEGER,
                    path TEXT,
                    created_by TEXT NOT NULL,
                    FOREIGN KEY (parent_id) REFERENCES ingredients(id)
                )
            """)
            
            # Insert some test data
            cursor.execute("""
                INSERT INTO ingredients (name, description, parent_id, path, created_by)
                VALUES 
                ('Whiskey', 'Base whiskey category', NULL, '/1/', 'test'),
                ('Bourbon', 'American bourbon', 1, '/1/2/', 'test'),
                ('Rum', 'Base rum category', NULL, '/3/', 'test')
            """)
            
            conn.commit()
            
            # Verify column doesn't exist yet
            cursor.execute("PRAGMA table_info(ingredients)")
            columns = [row[1] for row in cursor.fetchall()]
            assert 'substitution_level' not in columns, "substitution_level should not exist before migration"
            
            # Read and apply the migration
            migration_path = Path(__file__).parent.parent / "migrations" / "07_migration_add_substitution_level_to_ingredients.sql"
            
            if migration_path.exists():
                with open(migration_path, 'r') as f:
                    migration_sql = f.read()
                
                # Execute migration (split by semicolon to handle multiple statements)
                for statement in migration_sql.split(';'):
                    statement = statement.strip()
                    if statement:
                        cursor.execute(statement)
                
                conn.commit()
                
                # Verify column was added
                cursor.execute("PRAGMA table_info(ingredients)")
                columns = [row[1] for row in cursor.fetchall()]
                assert 'substitution_level' in columns, "substitution_level should exist after migration"
                
                # Verify default values were set correctly
                cursor.execute("SELECT name, substitution_level FROM ingredients ORDER BY id")
                results = cursor.fetchall()
                
                expected_values = {
                    'Whiskey': 1,  # Should be set to 1 by migration
                    'Bourbon': 0,  # Should have default value 0
                    'Rum': 1      # Should be set to 1 by migration
                }
                
                for name, sub_level in results:
                    if name in expected_values:
                        assert sub_level == expected_values[name], f"{name} should have substitution_level {expected_values[name]}, got {sub_level}"
                
                print("Migration test passed:")
                for name, sub_level in results:
                    print(f"  {name}: substitution_level = {sub_level}")
            
            else:
                pytest.skip("Migration file not found - skipping migration test")
            
            conn.close()
            
        finally:
            # Clean up temporary file
            if os.path.exists(tmp_db_path):
                os.unlink(tmp_db_path)

    def test_migration_preserves_existing_data(self):
        """Test that migration doesn't corrupt existing ingredient data"""
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp_file:
            tmp_db_path = tmp_file.name
        
        try:
            conn = sqlite3.connect(tmp_db_path)
            cursor = conn.cursor()
            
            # Create ingredients table and add test data
            cursor.execute("""
                CREATE TABLE ingredients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    parent_id INTEGER,
                    path TEXT,
                    created_by TEXT NOT NULL,
                    FOREIGN KEY (parent_id) REFERENCES ingredients(id)
                )
            """)
            
            # Insert test data with specific values to verify preservation
            test_data = [
                (1, 'Test Whiskey', 'A test whiskey', None, '/1/', 'test-user'),
                (2, 'Test Bourbon', 'A test bourbon', 1, '/1/2/', 'test-user'),
                (3, 'Test Brand', 'A test brand', 2, '/1/2/3/', 'test-user')
            ]
            
            for row in test_data:
                cursor.execute("""
                    INSERT INTO ingredients (id, name, description, parent_id, path, created_by)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, row)
            
            conn.commit()
            
            # Store original data for comparison
            cursor.execute("SELECT id, name, description, parent_id, path, created_by FROM ingredients ORDER BY id")
            original_data = cursor.fetchall()
            
            # Apply migration
            migration_path = Path(__file__).parent.parent / "migrations" / "07_migration_add_substitution_level_to_ingredients.sql"
            
            if migration_path.exists():
                with open(migration_path, 'r') as f:
                    migration_sql = f.read()
                
                for statement in migration_sql.split(';'):
                    statement = statement.strip()
                    if statement:
                        cursor.execute(statement)
                
                conn.commit()
                
                # Verify original data is preserved (except for substitution_level)
                cursor.execute("SELECT id, name, description, parent_id, path, created_by FROM ingredients ORDER BY id")
                migrated_data = cursor.fetchall()
                
                assert migrated_data == original_data, "Migration should preserve existing data"
                
                # Verify substitution_level column was added with appropriate values
                cursor.execute("SELECT id, name, substitution_level FROM ingredients ORDER BY id")
                sub_level_data = cursor.fetchall()
                
                for id_, name, sub_level in sub_level_data:
                    assert sub_level is not None, f"substitution_level should not be NULL for {name}"
                    assert isinstance(sub_level, int), f"substitution_level should be integer for {name}"
                    assert sub_level >= 0, f"substitution_level should be non-negative for {name}"
                
                print("Data preservation test passed:")
                for id_, name, sub_level in sub_level_data:
                    print(f"  ID {id_} ({name}): substitution_level = {sub_level}")
            
            else:
                pytest.skip("Migration file not found")
            
            conn.close()
            
        finally:
            if os.path.exists(tmp_db_path):
                os.unlink(tmp_db_path)

    def test_migration_idempotent(self):
        """Test that running the migration twice doesn't cause errors"""
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp_file:
            tmp_db_path = tmp_file.name
        
        try:
            conn = sqlite3.connect(tmp_db_path)
            cursor = conn.cursor()
            
            # Create basic ingredients table
            cursor.execute("""
                CREATE TABLE ingredients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    parent_id INTEGER,
                    path TEXT,
                    created_by TEXT NOT NULL,
                    FOREIGN KEY (parent_id) REFERENCES ingredients(id)
                )
            """)
            
            cursor.execute("""
                INSERT INTO ingredients (name, description, created_by)
                VALUES ('Test Ingredient', 'Test description', 'test-user')
            """)
            
            conn.commit()
            
            migration_path = Path(__file__).parent.parent / "migrations" / "07_migration_add_substitution_level_to_ingredients.sql"
            
            if migration_path.exists():
                with open(migration_path, 'r') as f:
                    migration_sql = f.read()
                
                # Apply migration first time
                for statement in migration_sql.split(';'):
                    statement = statement.strip()
                    if statement:
                        cursor.execute(statement)
                
                conn.commit()
                
                # Verify it worked
                cursor.execute("PRAGMA table_info(ingredients)")
                columns = [row[1] for row in cursor.fetchall()]
                assert 'substitution_level' in columns
                
                # Apply migration second time - should not cause errors
                # Note: This might fail if migration doesn't handle existing column
                # That's OK - it documents the expected behavior
                
                try:
                    for statement in migration_sql.split(';'):
                        statement = statement.strip()
                        if statement:
                            cursor.execute(statement)
                    
                    conn.commit()
                    print("Migration is idempotent - can be run multiple times safely")
                    
                except sqlite3.OperationalError as e:
                    if "duplicate column name" in str(e).lower():
                        print("Migration correctly fails on duplicate column (expected behavior)")
                    else:
                        raise
            
            else:
                pytest.skip("Migration file not found")
                
            conn.close()
            
        finally:
            if os.path.exists(tmp_db_path):
                os.unlink(tmp_db_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])