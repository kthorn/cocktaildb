"""ASGI wrapper that serves the MCP streamable-HTTP app inside FastAPI."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

NOT_READY_BODY = {
    "jsonrpc": "2.0",
    "id": None,
    "error": {
        "code": -32000,
        "message": "MCP endpoint is not ready. Please retry shortly.",
    },
}


class McpEndpoint:
    """Mountable ASGI endpoint. Call `running()` around the app lifespan.

    A fresh server is built on every `running()` because a session manager can
    only be run once.
    """

    def __init__(self, server_factory: Callable[[], MCPServer]):
        self._server_factory = server_factory
        self._app: ASGIApp | None = None

    @asynccontextmanager
    async def running(self) -> AsyncIterator[None]:
        server = self._server_factory()
        app = server.streamable_http_app(
            streamable_http_path="/mcp",
            stateless_http=True,
            json_response=True,
            # Public endpoint by design; Host/Origin checks would reject real clients.
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=False
            ),
        )
        async with server.session_manager.run():
            self._app = app
            try:
                yield
            finally:
                self._app = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        app = self._app
        if app is None:
            await JSONResponse(NOT_READY_BODY, status_code=503)(scope, receive, send)
            return
        if scope["type"] == "http" and scope.get("path") == "/mcp/":
            # Serve /mcp/ like /mcp (a redirect would drop Caddy's /api/v1 prefix).
            scope = {**scope, "path": "/mcp"}
            raw_path = scope.get("raw_path")
            if raw_path is not None:
                scope["raw_path"] = raw_path.removesuffix(b"/")
        await app(scope, receive, send)
