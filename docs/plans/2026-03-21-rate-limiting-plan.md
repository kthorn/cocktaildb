# Rate Limiting and Cache Headers Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Protect the API from being overwhelmed by unauthenticated traffic while keeping authenticated users unrestricted.

**Architecture:** Custom `BaseHTTPMiddleware` with a per-IP sliding window using a dict of deques. Authenticated requests (Bearer token in Authorization header) are exempt. Cache headers added at the Caddy reverse proxy layer.

**Tech Stack:** Python stdlib only (no new dependency). Caddy path matchers for cache headers.

**Design note:** The design doc specified `slowapi`, but after investigation, `slowapi` doesn't cleanly support request-level auth exemptions. A custom middleware is simpler (~40 lines), has no new dependency, and matches the existing `CORSHeaderMiddleware` pattern.

---

### Task 1: Write rate limiting tests

**Files:**
- Create: `tests/test_rate_limit.py`

**Step 1: Write the test file**

```python
"""Tests for rate limiting middleware"""

import pytest

pytestmark = pytest.mark.asyncio


class TestRateLimiting:
    """Test rate limiting behavior for unauthenticated requests"""

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
        # The default limit is 60/min, but the test client shares an IP.
        # We need to send enough requests to exceed the limit.
        for i in range(60):
            await test_client_memory.get("/stats")

        response = await test_client_memory.get("/stats")
        assert response.status_code == 429
        assert "Retry-After" in response.headers
        data = response.json()
        assert "detail" in data

    async def test_authenticated_requests_exempt(self, authenticated_client):
        """Authenticated requests (Bearer token) should bypass rate limiting"""
        # Send more than the rate limit
        for i in range(65):
            response = await authenticated_client.get("/units")
        # Should still succeed - not rate limited
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
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_rate_limit.py -v`
Expected: FAIL — no rate limiting middleware exists yet, so no 429s or rate limit headers.

**Step 3: Commit**

```bash
git add tests/test_rate_limit.py
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
"""Per-IP rate limiting middleware with auth exemption."""

import logging
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter. Authenticated requests (Bearer token) are exempt."""

    CLEANUP_INTERVAL = 100  # Purge stale IPs every N requests

    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, deque] = defaultdict(deque)
        self._request_count = 0

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
        # Exempt authenticated requests
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
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

Add import and `app.add_middleware(RateLimitMiddleware)` after the existing CORS middleware line in `api/main.py`. Rate limit middleware should be added before CORS so it runs after CORS in the middleware stack (Starlette processes middleware in reverse registration order).

In `api/main.py`, add to imports:

```python
from middleware.rate_limit import RateLimitMiddleware
```

After `app.add_middleware(CORSHeaderMiddleware)` (line 82), add:

```python
app.add_middleware(RateLimitMiddleware)
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_rate_limit.py -v`
Expected: All tests PASS.

**Step 5: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All existing tests still pass. The rate limit is 60/min per IP and no existing test sends more than 60 requests.

**Step 6: Commit**

```bash
git add api/middleware/__init__.py api/middleware/rate_limit.py api/main.py
git commit -m "feat: add per-IP rate limiting middleware with auth exemption"
```

---

### Task 3: Add cache headers to Caddy config

**Files:**
- Modify: `infrastructure/caddy/Caddyfile`
- Modify: `infrastructure/ansible/files/Caddyfile.j2`

**Step 1: Add cache header matchers to Caddyfile**

In `infrastructure/caddy/Caddyfile`, inside the main site block (`{$DOMAIN_NAME:localhost}`), add cache header matchers after the existing `@static` matcher (after line 45). Use compound matchers to only cache GET requests:

```caddy
    # Cache headers for read-only API responses
    @api_stable {
        method GET
        path /api/v1/stats /api/v1/analytics/*
    }
    header @api_stable Cache-Control "public, max-age=3600"

    @api_resources {
        method GET
        path /api/v1/recipes/* /api/v1/ingredients/* /api/v1/units /api/v1/tags/public /api/v1/ratings/*
    }
    header @api_resources Cache-Control "public, max-age=300"

    @api_openapi {
        method GET
        path /api/v1/openapi.json
    }
    header @api_openapi Cache-Control "public, max-age=86400"
```

**Step 2: Apply the same changes to the Ansible template**

Apply identical matchers to `infrastructure/ansible/files/Caddyfile.j2` inside the main site block, in the same position relative to existing directives.

**Step 3: Commit**

```bash
git add infrastructure/caddy/Caddyfile infrastructure/ansible/files/Caddyfile.j2
git commit -m "feat: add Cache-Control headers for read-only API responses"
```

---

### Task 4: Update design doc with implementation notes

**Files:**
- Modify: `docs/plans/2026-03-21-rate-limiting-design.md`

**Step 1: Add implementation note to design doc**

Add a section at the bottom of the design doc noting the deviation from `slowapi` to custom middleware and why:

```markdown
## Implementation notes

Used a custom `RateLimitMiddleware` (in `api/middleware/rate_limit.py`) instead of `slowapi`. The auth exemption requirement — skip rate limiting entirely when a Bearer token is present — doesn't map cleanly to slowapi's per-route decorator model. A custom middleware is simpler (~50 lines), has no new dependency, and matches the existing `CORSHeaderMiddleware` pattern.
```

**Step 2: Commit**

```bash
git add docs/plans/2026-03-21-rate-limiting-design.md
git commit -m "docs: add implementation notes to rate limiting design"
```
