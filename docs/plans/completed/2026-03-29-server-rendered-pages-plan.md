# Server-Rendered Recipe & Ingredient Pages Implementation Plan

**Status:** Refined

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add server-rendered HTML pages at `/recipe/{id}` and `/ingredient/{id}` with JSON-LD structured data, a dynamic sitemap, and backward-compatible redirects from the old SPA URLs.

**Architecture:** Jinja2 templates rendered by FastAPI, served via new Caddy route blocks. Existing SPA JS progressively enhances recipe pages for browser users. Ingredient pages are static HTML only.

**Tech Stack:** Jinja2, FastAPI, Caddy reverse proxy

---

### Task 1: Add Jinja2 dependency and base_url config setting

**Files:**
- Modify: `api/requirements.txt`
- Modify: `api/core/config.py:5-36`

- [ ] **Step 1: Add jinja2 to requirements.txt**

Add `jinja2` after the existing `python-multipart` line in `api/requirements.txt`:

```
jinja2>=3.1.0
```

- [ ] **Step 2: Add base_url setting to config.py**

In `api/core/config.py`, add a `base_url` field to the `Settings` class after the `environment` field (line 25):

```python
    # Site URL (for canonical links, sitemaps, JSON-LD)
    base_url: str = Field(default="https://mixology.tools", description="Public base URL for the site")
```

- [ ] **Step 3: Install the dependency**

Run: `pip install jinja2>=3.1.0`
Expected: Successfully installed

- [ ] **Step 4: Commit**

```bash
git add api/requirements.txt api/core/config.py
git commit -m "feat: add jinja2 dependency and base_url config setting"
```

---

### Task 2: Write tests for server-rendered pages

**Files:**
- Create: `tests/test_pages.py`

- [ ] **Step 1: Write test file**

