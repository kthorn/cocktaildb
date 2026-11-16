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


def _small_app():
    from middleware.rate_limit import RateLimitMiddleware
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    async def ok(request):
        return PlainTextResponse("ok")

    app = Starlette(
        routes=[
            Route("/stats", ok),
            Route("/mcp", ok, methods=["GET", "POST"]),
            Route("/mcp/", ok, methods=["GET", "POST"]),
        ]
    )
    app.add_middleware(RateLimitMiddleware, max_requests=2, mcp_max_requests=3)
    return app


def _client(app):
    import httpx

    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    )


class TestMcpBucket:
    async def test_mcp_and_api_buckets_are_independent(self):
        async with _client(_small_app()) as c:
            ip = {"X-Real-IP": "1.1.1.1"}
            api = [(await c.get("/stats", headers=ip)).status_code for _ in range(3)]
            assert api == [200, 200, 429]
            mcp = [(await c.get("/mcp", headers=ip)).status_code for _ in range(4)]
            assert mcp == [200, 200, 200, 429]
            # /mcp exhaustion does not affect a fresh IP's /stats
            fresh = await c.get("/stats", headers={"X-Real-IP": "2.2.2.2"})
            assert fresh.status_code == 200

    async def test_trailing_slash_counts_against_mcp_bucket(self):
        async with _client(_small_app()) as c:
            ip = {"X-Real-IP": "3.3.3.3"}
            codes = []
            for path in ("/mcp", "/mcp/", "/mcp", "/mcp/"):
                codes.append((await c.get(path, headers=ip)).status_code)
            assert codes == [200, 200, 200, 429]

    async def test_mcp_exhaustion_leaves_api_remaining(self):
        async with _client(_small_app()) as c:
            ip = {"X-Real-IP": "3.3.3.3"}
            for _ in range(4):
                await c.get("/mcp", headers=ip)
            r = await c.get("/stats", headers=ip)
            assert r.status_code == 200
            assert r.headers["X-RateLimit-Limit"] == "2"
            assert r.headers["X-RateLimit-Remaining"] == "1"

    async def test_mcp_headers_reflect_mcp_bucket(self):
        async with _client(_small_app()) as c:
            r = await c.get("/mcp")
            assert r.headers["X-RateLimit-Limit"] == "3"
            assert r.headers["X-RateLimit-Remaining"] == "2"

    async def test_mcp_429_is_jsonrpc_shaped(self):
        async with _client(_small_app()) as c:
            for _ in range(3):
                await c.get("/mcp")
            r = await c.get("/mcp")
            assert r.status_code == 429
            assert "Retry-After" in r.headers
            body = r.json()
            assert body["jsonrpc"] == "2.0"
            assert body["id"] is None
            assert body["error"]["code"] == -32000
            assert "Rate limit exceeded" in body["error"]["message"]

    async def test_options_exempt_for_mcp(self):
        async with _client(_small_app()) as c:
            for _ in range(5):
                assert (await c.options("/mcp")).status_code != 429

    async def test_app_uses_configured_mcp_limit(self, test_client_memory):
        from middleware.rate_limit import RateLimitMiddleware

        from api.main import app

        await test_client_memory.get("/health")  # builds the middleware stack
        layer = app.middleware_stack
        found = None
        while layer is not None:
            if isinstance(layer, RateLimitMiddleware):
                found = layer
                break
            layer = getattr(layer, "app", None)
        assert found is not None
        assert found.mcp_max_requests == 300
