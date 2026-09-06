"""Page route contracts that do not require a running database."""

from unittest.mock import Mock

import httpx
import pytest
from fastapi import FastAPI

from routes import pages


@pytest.fixture
def page_app():
    db = Mock()
    app = FastAPI()
    app.include_router(pages.router)
    app.dependency_overrides[pages.get_database] = lambda: db
    return app, db


@pytest.mark.asyncio
async def test_name_redirect_uses_database_query_and_list(page_app):
    app, db = page_app
    db.search_recipes_paginated.return_value = [{"id": 42}]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/recipe/by-name", params={"name": "Negroni"})
    assert response.status_code == 302
    assert response.headers["location"] == "/recipe/42"
    db.search_recipes_paginated.assert_called_once_with(
        search_params={"q": "Negroni"}, limit=1, offset=0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("outside_repo", [False, True])
@pytest.mark.parametrize(
    "url", ["/recipe/42", "/ingredient/42", "/recipe/by-name?name=missing"]
)
async def test_missing_pages_render_from_any_working_directory(
    page_app, monkeypatch, tmp_path, outside_repo, url
):
    app, db = page_app
    db.get_recipe.return_value = None
    db.get_ingredient.return_value = None
    db.search_recipes_paginated.return_value = []
    if outside_repo:
        monkeypatch.chdir(tmp_path)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(url)
    assert response.status_code == 404
    assert "text/html" in response.headers["content-type"]
    assert "not found" in response.text.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["/recipe/42", "/ingredient/42"])
async def test_existing_pages_render_outside_repository(
    page_app, monkeypatch, tmp_path, url
):
    app, db = page_app
    db.get_recipe.return_value = {"id": 42, "name": "Example recipe"}
    db.get_recipe_similarity.return_value = None
    db.get_ingredient.return_value = {"id": 42, "name": "Example ingredient"}
    db.get_ingredients.return_value = []
    monkeypatch.chdir(tmp_path)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(url)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Example" in response.text
    assert "application/ld+json" in response.text
