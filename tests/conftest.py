"""
PyTest configuration and shared fixtures for CocktailDB API tests
Uses PostgreSQL via testcontainers for realistic database testing
"""

import gzip
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

import psycopg2
from psycopg2.extras import RealDictCursor
import pytest
from fastapi.testclient import TestClient
from testcontainers.postgres import PostgresContainer

# Add project root and api directory to Python path for imports
project_root = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "api"))

# Test configuration
POSTGRES_IMAGE = "postgres:15"
TEST_DB_NAME = "cocktaildb_test"
TEST_DB_USER = "test_user"
TEST_DB_PASSWORD = "test_password"

# Path to production backup for integration tests
PROD_BACKUP_PATH = Path("/home/kurtt/cocktaildb/backup-2025-12-25_08-08-15.sql.gz")


def _reset_database_singleton():
    """Reset the database singleton to force new connection"""
    from api.db.db_core import Database
    from api.db import database as db_module

    # Clear the singleton instance
    db_module._DB_INSTANCE = None

    # Clear the connection pool
    if Database._pool is not None:
        try:
            Database._pool.closeall()
        except Exception:
            pass
        Database._pool = None


@pytest.fixture(scope="function", autouse=True)
def clear_database_cache():
    """Clear the global database cache between tests"""
    _reset_database_singleton()
    yield
    _reset_database_singleton()


@pytest.fixture(scope="session")
def postgres_container():
    """Session-scoped PostgreSQL container - shared across all tests"""
    with PostgresContainer(
        image=POSTGRES_IMAGE,
        username=TEST_DB_USER,
        password=TEST_DB_PASSWORD,
        dbname=TEST_DB_NAME,
    ) as container:
        # Wait for container to be ready
        container.get_connection_url()
        yield container


@pytest.fixture(scope="session")
def postgres_connection_params(postgres_container):
    """Get connection parameters for the test PostgreSQL container"""
    return {
        "host": postgres_container.get_container_host_ip(),
        "port": postgres_container.get_exposed_port(5432),
        "dbname": TEST_DB_NAME,
        "user": TEST_DB_USER,
        "password": TEST_DB_PASSWORD,
    }


@pytest.fixture(scope="session")
def schema_sql():
    """Load the PostgreSQL schema SQL"""
    schema_path = Path(__file__).parent.parent / "infrastructure" / "postgres" / "schema.sql"
    if not schema_path.exists():
        pytest.fail(f"Schema file not found at {schema_path}")
    return schema_path.read_text()


@pytest.fixture(scope="function")
def pg_db_with_schema(postgres_container, postgres_connection_params, schema_sql):
    """PostgreSQL database with schema initialized - fresh for each test"""
    conn = psycopg2.connect(**postgres_connection_params)
    conn.autocommit = True
    cursor = conn.cursor()

    # Drop and recreate all tables for a clean state
    cursor.execute("""
        DO $$ DECLARE
            r RECORD;
        BEGIN
            -- Drop extensions first (they own functions that can't be dropped)
            DROP EXTENSION IF EXISTS pg_trgm CASCADE;
            DROP EXTENSION IF EXISTS citext CASCADE;

            -- Drop all tables
            FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
            END LOOP;
            -- Drop all functions
            FOR r IN (SELECT proname, oidvectortypes(proargtypes) as args
                      FROM pg_proc INNER JOIN pg_namespace ns ON (pg_proc.pronamespace = ns.oid)
                      WHERE ns.nspname = 'public' AND proname NOT LIKE 'pg_%') LOOP
                EXECUTE 'DROP FUNCTION IF EXISTS ' || quote_ident(r.proname) || '(' || r.args || ') CASCADE';
            END LOOP;
        END $$;
    """)

    # Apply schema
    cursor.execute(schema_sql)

    # Seed essential test data - units that many tests expect
    cursor.execute("""
        INSERT INTO units (name, abbreviation, conversion_to_ml) VALUES
        ('ounce', 'oz', 29.5735),
        ('milliliter', 'ml', 1.0),
        ('teaspoon', 'tsp', 4.92892),
        ('tablespoon', 'tbsp', 14.7868),
        ('dash', 'dash', 0.9),
        ('drop', 'drop', 0.05),
        ('each', 'ea', NULL),
        ('to top', 'top', NULL)
        ON CONFLICT (name) DO NOTHING
    """)

    cursor.close()
    conn.close()

    yield postgres_connection_params

    # Cleanup is handled by dropping tables in next test


