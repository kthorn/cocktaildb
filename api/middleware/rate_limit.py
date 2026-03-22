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
