"""Cap on concurrent MCP database work.

The psycopg2 pool raises when empty instead of waiting, so MCP tool calls take
a slot here first and leave connections free for the website. Callers wait for
a slot in the event loop, not in a worker thread, so a full gate never ties up
the shared threadpool the website's sync routes use.
"""

import asyncio
import weakref
from collections.abc import Callable
from typing import TypeVar

import anyio
import anyio.to_thread
from mcp.server.mcpserver.exceptions import ToolError

BUSY_MESSAGE = "Mixology Tools is busy right now. Please retry in a few seconds."

T = TypeVar("T")


class DbGate:
    def __init__(self, max_concurrent: int, timeout_seconds: float):
        self._max_concurrent = max_concurrent
        self._timeout = timeout_seconds
        # Semaphores are bound to an event loop, so create one lazily per running
        # loop. This lets the gate be built at import time, before any loop exists.
        self._semaphores: weakref.WeakKeyDictionary[
            asyncio.AbstractEventLoop, anyio.Semaphore
        ] = weakref.WeakKeyDictionary()

    def _semaphore(self) -> anyio.Semaphore:
        loop = asyncio.get_running_loop()
        semaphore = self._semaphores.get(loop)
        if semaphore is None:
            semaphore = anyio.Semaphore(self._max_concurrent)
            self._semaphores[loop] = semaphore
        return semaphore

    async def run(self, fn: Callable[..., T], *args) -> T:
        """Run blocking `fn(*args)` in a worker thread while holding a slot."""
        semaphore = self._semaphore()
        try:
            with anyio.fail_after(self._timeout):
                await semaphore.acquire()
        except TimeoutError:
            raise ToolError(BUSY_MESSAGE) from None
        try:
            return await anyio.to_thread.run_sync(fn, *args)
        finally:
            semaphore.release()
