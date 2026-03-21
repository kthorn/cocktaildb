# Ideas

Future work and features under consideration. Not committed to — just captured.

---

## MCP Server

Wrap the cocktail API in the [Model Context Protocol](https://modelcontextprotocol.io/) so agents like Claude, Cursor, and Windsurf can call it directly as tools rather than discovering and constructing HTTP requests manually.

FastAPI already generates an OpenAPI spec at `/api/v1/openapi.json`, which could drive generation of the MCP tool definitions. The read-only public endpoints (search recipes, get ingredients, analytics) are natural fits for MCP tools.

---

## JSON-LD Structured Data

Embed [schema.org/Recipe](https://schema.org/Recipe) markup in recipe pages so search engines can display rich result cards (image, ingredients, prep time, ratings).

**The SPA problem:** Since recipe pages are client-rendered SPA routes, crawlers that don't execute JavaScript won't see the markup. Options:

- **Build-time pre-rendering:** Generate static HTML for each recipe at deploy time with JSON-LD embedded. Most reliable for search engines.
- **Server-side injection:** Have the API or Caddy inject a `<script type="application/ld+json">` block into the HTML response for recipe URLs. Avoids a full SSR setup.
- **Noscript block:** Extend the existing noscript fallback pattern to include structured data. Simpler but less standard.

Lower priority until there's a reason to care about search engine rich results specifically.

---

## Individual Recipe Pages

Currently recipes only exist inside the SPA — there are no crawlable `/recipe/{name}` URLs. Adding server-rendered or pre-rendered recipe pages would make each recipe independently linkable and discoverable by agents and search engines.

This is a prerequisite for JSON-LD structured data to be useful, and would make the sitemap significantly more valuable (one entry per recipe instead of just top-level pages).

---

## Ingredient Landing Pages

No `/ingredient/{name}` pages exist. Adding pages that list recipes by ingredient would give agents and search engines another way to navigate the database and would improve internal linking.

---

## Search and Recipe Pages for Non-JS Clients

`/search.html` returns form UI structure but no content without JS. `/recipes.html` is an add-recipe form, not a browsable recipe list. Adding noscript fallbacks with links to the API search endpoint or a static recipe index would help agents that land on these pages.

---

## Analytics Noscript Content

The analytics page has a noscript block pointing to raw API endpoints, but the actual analytics content (charts, visualizations) requires JavaScript. Consider adding a static summary of key stats (top ingredients, recipe count by complexity) in the noscript block so agents get useful data without needing to make separate API calls.
