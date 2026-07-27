# Design: Server-Rendered Recipe & Ingredient Pages

**Goal:** Make recipes and ingredients crawlable by agents and search engines by serving server-rendered HTML pages at `/recipe/{id}` and `/ingredient/{id}`, with JSON-LD structured data and a dynamic sitemap. The existing SPA JS progressively enhances the recipe pages for browser users.

**Architecture:** Jinja2 templates rendered by FastAPI, served via new Caddy route blocks. The SPA's existing JS loads on top of the server-rendered HTML and replaces it with the interactive version. Ingredient pages are static HTML only (no SPA equivalent exists).

**Tech Stack:** Jinja2 (new dependency), FastAPI routes, Caddy reverse proxy rules. No new database queries — reuses existing `db.get_recipe()`, `db.get_ingredient()`, and `db.search_recipes()`.

---

## Routing & Caddy

### New Caddy routes

Added before the existing static file catch-all handler:

| Path pattern | Target | Notes |
|---|---|---|
| `/recipe/*` | `reverse_proxy localhost:8000` | No path stripping — FastAPI sees `/recipe/{id}` |
| `/ingredient/*` | `reverse_proxy localhost:8000` | Same |
| `/sitemap.xml` | `reverse_proxy localhost:8000` | Dynamic sitemap |

### Backward-compatibility redirects

- `recipe.html?id=42` → 301 to `/recipe/42` (handled in Caddy with a rewrite/redirect rule)
- `recipe.html?name=Negroni` → Caddy redirects to `/recipe/by-name/Negroni`, which does a DB lookup and 301 redirects to `/recipe/{id}`

### Caddy routing summary

After this change, the Caddy routing order is:

1. `/api/v1/*` → strip prefix, proxy to FastAPI
2. `/api/*` → strip prefix, proxy to FastAPI (legacy)
3. `/health` → proxy to FastAPI
4. `/recipe/*` → proxy to FastAPI (NEW)
5. `/ingredient/*` → proxy to FastAPI (NEW)
6. `/sitemap.xml` → proxy to FastAPI (NEW)
7. Catch-all → static files from `/opt/cocktaildb/web` with SPA fallback

---

## FastAPI Route Structure

### New module: `api/routes/pages.py`

All HTML-rendering routes live here, separate from the JSON API routes.

| Route | Method | Returns |
|---|---|---|
| `/recipe/{recipe_id}` | GET | HTML — server-rendered recipe page |
| `/recipe/by-name/{name}` | GET | 301 redirect to `/recipe/{id}` (supports legacy `recipe.html?name=X` redirects) |
| `/ingredient/{ingredient_id}` | GET | HTML — server-rendered ingredient page |
| `/sitemap.xml` | GET | XML — dynamic sitemap |

### Dependencies

Same `db: Database = Depends(get_database)` pattern as existing routes.

- **Recipe pages:** Call `db.get_recipe(recipe_id)` — same as the existing JSON endpoint.
- **Ingredient pages:** Call `db.get_ingredient(ingredient_id)` for the ingredient data. The page links to the search page filtered by this ingredient rather than rendering a recipe list inline (lightweight approach — can be expanded later).
- **Sitemap:** Two queries: all recipe IDs, all ingredient IDs.

### Error handling

If a recipe/ingredient ID doesn't exist, return a 404 HTML page (not JSON) using a `404.html` template with a message and link back to search.

### Registration

The pages router is registered in `main.py` without a prefix (same as other routers). A `Jinja2Templates` instance is configured pointing to `api/templates/`.

---

## Templates

### Directory: `api/templates/`

Lives under `api/` so it's included by the existing `COPY api/ .` in `Dockerfile.prod`. No Docker changes needed.

### Template files

| File | Purpose |
|---|---|
| `base.html` | Shared layout: head, meta tags, CSS, header/footer structure |
| `recipe.html` | Recipe content + JSON-LD + SPA script loading |
| `ingredient.html` | Ingredient content with hierarchy, properties, recipe links |
| `404.html` | Not found page with link to search |

### `base.html`

Provides:
- Charset, viewport meta tags
- Blocks for `title`, `description`, `extra_head` (JSON-LD, canonical URL, OG tags)
- References the existing `/styles.css` from the frontend static root (served by Caddy)
- Minimal inline CSS for server-rendered content layout
- Blocks for `content` and `scripts`

### `recipe.html`

Server-rendered content:
- `<title>`: "{name} -- Mixology Tools"
- `<meta name="description">`: auto-generated summary (e.g., "Negroni cocktail recipe: Gin, Campari, Sweet Vermouth")
- OG tags (`og:title`, `og:description`, `og:url`, `og:type`)
- `<link rel="canonical" href="https://mixology.tools/recipe/{id}">`
- JSON-LD `schema.org/Recipe` block (see structured data section below)
- Visible HTML: name as `<h1>`, description, ingredients list with amounts/units, instructions, source with link, average rating, public tags, similar cocktails as links to `/recipe/{id}`
- Content wrapped in `<div id="recipe-container">` — the SPA JS targets this container and replaces its contents

