# Agent Discoverability — Phase 2 TODO

**Source:** External audit of mixology.tools (March 2026)
**Status:** Not started

Phase 1 (meta tags, noscript fallbacks, robots.txt, sitemap, self-describing API root, CORS) is complete and deployed. Phase 2 makes the site findable by agents whose users ask general cocktail questions without mentioning mixology.tools.

---

## TODO

### 1. Crawlable individual recipe pages
**Priority:** High — multiplies discoverable surface from ~5 pages to hundreds
**Effort:** ~1-2 days

Add a FastAPI route at `/recipe/{recipe_id}` that renders a Jinja2 HTML template with:
- Recipe name as `<h1>` and `<title>` (e.g., "Negroni -- Mixology Tools")
- `<meta name="description">` summarizing the recipe
- Ingredients as a visible HTML list with amounts and units
- Instructions as visible text
- Source attribution if present
- `<link rel="canonical">` tag
- Link back to main site / search
- JSON-LD structured data (see item 2)

The SPA remains the primary UI — these pages serve agents and crawlers. Update `sitemap.xml` to include all recipe URLs (can be dynamically generated from the database).

### 2. JSON-LD structured data on recipe pages
**Priority:** High — makes each recipe independently machine-parseable
**Effort:** ~1-2 hours (part of item 1)

Embed `<script type="application/ld+json">` with `schema.org/Recipe` in each recipe page:
- `name`, `recipeCategory` ("Cocktail")
- `recipeIngredient` — array of strings combining amount, unit, ingredient name
- `recipeInstructions` — array of `HowToStep` from instructions text
- `keywords` — derived from tags
- `url` — canonical recipe URL

### 3. Ingredient landing pages
**Priority:** High — directly answers "cocktails with X" queries
**Effort:** ~0.5-1 day

Add a FastAPI route at `/ingredient/{ingredient_id}` rendering a page with:
- Ingredient name in `<title>` (e.g., "Mezcal Cocktails -- Mixology Tools")
- `<meta description>` (e.g., "12 cocktail recipes using mezcal")
- Position in hierarchy using path (e.g., "Spirits > Agave spirits > Mezcal")
- Description, ABV, sugar, acidity data if available
- List of all recipes using this ingredient, linked to recipe pages
- Child ingredients if any
- JSON-LD using `schema.org/ItemList`

### 4. Make analytics content crawlable
**Priority:** Medium — unique differentiator for analytical queries
**Effort:** ~0.5-1 day

Add server-rendered summaries to analytics pages (or break into distinct crawlable pages). Key findings should be in initial HTML, not just JS. Options:
- Enhance existing noscript blocks with actual data (top ingredients, avg complexity, etc.)
- Create separate pages: `/analytics/ingredient-usage`, `/analytics/ingredient-tree`, `/analytics/complexity`, `/analytics/similar`

### 5. Register in API directories
**Priority:** Medium — one-time effort with long-term payoff
**Effort:** ~1-2 hours

- [ ] Submit to [Public APIs](https://github.com/public-apis/public-apis) (PR-based)
- [ ] Submit to [PublicAPI.dev](https://publicapi.dev/)
- [ ] Submit to [APIs.guru](https://apis.guru/) (accepts OpenAPI specs)
- [ ] Add `cocktail-db` and `cocktail-api` topics to GitHub repo
- [ ] Consider [RapidAPI Hub](https://rapidapi.com/) free listing

---

## Future (out of scope)

- **MCP server**: Implemented at `/api/v1/mcp`; see `docs/superpowers/specs/2026-11-14-public-mcp-server-design.md`
- **`/.well-known/ai-plugin.json`**: Agent plugin manifest pointing to OpenAPI spec
- **Prerendered homepage with live stats**: Inject recipe/ingredient counts at serve time instead of client-side JS
