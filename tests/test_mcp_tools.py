"""Unit tests for the MCP tools, using a stubbed Database (no Docker)"""

import os
import sys
import threading
from unittest.mock import MagicMock

import anyio
import anyio.to_thread
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from mcp.server.mcpserver.exceptions import ToolError
from mcp_tools.gate import BUSY_MESSAGE, DbGate
from mcp_tools.server import build_mcp_server

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


def _campari_batch(names):
    return {
        n: {"id": 4, "name": "Campari", "path": "/4/"}
        for n in names
        if n.casefold() == "campari"
    }


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
    db.search_ingredients_batch.side_effect = _campari_batch
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
    db.search_ingredients_batch.side_effect = _campari_batch
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
    db.search_ingredients_batch.return_value = {}
    result = await call(
        server, "search_recipes", {"include_ingredients": ["unobtainium"]}
    )
    db.search_recipes_paginated.assert_not_called()
    assert result["recipes"] == []
    assert result["has_more"] is False
    assert result["unresolved_ingredients"] == ["unobtainium"]


def _recipe(recipe_id, name):
    return {
        "id": recipe_id,
        "name": name,
        "ingredients": [],
        "tags": [],
        "abv": None,
        "avg_rating": None,
        "rating_count": 0,
    }


@pytest.mark.asyncio
async def test_search_query_returns_exact_name_match_separately(server, db):
    db.get_recipe_ids_by_exact_name.return_value = [7]
    db.get_recipe.return_value = _recipe(7, "Negroni")
    db.search_recipes_paginated.return_value = {
        "recipes": [_recipe(3, "Anthony Schmidt's Negroni"), _recipe(7, "Negroni")],
        "has_next": True,
    }
    result = await call(server, "search_recipes", {"query": " negroni "})
    db.get_recipe_ids_by_exact_name.assert_called_once_with("negroni")
    db.get_recipe.assert_called_once_with(7, None)
    assert [r["name"] for r in result["exact_matches"]] == ["Negroni"]
    assert result["exact_matches"][0]["url"] == "https://mixology.tools/recipe/7"
    # The exact match is not repeated in the paged results.
    assert [r["id"] for r in result["recipes"]] == [3]
    assert result["has_more"] is True


@pytest.mark.asyncio
async def test_exact_matches_only_on_first_page_but_always_excluded(server, db):
    db.get_recipe_ids_by_exact_name.return_value = [7]
    db.search_recipes_paginated.return_value = {
        "recipes": [_recipe(7, "Negroni"), _recipe(9, "Negroni Sbagliato")],
        "has_next": False,
    }
    result = await call(server, "search_recipes", {"query": "Negroni", "offset": 10})
    db.get_recipe.assert_not_called()
    assert result["exact_matches"] == []
    assert [r["id"] for r in result["recipes"]] == [9]


@pytest.mark.asyncio
async def test_search_without_query_skips_exact_lookup(server, db):
    db.search_recipes_paginated.return_value = {"recipes": [], "has_next": False}
    result = await call(server, "search_recipes", {"tags": ["classic"]})
    db.get_recipe_ids_by_exact_name.assert_not_called()
    assert result["exact_matches"] == []


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


@pytest.mark.asyncio
async def test_resolution_is_one_batch_call_and_no_per_name_search(server, db):
    db.search_ingredients_batch.side_effect = _campari_batch
    db.search_recipes_paginated.return_value = {"recipes": [], "has_next": False}
    await call(
        server,
        "search_recipes",
        {"include_ingredients": ["campari"], "exclude_ingredients": ["Campari", "x"]},
    )
    assert db.search_ingredients_batch.call_count == 1
    assert db.search_ingredients.call_count == 0


@pytest.mark.asyncio
async def test_duplicate_names_produce_one_spec_each(server, db):
    db.search_ingredients_batch.side_effect = _campari_batch
    db.search_recipes_paginated.return_value = {"recipes": [], "has_next": False}
    await call(
        server,
        "search_recipes",
        {"include_ingredients": ["campari", "CAMPARI", " Campari "]},
    )
    params = db.search_recipes_paginated.call_args.args[0]
    assert params["ingredients"] == ["Campari:MUST"]


@pytest.mark.asyncio
async def test_eleven_item_include_list_is_rejected(server, db):
    err = await call_error(
        server, "search_recipes", {"include_ingredients": ["a"] * 11}
    )
    assert isinstance(err, ToolError)
    db.search_ingredients_batch.assert_not_called()


@pytest.mark.asyncio
async def test_blank_list_item_is_rejected(server, db):
    for field in ("include_ingredients", "exclude_ingredients", "tags"):
        err = await call_error(server, "search_recipes", {field: ["  "]})
        assert isinstance(err, ToolError)


