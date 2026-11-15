"""Blocking database work must not stall the event loop for other requests."""

import asyncio
import inspect
import time

import anyio.to_thread
import httpx
import pytest
from httpx import ASGITransport

SLOW_SECONDS = 0.5


class SlowSearchDatabase:
    """Stands in for Database: search blocks like a slow psycopg2 query."""

    events: dict[str, float] = {}

    def search_recipes_paginated(self, **_kwargs):
        self.events["search_started"] = time.monotonic()
        time.sleep(SLOW_SECONDS)
        self.events["search_finished"] = time.monotonic()
        return {"recipes": [], "has_next": False, "next_cursor": None}

    def get_units(self):
        self.events["units_served"] = time.monotonic()
        return []


@pytest.mark.asyncio
async def test_slow_search_does_not_block_other_requests(test_settings):
    from db.database import get_database

    from api.main import app

    events = SlowSearchDatabase.events
    events.clear()
    app.dependency_overrides[get_database] = SlowSearchDatabase
    try:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            slow = asyncio.create_task(c.get("/recipes/search"))
            # If the search blocks the event loop, this poll only resumes
            # after the search has finished.
            while "search_started" not in events:
                await asyncio.sleep(0.005)
            units = await c.get("/units")
            assert (await slow).status_code == 200
    finally:
        app.dependency_overrides.pop(get_database, None)

    assert units.status_code == 200
    assert events["units_served"] < events["search_finished"]


def _uses_database(dependant, get_database) -> bool:
    return any(
        dep.call is get_database or _uses_database(dep, get_database)
        for dep in dependant.dependencies
    )


def _api_routes(routes):
    """Every APIRoute, including those inside included routers.

    Newer FastAPI keeps each include_router as a nested route (exposing
    original_router) instead of copying its routes into app.routes.
    """
    from fastapi.routing import APIRoute

    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        elif (nested := getattr(route, "original_router", None)) is not None:
            yield from _api_routes(nested.routes)


def test_database_route_handlers_are_sync():
    """psycopg2 blocks, so handlers using it must run in FastAPI's threadpool."""
    from db.database import get_database

    from api.main import app

    db_routes = [
        route
        for route in _api_routes(app.routes)
        if _uses_database(route.dependant, get_database)
    ]
    assert len(db_routes) > 40
    async_routes = [
        f"{sorted(route.methods)} {route.path}"
        for route in db_routes
        if inspect.iscoroutinefunction(route.endpoint)
    ]
    assert async_routes == []


@pytest.mark.asyncio
async def test_threadpool_cannot_exhaust_connection_pool():
    from db.db_core import Database

    from api.main import configure_threadpool

    configure_threadpool()

    limiter = anyio.to_thread.current_default_thread_limiter()
    assert (
        limiter.total_tokens * Database.MAX_CONNECTIONS_PER_REQUEST
        <= Database.POOL_MAX_CONNECTIONS
    )


def test_concurrent_first_requests_share_one_database(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from db import database

    built = []

    class SlowDatabase:
        def __init__(self):
            time.sleep(0.05)
            built.append(self)

    monkeypatch.setattr(database, "Database", SlowDatabase)
    monkeypatch.setattr(database, "_DB_INSTANCE", None)
    with ThreadPoolExecutor(max_workers=8) as pool:
        instances = list(pool.map(lambda _: database.get_database(), range(8)))

    assert len(built) == 1
    assert all(instance is built[0] for instance in instances)
