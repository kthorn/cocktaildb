"""
PyTest configuration and shared fixtures for CocktailDB API tests
"""

import os
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

# Test configuration
TEST_DB_PATH = "tests/fixtures/test_cocktaildb.db"
TEMP_DB_DIR = "tests/temp_dbs"


@pytest.fixture(scope="function", autouse=True)
def clear_database_cache():
    """Clear the global database cache between tests"""
    import sys

    # Clear before test - simple and minimal
    if "api.core.database" in sys.modules:
        api_core_database = sys.modules["api.core.database"]
        api_core_database._DB_INSTANCE = None
        api_core_database._DB_INIT_TIME = 0

    yield

    # Basic cleanup after test
    if "api.core.database" in sys.modules:
        api_core_database = sys.modules["api.core.database"]
        api_core_database._DB_INSTANCE = None
        api_core_database._DB_INIT_TIME = 0


@pytest.fixture(scope="session")
def test_settings():
    """Test settings configuration"""
    return {
        "db_path": ":memory:",
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


@pytest.fixture(scope="session")
def production_db_path():
    """Path to production database copy for read-only tests"""
    db_path = Path(TEST_DB_PATH)
    if not db_path.exists():
        pytest.skip(
            f"Production test database not found at {TEST_DB_PATH}. "
            f"Run: ./scripts/restore-backup.sh --target dev --source prod"
        )
    return str(db_path)


@pytest.fixture(scope="function")
def temp_db_from_production(production_db_path, tmp_path):
    """Create a temporary copy of production database for isolated tests using pytest's tmp_path"""
    # Use pytest's native temporary directory
    temp_db = tmp_path / "test_cocktaildb.db"
    shutil.copy2(production_db_path, temp_db)
    return str(temp_db)


@pytest.fixture(scope="function")
def memory_db():
    """In-memory SQLite database for unit tests"""
    return ":memory:"


@pytest.fixture(scope="function")
def memory_db_with_schema():
    """In-memory SQLite database with schema initialized for unit tests"""
    import sqlite3
    import tempfile
    from pathlib import Path

    # Create a temporary file-based database so we can initialize it
    temp_fd, temp_path = tempfile.mkstemp(suffix=".db")
    os.close(temp_fd)

    try:
        # Initialize schema
        schema_path = Path(__file__).parent.parent / "schema-deploy" / "schema.sql"
        if schema_path.exists():
            conn = sqlite3.connect(temp_path)
            with open(schema_path, "r") as f:
                schema_sql = f.read()
            conn.executescript(schema_sql)
            # Use DELETE journal mode for tests to avoid locking issues
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.close()

        yield temp_path
    finally:
        # Simple cleanup
        if os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                # If we can't delete it immediately, that's okay
                pass


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
def mock_admin_user():
    """Mock admin user for testing"""
    return {
        "sub": "admin-user-123",
        "username": "adminuser",
        "email": "admin@example.com",
        "cognito:groups": ["admins"],
        "user_id": "admin-user-123",
    }


@pytest.fixture(scope="function")
def test_client_memory_with_app(test_settings, memory_db_with_schema, monkeypatch):
    """Test client with in-memory database with schema - returns both client and app"""
    # Use monkeypatch to set environment variables for settings
    monkeypatch.setenv("DB_PATH", memory_db_with_schema)
    monkeypatch.setenv("ENVIRONMENT", "test")

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
    """Test client with in-memory database with schema - returns only client for simple tests"""
    client, app = test_client_memory_with_app
    yield client


@pytest.fixture(scope="function")
def test_client_memory_no_schema(test_settings, memory_db, monkeypatch):
    """Test client with in-memory database without schema (for testing connection failures)"""
    # Use monkeypatch to set environment variables for settings
    monkeypatch.setenv("DB_PATH", memory_db)
    monkeypatch.setenv("ENVIRONMENT", "test")

    # Import and create app after environment is configured
    from api.main import app

    client = TestClient(app)
    yield client


@pytest.fixture(scope="function")
def test_client_production_readonly(test_settings, production_db_path, monkeypatch):
    """Test client with production database (read-only tests)"""
    # Use monkeypatch to set environment variables
    monkeypatch.setenv("DB_PATH", production_db_path)
    monkeypatch.setenv("ENVIRONMENT", "test")

    # Import and create app after environment is configured
    from api.main import app

    client = TestClient(app)
    yield client


@pytest.fixture(scope="function")
def test_client_production_isolated(
    test_settings, temp_db_from_production, monkeypatch
):
    """Test client with isolated copy of production database"""
    # Use monkeypatch to set environment variables
    monkeypatch.setenv("DB_PATH", temp_db_from_production)
    monkeypatch.setenv("ENVIRONMENT", "test")

    # Import and create app after environment is configured
    from api.main import app

    client = TestClient(app)
    yield client


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

    # Clean up the override (test_client_memory_with_app will also clean up)
    if require_authentication in app.dependency_overrides:
        del app.dependency_overrides[require_authentication]


@pytest.fixture(scope="function")
def admin_client(test_client_memory_with_app, mock_admin_user):
    """Test client with mocked admin authentication using FastAPI dependency override"""
    from dependencies.auth import UserInfo, require_authentication

    client, app = test_client_memory_with_app

    # Create UserInfo with only the parameters it expects
    user_info = UserInfo(
        user_id=mock_admin_user["user_id"],
        username=mock_admin_user.get("username"),
        email=mock_admin_user.get("email"),
        groups=mock_admin_user.get("cognito:groups", []),
        claims=mock_admin_user,
    )

    # Override the dependency
    def override_require_authentication():
        return user_info

    app.dependency_overrides[require_authentication] = override_require_authentication

    yield client

    # Clean up the override (test_client_memory_with_app will also clean up)
    if require_authentication in app.dependency_overrides:
        del app.dependency_overrides[require_authentication]


@pytest.fixture(scope="function")
def db_connection(temp_db_from_production):
    """Direct database connection for test data inspection"""
    conn = sqlite3.connect(temp_db_from_production)
    conn.row_factory = sqlite3.Row  # Enable dict-like access
    yield conn
    conn.close()


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment (runs once per session)"""
    # Create directories
    Path("tests/fixtures").mkdir(parents=True, exist_ok=True)
    Path(TEMP_DB_DIR).mkdir(parents=True, exist_ok=True)

    yield

    # Cleanup temp databases
    if Path(TEMP_DB_DIR).exists():
        shutil.rmtree(TEMP_DB_DIR, ignore_errors=True)


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
            {"ingredient_id": 1, "quantity": 2.0, "unit_id": 1, "notes": "Dry gin"},
            {
                "ingredient_id": 2,
                "quantity": 0.5,
                "unit_id": 1,
                "notes": "Dry vermouth",
            },
        ],
        "tags": ["classic", "gin", "martini"],
    }


# Utility functions for tests
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
    expected_keys = ["id", "name", "instructions", "created_by"]
    assert_valid_response_structure(recipe, expected_keys)


def assert_unit_structure(unit: Dict[str, Any]):
    """Assert that unit has expected structure"""
    expected_keys = ["id", "name", "abbreviation", "conversion_to_ml"]
    assert_valid_response_structure(unit, expected_keys)
