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
