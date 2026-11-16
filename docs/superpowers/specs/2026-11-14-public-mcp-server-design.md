# Public MCP Server

**Date:** 2026-11-14
**Status:** Design approved
**Source:** `docs/IDEAS.md` "MCP Server"; Agent Discoverability Phase 2 "Future" list
**Follow-up:** #134 (public "what can I make from this list" search)

## Intent

When someone asks an AI assistant for cocktail recommendations, the assistant
should be able to look up real recipes from mixology.tools instead of answering
from its training data. A public, read-only Model Context Protocol (MCP)
endpoint gives hosted assistants (Claude, ChatGPT, Cursor and similar) a
direct, tool-shaped way to search recipes, read them, and find similar drinks.

This continues the agent-discoverability work: Phase 1 and the crawlable pages
serve crawlers; this serves agents at answer time.

## Goals

- Assistants can connect by URL alone. No install, no account, no API key.
- Four tools that cover recommendation questions answerable today:
  recipe search, recipe details, similar recipes, ingredient lookup.
- Similarity results carry the precomputed ingredient swaps (the transport
  plan summary in `recipe_similarity.neighbors`), so an assistant can explain
  *how* a neighbour differs ("swap Lillet for Cocchi Americano"), not just
  name it.
- Every recipe and ingredient in a result carries its canonical
  mixology.tools page URL (`{base_url}/recipe/{id}`,
  `{base_url}/ingredient/{id}`), so assistants can cite and link back.
- Results are compact and LLM-friendly: curated fields, short descriptions,
  bounded sizes.

## Non-goals

- Anything that needs login: inventory, ratings by the caller, private tags,
  groups.
- Any write operation (creating or editing recipes, ingredients, tags,
  ratings).
- "What can I make from this list of ingredients" — tracked in #134. It needs
  new backend work to run substitution matching against a caller-supplied
  list.
- Analytics chart payloads (cocktail space, ingredient tree, complexity).
- MCP resources and prompts. Tools only for now.
- Directory/registry listings for the MCP server (can follow once it is live).

## Anti-goals

These would make it a failure even if it technically works:

- Exposing any write path or any authenticated data through MCP.
- Leaking internal identifiers that are not already intended for the public,
  in particular `created_by` (Cognito user IDs) and private tags.
- Degrading the website or API: MCP traffic must not be able to starve the
  API workers or bypass the existing rate limiter.
- Dumping raw API responses (dozens of fields, deprecated legacy fields) into
  the model's context.

## Constraints

- FastAPI app in `api/main.py`, 2 uvicorn workers (`api/Dockerfile.prod`),
  sync psycopg2 `Database` singleton from `db.database.get_database`.
- Caddy strips `/api/v1` before proxying, so a FastAPI mount at `/mcp` is
  public at `https://mixology.tools/api/v1/mcp` with no Caddy change.
- Per-IP sliding-window rate limit, 60 requests/minute, keyed on `X-Real-IP`
  (`api/middleware/rate_limit.py`).
- Python 3.14 runtime, 3.12 minimum syntax (README "Python support").
- MCP Python SDK: `mcp==2.3.0` installs cleanly with the current Starlette
  1.10 and uvicorn 0.54 and requires `pydantic>=2.12`, so the existing
  `pydantic==2.13.5` pin stays.
- In `mcp` 2.x, `FastMCP` was renamed: use
  `from mcp.server.mcpserver import MCPServer`. v1 tutorials will not work
  as written.
- Routes raise `core/exceptions.py` types; don't wrap in broad
  `except Exception` → `DatabaseException` in new code.
- Deploys are human actions via `scripts/deploy-ec2.sh`. No migration is
  needed (no schema change).

## Approaches considered

| | Approach | Trade-offs |
|---|---|---|
| **A (chosen)** | MCP endpoint mounted inside the existing FastAPI app, hand-written tools calling the `Database` layer directly | Connect-by-URL; reuses deploy, rate limiter, logging, DB pool; one more dependency in the API image and MCP traffic shares the API process. |
| B | Separate MCP service on the same host calling the public HTTP API | Full isolation, but another systemd unit, Ansible and deploy changes, and an extra hop per call — real ops cost for a small read-only surface. |
| C | Auto-generate tools from the OpenAPI spec | Fastest, but the endpoints are shaped for the SPA (cursor pagination, `Gin:MUST` syntax, large analytics payloads), write routes must be filtered carefully, and LLMs choose and use small, well-described tools far better. |