@pytest.fixture(scope="function")
def pg_db_with_data(pg_db_with_schema):
    """PostgreSQL database with schema and test data"""
    conn = psycopg2.connect(**pg_db_with_schema)
    conn.autocommit = True
    cursor = conn.cursor()

    # Populate test data
    _populate_test_data_pg(cursor)

    cursor.close()
    conn.close()

    yield pg_db_with_schema


@pytest.fixture(scope="session")
def pg_db_with_prod_data(postgres_container, postgres_connection_params):
    """PostgreSQL database loaded with production backup - session scoped for efficiency"""
    if not PROD_BACKUP_PATH.exists():
        pytest.skip(f"Production backup not found at {PROD_BACKUP_PATH}")

    conn = psycopg2.connect(**postgres_connection_params)
    conn.autocommit = True
    cursor = conn.cursor()

    # Drop and recreate database for clean state
    cursor.execute("""
        DO $$ DECLARE
            r RECORD;
        BEGIN
            FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
            END LOOP;
        END $$;
    """)
    cursor.close()
    conn.close()

    # Load production backup using psql
    host = postgres_connection_params["host"]
    port = postgres_connection_params["port"]

    # Decompress and pipe to psql
    with gzip.open(PROD_BACKUP_PATH, 'rt') as f:
        sql_content = f.read()

    conn = psycopg2.connect(**postgres_connection_params)
    conn.autocommit = True
    cursor = conn.cursor()

    # Execute the SQL (may need to split on certain commands)
    try:
        cursor.execute(sql_content)
    except Exception as e:
        # Some statements may fail, log and continue
        print(f"Warning loading backup: {e}")

    cursor.close()
    conn.close()

    yield postgres_connection_params


@pytest.fixture(scope="function")
def set_pg_env(pg_db_with_schema, monkeypatch):
    """Set environment variables for PostgreSQL connection"""
    monkeypatch.setenv("DB_HOST", pg_db_with_schema["host"])
    monkeypatch.setenv("DB_PORT", str(pg_db_with_schema["port"]))
    monkeypatch.setenv("DB_NAME", pg_db_with_schema["dbname"])
    monkeypatch.setenv("DB_USER", pg_db_with_schema["user"])
    monkeypatch.setenv("DB_PASSWORD", pg_db_with_schema["password"])
    monkeypatch.setenv("ENVIRONMENT", "test")

    yield pg_db_with_schema


@pytest.fixture(scope="function")
def set_pg_env_with_data(pg_db_with_data, monkeypatch):
    """Set environment variables for PostgreSQL with test data"""
    monkeypatch.setenv("DB_HOST", pg_db_with_data["host"])
    monkeypatch.setenv("DB_PORT", str(pg_db_with_data["port"]))
    monkeypatch.setenv("DB_NAME", pg_db_with_data["dbname"])
    monkeypatch.setenv("DB_USER", pg_db_with_data["user"])
    monkeypatch.setenv("DB_PASSWORD", pg_db_with_data["password"])
    monkeypatch.setenv("ENVIRONMENT", "test")

    yield pg_db_with_data


# ============================================================================
# Legacy fixture aliases for backward compatibility
# These map old SQLite-based fixtures to new PostgreSQL-based ones
# ============================================================================

@pytest.fixture(scope="function")
def memory_db_with_schema(pg_db_with_schema, monkeypatch):
    """COMPATIBILITY: Maps to pg_db_with_schema"""
    monkeypatch.setenv("DB_HOST", pg_db_with_schema["host"])
    monkeypatch.setenv("DB_PORT", str(pg_db_with_schema["port"]))
    monkeypatch.setenv("DB_NAME", pg_db_with_schema["dbname"])
    monkeypatch.setenv("DB_USER", pg_db_with_schema["user"])
    monkeypatch.setenv("DB_PASSWORD", pg_db_with_schema["password"])
    monkeypatch.setenv("ENVIRONMENT", "test")
    return pg_db_with_schema


