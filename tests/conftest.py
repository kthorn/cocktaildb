"""
PyTest configuration and shared fixtures for CocktailDB API tests
"""

import os
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

# Add project root to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

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


# @pytest.fixture(scope="function")
# def temp_db_from_production(production_db_path, tmp_path):
#     """DEPRECATED: Create a temporary copy of production database for isolated tests using pytest's tmp_path"""
#     # Use pytest's native temporary directory
#     temp_db = tmp_path / "test_cocktaildb.db"
#     shutil.copy2(production_db_path, temp_db)
#     return str(temp_db)


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
def test_db_with_data():
    """Test database with schema and predictable test data for integration tests"""
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
            
            # Add predictable test data
            _populate_test_data(conn)
            
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


# @pytest.fixture(scope="function")
# def test_client_production_readonly(test_settings, production_db_path, monkeypatch):
#     """DEPRECATED: Test client with production database (read-only tests)"""
#     # Use monkeypatch to set environment variables
#     monkeypatch.setenv("DB_PATH", production_db_path)
#     monkeypatch.setenv("ENVIRONMENT", "test")
# 
#     # Import and create app after environment is configured
#     from api.main import app
# 
#     client = TestClient(app)
#     yield client


# @pytest.fixture(scope="function")
# def test_client_production_isolated(
#     test_settings, temp_db_from_production, monkeypatch
# ):
#     """DEPRECATED: Test client with isolated copy of production database"""
#     # Use monkeypatch to set environment variables
#     monkeypatch.setenv("DB_PATH", temp_db_from_production)
#     monkeypatch.setenv("ENVIRONMENT", "test")
# 
#     # Import and create app after environment is configured
#     from api.main import app
# 
#     client = TestClient(app)
#     yield client


@pytest.fixture(scope="function")
def test_client_with_data(test_settings, test_db_with_data, monkeypatch):
    """Test client with fresh database and predictable test data for integration tests"""
    # Use monkeypatch to set environment variables
    monkeypatch.setenv("DB_PATH", test_db_with_data)
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
def db_with_test_data(test_db_with_data):
    """Direct database connection to test database with predictable data"""
    import sqlite3
    conn = sqlite3.connect(test_db_with_data)
    conn.row_factory = sqlite3.Row  # Enable dict-like access
    yield conn
    conn.close()


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


