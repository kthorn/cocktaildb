"""Cap on concurrent MCP database work.

The psycopg2 pool raises when empty instead of waiting, so MCP tool calls take
a slot here first and leave connections free for the website.
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from mcp.server.mcpserver.exceptions import ToolError

BUSY_MESSAGE = "Mixology Tools is busy right now. Please retry in a few seconds."


class DbGate:
    def __init__(self, max_concurrent: int, timeout_seconds: float):
        self._semaphore = threading.BoundedSemaphore(max_concurrent)
        self._timeout = timeout_seconds

    @contextmanager
    def slot(self) -> Iterator[None]:
        if not self._semaphore.acquire(timeout=self._timeout):
            raise ToolError(BUSY_MESSAGE)
        try:
            yield
        finally:
            self._semaphore.release()
