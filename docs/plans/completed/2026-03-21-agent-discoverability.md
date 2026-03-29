# Agent Discoverability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make mixology.tools discoverable by AI agents and search engine crawlers by adding meta tags, noscript fallbacks, a self-describing API root, robots.txt, and sitemap.xml.

**Architecture:** The site is a static SPA served by Caddy with a FastAPI backend proxied at `/api/` and `/api/v1/`. Agents currently see empty HTML shells. We add static discoverability hints (meta tags, noscript, robots.txt, sitemap.xml) to the frontend and a self-describing JSON response to the API root. CORS is already configured with wildcard `*`. FastAPI auto-docs are already live at `/api/docs`, `/api/redoc`, and `/api/openapi.json`.

**Tech Stack:** HTML, FastAPI (Python), static files served by Caddy

---

## Pre-Implementation Notes

### What's already done (no work needed)
- **CORS headers**: Wildcard `*` CORS middleware in `api/main.py:41-54` — agents can call the API from any origin.
- **FastAPI auto-docs**: Swagger UI at `/api/docs`, ReDoc at `/api/redoc`, OpenAPI JSON spec at `/api/openapi.json` — all accessible through Caddy proxy. The OpenAPI JSON is machine-readable and usable by agents directly.
- **Health check**: `GET /health` returns `{"status": "healthy", "timestamp": "..."}`.

### Key Caddy routing behavior
- `/api/v1/*` → strips `/api/v1`, proxies to FastAPI on port 8000
- `/api/*` → strips `/api`, proxies to FastAPI on port 8000
- Everything else → serves static files from `/opt/cocktaildb/web` with `try_files {path} /index.html` SPA fallback
- **Important**: `robots.txt` and `sitemap.xml` must be actual files in `src/web/` — otherwise the SPA fallback will serve `index.html` for those paths.

### Public read-only API endpoints (what agents care about)
| Endpoint | Description |
|---|---|
| `GET /api/v1/recipes/search?q=&page=&limit=&sort_by=&ingredients=&tags=` | Search recipes (paginated) |
| `GET /api/v1/recipes/{id}` | Get recipe by ID |
| `GET /api/v1/ingredients` | List all ingredients |
| `GET /api/v1/ingredients/{id}` | Get ingredient by ID |
| `GET /api/v1/ingredients/search?q=` | Search ingredients by name |
| `GET /api/v1/stats` | Database stats (recipe count, ingredient count) |
| `GET /api/v1/units` | List all measurement units |
| `GET /api/v1/tags/public` | List all public tags |
| `GET /api/v1/analytics/ingredient-usage` | Ingredient usage statistics |
| `GET /api/v1/analytics/recipe-complexity` | Recipe complexity distribution |
| `GET /api/v1/analytics/cocktail-space` | UMAP recipe similarity coordinates |
| `GET /api/v1/analytics/ingredient-tree` | Hierarchical ingredient tree |
| `GET /api/v1/analytics/recipe-similar?recipe_id=&limit=` | Similar cocktails for a recipe |

---

### Task 1: Add meta tags and noscript fallback to index.html

**Files:**
- Modify: `src/web/index.html`

**Step 1: Add meta tags and noscript block to index.html**

Replace the current `<head>` and add a `<noscript>` block inside `<body>`:

```html
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="Curated cocktail recipe database with hierarchical ingredients, analytics, and a public API. Search by name, ingredient, or spirit category.">
    <meta property="og:title" content="Mixology Tools">
    <meta property="og:description" content="Curated cocktail recipe database with hierarchical ingredients, analytics, and a public API.">
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://mixology.tools/">
    <title>Mixology Tools</title>
    <!-- Prevent FOUC (Flash of Unstyled Content) with common.js fallback -->
</head>
```

Add a `<noscript>` block as the first child of `<main>`:

```html
<noscript>
    <h1>Mixology Tools</h1>
    <p>A curated cocktail recipe database with hierarchical ingredients, analytics, and a public API.
       Search cocktails by name, ingredient, or spirit category.</p>
    <h2>Explore</h2>
    <ul>
        <li><a href="/about.html">About this project</a></li>
        <li><a href="/search.html">Search recipes</a></li>
        <li><a href="/analytics.html">Database analytics</a></li>
    </ul>
    <h2>Public API</h2>
    <p>This site has a public read-only API. Machine-readable documentation:</p>
    <ul>
        <li><a href="/api/v1/openapi.json">OpenAPI specification (JSON)</a></li>
        <li><a href="/api/v1/docs">Interactive API docs (Swagger UI)</a></li>
        <li><a href="/api/v1/stats">Database statistics</a></li>
    </ul>
</noscript>
```