@pytest.mark.asyncio
async def test_overlong_item_and_query_are_rejected(server, db):
    err = await call_error(server, "search_recipes", {"tags": ["x" * 101]})
    assert isinstance(err, ToolError)
    err = await call_error(server, "search_recipes", {"query": "x" * 201})
    assert isinstance(err, ToolError)
    err = await call_error(server, "find_ingredients", {"query": "x" * 201})
    assert isinstance(err, ToolError)
    err = await call_error(server, "find_ingredients", {"query": "   "})
    assert isinstance(err, ToolError)


@pytest.mark.asyncio
async def test_recipe_id_below_one_is_rejected(server, db):
    for name in ("get_recipe", "find_similar_recipes"):
        err = await call_error(server, name, {"recipe_id": 0})
        assert isinstance(err, ToolError)
    db.get_recipe.assert_not_called()
    db.get_recipe_similarity.assert_not_called()


@pytest.mark.asyncio
async def test_descriptions_are_accurate(server):
    tools = {t.name: t for t in await server.list_tools()}
    desc = tools["search_recipes"].description
    assert "name or text" not in desc
    assert "random" in str(tools["search_recipes"].input_schema)


# Built at import time, outside any event loop, as the app will do.
MODULE_LEVEL_GATE = DbGate(1, 0.05)


@pytest.mark.asyncio
async def test_gate_built_outside_loop_works_in_each_loop():
    assert await MODULE_LEVEL_GATE.run(lambda: 41 + 1) == 42


@pytest.mark.asyncio
async def test_gate_built_outside_loop_works_in_a_second_loop():
    assert await MODULE_LEVEL_GATE.run(lambda: "ok") == "ok"


@pytest.mark.asyncio
async def test_gate_times_out_with_busy_message_when_full():
    gate = DbGate(1, 0.05)
    release = threading.Event()
    started = threading.Event()

    def hold():
        started.set()
        release.wait(5)

    async with anyio.create_task_group() as tg:
        tg.start_soon(gate.run, hold)
        await anyio.to_thread.run_sync(started.wait, 5)
        with pytest.raises(ToolError, match="busy") as exc_info:
            await gate.run(lambda: None)
        assert str(exc_info.value) == BUSY_MESSAGE
        release.set()


@pytest.mark.asyncio
async def test_gate_releases_slot_when_function_raises():
    gate = DbGate(1, 0.05)

    def boom():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        await gate.run(boom)
    assert await gate.run(lambda: "after") == "after"


@pytest.mark.asyncio
async def test_gate_caps_concurrency_under_parallel_load():
    gate = DbGate(2, 5.0)
    lock = threading.Lock()
    inside = 0
    peak = 0
    two_inside = threading.Event()

    def work():
        nonlocal inside, peak
        with lock:
            inside += 1
            peak = max(peak, inside)
            if inside == 2:
                two_inside.set()
        # Each worker waits until two are inside at once, so overlap is certain.
        two_inside.wait(5)
        with lock:
            inside -= 1

    async with anyio.create_task_group() as tg:
        for _ in range(8):
            tg.start_soon(gate.run, work)
    assert peak == 2


@pytest.mark.asyncio
async def test_gate_waiters_do_not_occupy_worker_threads():
    gate = DbGate(1, 2.0)
    release = threading.Event()
    started = threading.Event()
    limiter = anyio.to_thread.current_default_thread_limiter()

    def hold():
        started.set()
        release.wait(5)

    async def waiter():
        await gate.run(lambda: None)

    async with anyio.create_task_group() as tg:
        tg.start_soon(gate.run, hold)
        await anyio.to_thread.run_sync(started.wait, 5)
        baseline = limiter.borrowed_tokens
        for _ in range(10):
            tg.start_soon(waiter)
        await anyio.sleep(0.1)
        assert limiter.borrowed_tokens == baseline
        release.set()


@pytest.mark.asyncio
async def test_tool_call_reports_busy_when_gate_is_full(db):
    gate = DbGate(1, 0.05)
    server = build_mcp_server(lambda: db, base_url=BASE, gate=gate)
    release = threading.Event()
    started = threading.Event()

    def hold():
        started.set()
        release.wait(5)

    async with anyio.create_task_group() as tg:
        tg.start_soon(gate.run, hold)
        await anyio.to_thread.run_sync(started.wait, 5)
        err = await call_error(server, "get_recipe", {"recipe_id": 1})
        release.set()
    assert isinstance(err, ToolError)
    assert BUSY_MESSAGE in str(err)
    db.get_recipe.assert_not_called()
