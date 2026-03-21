# Rate Limiting and Cache Headers Implementation Plan

**Status:** Refined

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Protect the API from being overwhelmed by heavy traffic on a small EC2 instance (2 workers, 10 DB connections).

**Architecture:** Custom `BaseHTTPMiddleware` with a per-IP sliding window using a dict of deques. All requests are rate-limited equally (no auth exemption — simpler and avoids fake-header bypass). `OPTIONS` and `/health` requests are exempt. Cache headers added at the Caddy reverse proxy layer for endpoints that return identical responses regardless of auth status.

**Tech Stack:** Python stdlib only (no new dependency). Caddy path matchers for cache headers.

**Design note:** The design doc specified `slowapi`, but a custom middleware is simpler (~40 lines), has no new dependency, and matches the existing `CORSHeaderMiddleware` pattern. Auth exemption was removed entirely — 60 req/min per IP won't affect normal browser use, and it eliminates the fake-Bearer-header bypass risk.

**Per-worker note:** Rate limiting is per-process. With 2 uvicorn workers, the effective limit is up to ~120 req/min per IP (requests are distributed across workers). This is acceptable for the threat model (preventing instance overload from runaway scrapers).

---

### Task 1: Write rate limiting tests

**Files:**
- Create: `tests/test_rate_limit.py`
- Modify: `tests/conftest.py` (add autouse fixture to reset middleware state)

**Step 1: Add middleware reset fixture to conftest.py**

The `RateLimitMiddleware` stores per-IP request counts in memory. Since the app is a module-level singleton, this state persists across tests. Add an autouse fixture to `tests/conftest.py` that resets middleware state after each test (so the next test starts clean). Add this after the existing `clear_database_cache` fixture:

```python
@pytest.fixture(scope="function", autouse=True)
def reset_rate_limiter():
    """Reset rate limiter state after each test to prevent cross-test 429s"""
    yield
    try:
        from middleware.rate_limit import RateLimitMiddleware
        RateLimitMiddleware.reset_all()
    except (ImportError, AttributeError):
        pass  # Middleware not yet created
```

This calls a class-level reset method that clears all instance state. The `ImportError` catch handles the case where tests run before the middleware module exists (Task 1 runs before Task 2).

**Step 2: Write the test file**

```python
"""Tests for rate limiting middleware"""

import pytest

pytestmark = pytest.mark.asyncio


class TestRateLimiting:
    """Test per-IP rate limiting behavior"""

    async def test_requests_under_limit_succeed(self, test_client_memory):
        """Requests under the rate limit should succeed normally"""
        response = await test_client_memory.get("/stats")
        assert response.status_code == 200

    async def test_rate_limit_headers_present(self, test_client_memory):
        """Responses should include rate limit headers"""
        response = await test_client_memory.get("/stats")
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers

    async def test_rate_limit_remaining_decrements(self, test_client_memory):
        """X-RateLimit-Remaining should decrement with each request"""
        r1 = await test_client_memory.get("/stats")
        r2 = await test_client_memory.get("/stats")
        remaining1 = int(r1.headers["X-RateLimit-Remaining"])
        remaining2 = int(r2.headers["X-RateLimit-Remaining"])
        assert remaining2 == remaining1 - 1

    async def test_returns_429_when_limit_exceeded(self, test_client_memory):
        """Should return 429 when rate limit is exceeded"""
        for _ in range(60):
            await test_client_memory.get("/stats")

        response = await test_client_memory.get("/stats")
        assert response.status_code == 429
        assert "Retry-After" in response.headers
        data = response.json()
        assert "detail" in data

    async def test_health_endpoint_exempt(self, test_client_memory):
        """Health check should not be rate limited"""
        for _ in range(65):
            response = await test_client_memory.get("/health")
        assert response.status_code == 200

    async def test_options_request_exempt(self, test_client_memory):
        """OPTIONS (CORS preflight) should not be rate limited"""
        for _ in range(65):
            response = await test_client_memory.options("/stats")
        assert response.status_code != 429

    async def test_different_ips_have_separate_limits(self, test_client_memory):
        """Different X-Real-IP values should have independent rate limits"""
        # Exhaust limit for IP "1.2.3.4"
        for _ in range(60):
            await test_client_memory.get("/stats", headers={"X-Real-IP": "1.2.3.4"})
        # IP "1.2.3.4" should be limited
        response = await test_client_memory.get(
            "/stats", headers={"X-Real-IP": "1.2.3.4"}
        )
        assert response.status_code == 429
        # IP "5.6.7.8" should still work
        response = await test_client_memory.get(
            "/stats", headers={"X-Real-IP": "5.6.7.8"}
        )
        assert response.status_code == 200


class TestRateLimitHeaders:
    """Test rate limit response header values"""

    async def test_limit_header_value(self, test_client_memory):
        """X-RateLimit-Limit should reflect the configured max"""
        response = await test_client_memory.get("/stats")
        assert response.headers["X-RateLimit-Limit"] == "60"

    async def test_429_response_format(self, test_client_memory):
        """429 response should have correct format"""
        for _ in range(60):
            await test_client_memory.get("/stats")

        response = await test_client_memory.get("/stats")
        assert response.status_code == 429
        assert int(response.headers["Retry-After"]) > 0
        assert response.json()["detail"] == "Rate limit exceeded. Please slow down."

    async def test_429_includes_cors_headers(self, test_client_memory):
        """429 responses should still include CORS headers"""
        for _ in range(60):
            await test_client_memory.get("/stats")

        response = await test_client_memory.get("/stats")
        assert response.status_code == 429
        assert response.headers.get("Access-Control-Allow-Origin") == "*"
```

**Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_rate_limit.py -v`
Expected: FAIL — no rate limiting middleware exists yet, so no 429s or rate limit headers.

**Step 4: Commit**

```bash
git add tests/test_rate_limit.py tests/conftest.py
git commit -m "test: add rate limiting test cases"
```

---

### Task 2: Implement rate limiting middleware

**Files:**
- Create: `api/middleware/__init__.py`
- Create: `api/middleware/rate_limit.py`
- Modify: `api/main.py`

**Step 1: Create the middleware package**

Create empty `api/middleware/__init__.py`.

**Step 2: Write the rate limiting middleware**

Create `api/middleware/rate_limit.py`:

```python
"""Per-IP rate limiting middleware."""

import logging
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Paths exempt from rate limiting
EXEMPT_PATHS = {"/health"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window per-IP rate limiter.

    All requests are rate-limited equally. OPTIONS requests and
    health checks are exempt. Rate limiting is per-process — with
    multiple uvicorn workers, the effective limit per IP is
    max_requests * num_workers.
    """

    CLEANUP_INTERVAL = 100  # Purge stale IPs every N requests
    _instances: list["RateLimitMiddleware"] = []

    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, deque] = defaultdict(deque)
        self._request_count = 0
        RateLimitMiddleware._instances.append(self)

    def reset(self):
        """Clear all rate limit state. Used by test fixtures."""
        self._requests.clear()
        self._request_count = 0

    @classmethod
    def reset_all(cls):
        """Reset all middleware instances. Used by test fixtures."""
        for instance in cls._instances:
            instance.reset()

    def _get_client_ip(self, request: Request) -> str:
        """Client IP from X-Real-IP (set by Caddy) or direct connection."""
        return (
            request.headers.get("x-real-ip")
            or (request.client.host if request.client else "unknown")
        )

    def _cleanup_stale(self, now: float):
        """Remove IPs with no recent requests to prevent memory growth."""
        cutoff = now - self.window_seconds
        stale = [ip for ip, ts in self._requests.items() if not ts or ts[-1] < cutoff]
        for ip in stale:
            del self._requests[ip]

    async def dispatch(self, request: Request, call_next):
        # Exempt OPTIONS (CORS preflight) and health checks
        if request.method == "OPTIONS" or request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        now = time.monotonic()

        # Periodic cleanup
        self._request_count += 1
        if self._request_count % self.CLEANUP_INTERVAL == 0:
            self._cleanup_stale(now)

        # Trim timestamps outside the window
        timestamps = self._requests[client_ip]
        cutoff = now - self.window_seconds
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

        # Reject if over limit
        if len(timestamps) >= self.max_requests:
            retry_after = int(self.window_seconds - (now - timestamps[0])) + 1
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please slow down."},
                headers={"Retry-After": str(max(1, retry_after))},
            )

        # Record request
        timestamps.append(now)

        # Forward and add rate limit headers to response
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(
            self.max_requests - len(timestamps)
        )
        return response
```

**Step 3: Register middleware in main.py**

Starlette processes middleware in reverse registration order: the last middleware added wraps outermost and runs first. We need CORS to wrap outermost so that 429 responses from the rate limiter still pass through CORS and get `Access-Control-Allow-Origin` headers.

To achieve this, register `RateLimitMiddleware` **before** `CORSHeaderMiddleware`. In `api/main.py`:

Add to imports:

```python
from middleware.rate_limit import RateLimitMiddleware
```

Replace the existing CORS middleware registration (line 82):

```python
# app.add_middleware(CORSHeaderMiddleware)  # OLD
```

With:

```python
# Rate limiting first, then CORS wraps outermost (last registered = outermost).
# This ensures 429 responses still get CORS headers.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CORSHeaderMiddleware)
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_rate_limit.py -v`
Expected: All tests PASS.

**Step 5: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All existing tests still pass. The autouse `reset_rate_limiter` fixture clears middleware state after each test, preventing accumulated request counts from triggering 429s.

**Step 6: Commit**

```bash
git add api/middleware/__init__.py api/middleware/rate_limit.py api/main.py
git commit -m "feat: add per-IP rate limiting middleware"
```

---

### Task 3: Add cache headers to Caddy config

Only cache endpoints that return identical responses regardless of authentication status. Endpoints like `/recipes/*` include user-specific fields (`user_rating`, `private_tags`) when a Bearer token is present, so they must NOT be cached as `public`.

**Files:**
- Modify: `infrastructure/caddy/Caddyfile`
- Modify: `infrastructure/ansible/files/Caddyfile.j2`

**Step 1: Add cache header matchers to Caddyfile**

In `infrastructure/caddy/Caddyfile`, inside the main site block (`{$DOMAIN_NAME:localhost}`), add cache header matchers after the existing `@static` matcher and header directive (after line 45, after `header @static Cache-Control "public, max-age=3600"`):

```caddy
    # Cache headers for read-only, non-personalized API responses
    @api_stable {
        method GET
        path /api/v1/stats /api/v1/analytics/ingredient-usage /api/v1/analytics/recipe-complexity /api/v1/analytics/cocktail-space /api/v1/analytics/cocktail-space-em /api/v1/analytics/ingredient-tree /api/v1/analytics/recipe-similar /api/v1/analytics/recipe-distances-em/download
    }
    header @api_stable Cache-Control "public, max-age=3600"

    @api_public_lists {
        method GET
        path /api/v1/units /api/v1/tags/public
    }
    header @api_public_lists Cache-Control "public, max-age=300"

    @api_openapi {
        method GET
        path /api/v1/openapi.json
    }
    header @api_openapi Cache-Control "public, max-age=86400"
```

**Step 2: Add cache header matchers to Caddyfile.j2**

In `infrastructure/ansible/files/Caddyfile.j2`, inside the main site block (`{$DOMAIN_NAME:{{ domain_name }}}`), add the same matchers before the `header {` security headers block (before line 37):

```caddy
    # Cache headers for read-only, non-personalized API responses
    @api_stable {
        method GET
        path /api/v1/stats /api/v1/analytics/ingredient-usage /api/v1/analytics/recipe-complexity /api/v1/analytics/cocktail-space /api/v1/analytics/cocktail-space-em /api/v1/analytics/ingredient-tree /api/v1/analytics/recipe-similar /api/v1/analytics/recipe-distances-em/download
    }
    header @api_stable Cache-Control "public, max-age=3600"

    @api_public_lists {
        method GET
        path /api/v1/units /api/v1/tags/public
    }
    header @api_public_lists Cache-Control "public, max-age=300"

    @api_openapi {
        method GET
        path /api/v1/openapi.json
    }
    header @api_openapi Cache-Control "public, max-age=86400"
```

**Step 3: Validate Caddy config syntax**

Run: `caddy validate --config infrastructure/caddy/Caddyfile 2>&1 || echo "Caddy not installed locally — validate after deploy"`

**Step 4: Commit**

```bash
git add infrastructure/caddy/Caddyfile infrastructure/ansible/files/Caddyfile.j2
git commit -m "feat: add Cache-Control headers for non-personalized API responses"
```

---

### Task 4: Update design doc with implementation notes

**Files:**
- Modify: `docs/plans/2026-03-21-rate-limiting-design.md`

**Step 1: Add implementation note to design doc**

Add a section at the bottom of the design doc:

```markdown
## Implementation notes

Used a custom `RateLimitMiddleware` (in `api/middleware/rate_limit.py`) instead of `slowapi`. A custom middleware is simpler (~50 lines), has no new dependency, and matches the existing `CORSHeaderMiddleware` pattern.

Auth exemption was removed from the original design. 60 req/min per IP doesn't affect normal browser use, and checking for a Bearer header without validating the JWT would allow trivial bypass. All requests are rate-limited equally; `OPTIONS` and `/health` are exempt.

Rate limiting is per-worker (in-memory). With 2 uvicorn workers, the effective limit per IP is up to ~120 req/min. This is acceptable for the threat model (preventing instance overload).

Cache headers are only applied to endpoints that return identical responses regardless of authentication (`/stats`, all analytics endpoints, `/units`, `/tags/public`, `/openapi.json`). Endpoints like `/recipes/*` include user-specific fields (`user_rating`, `private_tags`) and must not be cached as `public`.
```

**Step 2: Commit**

```bash
git add docs/plans/2026-03-21-rate-limiting-design.md
git commit -m "docs: add implementation notes to rate limiting design"
```