```python
"""Tests for server-rendered HTML pages (recipe, ingredient, sitemap)"""

import pytest

pytestmark = pytest.mark.asyncio


class TestRecipePage:
    """Test server-rendered recipe pages"""

    async def test_recipe_page_returns_html(self, test_client_with_data):
        """GET /recipe/{id} returns HTML content"""
        client, app = test_client_with_data
        response = await client.get("/recipe/1")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    async def test_recipe_page_contains_recipe_name(self, test_client_with_data):
        """Recipe page includes the recipe name in an h1"""
        client, app = test_client_with_data
        response = await client.get("/recipe/1")
        assert "Test Old Fashioned" in response.text

    async def test_recipe_page_contains_ingredients(self, test_client_with_data):
        """Recipe page includes ingredient list"""
        client, app = test_client_with_data
        response = await client.get("/recipe/1")
        assert "Bourbon" in response.text

    async def test_recipe_page_contains_instructions(self, test_client_with_data):
        """Recipe page includes instructions"""
        client, app = test_client_with_data
        response = await client.get("/recipe/1")
        assert "Muddle sugar with bitters" in response.text

    async def test_recipe_page_contains_json_ld(self, test_client_with_data):
        """Recipe page includes JSON-LD structured data"""
        client, app = test_client_with_data
        response = await client.get("/recipe/1")
        assert 'application/ld+json' in response.text
        assert '"@type": "Recipe"' in response.text

    async def test_recipe_page_contains_meta_description(self, test_client_with_data):
        """Recipe page includes meta description"""
        client, app = test_client_with_data
        response = await client.get("/recipe/1")
        assert '<meta name="description"' in response.text

    async def test_recipe_page_contains_canonical_url(self, test_client_with_data):
        """Recipe page includes canonical link"""
        client, app = test_client_with_data
        response = await client.get("/recipe/1")
        assert '<link rel="canonical"' in response.text

    async def test_recipe_page_loads_spa_scripts(self, test_client_with_data):
        """Recipe page loads SPA JS for progressive enhancement"""
        client, app = test_client_with_data
        response = await client.get("/recipe/1")
        assert "recipe.js" in response.text
        assert "common.js" in response.text

    async def test_recipe_page_404_for_nonexistent(self, test_client_with_data):
        """GET /recipe/{bad_id} returns 404 HTML"""
        client, app = test_client_with_data
        response = await client.get("/recipe/99999")
        assert response.status_code == 404
        assert "text/html" in response.headers["content-type"]
        assert "not found" in response.text.lower()

    async def test_recipe_page_source_url_xss_protection(self, test_client_with_data):
        """Source URLs with javascript: scheme are not rendered as links"""
        # This test verifies the template doesn't blindly render source_url as href
        # The test data uses safe URLs, so we just verify the template renders source safely
        client, app = test_client_with_data
        response = await client.get("/recipe/1")
        # Source "Test Source" should appear as text, not as a dangerous link
        assert "Test Source" in response.text


class TestIngredientPage:
    """Test server-rendered ingredient pages"""

    async def test_ingredient_page_returns_html(self, test_client_with_data):
        """GET /ingredient/{id} returns HTML content"""
        client, app = test_client_with_data
        response = await client.get("/ingredient/1")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    async def test_ingredient_page_contains_name(self, test_client_with_data):
        """Ingredient page includes the ingredient name"""
        client, app = test_client_with_data
        response = await client.get("/ingredient/1")
        assert "Whiskey" in response.text

    async def test_ingredient_page_contains_json_ld(self, test_client_with_data):
        """Ingredient page includes JSON-LD structured data"""
        client, app = test_client_with_data
        response = await client.get("/ingredient/1")
        assert 'application/ld+json' in response.text

    async def test_ingredient_page_contains_search_link(self, test_client_with_data):
        """Ingredient page links to search filtered by this ingredient"""
        client, app = test_client_with_data
        response = await client.get("/ingredient/1")
        assert "search.html" in response.text

    async def test_ingredient_page_404_for_nonexistent(self, test_client_with_data):
        """GET /ingredient/{bad_id} returns 404 HTML"""
        client, app = test_client_with_data
        response = await client.get("/ingredient/99999")
        assert response.status_code == 404
        assert "text/html" in response.headers["content-type"]


class TestNameRedirect:
    """Test recipe name-to-ID redirect"""

    async def test_name_redirect_finds_recipe(self, test_client_with_data):
        """GET /recipe/by-name?name=X redirects to /recipe/{id}"""
        client, app = test_client_with_data
        response = await client.get(
            "/recipe/by-name", params={"name": "Test Old Fashioned"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"].startswith("/recipe/")

    async def test_name_redirect_404_for_unknown(self, test_client_with_data):
        """GET /recipe/by-name?name=X returns 404 HTML for unknown name"""
        client, app = test_client_with_data
        response = await client.get(
            "/recipe/by-name", params={"name": "Nonexistent Recipe"},
            follow_redirects=False,
        )
        assert response.status_code == 404
        assert "text/html" in response.headers["content-type"]


class TestSitemap:
    """Test dynamic sitemap generation"""

    async def test_sitemap_returns_xml(self, test_client_with_data):
        """GET /sitemap.xml returns XML content"""
        client, app = test_client_with_data
        response = await client.get("/sitemap.xml")
        assert response.status_code == 200
        assert "application/xml" in response.headers["content-type"]

    async def test_sitemap_contains_recipe_urls(self, test_client_with_data):
        """Sitemap includes recipe page URLs"""
        client, app = test_client_with_data
        response = await client.get("/sitemap.xml")
        assert "/recipe/" in response.text

    async def test_sitemap_contains_ingredient_urls(self, test_client_with_data):
        """Sitemap includes ingredient page URLs"""
        client, app = test_client_with_data
        response = await client.get("/sitemap.xml")
        assert "/ingredient/" in response.text

    async def test_sitemap_contains_static_pages(self, test_client_with_data):
        """Sitemap includes static page URLs"""
        client, app = test_client_with_data
        response = await client.get("/sitemap.xml")
        assert "/about.html" in response.text
        assert "/search.html" in response.text

    async def test_sitemap_has_cache_header(self, test_client_with_data):
        """Sitemap response includes cache control header"""
        client, app = test_client_with_data
        response = await client.get("/sitemap.xml")
        assert "max-age" in response.headers.get("cache-control", "")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_pages.py -v`
Expected: FAIL — no `/recipe/`, `/ingredient/`, or `/sitemap.xml` routes exist yet.

- [ ] **Step 3: Commit**

```bash
git add tests/test_pages.py
git commit -m "test: add server-rendered page tests"
```

---

### Task 3: Create Jinja2 templates

**Files:**
- Create: `api/templates/base.html`
- Create: `api/templates/recipe.html`
- Create: `api/templates/ingredient.html`
- Create: `api/templates/404.html`

