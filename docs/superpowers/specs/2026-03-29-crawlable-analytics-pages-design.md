# Crawlable Analytics Pages

**Date:** 2026-03-29
**Status:** Design approved
**Source:** Agent Discoverability Phase 2, item 4

## Goal

Make analytics content discoverable by search crawlers via static HTML pages generated at analytics refresh time. AI agents will be served by a future MCP server, so these pages target traditional search engines.

## Pages

Three static HTML pages:

| Page | URL | Content |
|------|-----|---------|
| Ingredient Usage | `/analytics/ingredient-usage` | Top ingredient categories by recipe frequency |
| Recipe Complexity | `/analytics/recipe-complexity` | Distribution of recipes by ingredient count |
| Cocktail Space | `/analytics/cocktail-space` | Descriptive landing page for UMAP visualizations |

Each page links to the interactive SPA at `/analytics.html` and back to the site root.

## Content

### Ingredient Usage

Reads `ingredient-usage.json` from analytics storage. Renders:

- Headline stats: number of top-level ingredient categories, max hierarchical usage as a proxy for total recipe coverage
- Table of top-level ingredient categories sorted by hierarchical usage (name, recipe count)
- Each ingredient links to its `/ingredient/{id}` page
- Meta description: "Top cocktail ingredients across N recipes -- spirits, citrus, sweeteners and more"

### Recipe Complexity

Reads `recipe-complexity.json` from analytics storage. Renders:

- Headline stats: average ingredients per cocktail, most common count (mode), total recipes
- Table showing distribution (ingredient count -> number of recipes)
- Prose summary ("Most cocktails use 3-6 ingredients...")
- Meta description: "How many ingredients do cocktails need? Complexity analysis of N recipes"

### Cocktail Space

Reads metadata from `cocktail-space.json` (recipe count, generation date). Renders:

- Descriptive prose explaining cocktail embeddings: ingredient-based similarity, UMAP dimensionality reduction, two distance metrics (Manhattan and EM-learned)
- Mention of clustering behavior (sours, stirred drinks, etc.)
- Stats: number of recipes analyzed, generation date
- Prominent link to interactive visualization at `/analytics.html`
- Meta description targeting "cocktail embeddings", "cocktail similarity map", "cocktail space visualization"

No JSON-LD on any of these pages -- no fitting schema.org type exists for analytics summaries.

## Architecture

### Templates

Three Jinja2 templates in `api/templates/`, extending `base.html`:

- `analytics_ingredient_usage.html`
- `analytics_recipe_complexity.html`
- `analytics_cocktail_space.html`

### Render script

New module at `api/analytics/render_pages.py`:

- Reads JSON from `ANALYTICS_PATH` via `AnalyticsStorage`
- Renders each template with standalone Jinja2 (no FastAPI dependency)
- Writes HTML to `ANALYTICS_PATH/pages/` (e.g., `pages/ingredient-usage.html`)
- CLI entrypoint: `python -m analytics.render_pages`
- Logs what it rendered, exits non-zero on failure

### Caddy

Add route block mapping analytics URLs to the generated static HTML files:

- `/analytics/ingredient-usage` -> `ANALYTICS_PATH/pages/ingredient-usage.html`
- `/analytics/recipe-complexity` -> `ANALYTICS_PATH/pages/recipe-complexity.html`
- `/analytics/cocktail-space` -> `ANALYTICS_PATH/pages/cocktail-space.html`

### Shell script

Update `infrastructure/scripts/trigger-analytics.sh` to chain the render step:

```
docker compose run --rm api python -m analytics.analytics_refresh
docker compose run --rm api python -m analytics.render_pages
```

### Sitemap

Update `pages.py` sitemap generation to include the three analytics URLs.

## Out of scope

- JSON-LD structured data (no suitable schema.org type)
- Server-side rendering at request time (data only changes on analytics refresh)
- Rendering the UMAP visualization as a static image
