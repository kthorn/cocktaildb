# Ideas

Future work and features under consideration. Not committed to — just captured.

---

## Crawlable Individual Recipe Pages

**Impact: High** — multiplies discoverable surface from ~5 pages to hundreds.

Currently recipes only exist inside the SPA — there are no crawlable `/recipe/{id}` URLs. Each recipe that becomes a real, fetchable HTML page is an independent entry point for agents and search engines answering queries like "negroni recipe" or "what can I make with mezcal?"

**Recommended approach:** Add a FastAPI route at `/recipe/{recipe_id}` that queries the database and renders a Jinja2 template. The SPA remains the primary UI — these pages serve agents and crawlers.

Each page should include:
- Recipe name as `<h1>` and in `<title>` (e.g., "Negroni — Mixology Tools")
- `<meta name="description">` summarizing the recipe
- Ingredients as a visible HTML list with amounts and units
- Instructions as visible text
- Source attribution if present
- JSON-LD structured data (see below)
- `<link rel="canonical">`
- Link back to the main site / search

Update `sitemap.xml` to be dynamically generated from the database once recipe pages exist.

This is the prerequisite for JSON-LD structured data to be useful.

---

## JSON-LD Structured Data

**Impact: High** — each recipe becomes machine-parseable via `schema.org/Recipe`.

Embed `<script type="application/ld+json">` in each recipe page (from above). Pairs naturally with the Jinja2 template — generate from the same data the page renders.

Key fields: `name`, `recipeIngredient` (array of strings combining amount + unit + name), `recipeInstructions` (array of `HowToStep` — split instructions text into steps), `recipeCategory`, `keywords` (from tags), `url`. Optional: `description`, `tool` (glassware).

Depends on crawlable recipe pages existing first.

---

## Ingredient Landing Pages

**Impact: High** — directly answers "cocktails with X" queries.

Add a FastAPI route at `/ingredient/{ingredient_id}` rendering a page for each ingredient. The hierarchical ingredient model makes this especially powerful — pages at every level of the tree.

Each page should include:
- Ingredient name in `<title>` (e.g., "Mezcal Cocktails — Mixology Tools")
- `<meta description>` (e.g., "12 cocktail recipes using mezcal")
- Position in the hierarchy using the path field (e.g., "Spirits > Agave spirits > Mezcal")
- Description, ABV, sugar, and acidity data if present
- List of all recipes using this ingredient, linked to recipe pages
- Child ingredients if any (navigate hierarchy via `parent_id`)
- Substitution info (from `allow_substitution` flag)
- JSON-LD using `schema.org/ItemList`

---

## Crawlable Analytics Pages

**Impact: Medium** — unique differentiator, surfaces for analytical queries.

The analytics noscript block now has descriptive summaries, but breaking analytics into separate crawlable pages with SEO-friendly titles would surface them for specific queries:

| Page | Title | Surfaces for |
|------|-------|-------------|
| `/analytics/ingredient-usage` | "Most common cocktail ingredients" | "popular cocktail ingredients," "most used spirits" |
| `/analytics/ingredient-tree` | "Cocktail ingredient taxonomy" | "types of bitters," "categories of spirits" |
| `/analytics/complexity` | "Cocktail complexity: recipes by ingredient count" | "simple cocktails," "easy three-ingredient drinks" |
| `/analytics/similar` | "Cocktail similarity map" | "cocktails similar to X," "drinks like a Manhattan" |

Could be FastAPI-rendered pages with static summaries that the JS visualizations enhance on load.

A lighter alternative: a deploy-time script that queries the API and injects live numbers (top ingredients, average complexity) into the existing analytics.html noscript block.

---

## Rate Limiting and Cache Headers

**Impact: High** — prerequisite before publicizing the API.

**Do this before API directory submissions.**

Currently zero protection at any layer. The instance has 2 uvicorn workers and a 10-connection database pool — easy to overwhelm with sustained traffic or a misbehaving scraper.

### Rate limiting with `slowapi`

Add [`slowapi`](https://github.com/laurentS/slowapi) (a FastAPI-friendly wrapper around `limits`). In-memory storage is fine for a single-instance deployment — no Redis needed.

Suggested limits:
- **Read-only public endpoints** (search, get recipe, ingredients, analytics, stats): ~60 req/min per IP
- **Write endpoints** (create/update recipe, ratings): ~20 req/min per IP
- **Authenticated users**: higher limits (identify via JWT)
- **OpenAPI/docs**: ~10 req/min (these are large responses, mostly fetched once)

Implementation: add `slowapi` to `requirements.txt`, create a `Limiter` instance in `main.py`, decorate routes or use a default limit. Return `429 Too Many Requests` with a `Retry-After` header.

### Cache headers on read-only responses

Add `Cache-Control` headers to read-only API responses so well-behaved agents and intermediaries don't re-fetch constantly. No library needed — just set response headers.

Suggested values:
- `/stats`, `/analytics/*`: `public, max-age=3600` (1 hour — changes infrequently)
- `GET /recipes/{id}`, `GET /ingredients/{id}`: `public, max-age=300` (5 min)
- Search results: `public, max-age=60` (1 min)
- Write responses, auth endpoints: `no-store`

### Future hardening: Caddy-level rate limiting

The `caddy-ratelimit` plugin can block abusive IPs before requests reach FastAPI. Requires rebuilding Caddy with the plugin (it's not in core). Worth considering if `slowapi` proves insufficient, but adds deployment complexity.

---

## API Directory Submissions

**Impact: Medium** — one-time effort with long-term discoverability payoff. **Do after rate limiting is in place.**

The API is free, open, and has a full OpenAPI spec + Swagger UI — stronger than most cocktail APIs. Submit to:

- [Public APIs](https://github.com/public-apis/public-apis) — PR-based, high visibility
- [PublicAPI.dev](https://publicapi.dev)
- [APIs.guru](https://apis.guru) — accepts OpenAPI specs directly
- Consider [RapidAPI Hub](https://rapidapi.com) as a free listing

---

## MCP Server

Wrap the cocktail API in the [Model Context Protocol](https://modelcontextprotocol.io/) so agents like Claude, Cursor, and Windsurf can call it directly as tools rather than discovering and constructing HTTP requests manually.

FastAPI already generates an OpenAPI spec at `/api/v1/openapi.json`, which could drive generation of the MCP tool definitions. The read-only public endpoints (search recipes, get ingredients, analytics) are natural fits for MCP tools.

---

## Search and Recipe Pages for Non-JS Clients

`/search.html` returns form UI structure but no content without JS. `/recipes.html` is an add-recipe form, not a browsable recipe list. Adding noscript fallbacks with links to the API search endpoint or a static recipe index would help agents that land on these pages.
