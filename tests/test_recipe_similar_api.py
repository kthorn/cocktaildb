import json

import httpx
import psycopg2
import pytest
from httpx import ASGITransport


def _insert_recipe_similarity(conn_params, recipe_id, recipe_name, neighbors):
    conn = psycopg2.connect(**conn_params)
    conn.autocommit = True
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO recipes (id, name)
        VALUES (%s, %s)
        ON CONFLICT (id) DO NOTHING
        """,
        (recipe_id, recipe_name),
    )
    cursor.execute(
        """
        INSERT INTO recipe_similarity (recipe_id, recipe_name, neighbors)
        VALUES (%s, %s, %s)
        ON CONFLICT (recipe_id) DO UPDATE SET
            recipe_name = EXCLUDED.recipe_name,
            neighbors = EXCLUDED.neighbors
        """,
        (recipe_id, recipe_name, json.dumps(neighbors)),
    )

    cursor.close()
    conn.close()


@pytest.mark.asyncio
async def test_get_recipe_similar_returns_entry(set_pg_env):
    _insert_recipe_similarity(
        set_pg_env,
        1,
        "One",
        [
            {
                "neighbor_recipe_id": 2,
                "neighbor_name": "Two",
                "distance": 0.1,
                "transport_plan": [
                    {
                        "from_ingredient_id": 10,
                        "from_ingredient_name": "Lillet",
                        "to_ingredient_id": 11,
                        "to_ingredient_name": "Cocchi Americano",
                        "mass": 0.4,
                    }
                ],
            }
        ],
    )

    from api.main import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/analytics/recipe-similar", params={"recipe_id": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["recipe_id"] == 1
    assert body["recipe_name"] == "One"
    assert body["neighbors"][0]["neighbor_recipe_id"] == 2


@pytest.mark.asyncio
async def test_get_recipe_similar_includes_transport_names(set_pg_env):
    _insert_recipe_similarity(
        set_pg_env,
        1,
        "One",
        [
            {
                "neighbor_recipe_id": 2,
                "neighbor_name": "Two",
                "distance": 0.1,
                "transport_plan": [
                    {
                        "from_ingredient_id": 10,
                        "from_ingredient_name": "Lillet",
                        "to_ingredient_id": 11,
                        "to_ingredient_name": "Cocchi Americano",
                        "mass": 0.4,
                    }
                ],
            }
        ],
    )

    from api.main import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/analytics/recipe-similar", params={"recipe_id": 1})

    assert response.status_code == 200
    body = response.json()
    transport_plan = body["neighbors"][0]["transport_plan"][0]
    assert transport_plan["from_ingredient_name"] == "Lillet"
    assert transport_plan["to_ingredient_name"] == "Cocchi Americano"


@pytest.mark.asyncio
async def test_get_recipe_similar_returns_404_for_missing_recipe(set_pg_env):
    _insert_recipe_similarity(set_pg_env, 1, "One", [])

    from api.main import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/analytics/recipe-similar", params={"recipe_id": 2})

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_recipe_similar_respects_limit_param(set_pg_env):
    _insert_recipe_similarity(
        set_pg_env,
        11,
        "Eleven",
        [
            {"neighbor_recipe_id": 1, "neighbor_name": "One", "distance": 0.4},
            {"neighbor_recipe_id": 2, "neighbor_name": "Two", "distance": 0.1},
            {"neighbor_recipe_id": 3, "neighbor_name": "Three", "distance": 0.9},
            {"neighbor_recipe_id": 4, "neighbor_name": "Four", "distance": 0.2},
            {"neighbor_recipe_id": 5, "neighbor_name": "Five", "distance": 0.3},
            {"neighbor_recipe_id": 6, "neighbor_name": "Six", "distance": 0.8},
        ],
    )

    from api.main import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/analytics/recipe-similar",
            params={"recipe_id": 11, "limit": 3},
        )

    assert response.status_code == 200
    body = response.json()
    distances = [neighbor["distance"] for neighbor in body["neighbors"]]
    assert len(distances) == 3
    assert distances == sorted(distances)
