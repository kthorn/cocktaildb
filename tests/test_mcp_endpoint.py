"""Integration tests for the public MCP endpoint mounted in FastAPI (Docker)"""

import asyncio
import json

import anyio
import pytest
import pytest_asyncio

HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}
EXPECTED_TOOLS = {
    "search_recipes",
    "get_recipe",
    "find_similar_recipes",
    "find_ingredients",
}


async def mcp_post(client, method, params=None, id=1):
    body = {"jsonrpc": "2.0", "id": id, "method": method}
    if params is not None:
        body["params"] = params
    return await client.post("/mcp", json=body, headers=HEADERS)


async def call_tool(client, name, arguments):
    resp = await mcp_post(client, "tools/call", {"name": name, "arguments": arguments})
    assert resp.status_code == 200, resp.text
    return resp.json()["result"]


@pytest_asyncio.fixture
async def mcp_client(test_client_with_data):
    """Client whose test body runs inside `mcp_endpoint.running()`.

    ASGITransport doesn't run lifespan. The endpoint's anyio task group must be
    entered and exited in one task, but pytest-asyncio runs fixture setup and
    teardown in different tasks, so the context is held open by a single
    background task instead of an async-generator fixture.
    """
    client, _app = test_client_with_data
    from api.main import mcp_endpoint

    ready = asyncio.Event()
    stop = asyncio.Event()

    async def hold():
        async with mcp_endpoint.running():
            ready.set()
            await stop.wait()

    task = asyncio.create_task(hold())
    await ready.wait()
    try:
        yield client
    finally:
        stop.set()
        await task


def _base_url():
    from core.config import settings

    return settings.base_url.rstrip("/")


@pytest.mark.asyncio
async def test_tools_list_over_http(mcp_client):
    resp = await mcp_post(mcp_client, "tools/list")
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()["result"]["tools"]}
    assert names == EXPECTED_TOOLS
    for tool in resp.json()["result"]["tools"]:
        assert tool["annotations"]["readOnlyHint"] is True


@pytest.mark.asyncio
async def test_search_recipes_over_http_returns_seeded_recipe(mcp_client):
    result = await call_tool(mcp_client, "search_recipes", {"query": "Old Fashioned"})
    assert not result.get("isError")
    recipes = result["structuredContent"]["recipes"]
    match = [r for r in recipes if r["name"] == "Test Old Fashioned"]
    assert match
    assert match[0]["url"].startswith(f"{_base_url()}/recipe/")


@pytest.mark.asyncio
async def test_get_recipe_over_http_has_no_private_fields(mcp_client):
    result = await call_tool(mcp_client, "get_recipe", {"recipe_id": 1})
    assert not result.get("isError")
    text = json.dumps(result)
    assert "created_by" not in text
    assert "user_rating" not in text
    assert result["structuredContent"]["id"] == 1


@pytest.mark.asyncio
async def test_similar_over_http_with_seeded_similarity_row(mcp_client):
    from db.database import get_database

    get_database().upsert_recipe_similarity_batch(
        [
            {
                "recipe_id": 1,
                "recipe_name": "Test Old Fashioned",
                "neighbors": [
                    {
                        "neighbor_recipe_id": 2,
                        "neighbor_name": "Seeded Neighbor",
                        "distance": 0.25,
                        "transport_plan": [
                            {
                                "from_ingredient_name": "Bourbon",
                                "to_ingredient_name": "Rye",
                                "mass": 0.5,
                            }
                        ],
                    }
                ],
            }
        ]
    )
    result = await call_tool(mcp_client, "find_similar_recipes", {"recipe_id": 1})
    assert not result.get("isError")
    similar = result["structuredContent"]["similar"]
    assert similar[0]["name"] == "Seeded Neighbor"
    assert similar[0]["swaps"][0]["from_ingredient"] == "Bourbon"
    assert similar[0]["swaps"][0]["to_ingredient"] == "Rye"


@pytest.mark.asyncio
async def test_endpoint_restarts_cleanly(test_client_with_data):
    client, _app = test_client_with_data
    from api.main import mcp_endpoint

    for _ in range(2):
        async with mcp_endpoint.running():
            resp = await mcp_post(client, "tools/list")
            assert resp.status_code == 200
            assert {t["name"] for t in resp.json()["result"]["tools"]} == EXPECTED_TOOLS


@pytest.mark.asyncio
async def test_not_running_returns_503_jsonrpc_error(test_client_with_data):
    client, _app = test_client_with_data
    resp = await mcp_post(client, "tools/list")
    assert resp.status_code == 503
    body = resp.json()
    assert body["jsonrpc"] == "2.0"
    assert body["error"]["code"] == -32000


@pytest.mark.asyncio
async def test_root_advertises_mcp(test_client_with_data):
    client, _app = test_client_with_data
    resp = await client.get("/")
    assert resp.json()["mcp"] == "/api/v1/mcp"


@pytest.mark.asyncio
async def test_get_mcp_returns_405_without_opening_stream(mcp_client):
    with anyio.fail_after(2):
        resp = await mcp_client.get("/mcp", headers={"Accept": "text/event-stream"})
    assert resp.status_code == 405


@pytest.mark.asyncio
async def test_delete_mcp_returns_405(mcp_client):
    resp = await mcp_client.delete("/mcp")
    assert resp.status_code == 405