**Step 2: Verify the changes render correctly**

Open `src/web/index.html` in a browser. The noscript block should not be visible (since JS is enabled). Verify meta tags appear in the `<head>` using browser dev tools.

**Step 3: Commit**

```bash
git add src/web/index.html
git commit -m "feat: add meta tags and noscript fallback to index.html for agent discoverability"
```

---

### Task 2: Add meta tags and noscript fallbacks to other HTML pages

**Files:**
- Modify: `src/web/about.html`
- Modify: `src/web/search.html`
- Modify: `src/web/recipes.html`
- Modify: `src/web/recipe.html`
- Modify: `src/web/analytics.html`

Each page gets the same `<meta charset>` and `<meta viewport>` tags, plus a page-specific `<meta description>` and a minimal `<noscript>` block.

**Step 1: Add meta tags to each page's `<head>`**

For all five pages, add after `<head>`:

```html
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
```

Then a page-specific description:

- **about.html**: `<meta name="description" content="About Mixology Tools - a cocktail recipe database with hierarchical ingredients and analytics.">`
- **search.html**: `<meta name="description" content="Search cocktail recipes by name, ingredient, tag, or spirit category.">`
- **recipes.html**: `<meta name="description" content="Browse all cocktail recipes in the Mixology Tools database.">`
- **recipe.html**: `<meta name="description" content="Cocktail recipe details including ingredients, instructions, and ratings.">`
- **analytics.html**: `<meta name="description" content="Cocktail database analytics - ingredient usage, recipe complexity, and similarity visualizations.">`

**Step 2: Add noscript blocks to about.html and analytics.html**

These two pages have the most useful static content for agents. Add a `<noscript>` as the first child of `<main>`:

**about.html** — the existing `<section class="about-content">` already contains static HTML that agents can read, so no noscript needed. Just add the meta tags.

**analytics.html** — add:
```html
<noscript>
    <h1>Cocktail Database Analytics</h1>
    <p>Interactive analytics for the Mixology Tools cocktail database. Requires JavaScript for visualizations.</p>
    <p>Raw analytics data is available via the API:</p>
    <ul>
        <li><a href="/api/v1/analytics/ingredient-usage">Ingredient usage statistics (JSON)</a></li>
        <li><a href="/api/v1/analytics/recipe-complexity">Recipe complexity distribution (JSON)</a></li>
        <li><a href="/api/v1/analytics/cocktail-space">Cocktail similarity coordinates (JSON)</a></li>
        <li><a href="/api/v1/analytics/ingredient-tree">Ingredient hierarchy tree (JSON)</a></li>
    </ul>
</noscript>
```

**Step 3: Commit**

```bash
git add src/web/about.html src/web/search.html src/web/recipes.html src/web/recipe.html src/web/analytics.html
git commit -m "feat: add meta tags and noscript fallbacks to HTML pages"
```

---

### Task 3: Make the API root self-describing

**Files:**
- Modify: `api/main.py:105-111` (root endpoint)
- Modify: `tests/test_api_unit.py:16-22` (existing root test)

**Step 1: Update the existing root endpoint test**

The existing test at `tests/test_api_unit.py:16-22` checks for `"message"` key. Update it to verify the new self-describing response:

```python
async def test_root_endpoint(self, test_client_memory):
    """Test root endpoint returns self-describing API information"""
    response = await test_client_memory.get("/")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["name"] == "Mixology Tools API"
    assert "description" in data
    assert "docs" in data
    assert "openapi" in data
    assert "endpoints" in data
    # Verify key endpoints are listed
    endpoints = data["endpoints"]
    assert "search_recipes" in endpoints
    assert "ingredients" in endpoints
    assert "stats" in endpoints
```

**Step 2: Run the test to verify it fails**

Run: `pytest tests/test_api_unit.py::TestBasicEndpoints::test_root_endpoint -v`
Expected: FAIL — current root returns `{"message": "..."}` which doesn't have `"name"` key.

**Step 3: Update the root endpoint in main.py**

Replace the root endpoint at `api/main.py:105-111`:

