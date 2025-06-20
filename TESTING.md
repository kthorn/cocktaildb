# CocktailDB API Testing Guide

This document provides comprehensive instructions for running and maintaining tests for the CocktailDB FastAPI application.

## Table of Contents

- [Quick Start](#quick-start)
- [Test Structure](#test-structure)
- [Environment Setup](#environment-setup)
- [Database Setup for Testing](#database-setup-for-testing)
- [Running Tests](#running-tests)
- [Test Types](#test-types)
- [Writing New Tests](#writing-new-tests)
- [Troubleshooting](#troubleshooting)

## Quick Start

### 1. Environment Setup

```bash
# Activate the cocktaildb environment
mamba activate cocktaildb

# Install test dependencies (if not already installed)
pip install -r requirements.txt
```

### 2. Database Setup for Testing

For integration tests that require production data, you need to set up a test database:

```bash
# Easy option: Use the helper script to download latest backup
./scripts/download-test-db.sh

# Manual option: Download specific backup
./scripts/restore-backup.sh --list  # View available backups
# Then download specific file:
# aws s3 cp s3://backup-bucket/backup-YYYY-MM-DD_HH-MM-SS.db tests/fixtures/test_cocktaildb.db
```

### 3. Run Basic Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test categories
python -m pytest tests/test_fastapi.py -v          # Basic API tests
python -m pytest tests/test_api_unit.py -v         # Unit tests
python -m pytest tests/test_api_integration.py -v  # Integration tests (requires test DB)
python -m pytest tests/test_crud_operations.py -v  # CRUD workflow tests
```

## Test Structure

The test suite is organized into several focused modules:

```
tests/
├── conftest.py                 # Test configuration and shared fixtures
├── test_fastapi.py            # Basic FastAPI functionality tests
├── test_api_unit.py           # Unit tests for individual endpoints
├── test_api_integration.py    # Integration tests with production data
├── test_crud_operations.py    # Full CRUD workflow tests
├── fixtures/                  # Test data and database files
│   └── test_cocktaildb.db    # Production data copy for testing
└── temp_dbs/                  # Temporary databases for isolated tests
```

### Key Test Files

- **`conftest.py`**: Contains pytest fixtures and test configuration
- **`test_fastapi.py`**: Basic API health checks and model validation
- **`test_api_unit.py`**: Individual endpoint testing with mocked dependencies
- **`test_api_integration.py`**: End-to-end tests with real production data
- **`test_crud_operations.py`**: Complete Create/Read/Update/Delete workflows

## Environment Setup

### Prerequisites

1. **Python Environment**: CocktailDB conda/mamba environment activated
2. **Dependencies**: All packages from `requirements.txt` installed
3. **AWS Access**: For downloading production database (integration tests only)

### Required Packages

The following test-specific packages are included in `requirements.txt`:

```
pytest==7.4.3              # Testing framework
pytest-asyncio==0.21.1     # Async test support
pytest-mock==3.14.1        # Improved mocking capabilities
httpx==0.25.0              # HTTP client for FastAPI testing
```

## Database Setup for Testing

### Option 1: Production Data (Recommended for Integration Tests)

```bash
# Easiest: Use the helper script
./scripts/download-test-db.sh

# Manual method if you need a specific backup:
./scripts/restore-backup.sh --list  # View available backups

# Download specific backup from S3
BACKUP_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name cocktail-db-prod \
  --query "Stacks[0].Outputs[?OutputKey=='BackupBucketName'].OutputValue" \
  --output text)

aws s3 cp s3://$BACKUP_BUCKET/backup-YYYY-MM-DD_HH-MM-SS.db tests/fixtures/test_cocktaildb.db
```

### Option 2: Schema-Only Database

```bash
# Apply schema to create empty test database
./scripts/apply-migration.sh -f schema-deploy/schema.sql -e test --force-init

# Copy schema-only database to fixtures
cp /path/to/test/cocktaildb.db tests/fixtures/test_cocktaildb.db
```

### Option 3: In-Memory Testing (Unit Tests)

Many tests use in-memory SQLite databases and don't require external data setup.

## Running Tests

### Basic Test Execution

```bash
# Run all tests with verbose output
python -m pytest tests/ -v

# Run tests with coverage report
python -m pytest tests/ --cov=api --cov-report=html

# Run specific test file
python -m pytest tests/test_api_unit.py -v

# Run specific test class
python -m pytest tests/test_api_unit.py::TestIngredientEndpoints -v

# Run specific test method
python -m pytest tests/test_api_unit.py::TestIngredientEndpoints::test_get_ingredients_unauthorized -v
```

### Test Categories

#### 1. Unit Tests (No Database Required)
```bash
# Fast tests that use mocked dependencies
python -m pytest tests/test_fastapi.py::TestCocktailAPIBasic -v
python -m pytest tests/test_api_unit.py::TestHealthAndRoot -v
python -m pytest tests/test_api_unit.py::TestAuthEndpoints -v
```

#### 2. Integration Tests (Requires Test Database)
```bash
# Tests that use production data
python -m pytest tests/test_api_integration.py -v
```

#### 3. CRUD Tests (Requires Test Database)
```bash
# Full workflow tests with database modifications
python -m pytest tests/test_crud_operations.py -v
```

### Filtering Tests

```bash
# Run only tests that don't require database
python -m pytest tests/ -k "not integration and not crud" -v

# Run only authentication-related tests
python -m pytest tests/ -k "auth" -v

# Skip slow integration tests
python -m pytest tests/ -m "not slow" -v
```

## Test Types

### 1. Unit Tests
- **Purpose**: Test individual functions and endpoints in isolation
- **Database**: In-memory SQLite or mocked
- **Authentication**: Mocked using pytest-mock
- **Speed**: Fast (< 1 second per test)

### 2. Integration Tests
- **Purpose**: Test end-to-end functionality with real data
- **Database**: Copy of production data
- **Authentication**: Mocked at the dependency level
- **Speed**: Medium (1-5 seconds per test)

### 3. CRUD Operation Tests
- **Purpose**: Test complete Create/Read/Update/Delete workflows
- **Database**: Isolated copy of production data per test
- **Authentication**: Mocked using pytest fixtures
- **Speed**: Medium to slow (2-10 seconds per test)

### 4. Performance Tests
- **Purpose**: Ensure API responses within acceptable time limits
- **Database**: Production data copy
- **Thresholds**: < 5 seconds for most endpoints
- **Speed**: Medium (varies by endpoint)

## Writing New Tests

### Test Structure Guidelines

1. **Use pytest fixtures** from `conftest.py` for common setup
2. **Follow naming conventions**: `test_<functionality>_<scenario>`
3. **Use pytest-mock** instead of unittest.mock for cleaner mocking
4. **Assert specific status codes** rather than generic "success" checks

### Example Test Structure

```python
def test_create_ingredient_success(self, authenticated_client, sample_ingredient_data):
    """Test successful ingredient creation with valid data"""
    response = authenticated_client.post("/api/v1/ingredients", json=sample_ingredient_data)
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == sample_ingredient_data["name"]
    assert "ingredient_id" in data
```

### Available Fixtures

- `test_client_memory`: FastAPI client with in-memory database
- `test_client_production_readonly`: Client with production data (read-only)
- `test_client_production_isolated`: Client with isolated production data copy
- `authenticated_client`: Client with mocked user authentication
- `admin_client`: Client with mocked admin authentication
- `mock_user`: Sample user data for testing
- `sample_ingredient_data`: Sample ingredient for testing
- `sample_recipe_data`: Sample recipe with ingredients for testing

### Authentication Testing

```python
def test_protected_endpoint(self, authenticated_client):
    """Test endpoint that requires authentication"""
    response = authenticated_client.post("/api/v1/ingredients", json={"name": "Test"})
    # Authentication is automatically mocked by the fixture
    assert response.status_code != 401

def test_unauthorized_access(self, test_client_memory):
    """Test endpoint without authentication"""
    response = test_client_memory.post("/api/v1/ingredients", json={"name": "Test"})
    assert response.status_code == 401
```

## Troubleshooting

### Common Issues

#### 1. Database Connection Errors
```
sqlite3.OperationalError: unable to open database file
```

**Solution**: Ensure test database exists in `tests/fixtures/test_cocktaildb.db`

```bash
# Set up test database as described in Database Setup section
./scripts/restore-backup.sh --target dev --source prod
cp /path/to/cocktaildb.db tests/fixtures/test_cocktaildb.db
```

#### 2. Import Errors
```
ModuleNotFoundError: No module named 'api'
```

**Solution**: Ensure you're running tests from the project root and environment is activated

```bash
cd /home/kurtt/cocktaildb
mamba activate cocktaildb
python -m pytest tests/ -v
```

#### 3. Authentication Mock Errors
```
AttributeError: module does not have the attribute 'verify_token'
```

**Solution**: Update test to use correct FastAPI authentication function

```python
# Correct: Mock the actual dependency function
mock_auth = mocker.patch('api.dependencies.auth.get_user_from_lambda_event')
```

#### 4. Pydantic Warnings
```
PydanticDeprecatedSince20: Using extra keyword arguments on Field is deprecated
```

**Solution**: These are warnings about deprecated Pydantic usage and don't affect test functionality. Can be suppressed with:

```bash
python -m pytest tests/ -v --disable-warnings
```

### Performance Issues

If tests are running slowly:

1. **Use unit tests for development**: `python -m pytest tests/test_api_unit.py -v`
2. **Skip integration tests**: `python -m pytest tests/ -k "not integration" -v`
3. **Run specific test files**: Focus on the functionality you're working on

### Debug Test Failures

```bash
# Run with extra verbose output
python -m pytest tests/test_api_unit.py::TestIngredientEndpoints::test_create_ingredient_authorized -vvv

# Stop on first failure
python -m pytest tests/ -x

# Drop into debugger on failure
python -m pytest tests/ --pdb
```

## Continuous Integration

### Pre-commit Checks

Before committing code, run:

```bash
# Run all unit tests (fast)
python -m pytest tests/test_fastapi.py tests/test_api_unit.py -v

# Run integration tests if you have test database
python -m pytest tests/test_api_integration.py -v
```

### Automated Testing

For CI/CD pipelines, consider:

1. **Unit tests**: Run on every commit (fast feedback)
2. **Integration tests**: Run on main branch merges
3. **CRUD tests**: Run nightly or weekly (slower, more thorough)

---

## 📋 Quick Reference Commands

```bash
# Setup test database with production data (downloads locally)
./scripts/download-test-db.sh

# Run all tests
python -m pytest tests/ -v

# Run only fast unit tests  
python -m pytest tests/test_fastapi.py tests/test_api_unit.py -v

# Run integration tests (requires test database)
python -m pytest tests/test_api_integration.py -v
```

## Additional Resources

- [pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing Guide](https://fastapi.tiangolo.com/tutorial/testing/)
- [pytest-mock Documentation](https://pytest-mock.readthedocs.io/)
- [Project CLAUDE.md](./CLAUDE.md) - Development commands and architecture