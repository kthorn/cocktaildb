"""Unit tests for the MCP tools, using a stubbed Database (no Docker)"""

import os
import sys
import threading
import time
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from mcp.server.mcpserver.exceptions import ToolError
from mcp_tools.gate import BUSY_MESSAGE, DbGate
from mcp_tools.server import build_mcp_server, resolve_ingredient_name

BASE = "https://mixology.tools"


@pytest.fixture
def db():
    return MagicMock()


@pytest.fixture
def server(db):
    return build_mcp_server(lambda: db, base_url=BASE, gate=DbGate(2, 0.05))


async def call(server, name, args):
    """Return structured content; tool errors and bad arguments raise ToolError."""
    result = await server.call_tool(name, args)
    return result.structured_content


async def call_error(server, name, args):
    with pytest.raises(Exception) as exc_info:
        await server.call_tool(name, args)
    return exc_info.value


def _campari_lookup(name):
    if name.lower() == "campari":
        return [{"id": 4, "name": "Campari", "path": "/4/"}]
    return []


@pytest.mark.asyncio
async def test_lists_exactly_four_read_only_tools(server):
    tools = await server.list_tools()
    assert {t.name for t in tools} == {
        "search_recipes",
        "get_recipe",
        "find_similar_recipes",
        "find_ingredients",
    }
    assert all(t.annotations.read_only_hint for t in tools)
    assert all(t.annotations.open_world_hint is False for t in tools)
    assert all(t.description for t in tools)


@pytest.mark.asyncio
async def test_search_resolves_names_case_insensitively(server, db):
    db.search_ingredients.side_effect = _campari_lookup
    db.search_recipes_paginated.return_value = {
        "recipes": [],
        "has_next": False,
        "next_cursor": None,
    }
    result = await call(
        server,
        "search_recipes",
        {"include_ingredients": ["campari"], "exclude_ingredients": ["nope"]},
    )
    params = db.search_recipes_paginated.call_args.args[0]
    assert params["ingredients"] == ["Campari:MUST"]
    assert result["unresolved_ingredients"] == ["nope"]


@pytest.mark.asyncio
async def test_search_builds_must_not_and_other_filters(server, db):
    db.search_ingredients.side_effect = _campari_lookup
    db.search_recipes_paginated.return_value = {"recipes": [], "has_next": True}
    result = await call(
        server,
        "search_recipes",
        {
            "query": "negroni",
            "exclude_ingredients": ["Campari"],
            "tags": ["classic"],
            "min_abv": 10,
            "max_abv": 30,
            "limit": 5,
            "offset": 5,
        },
    )
    params = db.search_recipes_paginated.call_args.args[0]
    assert params == {
        "q": "negroni",
        "ingredients": ["Campari:MUST_NOT"],
        "tags": ["classic"],
        "min_abv": 10,
        "max_abv": 30,
    }
    kwargs = db.search_recipes_paginated.call_args.kwargs
    assert kwargs["limit"] == 5 and kwargs["offset"] == 5
    assert result["has_more"] is True and result["offset"] == 5


@pytest.mark.asyncio
async def test_search_with_unresolved_include_returns_empty_without_querying(
    server, db
):
    db.search_ingredients.return_value = []
    result = await call(
        server, "search_recipes", {"include_ingredients": ["unobtainium"]}
    )
    db.search_recipes_paginated.assert_not_called()
    assert result["recipes"] == []
    assert result["has_more"] is False
    assert result["unresolved_ingredients"] == ["unobtainium"]


@pytest.mark.asyncio
async def test_search_sort_rating_maps_to_avg_rating_desc(server, db):
    db.search_recipes_paginated.return_value = {"recipes": [], "has_next": False}
    await call(server, "search_recipes", {"sort": "rating"})
    kwargs = db.search_recipes_paginated.call_args.kwargs
    assert kwargs["sort_by"] == "avg_rating"
    assert kwargs["sort_order"] == "desc"
    assert kwargs["user_id"] is None
    assert kwargs["return_pagination"] is True


@pytest.mark.asyncio
async def test_search_sort_random(server, db):
    db.search_recipes_paginated.return_value = {"recipes": [], "has_next": False}
    await call(server, "search_recipes", {"sort": "random"})
    kwargs = db.search_recipes_paginated.call_args.kwargs
    assert (kwargs["sort_by"], kwargs["sort_order"]) == ("random", "asc")