@pytest.fixture(scope="function")
def test_db_with_data(pg_db_with_data, monkeypatch):
    """COMPATIBILITY: Maps to pg_db_with_data"""
    monkeypatch.setenv("DB_HOST", pg_db_with_data["host"])
    monkeypatch.setenv("DB_PORT", str(pg_db_with_data["port"]))
    monkeypatch.setenv("DB_NAME", pg_db_with_data["dbname"])
    monkeypatch.setenv("DB_USER", pg_db_with_data["user"])
    monkeypatch.setenv("DB_PASSWORD", pg_db_with_data["password"])
    monkeypatch.setenv("ENVIRONMENT", "test")
    return pg_db_with_data


@pytest.fixture(scope="session")
def test_settings():
    """Test settings configuration"""
    return {
        "environment": "test",
        "debug": True,
        "log_level": "DEBUG",
        "cors_origins": ["*"],
        "cors_credentials": True,
        "cors_methods": ["*"],
        "cors_headers": ["*"],
        "api_title": "CocktailDB Test API",
        "api_description": "Test API for CocktailDB",
        "api_version": "1.0.0-test",
    }


@pytest.fixture(scope="function")
def mock_user():
    """Mock authenticated user for testing"""
    return {
        "sub": "test-user-123",
        "username": "testuser",
        "email": "test@example.com",
        "cognito:groups": ["users"],
        "user_id": "test-user-123",
    }


@pytest.fixture(scope="function")
def mock_editor_user():
    """Mock editor user for testing"""
    return {
        "sub": "editor-user-123",
        "username": "editoruser",
        "email": "editor@example.com",
        "cognito:groups": ["editor"],
        "user_id": "editor-user-123",
    }


@pytest.fixture(scope="function")
def mock_admin_user():
    """Mock admin user for testing"""
    return {
        "sub": "admin-user-123",
        "username": "adminuser",
        "email": "admin@example.com",
        "cognito:groups": ["admin"],
        "user_id": "admin-user-123",
    }


@pytest.fixture(scope="function")
def test_client_memory_with_app(test_settings, memory_db_with_schema):
    """Test client with PostgreSQL database with schema - returns both client and app"""
    # Import and create app after environment is configured
    from api.main import app

    # Clear any existing dependency overrides
    app.dependency_overrides.clear()
    client = TestClient(app)
    yield client, app
    # Clean up after test
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def test_client_memory(test_client_memory_with_app):
    """Test client with database with schema - returns only client for simple tests"""
    client, app = test_client_memory_with_app
    yield client


@pytest.fixture(scope="function")
def test_client_with_data(test_settings, test_db_with_data):
    """Test client with fresh database and predictable test data for integration tests"""
    # Import and create app after environment is configured
    from api.main import app

    # Clear any existing dependency overrides
    app.dependency_overrides.clear()
    client = TestClient(app)
    yield client, app
    # Clean up after test
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def db_with_test_data(pg_db_with_data):
    """Direct database connection to test database with predictable data"""
    conn = psycopg2.connect(**pg_db_with_data)
    conn.autocommit = False
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture(scope="function")
def db_instance(memory_db_with_schema):
    """Database instance with environment properly configured"""
    from api.db.db_core import Database

    # Create and return Database instance
    db = Database()
    yield db


@pytest.fixture(scope="function")
def db_instance_with_data(test_db_with_data):
    """Database instance with environment properly configured and test data"""
    from api.db.db_core import Database

    # Create and return Database instance
    db = Database()
    yield db


@pytest.fixture(scope="function")
def authenticated_client(test_client_memory_with_app, mock_user):
    """Test client with mocked authentication using FastAPI dependency override"""
    from dependencies.auth import UserInfo, require_authentication

    client, app = test_client_memory_with_app

    # Create UserInfo with only the parameters it expects
    user_info = UserInfo(
        user_id=mock_user["user_id"],
        username=mock_user.get("username"),
        email=mock_user.get("email"),
        groups=mock_user.get("cognito:groups", []),
        claims=mock_user,
    )

    # Override the dependency
    def override_require_authentication():
        return user_info

    app.dependency_overrides[require_authentication] = override_require_authentication

    yield client

    # Clean up the override
    if require_authentication in app.dependency_overrides:
        del app.dependency_overrides[require_authentication]