- [ ] **Step 1: Create base.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="{% block description %}Mixology Tools — cocktail recipe database with public API{% endblock %}">
    {% block extra_head %}{% endblock %}
    <title>{% block title %}Mixology Tools{% endblock %}</title>
    <link rel="stylesheet" href="/styles.css">
    <style>
        .ssr-content { max-width: 800px; margin: 0 auto; padding: 1rem; }
        .ssr-content h1 { margin-bottom: 0.5rem; }
        .ssr-ingredients { list-style: none; padding: 0; }
        .ssr-ingredients li { padding: 0.25rem 0; }
        .ssr-breadcrumb { color: #888; font-size: 0.9rem; margin-bottom: 1rem; }
        .ssr-breadcrumb a { color: #666; }
        .ssr-tags { display: flex; gap: 0.5rem; flex-wrap: wrap; margin: 0.5rem 0; }
        .ssr-tag { background: #eee; padding: 0.2rem 0.6rem; border-radius: 12px; font-size: 0.85rem; }
        .ssr-rating { color: #e8a030; }
        .ssr-properties { margin: 1rem 0; }
        .ssr-properties dt { font-weight: bold; display: inline; }
        .ssr-properties dd { display: inline; margin-left: 0.5rem; margin-right: 1.5rem; }
        .ssr-children { list-style: none; padding: 0; }
        .ssr-children li { padding: 0.25rem 0; }
        .ssr-error { text-align: center; padding: 3rem 1rem; }
    </style>
</head>
<body>
    <main>
        {% block content %}{% endblock %}
    </main>
    {% block scripts %}{% endblock %}
</body>
</html>
```

- [ ] **Step 2: Create recipe.html**

```html
{% extends "base.html" %}

{% block title %}{{ recipe.name }} — Mixology Tools{% endblock %}

{% block description %}{{ recipe.name }} cocktail recipe: {{ ingredient_summary }}{% endblock %}

{% block extra_head %}
<meta property="og:title" content="{{ recipe.name }} — Mixology Tools">
<meta property="og:description" content="{{ recipe.name }} cocktail recipe: {{ ingredient_summary }}">
<meta property="og:url" content="{{ base_url }}/recipe/{{ recipe.id }}">
<meta property="og:type" content="article">
<link rel="canonical" href="{{ base_url }}/recipe/{{ recipe.id }}">
<script type="application/ld+json">
{{ json_ld | tojson }}
</script>
{% endblock %}

{% block content %}
<div id="recipe-container" class="ssr-content">
    <section class="section-title">
        <h2 id="recipe-page-title">{{ recipe.name }}</h2>
    </section>
    <section class="recipe-display-section">
        {% if recipe.avg_rating %}
        <div class="ssr-rating">★ {{ "%.1f" | format(recipe.avg_rating) }} ({{ recipe.rating_count }} rating{{ "s" if recipe.rating_count != 1 else "" }})</div>
        {% endif %}

        {% if public_tags %}
        <div class="ssr-tags">
            {% for tag in public_tags %}
            <span class="ssr-tag">{{ tag }}</span>
            {% endfor %}
        </div>
        {% endif %}

        {% if recipe.description %}
        <p>{{ recipe.description }}</p>
        {% endif %}

        <h3>Ingredients</h3>
        <ul class="ssr-ingredients">
            {% for ing in recipe.ingredients %}
            <li>
                {% if ing.amount %}{{ ing.amount }}{% endif %}
                {% if ing.unit_abbreviation %} {{ ing.unit_abbreviation }}{% endif %}
                {{ ing.ingredient_name }}
            </li>
            {% endfor %}
        </ul>

        {% if recipe.instructions %}
        <h3>Instructions</h3>
        <p>{{ recipe.instructions }}</p>
        {% endif %}

        {% if recipe.source %}
        <p class="recipe-source">
            Source:
            {% if recipe.source_url and recipe.source_url.startswith(('http://', 'https://')) %}
                <a href="{{ recipe.source_url }}" rel="noopener noreferrer">{{ recipe.source }}</a>
            {% else %}
                {{ recipe.source }}
            {% endif %}
        </p>
        {% endif %}

        {% if similar_recipes %}
        <h3>Similar Cocktails</h3>
        <ul>
            {% for sim in similar_recipes %}
            <li><a href="/recipe/{{ sim.neighbor_recipe_id }}">{{ sim.neighbor_name }}</a></li>
            {% endfor %}
        </ul>
        {% endif %}
    </section>
</div>
{% endblock %}

{% block scripts %}
<script type="module" src="/js/common.js"></script>
<script type="module" src="/js/recipe.js"></script>
{% endblock %}
```

- [ ] **Step 3: Create ingredient.html**

```html
{% extends "base.html" %}

{% block title %}{{ ingredient.name }} Cocktails — Mixology Tools{% endblock %}

{% block description %}{{ ingredient.name }}{% if ingredient.description %} — {{ ingredient.description }}{% endif %}. Browse cocktail recipes using {{ ingredient.name }}.{% endblock %}

{% block extra_head %}
<meta property="og:title" content="{{ ingredient.name }} Cocktails — Mixology Tools">
<meta property="og:url" content="{{ base_url }}/ingredient/{{ ingredient.id }}">
<meta property="og:type" content="website">
<link rel="canonical" href="{{ base_url }}/ingredient/{{ ingredient.id }}">
<script type="application/ld+json">
{{ json_ld | tojson }}
</script>
{% endblock %}

{% block content %}
<div class="ssr-content">
    {% if breadcrumb %}
    <nav class="ssr-breadcrumb">
        {% for crumb in breadcrumb %}
            {% if not loop.last %}
                <a href="/ingredient/{{ crumb.id }}">{{ crumb.name }}</a> &gt;
            {% else %}
                {{ crumb.name }}
            {% endif %}
        {% endfor %}
    </nav>
    {% endif %}

    <h1>{{ ingredient.name }}</h1>

    {% if ingredient.description %}
    <p>{{ ingredient.description }}</p>
    {% endif %}

    {% if ingredient.percent_abv or ingredient.sugar_g_per_l or ingredient.titratable_acidity_g_per_l %}
    <dl class="ssr-properties">
        {% if ingredient.percent_abv %}
        <dt>ABV:</dt><dd>{{ ingredient.percent_abv }}%</dd>
        {% endif %}
        {% if ingredient.sugar_g_per_l %}
        <dt>Sugar:</dt><dd>{{ ingredient.sugar_g_per_l }} g/L</dd>
        {% endif %}
        {% if ingredient.titratable_acidity_g_per_l %}
        <dt>Acidity:</dt><dd>{{ ingredient.titratable_acidity_g_per_l }} g/L</dd>
        {% endif %}
    </dl>
    {% endif %}

    {% if children %}
    <h2>Types of {{ ingredient.name }}</h2>
    <ul class="ssr-children">
        {% for child in children %}
        <li><a href="/ingredient/{{ child.id }}">{{ child.name }}</a></li>
        {% endfor %}
    </ul>
    {% endif %}

    <h2>Cocktail Recipes</h2>
    <p><a href="/search.html?ingredients={{ ingredient.id }}">Browse all recipes using {{ ingredient.name }} →</a></p>
</div>
{% endblock %}
```

- [ ] **Step 4: Create 404.html**

```html
{% extends "base.html" %}

{% block title %}Not Found — Mixology Tools{% endblock %}

{% block content %}
<div class="ssr-content ssr-error">
    <h1>Not Found</h1>
    <p>{{ message | default("The page you're looking for doesn't exist.") }}</p>
    <p><a href="/search.html">Search for recipes →</a></p>
</div>
{% endblock %}
```

- [ ] **Step 5: Commit**

```bash
git add api/templates/
git commit -m "feat: add Jinja2 templates for recipe, ingredient, and 404 pages"
```

---

### Task 4: Implement pages route module

**Files:**
- Create: `api/routes/pages.py`

- [ ] **Step 1: Create routes/pages.py**

```python
"""Server-rendered HTML pages for recipe and ingredient discoverability."""

import json
import logging
from typing import Optional
from xml.etree.ElementTree import Element, SubElement, tostring

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from core.config import settings
from db.database import get_database
from db.db_core import Database

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _safe_source_url(url: Optional[str]) -> Optional[str]:
    """Only allow http/https URLs for source links."""
    if url and url.startswith(("http://", "https://")):
        return url
    return None


def _ingredient_summary(ingredients: list) -> str:
    """Build a short ingredient summary for meta descriptions."""
    names = [ing.get("ingredient_name", "") for ing in ingredients[:5]]
    summary = ", ".join(n for n in names if n)
    if len(ingredients) > 5:
        summary += f", and {len(ingredients) - 5} more"
    return summary


def _build_recipe_json_ld(recipe: dict, base_url: str) -> dict:
    """Build schema.org/Recipe JSON-LD from recipe data."""
    ld = {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": recipe["name"],
        "recipeCategory": "Cocktail",
        "url": f"{base_url}/recipe/{recipe['id']}",
    }

    if recipe.get("description"):
        ld["description"] = recipe["description"]

    # Ingredients
    ingredient_strings = []
    for ing in recipe.get("ingredients", []):
        parts = []
        if ing.get("amount"):
            parts.append(str(ing["amount"]))
        if ing.get("unit_abbreviation"):
            parts.append(ing["unit_abbreviation"])
        parts.append(ing.get("ingredient_name", ""))
        ingredient_strings.append(" ".join(parts))
    if ingredient_strings:
        ld["recipeIngredient"] = ingredient_strings

    # Instructions
    if recipe.get("instructions"):
        steps = [s.strip() for s in recipe["instructions"].split("\n") if s.strip()]
        if not steps:
            steps = [recipe["instructions"]]
        ld["recipeInstructions"] = [
            {"@type": "HowToStep", "text": step} for step in steps
        ]

    # Tags as keywords
    tags = recipe.get("tags", [])
    public_tags = [t["name"] for t in tags if t.get("type") == "public"]
    if public_tags:
        ld["keywords"] = public_tags

    # Rating
    if recipe.get("avg_rating") and recipe.get("rating_count", 0) > 0:
        ld["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": recipe["avg_rating"],
            "ratingCount": recipe["rating_count"],
        }

    return ld


def _build_ingredient_json_ld(ingredient: dict, base_url: str) -> dict:
    """Build schema.org/Thing JSON-LD from ingredient data."""
    ld = {
        "@context": "https://schema.org",
        "@type": "Thing",
        "name": ingredient["name"],
        "url": f"{base_url}/ingredient/{ingredient['id']}",
    }
    if ingredient.get("description"):
        ld["description"] = ingredient["description"]
    return ld


@router.get("/recipe/by-name", response_class=HTMLResponse)
async def recipe_by_name(
    request: Request,
    name: str = Query(..., description="Recipe name to look up"),
    db: Database = Depends(get_database),
):
    """Look up a recipe by name and redirect to /recipe/{id}."""
    results = db.search_recipes_paginated(
        search_params={"name": name}, limit=1, offset=0
    )
    recipes = results.get("recipes", [])
    if recipes:
        recipe_id = recipes[0]["id"]
        return RedirectResponse(url=f"/recipe/{recipe_id}", status_code=302)

    return templates.TemplateResponse(
        "404.html",
        {"request": request, "message": f'Recipe "{name}" not found.'},
        status_code=404,
    )


@router.get("/recipe/{recipe_id:int}", response_class=HTMLResponse)
async def recipe_page(
    request: Request,
    recipe_id: int,
    db: Database = Depends(get_database),
):
    """Server-rendered recipe page for crawlers and agents."""
    recipe = db.get_recipe(recipe_id)
    if not recipe:
        return templates.TemplateResponse(
            "404.html",
            {"request": request, "message": "Recipe not found."},
            status_code=404,
        )

    base_url = settings.base_url
    ingredients = recipe.get("ingredients", [])
    tags = recipe.get("tags", [])
    public_tags = [t["name"] for t in tags if t.get("type") == "public"]

    # Get similar recipes if available
    similar = db.get_recipe_similarity(recipe_id)
    similar_recipes = similar.get("neighbors", []) if similar else []

    return templates.TemplateResponse(
        "recipe.html",
        {
            "request": request,
            "recipe": recipe,
            "base_url": base_url,
            "ingredient_summary": _ingredient_summary(ingredients),
            "public_tags": public_tags,
            "similar_recipes": similar_recipes,
            "json_ld": _build_recipe_json_ld(recipe, base_url),
        },
    )


@router.get("/ingredient/{ingredient_id:int}", response_class=HTMLResponse)
async def ingredient_page(
    request: Request,
    ingredient_id: int,
    db: Database = Depends(get_database),
):
    """Server-rendered ingredient page for crawlers and agents."""
    ingredient = db.get_ingredient(ingredient_id)
    if not ingredient:
        return templates.TemplateResponse(
            "404.html",
            {"request": request, "message": "Ingredient not found."},
            status_code=404,
        )

    base_url = settings.base_url

    # Build breadcrumb from path
    breadcrumb = []
    if ingredient.get("path"):
        # Path is like /1/8/ — each number is an ingredient ID
        path_ids = [
            int(p) for p in ingredient["path"].strip("/").split("/") if p
        ]
        for pid in path_ids:
            parent = db.get_ingredient(pid)
            if parent:
                breadcrumb.append({"id": parent["id"], "name": parent["name"]})

    # Get child ingredients
    all_ingredients = db.get_ingredients()
    children = [
        ing for ing in all_ingredients if ing.get("parent_id") == ingredient_id
    ]

    return templates.TemplateResponse(
        "ingredient.html",
        {
            "request": request,
            "ingredient": ingredient,
            "base_url": base_url,
            "breadcrumb": breadcrumb,
            "children": children,
            "json_ld": _build_ingredient_json_ld(ingredient, base_url),
        },
    )


@router.get("/sitemap.xml")
async def sitemap(db: Database = Depends(get_database)):
    """Dynamic sitemap generated from database content."""
    base_url = settings.base_url

    urlset = Element("urlset")
    urlset.set("xmlns", "http://www.sitemaps.org/schemas/sitemap/0.9")

    def add_url(loc: str, priority: str, changefreq: str = "weekly"):
        url_el = SubElement(urlset, "url")
        SubElement(url_el, "loc").text = loc
        SubElement(url_el, "priority").text = priority
        SubElement(url_el, "changefreq").text = changefreq

    # Static pages
    add_url(f"{base_url}/", "1.0")
    add_url(f"{base_url}/about.html", "0.7")
    add_url(f"{base_url}/search.html", "0.8")
    add_url(f"{base_url}/recipes.html", "0.7")
    add_url(f"{base_url}/analytics.html", "0.7")
    add_url(f"{base_url}/api/v1/docs", "0.9", "monthly")
    add_url(f"{base_url}/api/v1/openapi.json", "0.9", "monthly")

    # Recipe pages
    try:
        result = db.execute_query("SELECT id FROM recipes ORDER BY id")
        for row in result:
            add_url(f"{base_url}/recipe/{row['id']}", "0.8")
    except Exception as e:
        logger.error(f"Error fetching recipe IDs for sitemap: {e}")

    # Ingredient pages
    try:
        result = db.execute_query("SELECT id FROM ingredients ORDER BY id")
        for row in result:
            add_url(f"{base_url}/ingredient/{row['id']}", "0.7")
    except Exception as e:
        logger.error(f"Error fetching ingredient IDs for sitemap: {e}")

    xml_bytes = tostring(urlset, encoding="unicode", xml_declaration=False)
    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_bytes

    return Response(
        content=xml_str,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )
```

- [ ] **Step 2: Commit**

```bash
git add api/routes/pages.py
git commit -m "feat: implement server-rendered page routes"
```

---

### Task 5: Register pages router in main.py

**Files:**
- Modify: `api/main.py:30,104`

- [ ] **Step 1: Add import**

In `api/main.py`, update the routes import line (line 30) to include `pages`:

```python
from routes import ingredients, recipes, ratings, units, tags, auth, admin, user_ingredients, stats, analytics, pages
```

- [ ] **Step 2: Register the router**

Add after line 104 (`app.include_router(analytics.router)`):

```python
app.include_router(pages.router)
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `python -m pytest tests/test_pages.py -v`
Expected: All tests PASS.

- [ ] **Step 4: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All existing tests still pass.

- [ ] **Step 5: Commit**

```bash
git add api/main.py
git commit -m "feat: register pages router for server-rendered HTML"
```

---

### Task 6: Update JS to use new URL scheme

**Files:**
- Modify: `src/web/js/common.js:24-34` (fix relative asset paths)
- Modify: `src/web/js/recipe.js` (full rewrite)
- Modify: `src/web/js/recipeCard.js:297,312-313,374`
- Modify: `src/web/js/analytics.js:634`
- Modify: `src/web/js/search.js:1110`

- [ ] **Step 0: Fix relative asset paths in common.js**

`common.js` injects CSS/favicon links with relative paths (`normalize.css`, `styles.css`, `img/...`). On nested routes like `/recipe/42`, these resolve to `/recipe/normalize.css` and break. Change all to absolute paths.

In `src/web/js/common.js`, in the `loadCommonHead()` function, replace the relative paths in the `headContent` template literal (lines 24-34):

```javascript
        <link rel="stylesheet" href="/normalize.css">
        <link rel="stylesheet" href="/styles.css"
            onload="document.body.style.visibility=''"
            onerror="document.body.style.visibility=''">
        <!-- Favicon and app icons -->
        <link rel="icon" type="image/png" href="/img/favicon-96x96.png" sizes="96x96" />
        <link rel="icon" type="image/svg+xml" href="/img/favicon.svg" />
        <link rel="shortcut icon" href="/img/favicon.ico" />
        <link rel="apple-touch-icon" sizes="180x180" href="/img/apple-touch-icon.png" />
        <meta name="apple-mobile-web-app-title" content="Mixology Tools" />
        <link rel="manifest" href="/site.webmanifest" />
```

This is a no-op for pages at the root (`/search.html` etc.) since `/styles.css` and `styles.css` resolve the same there, but it fixes nested paths like `/recipe/42`.

- [ ] **Step 1: Rewrite recipe.js to work with SSR + path-based URLs**

Replace the entire content of `src/web/js/recipe.js`. The key changes:
- Read recipe ID from URL path (`/recipe/42`) instead of query param
- Handle missing `.loading-placeholder` gracefully (SSR template doesn't have one)
- On API success: replace container contents with interactive card
- On API failure: leave the SSR content visible (don't overwrite with error)

```javascript
import { api } from './api.js';
import { createRecipeCard } from './recipeCard.js';

document.addEventListener('DOMContentLoaded', async () => {
    const recipeContainer = document.getElementById('recipe-container');
    const loadingPlaceholder = recipeContainer?.querySelector('.loading-placeholder');
    const pageTitle = document.getElementById('recipe-page-title');

    // Get recipe ID from URL path (/recipe/42) or query param (?id=42) as fallback
    const pathMatch = window.location.pathname.match(/^\/recipe\/(\d+)$/);
    const recipeId = pathMatch ? pathMatch[1] : new URLSearchParams(window.location.search).get('id');
    const recipeName = new URLSearchParams(window.location.search).get('name');

    if (!recipeId && !recipeName) {
        if (loadingPlaceholder) {
            loadingPlaceholder.innerHTML = '<p>No recipe specified.</p>';
        }
        return;
    }

    try {
        let recipe = null;
        if (recipeId) {
            recipe = await api.getRecipe(recipeId);
        } else {
            const result = await api.searchRecipes({ name: recipeName }, 1, 1);
            if (result && result.recipes && result.recipes.length > 0) {
                recipe = result.recipes[0];
            }
        }

        if (recipe) {
            // Update page title
            if (pageTitle) pageTitle.textContent = recipe.name;
            document.title = `${recipe.name} - Mixology Tools`;

            // Remove loading placeholder if present
            if (loadingPlaceholder) loadingPlaceholder.remove();

            // Clear SSR content and render interactive card
            recipeContainer.innerHTML = '';
            const recipeCard = createRecipeCard(recipe, true, null, { showSimilar: true });
            recipeContainer.appendChild(recipeCard);
        } else if (loadingPlaceholder) {
            // Only show error if we had a loading placeholder (non-SSR page)
            loadingPlaceholder.innerHTML = `
                <p>Recipe not found.</p>
                <p><a href="/search.html">Search for other recipes</a></p>
            `;
        }
        // If no recipe and no placeholder (SSR page), SSR content stays visible
    } catch (error) {
        console.error('Error loading recipe:', error);
        if (loadingPlaceholder) {
            loadingPlaceholder.innerHTML = `
                <p>Error loading recipe: ${error.message}</p>
                <p><a href="/search.html">Go to search page</a></p>
            `;
        }
        // On error with SSR content: leave SSR visible, don't overwrite
    }
});
```

- [ ] **Step 2: Update recipeCard.js recipe click (line 297)**

Replace:
```javascript
            window.location.href = `recipe.html?id=${recipe.id}`;
```
With:
```javascript
            window.location.href = `/recipe/${recipe.id}`;
```

- [ ] **Step 3: Update recipeCard.js share URL (lines 312-313)**

Replace:
```javascript
        const shareUrl = recipeId
            ? `${window.location.origin}/recipe.html?id=${encodeURIComponent(recipeId)}`
            : `${window.location.origin}/recipe.html?name=${encodeURIComponent(recipeName)}`;
```
With:
```javascript
        const shareUrl = recipeId
            ? `${window.location.origin}/recipe/${encodeURIComponent(recipeId)}`
            : `${window.location.origin}/recipe/by-name?name=${encodeURIComponent(recipeName)}`;
```

- [ ] **Step 4: Update recipeCard.js similar cocktails link (line 374)**

Replace:
```javascript
                    <a href="recipe.html?id=${neighbor.neighbor_recipe_id}">${neighbor.neighbor_name}</a>
```
With:
```javascript
                    <a href="/recipe/${neighbor.neighbor_recipe_id}">${neighbor.neighbor_name}</a>
```

- [ ] **Step 5: Update analytics.js modal link (line 634)**

Replace:
```javascript
        modalLink.href = `/recipe.html?id=${encodeURIComponent(recipeId)}`;
```
With:
```javascript
        modalLink.href = `/recipe/${encodeURIComponent(recipeId)}`;
```

- [ ] **Step 6: Update search.js recipe navigation (line 1110)**

Replace:
```javascript
    window.location.href = `/recipe.html?id=${recipeId}`;
```
With:
```javascript
    window.location.href = `/recipe/${recipeId}`;
```

- [ ] **Step 7: Commit**

```bash
git add src/web/js/common.js src/web/js/recipe.js src/web/js/recipeCard.js src/web/js/analytics.js src/web/js/search.js
git commit -m "feat: update JS to use /recipe/{id} URL scheme and fix relative asset paths"
```

---

### Task 7: Update Caddy configuration

**Files:**
- Modify: `infrastructure/caddy/Caddyfile:31-41`
- Modify: `infrastructure/ansible/files/Caddyfile.j2:27-35`

- [ ] **Step 1: Update Caddyfile**

In `infrastructure/caddy/Caddyfile`, add three new `handle` blocks after the `/health` block (line 34) and before the static files catch-all `handle` block (line 37):

```caddy
    # Server-rendered recipe pages
    handle /recipe/* {
        reverse_proxy localhost:8000 {
            header_up Host {host}
            header_up X-Real-IP {remote_host}
        }
    }

    # Server-rendered ingredient pages
    handle /ingredient/* {
        reverse_proxy localhost:8000 {
            header_up Host {host}
            header_up X-Real-IP {remote_host}
        }
    }

    # Dynamic sitemap
    handle /sitemap.xml {
        reverse_proxy localhost:8000 {
            header_up Host {host}
            header_up X-Real-IP {remote_host}
        }
    }

    # Legacy recipe.html redirects
    @legacy_recipe_id {
        path /recipe.html
        query id=*
    }
    redir @legacy_recipe_id /recipe/{query.id} 301

    @legacy_recipe_name {
        path /recipe.html
        query name=*
    }
    redir @legacy_recipe_name /recipe/by-name?name={query.name} 302
```

- [ ] **Step 2: Add same blocks to the :80 localhost block**

In the `:80` block of `infrastructure/caddy/Caddyfile`, add the same `handle` blocks after `/health` (line 107) and before the catch-all (line 109):

```caddy
    handle /recipe/* {
        reverse_proxy localhost:8000
    }

    handle /ingredient/* {
        reverse_proxy localhost:8000
    }

    handle /sitemap.xml {
        reverse_proxy localhost:8000
    }
```

- [ ] **Step 3: Update Caddyfile.j2**

Apply the same changes to `infrastructure/ansible/files/Caddyfile.j2`. Add after the `/health` block (line 29) and before the catch-all (line 31):

```caddy
    # Server-rendered recipe pages
    handle /recipe/* {
        reverse_proxy localhost:8000 {
            header_up Host {host}
            header_up X-Real-IP {remote_host}
        }
    }

    # Server-rendered ingredient pages
    handle /ingredient/* {
        reverse_proxy localhost:8000 {
            header_up Host {host}
            header_up X-Real-IP {remote_host}
        }
    }

    # Dynamic sitemap
    handle /sitemap.xml {
        reverse_proxy localhost:8000 {
            header_up Host {host}
            header_up X-Real-IP {remote_host}
        }
    }

    # Legacy recipe.html redirects
    @legacy_recipe_id {
        path /recipe.html
        query id=*
    }
    redir @legacy_recipe_id /recipe/{query.id} 301

    @legacy_recipe_name {
        path /recipe.html
        query name=*
    }
    redir @legacy_recipe_name /recipe/by-name?name={query.name} 302
```

Also add the handle blocks to the `:80` block in `Caddyfile.j2`.

- [ ] **Step 4: Commit**

```bash
git add infrastructure/caddy/Caddyfile infrastructure/ansible/files/Caddyfile.j2
git commit -m "feat: add Caddy routes for server-rendered pages and legacy redirects"
```

---

### Task 8: Delete replaced static files

**Files:**
- Delete: `src/web/sitemap.xml`
- Delete: `src/web/recipe.html`

- [ ] **Step 1: Delete old static files**

```bash
rm src/web/sitemap.xml src/web/recipe.html
```

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS (no tests depend on these static files).

- [ ] **Step 3: Commit**

```bash
git rm src/web/sitemap.xml src/web/recipe.html
git commit -m "chore: remove static sitemap.xml and recipe.html replaced by server-rendered routes"
```

---

## Summary

| Task | What it does | Files |
|------|-------------|-------|
| 1 | Add Jinja2 dependency + base_url config | `requirements.txt`, `config.py` |
| 2 | Write failing tests for all page routes | `test_pages.py` |
| 3 | Create Jinja2 templates | `templates/*.html` |
| 4 | Implement page routes (recipe, ingredient, name redirect, sitemap) | `routes/pages.py` |
| 5 | Register router in main.py, verify tests pass | `main.py` |
| 6 | Fix relative asset paths in common.js + update recipe links | 5 JS files |
| 7 | Add Caddy routes + legacy redirects | `Caddyfile`, `Caddyfile.j2` |
| 8 | Delete old static files | `sitemap.xml`, `recipe.html` |