# @pytest.fixture(scope="function")
# def db_connection(temp_db_from_production):
#     """DEPRECATED: Direct database connection for test data inspection"""
#     conn = sqlite3.connect(temp_db_from_production)
#     conn.row_factory = sqlite3.Row  # Enable dict-like access
#     yield conn
#     conn.close()


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
            ingredient_fields = ["id", "name", "amount", "unit", "notes"]
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
        "total_pages",
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
    total_pages = pagination["total_pages"]
    has_next = pagination["has_next"]
    has_previous = pagination["has_previous"]

    # Basic type validation
    assert isinstance(page, int) and page >= 1, "page must be positive integer"
    assert isinstance(limit, int) and limit >= 1, "limit must be positive integer"
    assert isinstance(total_count, int) and total_count >= 0, (
        "total_count must be non-negative integer"
    )
    assert isinstance(total_pages, int) and total_pages >= 1, (
        "total_pages must be positive integer"
    )
    assert isinstance(has_next, bool), "has_next must be boolean"
    assert isinstance(has_previous, bool), "has_previous must be boolean"

    # Mathematical relationships
    expected_total_pages = ((total_count - 1) // limit) + 1 if total_count > 0 else 1
    assert total_pages == expected_total_pages, "total_pages calculation incorrect"

    # has_next/has_previous logic
    assert has_previous == (page > 1), "has_previous logic incorrect"
    assert has_next == (page < total_pages), "has_next logic incorrect"


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
    # If tag is just a string, that's also acceptable in some contexts


def create_test_recipe_with_rating(
    db_connection, user_id: str, recipe_name: str, rating: int
):
    """Helper function to create a test recipe with a user rating"""
    # Create recipe
    cursor = db_connection.execute(
        "INSERT INTO recipes (name, instructions, created_by) VALUES (?, ?, ?) RETURNING id",
        (recipe_name, "Test instructions for " + recipe_name, user_id),
    )
    recipe_id = cursor.fetchone()["id"]

    # Create rating
    db_connection.execute(
        "INSERT INTO ratings (recipe_id, user_id, rating) VALUES (?, ?, ?)",
        (recipe_id, user_id, rating),
    )

    db_connection.commit()
    return recipe_id


def create_test_recipe_with_tags(
    db_connection,
    user_id: str,
    recipe_name: str,
    public_tags: list = None,
    private_tags: list = None,
):
    """Helper function to create a test recipe with public and private tags"""
    # Create recipe
    cursor = db_connection.execute(
        "INSERT INTO recipes (name, instructions, created_by) VALUES (?, ?, ?) RETURNING id",
        (recipe_name, "Test instructions for " + recipe_name, user_id),
    )
    recipe_id = cursor.fetchone()["id"]

    # Create and associate public tags
    if public_tags:
        for tag_name in public_tags:
            cursor = db_connection.execute(
                "INSERT INTO tags (name, is_public, created_by) VALUES (?, ?, ?) RETURNING id",
                (tag_name, 1, user_id),
            )
            tag_id = cursor.fetchone()["id"]
            db_connection.execute(
                "INSERT INTO recipe_tags (recipe_id, tag_id) VALUES (?, ?)",
                (recipe_id, tag_id),
            )

    # Create and associate private tags
    if private_tags:
        for tag_name in private_tags:
            cursor = db_connection.execute(
                "INSERT INTO tags (name, is_public, created_by) VALUES (?, ?, ?) RETURNING id",
                (tag_name, 0, user_id),
            )
            tag_id = cursor.fetchone()["id"]
            db_connection.execute(
                "INSERT INTO recipe_tags (recipe_id, tag_id) VALUES (?, ?)",
                (recipe_id, tag_id),
            )

    db_connection.commit()
    return recipe_id


def _populate_test_data(conn):
    """Populate test database with predictable test data for integration tests"""
    cursor = conn.cursor()
    
    # Add additional ingredients beyond what's already in schema.sql
    cursor.execute("""
        INSERT INTO ingredients (name, description, parent_id, path) VALUES
        ('Bourbon', 'American whiskey made from corn', 1, '/1/8/'),
        ('Rye Whiskey', 'Whiskey made from rye grain', 1, '/1/9/'),
        ('Lemon Juice', 'Fresh citrus juice', 7, '/7/10/'),
        ('Lime Juice', 'Fresh citrus juice', 7, '/7/11/'),
        ('Simple Syrup', 'Sugar and water syrup', NULL, '/12/'),
        ('Angostura Bitters', 'Aromatic bitters', NULL, '/13/')
    """)
    
    # Add test recipes with predictable content
    cursor.execute("""
        INSERT INTO recipes (name, instructions, description, source, avg_rating, rating_count) VALUES
        ('Test Old Fashioned', 'Muddle sugar with bitters, add whiskey and ice', 'Classic whiskey cocktail', 'Test Source', 4.5, 2),
        ('Test Whiskey Sour', 'Shake whiskey, lemon juice, and simple syrup with ice', 'Tart whiskey cocktail', 'Test Source', 4.0, 1),
        ('Test Daiquiri', 'Shake rum, lime juice, and simple syrup with ice', 'Classic rum cocktail', 'Test Source', 0, 0),
        ('Test Gin Martini', 'Stir gin and vermouth with ice, strain', 'Classic gin cocktail', 'Test Source', 5.0, 1)
    """)
    
    # Add recipe ingredients
    cursor.execute("""
        INSERT INTO recipe_ingredients (recipe_id, ingredient_id, unit_id, amount) VALUES
        (1, 8, 1, 2.0),     -- Old Fashioned: 2 oz Bourbon
        (1, 13, 5, 2),      -- Old Fashioned: 2 dashes Angostura Bitters
        (1, 12, 3, 0.25),   -- Old Fashioned: 1/4 tsp Simple Syrup
        (2, 8, 1, 2.0),     -- Whiskey Sour: 2 oz Bourbon
        (2, 10, 1, 0.75),   -- Whiskey Sour: 0.75 oz Lemon Juice
        (2, 12, 1, 0.5),    -- Whiskey Sour: 0.5 oz Simple Syrup
        (3, 2, 1, 2.0),     -- Daiquiri: 2 oz Rum
        (3, 11, 1, 0.75),   -- Daiquiri: 0.75 oz Lime Juice
        (3, 12, 1, 0.5),    -- Daiquiri: 0.5 oz Simple Syrup
        (4, 4, 1, 2.5),     -- Gin Martini: 2.5 oz Gin
        (4, 1, 1, 0.5)      -- Gin Martini: 0.5 oz Vermouth (using Whiskey as placeholder)
    """)
    
    # Add test ratings
    cursor.execute("""
        INSERT INTO ratings (cognito_user_id, cognito_username, recipe_id, rating) VALUES
        ('test-user-1', 'testuser1', 1, 4),
        ('test-user-2', 'testuser2', 1, 5),
        ('test-user-1', 'testuser1', 2, 4),
        ('test-user-1', 'testuser1', 4, 5)
    """)
    
    # Add test tags (Note: Tiki=1, Classic=2 already exist from schema)
    cursor.execute("""
        INSERT INTO tags (name, created_by) VALUES
        ('Whiskey', NULL),
        ('Citrus', NULL),
        ('Sweet', NULL),
        ('Stirred', NULL),
        ('Shaken', NULL),
        ('My Favorite', 'test-user-1')
    """)
    
    # Add recipe-tag associations (adjusting for existing tags: Tiki=1, Classic=2)
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
    """)
    
    conn.commit()