@pytest.fixture(scope="function")
def editor_client(test_client_memory_with_app, mock_editor_user):
    """Test client with mocked editor authentication using FastAPI dependency override"""
    from dependencies.auth import UserInfo, require_authentication, require_editor_access

    client, app = test_client_memory_with_app

    # Create UserInfo with only the parameters it expects
    user_info = UserInfo(
        user_id=mock_editor_user["user_id"],
        username=mock_editor_user.get("username"),
        email=mock_editor_user.get("email"),
        groups=mock_editor_user.get("cognito:groups", []),
        claims=mock_editor_user,
    )

    # Override both dependencies
    def override_require_authentication():
        return user_info

    def override_require_editor_access():
        return user_info

    app.dependency_overrides[require_authentication] = override_require_authentication
    app.dependency_overrides[require_editor_access] = override_require_editor_access

    yield client

    # Clean up the overrides
    if require_authentication in app.dependency_overrides:
        del app.dependency_overrides[require_authentication]
    if require_editor_access in app.dependency_overrides:
        del app.dependency_overrides[require_editor_access]


@pytest.fixture(scope="function")
def editor_client_with_data(test_client_with_data, mock_editor_user):
    """Test client with mocked editor authentication AND test data"""
    from dependencies.auth import UserInfo, require_authentication, require_editor_access

    client, app = test_client_with_data

    # Create UserInfo with only the parameters it expects
    user_info = UserInfo(
        user_id=mock_editor_user["user_id"],
        username=mock_editor_user.get("username"),
        email=mock_editor_user.get("email"),
        groups=mock_editor_user.get("cognito:groups", []),
        claims=mock_editor_user,
    )

    # Override both dependencies
    def override_require_authentication():
        return user_info

    def override_require_editor_access():
        return user_info

    app.dependency_overrides[require_authentication] = override_require_authentication
    app.dependency_overrides[require_editor_access] = override_require_editor_access

    yield client

    # Clean up the overrides
    if require_authentication in app.dependency_overrides:
        del app.dependency_overrides[require_authentication]
    if require_editor_access in app.dependency_overrides:
        del app.dependency_overrides[require_editor_access]