Dropped early: a locally installed package (uvx/npx). Hosted assistants can't
use it, which defeats the public-agent goal.

The owner chose **A**.

## Design

### Endpoint

- New module `api/mcp_server.py` (name is the builder's call) that builds an
  `MCPServer` named "Mixology Tools" with `instructions` describing the
  database and when to use it (e.g. "Use these tools to recommend cocktails
  with real recipes from mixology.tools; cite the recipe URL").
- Transport: streamable HTTP, **stateless** (`stateless_http=True`) and
  **JSON responses** (`json_response=True`). Stateless means any of the two
  uvicorn workers can serve any request, and no long-lived SSE streams hold
  connections open through the existing `BaseHTTPMiddleware` stack.
- Mounted in `api/main.py` so the public URL is
  `https://mixology.tools/api/v1/mcp`. The SDK's session manager must be run
  inside the FastAPI `lifespan` (`async with mcp.session_manager.run():`
  around the existing `yield`).
- DNS-rebinding/host checking (`TransportSecuritySettings`): the endpoint is
  intentionally public and unauthenticated, so host validation adds nothing
  but breakage behind Caddy. Disable it, or allow the configured
  domain(s) derived from `settings.base_url` plus localhost — builder's call,
  but it must work for prod, dev, and local test clients.
- The existing `CORSHeaderMiddleware` wraps the mount unchanged. *(Design
  call, not owner decision:)* browser-based MCP clients are out of scope —
  the current CORS headers don't allow `Mcp-Protocol-Version` /
  `Mcp-Session-Id` and preflight isn't handled for the mount. Hosted
  assistants and the MCP Inspector via its local proxy call server-side and
  are unaffected. Document this as a known limitation.
- Rate limiting: see "Abuse and load".
- Add `"mcp": "/api/v1/mcp"` to the self-describing root (`GET /`) so agents
  that read it find the endpoint.

### Tools

All tools are read-only and anonymous: they never call
`get_current_user_optional` and pass `user_id=None` to the DB layer. Mark
each with MCP tool annotations `readOnlyHint=true`, `openWorldHint=false`.
DB calls are synchronous; register tools as sync functions (or run DB calls
in a worker thread) so they don't block the event loop.

Descriptions are part of the product: they decide whether an assistant picks
the tool. Each should say what it's for in recommendation terms and how it
chains with the others (e.g. "use `find_ingredients` to get exact ingredient
names before filtering `search_recipes` by ingredient").

1. **`search_recipes`** — find recipes.
   - Inputs: `query` (name/text, optional), `include_ingredients` (list of
     ingredient names, all required), `exclude_ingredients` (list),
     `tags` (list of public tag names), `min_abv` / `max_abv` (0–100),
     `sort` (`name` | `rating` | `random`, default `name`), `limit`
     (default 10, max 25), `offset` (default 0).
   - Maps onto `db.search_recipes_paginated` with the existing
     `ingredients` syntax (`Name:MUST`, `Name:MUST_NOT`) built internally, so
     the model never sees that syntax.
   - Returns a compact summary per recipe: id, name, url, short ingredient
     list (names only), ABV estimate, average rating and count, public tags;
     plus `has_more`.
   - Offset pagination, not cursors: simpler for a model to use.

2. **`get_recipe`** — full recipe by id.
   - Returns name, url, description, instructions, ingredients with amount,
     unit and ingredient id/name, ABV estimate, average rating and count,
     public tags, source and source_url.
   - Omits `created_by`, `user_rating`, private tags, deprecated legacy tag
     fields and `image_url` if empty.
   - Unknown id → MCP tool error with a clear message.

3. **`find_similar_recipes`** — nearest neighbours of a recipe.
   - Inputs: `recipe_id`, `limit` (default 5, capped at what is stored).
   - Uses `db.get_recipe_similarity`; neighbours sorted by distance.
   - Per neighbour: id, name, url, distance, and its top ingredient swaps
     (`from` ingredient name → `to` ingredient name, with mass/weight),
     rendered so a model can read them as "swap A for B".
   - The description explains what distance means in plain terms
     (ingredient-based Earth Mover's distance; 0 = same ingredient
     profile; lower = more similar) and that it reflects ingredients only,
     not taste notes or technique.
   - Recipe with no similarity row → tool error saying similarity isn't
     available for that recipe yet.

4. **`find_ingredients`** — resolve ingredient names.
   - Inputs: `query`, `limit` (default 10).
   - Uses the existing ingredient search in the DB layer.
   - Returns id, name, url, hierarchy path as names (e.g.
     "Spirits > Agave spirits > Mezcal"), and ABV if known.
   - Purpose: map a user's words ("rye", "Campari") to the database's
     canonical names for `search_recipes`.

Getting a recipe by name is covered by `search_recipes(query=...)`; no
separate tool.

### Output shape

Return structured content (Pydantic models or typed dicts) so the SDK emits
both `structuredContent` and a text rendering. Keep field names
self-explanatory. Every recipe/ingredient object includes `url`, built from
`settings.base_url` the same way `api/routes/pages.py` does.

### Errors

Validation errors (bad ABV range, limit out of range, unknown sort) and
not-found return MCP tool errors (`isError: true`) with a message the model
can act on. Unexpected DB failures surface as a generic tool error; log the
detail server-side, don't return it.

### Abuse and load

Hosted assistants call from a small set of provider egress IPs, so under the
site-wide 60 req/min per-IP limit every user of one assistant would share one
bucket. The owner chose a separate MCP budget plus a database concurrency cap:

- **Own per-IP bucket for `/mcp`**, separate from the website/API bucket and
  larger (default 300 req/min per IP per worker; configurable via settings).
  MCP requests neither consume nor are blocked by the website's bucket, and
  vice versa. Every request is still limited — nothing bypasses rate
  limiting.
- **Concurrency cap on MCP database work**: at most 2 concurrent MCP tool
  DB calls per worker (configurable). The psycopg2 pool allows 10 connections
  per worker and raises when empty rather than waiting
  (`api/db/db_core.py` `_init_pool`); `configure_threadpool()` in
  `api/main.py` therefore bounds the shared threadpool to 5 threads, and MCP
  DB work runs in that same pool. Capping MCP at 2 keeps at least 3 threads
  for website routes. *(Originally 4; lowered when the threadpool bound
  landed on main.)* Excess MCP calls wait briefly for a slot;
  if they can't get one within a short timeout, return a tool error saying
  the service is busy.
- When the MCP bucket is exhausted, respond 429 with `Retry-After` and a
  JSON-RPC-shaped error body, so MCP clients surface "rate limited, retry
  later" rather than a broken connector.
- Each MCP HTTP request counts once; `limit` caps on every tool bound
  response size.
- Tests cover: MCP and website buckets are independent; MCP bucket
  enforces its limit; concurrency cap holds with more parallel calls than
  slots.
- Request body size: rely on the SDK default maximum.

### Testing

- Unit-level: each tool's mapping and output shaping against a stubbed
  `Database` (no Docker): ingredient filter syntax built correctly, private
  fields absent, URLs correct, limits enforced, not-found → tool error.
- Integration: an MCP client session (the SDK's client over the ASGI app via
  httpx, or plain JSON-RPC `initialize` / `tools/list` / `tools/call` POSTs
  through `TestClient`) against the real app with the testcontainers
  Postgres fixture used elsewhere in `tests/`. Assert `tools/list` returns
  exactly the four tools, all marked read-only.
- Regression: rate limiter applies to `/mcp`; root endpoint advertises it;
  existing suite still passes.
- Manual (can't be automated here): connect Claude (custom connector) and
  the MCP Inspector to the dev URL and run a few recommendation
  conversations.

### Documentation

- `api/README.md` or a short section in the main README: endpoint URL, the
  four tools, how to add it as a connector in an assistant.
- `docs/IDEAS.md` "MCP Server" section and the Phase 2 plan's "Future" bullet
  updated to point at this design.
- `docs/operations-runbook.md`: how to smoke-test the endpoint after deploy
  (a `curl` JSON-RPC `initialize` / `tools/list`).

## Left to the builder

- Module layout and names; whether tools share a small helper for URL
  building and recipe summarising.
- Exact Pydantic output models and field names, within the shapes above.
- Exact tool description wording.
- Host-validation setting, provided prod, dev and tests all work.
- Whether to call DB methods directly or factor shared logic out of the
  route handlers (prefer reuse over duplication where it's clean).
