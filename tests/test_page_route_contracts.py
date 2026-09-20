"""Page route contracts that do not require a running database."""

from unittest.mock import Mock

import httpx
import pytest
from fastapi import FastAPI
from routes import pages

# Reject the legacy call order on older Starlette too; 1.x no longer accepts it.
pytestmark = pytest.mark.filterwarnings(
    "error:The `name` is not the first parameter anymore:DeprecationWarning"
)


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
async def test_revolver_page_renders_with_request_first_template_api(page_app):
    app, db = page_app
    db.get_recipe.return_value = {"id": 1025, "name": "Revolver"}
    db.get_recipe_similarity.return_value = None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/recipe/1025")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Revolver" in response.text
    assert "application/ld+json" in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "display", "notes"),
    [
        ("calculated", "27%", []),
        ("estimated", "Estimated 20–30%", ["<script>alert(1)</script>: 1 mL rinse"]),
        ("unknown", "Unknown", ["Ingredient volume unavailable"]),
        ("estimated", "Estimated <1%", ["Single family observation"]),
    ],
)
async def test_recipe_abv_renders_backend_display_and_safe_notes(
    page_app, status, display, notes
):
    from html import escape

    app, db = page_app
    db.get_recipe.return_value = {
        "id": 42,
        "name": "Test drink",
        "ingredients": [],
        "abv": {"status": status, "display": display, "notes": notes},
    }
    db.get_recipe_similarity.return_value = None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/recipe/42")
    assert response.status_code == 200
    assert "ABV before dilution" in response.text
    assert escape(display) in response.text
    assert ("<summary>Calculation notes</summary>" in response.text) == bool(notes)
    for note in notes:
        assert escape(note) in response.text
    assert "<script>alert(1)</script>" not in response.text
    assert '"nutrition"' not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("include_null", [False, True])
async def test_recipe_without_abv_omits_display(page_app, include_null):
    app, db = page_app
    recipe = {"id": 42, "name": "Legacy drink"}
    if include_null:
        recipe["abv"] = None
    db.get_recipe.return_value = recipe
    db.get_recipe_similarity.return_value = None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/recipe/42")
    assert response.status_code == 200
    assert "ABV before dilution" not in response.text


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

    assert response.text.count('name="viewport"') == 1
    assert 'href="/normalize.css"' in response.text
    assert 'href="/styles.css"' in response.text
    assert 'href="/img/favicon.svg"' in response.text
    if url.startswith("/recipe/"):
        assert 'href="/recipe-card.css"' in response.text
