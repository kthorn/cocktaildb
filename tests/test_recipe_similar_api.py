import httpx
import pytest
from httpx import ASGITransport

from api.utils.analytics_cache import AnalyticsStorage


@pytest.mark.asyncio
async def test_get_recipe_similar_returns_entry(tmp_path):
    storage = AnalyticsStorage(str(tmp_path))
    storage.put_analytics(
        "recipe-similar",
        [
            {
                "recipe_id": 1,
                "recipe_name": "One",
                "neighbors": [
                    {
                        "neighbor_recipe_id": 2,
                        "neighbor_name": "Two",
                        "distance": 0.1,
                        "transport_plan": [
                            {
                                "from_ingredient_id": 10,
                                "to_ingredient_id": 11,
                                "mass": 0.4,
                            }
                        ],
                    }
                ],
            }
        ],
    )

    from routes import analytics as analytics_routes

    analytics_routes.storage_manager = storage

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
async def test_get_recipe_similar_returns_404_for_missing_recipe(tmp_path):
    storage = AnalyticsStorage(str(tmp_path))
    storage.put_analytics(
        "recipe-similar",
        [
            {
                "recipe_id": 1,
                "recipe_name": "One",
                "neighbors": [],
            }
        ],
    )

    from routes import analytics as analytics_routes

    analytics_routes.storage_manager = storage

    from api.main import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/analytics/recipe-similar", params={"recipe_id": 2})

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_recipe_similar_respects_limit_param(tmp_path):
    storage = AnalyticsStorage(str(tmp_path))
    storage.put_analytics(
        "recipe-similar",
        [
            {
                "recipe_id": 11,
                "recipe_name": "Eleven",
                "neighbors": [
                    {"neighbor_recipe_id": 1, "neighbor_name": "One", "distance": 0.4},
                    {"neighbor_recipe_id": 2, "neighbor_name": "Two", "distance": 0.1},
                    {"neighbor_recipe_id": 3, "neighbor_name": "Three", "distance": 0.9},
                    {"neighbor_recipe_id": 4, "neighbor_name": "Four", "distance": 0.2},
                    {"neighbor_recipe_id": 5, "neighbor_name": "Five", "distance": 0.3},
                    {"neighbor_recipe_id": 6, "neighbor_name": "Six", "distance": 0.8},
                ],
            }
        ],
    )

    from routes import analytics as analytics_routes

    analytics_routes.storage_manager = storage

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