@pytest.fixture(scope="function")
def admin_client(test_client_memory_with_app, mock_admin_user):
    """Test client with mocked admin authentication using FastAPI dependency override"""
    from dependencies.auth import UserInfo, require_authentication, require_editor_access

    client, app = test_client_memory_with_app

    # Create UserInfo with only the parameters it expects
    user_info = UserInfo(
        user_id=mock_admin_user["user_id"],
        username=mock_admin_user.get("username"),
        email=mock_admin_user.get("email"),
        groups=mock_admin_user.get("cognito:groups", []),
        claims=mock_admin_user,
    )

    # Override both dependencies
    def override_require_authentication():
        return user_info

    def override_require_editor_access():
        return user_info

    app.dependency_overrides[require_authentication] = override_require_authentication
    app.dependency_overrides[require_editor_access] = override_require_editor_access

    yield client

    # Clean up the overrides
    if require_authentication in app.dependency_overrides:
        del app.dependency_overrides[require_authentication]
    if require_editor_access in app.dependency_overrides:
        del app.dependency_overrides[require_editor_access]


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment (runs once per session)"""
    # Create directories
    Path("tests/fixtures").mkdir(parents=True, exist_ok=True)
    yield


@pytest.fixture(scope="function")
def sample_ingredient_data():
    """Sample ingredient data for testing"""
    return {
        "name": "Test Gin",
        "description": "A test gin for testing purposes",
        "parent_id": None,
    }


@pytest.fixture(scope="function")
def sample_recipe_data():
    """Sample recipe data for testing"""
    return {
        "name": "Test Martini",
        "instructions": "Stir gin and vermouth with ice. Strain into glass.",
        "ingredients": [
            {"ingredient_id": 1, "amount": 2.0, "unit_id": 1},
            {
                "ingredient_id": 2,
                "amount": 0.5,
                "unit_id": 1,
            },
        ],
        "tags": ["classic", "gin", "martini"],
    }


# ============================================================================
# Utility functions for tests
# ============================================================================

def assert_valid_response_structure(response_data: Dict[str, Any], expected_keys: list):
    """Assert that response has expected structure"""
    assert isinstance(response_data, dict)
    for key in expected_keys:
        assert key in response_data, f"Expected key '{key}' not found in response"


def assert_ingredient_structure(ingredient: Dict[str, Any]):
    """Assert that ingredient has expected structure"""
    expected_keys = ["id", "name", "description", "parent_id", "path"]
    assert_valid_response_structure(ingredient, expected_keys)


def assert_recipe_structure(recipe: Dict[str, Any]):
    """Assert that recipe has expected structure"""
    expected_keys = [
        "id",
        "name",
        "instructions",
        "description",
        "source",
        "source_url",
        "avg_rating",
        "rating_count",
    ]
    assert_valid_response_structure(recipe, expected_keys)


def assert_unit_structure(unit: Dict[str, Any]):
    """Assert that unit has expected structure"""
    expected_keys = ["id", "name", "abbreviation", "conversion_to_ml"]
    assert_valid_response_structure(unit, expected_keys)


def assert_complete_recipe_structure(
    recipe: Dict[str, Any], include_user_fields: bool = False
):
    """Assert that recipe has complete structure required for infinite scroll (no N+1 queries)"""
    # Core recipe fields
    core_fields = [
        "id",
        "name",
        "instructions",
        "created_by",
        "avg_rating",
        "rating_count",
        "created_at",
    ]
    assert_valid_response_structure(recipe, core_fields)

    # Extended fields for complete data
    extended_fields = ["image_url", "source", "source_url"]
    for field in extended_fields:
        assert field in recipe, (
            f"Recipe must include '{field}' field for infinite scroll"
        )

    # Tag structure validation
    assert "public_tags" in recipe, "Recipe must include 'public_tags' array"
    assert "private_tags" in recipe, "Recipe must include 'private_tags' array"
    assert isinstance(recipe["public_tags"], list), "public_tags must be a list"
    assert isinstance(recipe["private_tags"], list), "private_tags must be a list"

    # Ingredient data completeness
    if "ingredients" in recipe and recipe["ingredients"]:
        for ingredient in recipe["ingredients"]:
            ingredient_fields = ["id", "name", "amount", "unit"]
            for field in ingredient_fields:
                assert field in ingredient, f"Ingredient must include '{field}' field"

    # User-specific fields (when authenticated)
    if include_user_fields:
        if "user_rating" in recipe:
            user_rating = recipe["user_rating"]
            assert user_rating is None or isinstance(user_rating, (int, float)), (
                "user_rating must be null or numeric"
            )
            if user_rating is not None:
                assert 1 <= user_rating <= 5, "user_rating must be between 1 and 5"


def assert_search_response_structure(
    response_data: Dict[str, Any], include_user_fields: bool = False
):
    """Assert that search response has complete structure required by API_SPEC.md"""
    # Top-level response structure
    top_level_fields = ["recipes", "pagination", "query"]
    assert_valid_response_structure(response_data, top_level_fields)

    # Pagination structure
    pagination_fields = [
        "page",
        "limit",
        "total_count",
        "has_next",
        "has_previous",
    ]
    assert_valid_response_structure(response_data["pagination"], pagination_fields)

    # Recipe array
    assert isinstance(response_data["recipes"], list), "recipes must be a list"

    # Each recipe should have complete structure
    for recipe in response_data["recipes"]:
        assert_complete_recipe_structure(recipe, include_user_fields)

    # Query field validation
    query = response_data["query"]
    assert query is None or isinstance(query, str), "query field must be null or string"


def assert_pagination_mathematical_consistency(pagination: Dict[str, Any]):
    """Assert that pagination metadata is mathematically consistent"""
    page = pagination["page"]
    limit = pagination["limit"]
    total_count = pagination["total_count"]
    has_next = pagination["has_next"]
    has_previous = pagination["has_previous"]

    # Basic type validation
    assert isinstance(page, int) and page >= 1, "page must be positive integer"
    assert isinstance(limit, int) and limit >= 1, "limit must be positive integer"
    assert isinstance(total_count, int) and total_count >= 0, (
        "total_count must be non-negative integer"
    )
    assert isinstance(has_next, bool), "has_next must be boolean"
    assert isinstance(has_previous, bool), "has_previous must be boolean"

    # has_next/has_previous logic
    assert has_previous == (page > 1), "has_previous logic incorrect"


def assert_sort_order_correctness(recipes: list, sort_by: str, sort_order: str = "asc"):
    """Assert that recipes are correctly sorted according to parameters"""
    if len(recipes) <= 1:
        return  # Nothing to sort

    values = []
    for recipe in recipes:
        if sort_by == "name":
            values.append(recipe["name"].lower())
        elif sort_by == "created_at":
            values.append(recipe["created_at"])
        elif sort_by == "avg_rating":
            values.append(recipe["avg_rating"] or 0)  # Handle null ratings
        else:
            raise ValueError(f"Unknown sort_by parameter: {sort_by}")

    if sort_order == "asc":
        sorted_values = sorted(values)
    elif sort_order == "desc":
        sorted_values = sorted(values, reverse=True)
    else:
        raise ValueError(f"Unknown sort_order parameter: {sort_order}")

    assert values == sorted_values, (
        f"Recipes not properly sorted by {sort_by} {sort_order}"
    )


def assert_tag_structure(tag: Dict[str, Any]):
    """Assert that tag object has expected structure"""
    if isinstance(tag, dict):
        required_fields = ["id", "name"]
        for field in required_fields:
            assert field in tag, f"Tag must include '{field}' field"


def _populate_test_data_pg(cursor):
    """Populate test database with predictable test data for integration tests (PostgreSQL)"""

    # Add units first (they are required by recipe_ingredients)
    cursor.execute("""
        INSERT INTO units (name, abbreviation, conversion_to_ml) VALUES
        ('ounce', 'oz', 29.5735),
        ('milliliter', 'ml', 1.0),
        ('teaspoon', 'tsp', 4.92892),
        ('tablespoon', 'tbsp', 14.7868),
        ('dash', 'dash', 0.9),
        ('to top', 'to top', NULL),
        ('to rinse', 'to rinse', NULL),
        ('Each', 'ea', NULL)
        ON CONFLICT (name) DO NOTHING
    """)

    # Add base ingredients
    cursor.execute("""
        INSERT INTO ingredients (name, description, parent_id, path) VALUES
        ('Whiskey', 'Distilled grain spirit', NULL, '/1/'),
        ('Rum', 'Distilled sugarcane spirit', NULL, '/2/'),
        ('Vodka', 'Neutral grain spirit', NULL, '/3/'),
        ('Gin', 'Juniper-flavored spirit', NULL, '/4/'),
        ('Tequila', 'Agave-based spirit', NULL, '/5/'),
        ('Brandy', 'Distilled wine', NULL, '/6/'),
        ('Citrus', 'Citrus fruits and juices', NULL, '/7/')
        ON CONFLICT (name) DO NOTHING
    """)

    # Add child ingredients
    cursor.execute("""
        INSERT INTO ingredients (name, description, parent_id, path) VALUES
        ('Bourbon', 'American whiskey made from corn', 1, '/1/8/'),
        ('Rye Whiskey', 'Whiskey made from rye grain', 1, '/1/9/'),
        ('Lemon Juice', 'Fresh citrus juice', 7, '/7/10/'),
        ('Lime Juice', 'Fresh citrus juice', 7, '/7/11/'),
        ('Simple Syrup', 'Sugar and water syrup', NULL, '/12/'),
        ('Angostura Bitters', 'Aromatic bitters', NULL, '/13/')
        ON CONFLICT (name) DO NOTHING
    """)

    # Add test recipes with predictable content
    cursor.execute("""
        INSERT INTO recipes (name, instructions, description, source, avg_rating, rating_count) VALUES
        ('Test Old Fashioned', 'Muddle sugar with bitters, add whiskey and ice', 'Classic whiskey cocktail', 'Test Source', 4.5, 2),
        ('Test Whiskey Sour', 'Shake whiskey, lemon juice, and simple syrup with ice', 'Tart whiskey cocktail', 'Test Source', 4.0, 1),
        ('Test Daiquiri', 'Shake rum, lime juice, and simple syrup with ice', 'Classic rum cocktail', 'Test Source', 0, 0),
        ('Test Gin Martini', 'Stir gin and vermouth with ice, strain', 'Classic gin cocktail', 'Test Source', 5.0, 1)
        ON CONFLICT (name) DO NOTHING
    """)

    # Get ingredient IDs for recipe_ingredients
    cursor.execute("SELECT id, name FROM ingredients")
    ingredients = {row[1]: row[0] for row in cursor.fetchall()}

    cursor.execute("SELECT id, name FROM units")
    units = {row[1]: row[0] for row in cursor.fetchall()}

    cursor.execute("SELECT id, name FROM recipes")
    recipes = {row[1]: row[0] for row in cursor.fetchall()}

    # Add recipe ingredients using dynamic IDs
    if ingredients and units and recipes:
        bourbon_id = ingredients.get('Bourbon', 8)
        lemon_id = ingredients.get('Lemon Juice', 10)
        lime_id = ingredients.get('Lime Juice', 11)
        syrup_id = ingredients.get('Simple Syrup', 12)
        bitters_id = ingredients.get('Angostura Bitters', 13)
        rum_id = ingredients.get('Rum', 2)
        gin_id = ingredients.get('Gin', 4)
        whiskey_id = ingredients.get('Whiskey', 1)

        oz_id = units.get('ounce', 1)
        dash_id = units.get('dash', 5)
        tsp_id = units.get('teaspoon', 3)

        old_fashioned_id = recipes.get('Test Old Fashioned', 1)
        whiskey_sour_id = recipes.get('Test Whiskey Sour', 2)
        daiquiri_id = recipes.get('Test Daiquiri', 3)
        martini_id = recipes.get('Test Gin Martini', 4)

        cursor.execute("""
            INSERT INTO recipe_ingredients (recipe_id, ingredient_id, unit_id, amount) VALUES
            (%s, %s, %s, 2.0),
            (%s, %s, %s, 2),
            (%s, %s, %s, 0.25),
            (%s, %s, %s, 2.0),
            (%s, %s, %s, 0.75),
            (%s, %s, %s, 0.5),
            (%s, %s, %s, 2.0),
            (%s, %s, %s, 0.75),
            (%s, %s, %s, 0.5),
            (%s, %s, %s, 2.5),
            (%s, %s, %s, 0.5)
            ON CONFLICT DO NOTHING
        """, (
            old_fashioned_id, bourbon_id, oz_id,  # Old Fashioned: Bourbon
            old_fashioned_id, bitters_id, dash_id,  # Old Fashioned: Bitters
            old_fashioned_id, syrup_id, tsp_id,  # Old Fashioned: Syrup
            whiskey_sour_id, bourbon_id, oz_id,  # Whiskey Sour: Bourbon
            whiskey_sour_id, lemon_id, oz_id,  # Whiskey Sour: Lemon
            whiskey_sour_id, syrup_id, oz_id,  # Whiskey Sour: Syrup
            daiquiri_id, rum_id, oz_id,  # Daiquiri: Rum
            daiquiri_id, lime_id, oz_id,  # Daiquiri: Lime
            daiquiri_id, syrup_id, oz_id,  # Daiquiri: Syrup
            martini_id, gin_id, oz_id,  # Martini: Gin
            martini_id, whiskey_id, oz_id,  # Martini: Vermouth placeholder
        ))

    # Add test ratings
    cursor.execute("""
        INSERT INTO ratings (cognito_user_id, recipe_id, rating) VALUES
        ('test-user-1', 1, 4),
        ('test-user-2', 1, 5),
        ('test-user-1', 2, 4),
        ('test-user-1', 4, 5)
        ON CONFLICT DO NOTHING
    """)

    # Add test tags
    cursor.execute("""
        INSERT INTO tags (name, created_by) VALUES
        ('Tiki', NULL),
        ('Classic', NULL),
        ('Whiskey', NULL),
        ('Citrus', NULL),
        ('Sweet', NULL),
        ('Stirred', NULL),
        ('Shaken', NULL),
        ('My Favorite', 'test-user-1')
        ON CONFLICT DO NOTHING
    """)

    # Add recipe-tag associations
    cursor.execute("""
        INSERT INTO recipe_tags (recipe_id, tag_id) VALUES
        (1, 2),  -- Old Fashioned: Classic
        (1, 3),  -- Old Fashioned: Whiskey
        (1, 5),  -- Old Fashioned: Sweet
        (1, 6),  -- Old Fashioned: Stirred
        (2, 3),  -- Whiskey Sour: Whiskey
        (2, 4),  -- Whiskey Sour: Citrus
        (2, 7),  -- Whiskey Sour: Shaken
        (3, 1),  -- Daiquiri: Tiki
        (3, 4),  -- Daiquiri: Citrus
        (3, 7),  -- Daiquiri: Shaken
        (4, 2),  -- Gin Martini: Classic
        (4, 6),  -- Gin Martini: Stirred
        (1, 8)   -- Old Fashioned: My Favorite (private tag)
        ON CONFLICT DO NOTHING
    """)
