# AsyncClient Test Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Starlette/FastAPI TestClient usage in tests with httpx.AsyncClient + ASGITransport to avoid sync→async hangs.

**Architecture:** Convert shared fixtures and test modules to async/await with `httpx.AsyncClient` backed by `httpx.ASGITransport(app=app)`. Keep dependency overrides and environment setup intact, but remove the sync bridge entirely. Use `pytest.mark.asyncio` consistently for async test execution.

**Tech Stack:** pytest, pytest-asyncio, httpx AsyncClient + ASGITransport, FastAPI app.

### Task 1: Add httpx test dependency

**Files:**
- Modify: `requirements-test.txt`

**Step 1: Add httpx to test requirements**

```text
httpx>=0.24.0
```

**Step 2: Save file**

### Task 2: Convert shared TestClient fixtures to AsyncClient

**Files:**
- Modify: `tests/conftest.py`

**Step 1: Replace TestClient imports with httpx**

```python
import httpx
from httpx import ASGITransport
```

**Step 2: Convert `test_client_memory_with_app` fixture to async + AsyncClient**

```python
@pytest.fixture(scope="function")
async def test_client_memory_with_app(test_settings, memory_db_with_schema):
    from api.main import app
    app.dependency_overrides.clear()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, app
    app.dependency_overrides.clear()
```

**Step 3: Convert dependent fixtures to async**

```python
@pytest.fixture(scope="function")
async def test_client_memory(test_client_memory_with_app):
    client, app = test_client_memory_with_app
    yield client
```

```python
@pytest.fixture(scope="function")
async def test_client_with_data(test_settings, test_db_with_data):
    from api.main import app
    app.dependency_overrides.clear()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, app
    app.dependency_overrides.clear()
```

**Step 4: Convert auth client fixtures to async**

```python
@pytest.fixture(scope="function")
async def authenticated_client(test_client_memory_with_app, mock_user):
    # override deps as today
    client, app = test_client_memory_with_app
    yield client
    # cleanup overrides
```

(Repeat for `editor_client`, `editor_client_with_data`, `admin_client`.)

### Task 3: Convert test modules to async client usage

**Files:**
- Modify: `tests/test_fastapi.py`
- Modify: `tests/test_pagination.py`
- Modify: `tests/test_substitution_api.py`
- Modify: `tests/test_analytics_em_distances_download.py`

**Step 1: Replace TestClient imports and type hints with httpx.AsyncClient**

```python
import httpx
```

**Step 2: Mark async tests and await client calls**

```python
@pytest.mark.asyncio
async def test_health_endpoint(self, test_client_memory):
    response = await test_client_memory.get("/health")
    ...
```

**Step 3: Convert fixture-scoped client creation in substitution tests**

```python
@pytest.fixture
async def client(self, db_instance):
    app.dependency_overrides[get_database] = lambda: db_instance
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
```

**Step 4: Update analytics download test to use AsyncClient**

```python
transport = ASGITransport(app=app)
async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
    response = await client.get("/analytics/recipe-distances-em/download")
```

### Task 4: Validate test collection

**Files:**
- None

**Step 1: Run targeted test modules**

```bash
pytest tests/test_fastapi.py tests/test_pagination.py tests/test_substitution_api.py tests/test_analytics_em_distances_download.py -v
```

Expected: tests run without hanging; async tests execute normally.