Script loading (same as current `recipe.html`):
- `common.js`, `api.js`, `auth.js`, `recipeCard.js`, `recipe.js`
- When JS executes in a browser, it reads the recipe ID from the URL path, fetches from the API, and renders the interactive recipe card — replacing the static HTML
- Agents/crawlers without JS see the fully rendered static content

### `ingredient.html`

Server-rendered content:
- `<title>`: "{name} Cocktails -- Mixology Tools"
- `<meta name="description">`: e.g., "12 cocktail recipes using mezcal"
- Hierarchy breadcrumb (e.g., Spirits > Agave Spirits > Mezcal) with each level linked to `/ingredient/{id}`
- Description if available
- Properties (ABV, sugar, acidity) if present
- Child ingredients as links to their `/ingredient/{id}` pages
- Link to search page filtered by this ingredient

No JS enhancement — the ingredient page is static HTML only (no existing SPA equivalent).

### `404.html`

Simple page with "Recipe/Ingredient not found" message and a link to `/search.html`.

---

## JSON-LD Structured Data

Embedded in recipe pages as `<script type="application/ld+json">`:

```json
{
  "@context": "https://schema.org",
  "@type": "Recipe",
  "name": "Negroni",
  "recipeCategory": "Cocktail",
  "recipeIngredient": [
    "1 oz Gin",
    "1 oz Campari",
    "1 oz Sweet Vermouth"
  ],
  "recipeInstructions": [
    {
      "@type": "HowToStep",
      "text": "Stir all ingredients with ice."
    }
  ],
  "keywords": ["gin", "campari", "vermouth"],
  "url": "https://mixology.tools/recipe/42"
}
```

Fields mapped from existing data:
- `name` from `recipe.name`
- `recipeIngredient` — array of strings combining `amount`, `unit_abbreviation`, and `ingredient_name` from each `RecipeIngredientResponse`
- `recipeInstructions` — split `recipe.instructions` into steps (by newline or sentence), each as a `HowToStep`
- `keywords` — derived from `recipe.tags` (public tags only)
- `url` — canonical URL
- `description` from `recipe.description` if present
- `aggregateRating` from `recipe.avg_rating` and `recipe.rating_count` if present

Ingredient pages use `schema.org/ItemList` with the recipe list as entries.

---

## JS Changes

Minimal changes to make the existing SPA work with `/recipe/{id}` URLs.

### `recipe.js`

Currently reads `?id=` from `window.location.search`. Change to:
1. Extract ID from URL path (`/recipe/42` -> `42`)
2. Fall back to query param for edge cases

### Link updates (~6 lines across 4 files)

| File | Change |
|---|---|
| `recipeCard.js:294` | Recipe click: `recipe.html?id=${recipe.id}` -> `/recipe/${recipe.id}` |
| `recipeCard.js:309-310` | Share URL: same pattern change |
| `recipeCard.js:371` | Similar cocktails link: same |
| `analytics.js:582` | Cocktail space modal link: same |
| `search.js:1110` | Recipe click: same |

No logic changes — just URL pattern updates.

---

## Dynamic Sitemap

### Route: `GET /sitemap.xml`

Returns `Response(content=xml_string, media_type="application/xml")`.

### Content

Generated from DB queries:
- All recipe IDs -> `/recipe/{id}` entries (priority 0.8)
- All ingredient IDs -> `/ingredient/{id}` entries (priority 0.7)
- Static pages: homepage (1.0), about/search/analytics/recipes (0.7), API docs + OpenAPI spec (0.9)

### Caching

`Cache-Control: public, max-age=3600` header. The underlying queries are trivial (`SELECT id FROM recipes`, `SELECT id FROM ingredients`), but this avoids repeated crawler hits.

### Replaces

The static `src/web/sitemap.xml` is deleted. Caddy routes `/sitemap.xml` to FastAPI before the static file handler.

---

## Cleanup

| Item | Action |
|---|---|
| `src/web/sitemap.xml` | Delete — replaced by dynamic sitemap |
| `src/web/recipe.html` | Delete — replaced by server-rendered route |
| `src/web/js/recipe.js` | Keep — loaded by the Jinja2 template for progressive enhancement |
| Caddy `Caddyfile` + `Caddyfile.j2` | Add new route blocks |

---

## Files Changed

| File | Change type |
|---|---|
| `api/requirements.txt` | Add `jinja2` |
| `api/routes/pages.py` | New — HTML route handlers |
| `api/main.py` | Register pages router, configure Jinja2Templates |
| `api/templates/base.html` | New — shared layout template |
| `api/templates/recipe.html` | New — recipe page template |
| `api/templates/ingredient.html` | New — ingredient page template |
| `api/templates/404.html` | New — not found template |
| `infrastructure/caddy/Caddyfile` | Add recipe/ingredient/sitemap route blocks + redirect |
| `infrastructure/ansible/files/Caddyfile.j2` | Same changes as Caddyfile |
| `src/web/js/recipe.js` | Read ID from URL path instead of query param |
| `src/web/js/recipeCard.js` | Update recipe link URLs (3 locations) |
| `src/web/js/analytics.js` | Update recipe link URL (1 location) |
| `src/web/js/search.js` | Update recipe link URL (1 location) |
| `src/web/sitemap.xml` | Delete |
| `src/web/recipe.html` | Delete |

No database schema changes. No new database queries.