@pytest.mark.asyncio
async def test_search_rejects_min_abv_above_max(server, db):
    err = await call_error(server, "search_recipes", {"min_abv": 40, "max_abv": 10})
    assert isinstance(err, ToolError)
    db.search_recipes_paginated.assert_not_called()


@pytest.mark.asyncio
async def test_search_limit_above_25_is_rejected(server, db):
    err = await call_error(server, "search_recipes", {"limit": 26})
    assert isinstance(err, ToolError)
    db.search_recipes_paginated.assert_not_called()


@pytest.mark.asyncio
async def test_get_recipe_unknown_id_is_tool_error_mentioning_search_recipes(
    server, db
):
    db.get_recipe.return_value = None
    err = await call_error(server, "get_recipe", {"recipe_id": 999})
    assert isinstance(err, ToolError)
    assert "search_recipes" in str(err) and "999" in str(err)


@pytest.mark.asyncio
async def test_get_recipe_passes_no_user(server, db):
    db.get_recipe.return_value = {
        "id": 3,
        "name": "Negroni",
        "ingredients": [],
        "created_by": "someone",
    }
    result = await call(server, "get_recipe", {"recipe_id": 3})
    db.get_recipe.assert_called_once_with(3, None)
    assert result["name"] == "Negroni"
    assert "created_by" not in result


@pytest.mark.asyncio
async def test_similar_missing_row_is_tool_error(server, db):
    db.get_recipe_similarity.return_value = None
    err = await call_error(server, "find_similar_recipes", {"recipe_id": 5})
    assert isinstance(err, ToolError)
    assert "isn't available" in str(err)


@pytest.mark.asyncio
async def test_similar_returns_limited_neighbors(server, db):
    db.get_recipe_similarity.return_value = {
        "recipe_id": 5,
        "recipe_name": "Boulevardier",
        "neighbors": [
            {"neighbor_recipe_id": n, "neighbor_name": f"R{n}", "distance": n / 10}
            for n in (1, 2, 3)
        ],
    }
    result = await call(server, "find_similar_recipes", {"recipe_id": 5, "limit": 2})
    assert [s["id"] for s in result["similar"]] == [1, 2]


@pytest.mark.asyncio
async def test_find_ingredients_returns_hierarchy_names(server, db):
    db.search_ingredients.return_value = [
        {
            "id": 8,
            "name": "Bourbon",
            "path": "/1/8/",
            "description": None,
            "percent_abv": 45.0,
        }
    ]
    db.get_ingredient_names.return_value = {1: "Whiskey", 8: "Bourbon"}
    result = await call(server, "find_ingredients", {"query": "bourbon"})
    item = result["ingredients"][0]
    assert item["hierarchy"] == ["Whiskey", "Bourbon"]
    assert item["url"].endswith("/ingredient/8")
    db.get_ingredient_names.assert_called_once()


@pytest.mark.asyncio
async def test_find_ingredients_rejects_empty_query(server):
    err = await call_error(server, "find_ingredients", {"query": ""})
    assert isinstance(err, ToolError)


@pytest.mark.asyncio
async def test_unexpected_db_error_hides_detail(server, db):
    db.get_recipe.side_effect = RuntimeError("password=secret")
    err = await call_error(server, "get_recipe", {"recipe_id": 1})
    assert "secret" not in str(err)


def test_resolve_ingredient_name_picks_exact_casefold_match():
    db = MagicMock()
    db.search_ingredients.return_value = [
        {"id": 1, "name": "Rye Whiskey Blend"},
        {"id": 2, "name": "Rye Whiskey"},
    ]
    assert resolve_ingredient_name(db, " rye whiskey ") == "Rye Whiskey"
    db.search_ingredients.return_value = [{"id": 1, "name": "Rye Whiskey Blend"}]
    assert resolve_ingredient_name(db, "rye") is None


def test_gate_times_out_with_busy_message_when_full():
    gate = DbGate(1, 0.05)
    with gate.slot():
        with pytest.raises(ToolError, match="busy") as exc_info:
            with gate.slot():
                pass
    assert str(exc_info.value) == BUSY_MESSAGE


def test_gate_caps_concurrency_under_parallel_load():
    gate = DbGate(2, 1.0)
    lock = threading.Lock()
    inside = 0
    peak = 0

    def worker():
        nonlocal inside, peak
        with gate.slot():
            with lock:
                inside += 1
                peak = max(peak, inside)
            time.sleep(0.02)
            with lock:
                inside -= 1

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak == 2