```python
@app.get("/")
async def root():
    """Root endpoint returning self-describing API information for agent discovery"""
    return {
        "name": "Mixology Tools API",
        "description": "Public API for the Mixology Tools cocktail recipe database. "
                       "Search cocktails by name, ingredient, or category. "
                       "Hierarchical ingredient taxonomy with analytics.",
        "version": settings.api_version,
        "docs": "/api/v1/docs",
        "redoc": "/api/v1/redoc",
        "openapi": "/api/v1/openapi.json",
        "endpoints": {
            "search_recipes": "/api/v1/recipes/search",
            "get_recipe": "/api/v1/recipes/{id}",
            "ingredients": "/api/v1/ingredients",
            "get_ingredient": "/api/v1/ingredients/{id}",
            "search_ingredients": "/api/v1/ingredients/search",
            "stats": "/api/v1/stats",
            "units": "/api/v1/units",
            "public_tags": "/api/v1/tags/public",
            "analytics_ingredient_usage": "/api/v1/analytics/ingredient-usage",
            "analytics_recipe_complexity": "/api/v1/analytics/recipe-complexity",
            "analytics_cocktail_space": "/api/v1/analytics/cocktail-space",
            "analytics_ingredient_tree": "/api/v1/analytics/ingredient-tree",
            "analytics_recipe_similar": "/api/v1/analytics/recipe-similar",
        },
    }
```

Note: The endpoint URLs include `/api/v1/` prefix because that's the public-facing path through Caddy. The FastAPI app itself runs without the prefix (Caddy strips it), but agents hitting the root via `/api/v1/` need the full paths.

**Step 4: Run the test to verify it passes**

Run: `pytest tests/test_api_unit.py::TestBasicEndpoints::test_root_endpoint -v`
Expected: PASS

**Step 5: Run the full test suite to check for regressions**

Run: `pytest tests/test_api_unit.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add api/main.py tests/test_api_unit.py
git commit -m "feat: make API root self-describing for agent discovery"
```

---

### Task 4: Add robots.txt

**Files:**
- Create: `src/web/robots.txt`

**Step 1: Create robots.txt**

```
User-agent: *
Allow: /

# Public API documentation
# Interactive docs: https://mixology.tools/api/v1/docs
# OpenAPI spec: https://mixology.tools/api/v1/openapi.json

Sitemap: https://mixology.tools/sitemap.xml
```

**Step 2: Verify Caddy will serve it**

The Caddy static file handler serves files from `/opt/cocktaildb/web` before the SPA fallback. Since `robots.txt` will be an actual file, Caddy's `file_server` directive will serve it directly with the correct content type. No Caddy config changes needed.

**Step 3: Commit**

```bash
git add src/web/robots.txt
git commit -m "feat: add robots.txt for crawler and agent discoverability"
```

---

### Task 5: Add sitemap.xml

**Files:**
- Create: `src/web/sitemap.xml`

**Step 1: Create sitemap.xml**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://mixology.tools/</loc>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>https://mixology.tools/about.html</loc>
    <priority>0.7</priority>
  </url>
  <url>
    <loc>https://mixology.tools/search.html</loc>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>https://mixology.tools/recipes.html</loc>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>https://mixology.tools/analytics.html</loc>
    <priority>0.7</priority>
  </url>
  <url>
    <loc>https://mixology.tools/api/v1/docs</loc>
    <priority>0.9</priority>
    <changefreq>monthly</changefreq>
  </url>
  <url>
    <loc>https://mixology.tools/api/v1/openapi.json</loc>
    <priority>0.9</priority>
    <changefreq>monthly</changefreq>
  </url>
</urlset>
```

Note: Individual recipe pages (`/recipe.html?id=N`) are SPA routes that return the same HTML shell regardless of ID. Including them in the sitemap wouldn't help agents since the content requires JS. Agents should use the search API instead.

**Step 2: Verify Caddy will serve it**

Same as robots.txt — the file will be served directly by Caddy's `file_server` before the SPA fallback.

**Step 3: Commit**

```bash
git add src/web/sitemap.xml
git commit -m "feat: add sitemap.xml for search engine and agent discovery"
```

---

## Summary

| Task | Files | What it does |
|------|-------|-------------|
| 1 | `src/web/index.html` | Meta tags + noscript with site description, page links, and API pointers |
| 2 | 5 HTML files | Meta tags + noscript for about, search, recipes, recipe, analytics pages |
| 3 | `api/main.py`, `tests/test_api_unit.py` | Self-describing JSON at API root with endpoint listing |
| 4 | `src/web/robots.txt` | Standard crawler file pointing to sitemap and API docs |
| 5 | `src/web/sitemap.xml` | Site map including API docs and OpenAPI spec URLs |

**Skipped from original recommendations:**
- **CORS headers (Item 6)**: Already configured — wildcard `*` CORS middleware in `api/main.py`.
- **Separate API docs page (Item 3)**: FastAPI already serves interactive docs at `/api/v1/docs` and machine-readable OpenAPI JSON at `/api/v1/openapi.json`. Creating a separate static docs page would duplicate what exists. The self-describing root (Task 3) makes these discoverable.

**Total estimated changes:** ~100 lines of HTML, ~25 lines of Python, ~15 lines of test updates.
