# Public MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve a public, read-only MCP endpoint at `/mcp` (public URL `https://mixology.tools/api/v1/mcp`) with four recommendation tools, its own rate-limit bucket and a database concurrency cap.

**Architecture:** A new `api/mcp_tools/` package builds an `MCPServer` (mcp 2.x SDK) whose sync tools call the existing `Database` layer through a per-process concurrency gate and shape results into compact Pydantic models with canonical page URLs. An `McpEndpoint` ASGI wrapper owns the SDK's stateless, JSON-response streamable-HTTP app and is started from the FastAPI lifespan and registered as the `/mcp` route. `RateLimitMiddleware` gains a separate per-IP bucket for `/mcp` with a JSON-RPC-shaped 429.

**Tech Stack:** FastAPI / Starlette 1.10, `mcp==2.3.0` (`from mcp.server.mcpserver import MCPServer`), psycopg2, pytest + testcontainers, httpx `ASGITransport`.

**Spec:** `docs/superpowers/specs/2026-11-14-public-mcp-server-design.md`

## Global Constraints

- Python interpreter: `/home/kurtt/miniforge3/envs/cocktaildb-py314/bin/python` (3.14.10, matches CI); syntax must stay 3.12-compatible.
- Add `mcp==2.3.0` to `api/requirements.txt`; keep `pydantic==2.13.5` (mcp requires `pydantic>=2.12`).
- The package must **not** be named `mcp` (it would shadow the SDK, since `api/` is on `sys.path`). Use `api/mcp_tools/`.
- In mcp 2.x `FastMCP` is gone: import `MCPServer` from `mcp.server.mcpserver`, `ToolError` from `mcp.server.mcpserver.exceptions`, `ToolAnnotations` from `mcp_types`, `TransportSecuritySettings` from `mcp.server.transport_security`.
- Tools are anonymous and read-only: never read auth, always pass `user_id=None` / `cognito_user_id=None`. Annotate every tool `ToolAnnotations(readOnlyHint=True, openWorldHint=False)`.
- Never return `created_by`, `user_rating`, private tags, legacy `public_tags`/`private_tags` fields, or exception detail.
- URLs: `{base_url}/recipe/{id}` and `{base_url}/ingredient/{id}` with `settings.base_url` (strip any trailing `/`).
- New settings (in `api/core/config.py`): `mcp_rate_limit_per_minute: int = 300`, `mcp_max_concurrent_db_calls: int = 4`, `mcp_db_slot_timeout_seconds: float = 5.0`.
- Transport: `stateless_http=True`, `json_response=True`, DNS-rebinding protection disabled (endpoint is intentionally public).
- Browser-based MCP clients are out of scope; CORS middleware is unchanged.
- No schema change, no migration. Don't deploy.
- Full checks: `python -m pytest -q`, `python -m pre_commit run --all-files`. DB-backed tests need Docker.
- Commit prefixes: `feat:`, `fix:`, `docs:`, `chore:`.

## Review Focus

1. **Ingredient names in different case or partial form** ("campari", "rye"): the existing filter needs an exact, case-sensitive name and silently returns nothing otherwise. Expect a case-insensitive exact match to work, and anything else to come back in `unresolved_ingredients` rather than as a silent empty result. (Task 2 tests.)
2. **Ingredient names containing `:`** (e.g. "Amaro: Nonino"): the DB splits `name:OP` on the first colon, mangling the name. Expect such names to filter correctly. (Task 2: parse on the last colon only when the suffix is a known operator.)
3. **Recipe with no similarity row / unknown recipe id**: expect a tool error the model can act on, not an empty success or a 500. (Task 2 tests.)
4. **Lifespan restarts** (tests, or uvicorn reload): the SDK session manager's `run()` works once per instance. Expect each `running()` to build a fresh server so a second start works. (Task 3 test.)
5. **Busy database**: more concurrent MCP calls than slots. Expect waiting callers to time out with the busy tool error, while website routes keep their connections. (Task 2 gate test.)

---

### Task 1: Dependency, settings, output models and shaping helpers

**Files:**
- Modify: `api/requirements.txt` (add `mcp==2.3.0`)
- Modify: `api/core/config.py` (three `mcp_*` settings from Global Constraints)
- Create: `api/mcp_tools/__init__.py` (empty)
- Create: `api/mcp_tools/models.py`
- Create: `api/mcp_tools/shaping.py`
- Test: `tests/test_mcp_shaping.py` (pure unit tests, no Docker)

**Interfaces:**
- Produces, in `models.py` (Pydantic `BaseModel`s; field descriptions are part of the tool schema, keep them short and plain):
  - `RecipeSummary(id: int, name: str, url: str, ingredients: list[str], abv: str | None, avg_rating: float | None, rating_count: int, tags: list[str])`
  - `RecipeIngredientLine(ingredient_id: int, name: str, url: str, amount: float | None, unit: str | None)`
  - `RecipeDetail(id: int, name: str, url: str, description: str | None, instructions: str | None, ingredients: list[RecipeIngredientLine], abv: str | None, abv_notes: list[str], avg_rating: float | None, rating_count: int, tags: list[str], source: str | None, source_url: str | None)`
  - `RecipeSearchResult(recipes: list[RecipeSummary], has_more: bool, offset: int, unresolved_ingredients: list[str])`
  - `IngredientSwap(from_ingredient: str, to_ingredient: str, weight: float)`
  - `SimilarRecipe(id: int, name: str, url: str, distance: float, swaps: list[IngredientSwap])`
  - `SimilarRecipesResult(recipe_id: int, recipe_name: str, recipe_url: str, similar: list[SimilarRecipe])`
  - `IngredientMatch(id: int, name: str, url: str, hierarchy: list[str], description: str | None, percent_abv: float | None)`
  - `IngredientSearchResult(ingredients: list[IngredientMatch])`
- Produces, in `shaping.py`:
  - `recipe_url(base_url: str, recipe_id: int) -> str`, `ingredient_url(base_url: str, ingredient_id: int) -> str`
  - `to_summary(recipe: dict, base_url: str) -> RecipeSummary`
  - `to_detail(recipe: dict, base_url: str) -> RecipeDetail`
  - `to_similar(row: dict, base_url: str, limit: int) -> SimilarRecipesResult`
  - `hierarchy_names(path: str | None, names: dict[int, str]) -> list[str]`
  - `path_ids(path: str | None) -> list[int]`

Input dicts are what `Database.get_recipe` / `search_recipes_paginated` return (see `RecipeResponse` in `api/models/responses.py`: `ingredients[]` with `ingredient_id`, `ingredient_name`, `amount`, `unit_name`, `unit_abbreviation`; `tags[]` with `name`, `type`; `abv` with `display`, `notes`) and the `recipe_similarity` row (`recipe_id`, `recipe_name`, `neighbors[]` with `neighbor_recipe_id`, `neighbor_name`, `distance`, `transport_plan[]` of `from_ingredient_name`, `to_ingredient_name`, `mass`).

- [ ] **Step 1: Write failing tests** in `tests/test_mcp_shaping.py`:

```python
BASE = "https://mixology.tools"

def test_urls_strip_trailing_slash():
    assert recipe_url(BASE + "/", 12) == "https://mixology.tools/recipe/12"
    assert ingredient_url(BASE, 8) == "https://mixology.tools/ingredient/8"

def test_detail_drops_private_fields_and_keeps_public_tags():
    recipe = {  # minimal get_recipe-shaped dict
        "id": 1, "name": "Negroni", "instructions": "Stir.", "description": None,
        "source": "Book", "source_url": None, "avg_rating": 4.5, "rating_count": 2,
        "created_by": "cognito-sub-123", "user_rating": 5,
        "abv": {"status": "calculated", "display": "24%", "notes": ["n"]},
        "ingredients": [{"ingredient_id": 4, "ingredient_name": "Gin", "amount": 1.0,
                         "unit_name": "ounce", "unit_abbreviation": "oz"}],
        "tags": [{"id": 1, "name": "bitter", "type": "public"},
                 {"id": 2, "name": "mine", "type": "private"}],
    }
    d = to_detail(recipe, BASE)
    dumped = d.model_dump()
    assert "created_by" not in dumped and "user_rating" not in dumped
    assert d.tags == ["bitter"]
    assert d.url == "https://mixology.tools/recipe/1"
    assert d.ingredients[0].unit == "oz"
    assert d.ingredients[0].url == "https://mixology.tools/ingredient/4"
    assert d.abv == "24%" and d.abv_notes == ["n"]

def test_summary_lists_ingredient_names_and_handles_missing_rating():
    s = to_summary({"id": 3, "name": "X", "avg_rating": None, "rating_count": None,
                    "ingredients": [{"ingredient_id": 1, "ingredient_name": "Rum"}],
                    "tags": [], "abv": None}, BASE)
    assert s.ingredients == ["Rum"] and s.rating_count == 0 and s.abv is None

def test_similar_sorted_by_distance_and_limited_with_swaps_by_weight():
    row = {"recipe_id": 1, "recipe_name": "Negroni", "neighbors": [
        {"neighbor_recipe_id": 3, "neighbor_name": "Far", "distance": 0.9, "transport_plan": []},
        {"neighbor_recipe_id": 2, "neighbor_name": "Near", "distance": 0.1, "transport_plan": [
            {"from_ingredient_name": "Gin", "to_ingredient_name": "Bourbon", "mass": 0.2},
            {"from_ingredient_name": "Campari", "to_ingredient_name": "Aperol", "mass": 0.5}]},
    ]}
    r = to_similar(row, BASE, limit=1)
    assert [s.name for s in r.similar] == ["Near"]
    assert r.similar[0].swaps[0].from_ingredient == "Campari"
    assert r.similar[0].url == "https://mixology.tools/recipe/2"

def test_hierarchy_names_from_path():
    assert path_ids("/1/8/") == [1, 8]
    assert hierarchy_names("/1/8/", {1: "Whiskey", 8: "Bourbon"}) == ["Whiskey", "Bourbon"]
    assert hierarchy_names(None, {}) == []
```

- [ ] **Step 2: Run to verify failure**
Run: `python -m pytest tests/test_mcp_shaping.py -q`
Expected: FAIL (`ModuleNotFoundError: mcp_tools`).

- [ ] **Step 3: Install the dependency and implement** `models.py` and `shaping.py` per Interfaces. Install with `python -m pip install mcp==2.3.0` and confirm `pip check` is clean. Tags: keep only `type == "public"` names. ABV: `abv["display"]` or `None` when `abv` is missing; `abv_notes` defaults to `[]`. `hierarchy_names` skips ids missing from `names`.

- [ ] **Step 4: Run to verify pass**
Run: `python -m pytest tests/test_mcp_shaping.py -q` → all pass.

- [ ] **Step 5: Commit**
`git add api/requirements.txt api/core/config.py api/mcp_tools tests/test_mcp_shaping.py && git commit -m "feat: add MCP output models and result shaping"`

---

### Task 2: Concurrency gate and the four MCP tools

**Files:**
- Create: `api/mcp_tools/gate.py`
- Create: `api/mcp_tools/server.py`
- Modify: `api/db/db_core.py` (ingredient-spec parsing near line 1974; new `get_ingredient_names`)
- Test: `tests/test_mcp_tools.py` (stub `Database` via `unittest.mock.MagicMock`, no Docker)
- Test: `tests/test_db_ingredients.py` (add DB tests for colon names and `get_ingredient_names`; Docker)

**Interfaces:**
- Consumes: Task 1 models and shaping functions.
- Produces:
  - `gate.py`: `BUSY_MESSAGE = "Mixology Tools is busy right now. Please retry in a few seconds."`; `class DbGate(max_concurrent: int, timeout_seconds: float)` with context manager `slot() -> Iterator[None]` (a `threading.BoundedSemaphore`, acquired with timeout; on timeout raises `ToolError(BUSY_MESSAGE)`).
  - `server.py`: `build_mcp_server(get_db: Callable[[], Database], *, base_url: str, gate: DbGate) -> MCPServer`, registering sync tools `search_recipes`, `get_recipe`, `find_similar_recipes`, `find_ingredients`.
  - `server.py`: `resolve_ingredient_name(db: Database, name: str) -> str | None`. Uses `db.search_ingredients(name)` and returns the canonical `name` of the result whose `name.casefold()` equals `name.strip().casefold()`, else `None`.
  - `db_core.py`: `Database.get_ingredient_names(ids: Iterable[int]) -> dict[int, str]` (one `SELECT id, name ... WHERE id = ANY(%s)`; empty input returns `{}` without querying).

Tool signatures. Use `Annotated[..., Field(...)]` for bounds and descriptions so they appear in the input schema:
- `search_recipes(query: str | None = None, include_ingredients: list[str] | None = None, exclude_ingredients: list[str] | None = None, tags: list[str] | None = None, min_abv: int | None (0–100) = None, max_abv: int | None (0–100) = None, sort: Literal["name", "rating", "random"] = "name", limit: int (1–25) = 10, offset: int (0–1000) = 0) -> RecipeSearchResult`
  - Sort mapping: `name` → (`name`, `asc`); `rating` → (`avg_rating`, `desc`); `random` → (`random`, `asc`).
  - Call `db.search_recipes_paginated(search_params, limit=limit, offset=offset, sort_by=..., sort_order=..., user_id=None, return_pagination=True)`. `search_params["ingredients"]` is a list of `f"{canonical}:MUST"` / `f"{canonical}:MUST_NOT"` strings.
  - Unresolved include names: don't search. Return `recipes=[]`, `has_more=False` and list those names in `unresolved_ingredients`.
  - Unresolved exclude names: drop them from the filter and still list them.
  - `min_abv > max_abv` raises `ToolError`.
- `get_recipe(recipe_id: int) -> RecipeDetail`. If `db.get_recipe(recipe_id, None)` returns `None`, raise `ToolError(f"No recipe with id {recipe_id}. Use search_recipes to find recipe ids.")`.
- `find_similar_recipes(recipe_id: int, limit: int (1–10) = 5) -> SimilarRecipesResult`. If there is no row, raise `ToolError(f"Similarity data isn't available for recipe {recipe_id}. Check the id with search_recipes or get_recipe.")`.
- `find_ingredients(query: str (min_length 1), limit: int (1–25) = 10) -> IngredientSearchResult`. Take the first `limit` rows of `db.search_ingredients`, then resolve hierarchy names with a single `get_ingredient_names` call over every id in their paths.

Every DB call sits inside `with gate.slot():`. Leave unexpected exceptions alone: the SDK turns them into a detail-free `UnexpectedToolError`. Write server `instructions` and tool descriptions per the spec "Tools" section: say when to use each tool, how they chain, and what similarity distance means.

- [ ] **Step 1: Write failing tool tests** in `tests/test_mcp_tools.py`. Build the server with a `MagicMock` db, `base_url="https://mixology.tools"` and `DbGate(2, 0.05)`. Call tools with `await server.call_tool(name, args)` (check the 2.3.0 return shape and read structured content from it). Mark with `pytest.mark.asyncio`.

```python
async def test_lists_exactly_four_read_only_tools(server):
    tools = await server.list_tools()
    assert {t.name for t in tools} == {"search_recipes", "get_recipe", "find_similar_recipes", "find_ingredients"}
    assert all(t.annotations.readOnlyHint for t in tools)

async def test_search_resolves_names_case_insensitively(server, db):
    db.search_ingredients.side_effect = lambda n: [{"id": 4, "name": "Campari", "path": "/4/"}] if n.lower() == "campari" else []
    db.search_recipes_paginated.return_value = {"recipes": [], "has_next": False, "next_cursor": None}
    result = await call(server, "search_recipes", {"include_ingredients": ["campari"], "exclude_ingredients": ["nope"]})
    params = db.search_recipes_paginated.call_args.args[0]
    assert params["ingredients"] == ["Campari:MUST"]
    assert result["unresolved_ingredients"] == ["nope"]

async def test_search_with_unresolved_include_returns_empty_without_querying(server, db):
    db.search_ingredients.return_value = []
    result = await call(server, "search_recipes", {"include_ingredients": ["unobtainium"]})
    db.search_recipes_paginated.assert_not_called()
    assert result["recipes"] == [] and result["unresolved_ingredients"] == ["unobtainium"]

async def test_search_sort_rating_maps_to_avg_rating_desc(server, db): ...
    # assert call kwargs sort_by == "avg_rating", sort_order == "desc", user_id is None

async def test_search_rejects_min_abv_above_max(server):  # isError result
async def test_search_limit_above_25_is_rejected(server):  # isError result
async def test_get_recipe_unknown_id_is_tool_error_mentioning_search_recipes(server, db)
async def test_get_recipe_passes_no_user(server, db):  # db.get_recipe called with (id, None)
async def test_similar_missing_row_is_tool_error(server, db)
async def test_find_ingredients_returns_hierarchy_names(server, db):
    # search_ingredients -> [{"id": 8, "name": "Bourbon", "path": "/1/8/", "description": None, "percent_abv": 45.0}]
    # get_ingredient_names -> {1: "Whiskey", 8: "Bourbon"}; assert hierarchy == ["Whiskey", "Bourbon"], url ends /ingredient/8
async def test_unexpected_db_error_hides_detail(server, db):
    db.get_recipe.side_effect = RuntimeError("password=secret")
    # assert isError and "secret" not in the error text
```

Gate tests (plain sync tests):

```python
def test_gate_times_out_with_busy_message_when_full():
    gate = DbGate(1, 0.05)
    with gate.slot():
        with pytest.raises(ToolError, match="busy"):
            with gate.slot():
                pass

def test_gate_caps_concurrency_under_parallel_load():
    # 8 threads each hold a slot ~20 ms with DbGate(2, 1.0); track the max number inside slot() at once; assert == 2
```

- [ ] **Step 2: Write failing DB tests** in `tests/test_db_ingredients.py` (use the existing `db_instance_with_data` fixture):
  - `test_get_ingredient_names_returns_mapping`: `{1: "Whiskey", 8: "Bourbon"}` for ids `[1, 8]`; `{}` for `[]`.
  - `test_search_ingredient_filter_handles_colon_in_name`: insert ingredient `"Amaro: Nonino"` and a recipe using it; `search_recipes_paginated({"ingredients": ["Amaro: Nonino:MUST"]}, ...)` returns that recipe. `["Amaro: Nonino"]` with no operator also returns it.

- [ ] **Step 3: Run to verify failure**
Run: `python -m pytest tests/test_mcp_tools.py tests/test_db_ingredients.py -q`
Expected: new tests FAIL.

- [ ] **Step 4: Implement** `gate.py`, `server.py` and the two `db_core.py` changes. Ingredient-spec parsing: `name, sep, op = spec.rpartition(":")`. If `sep` is present and `op.strip().upper()` is in `{"MUST", "MUST_NOT"}`, use that split. Otherwise the whole spec is the name and the operator is `MUST`.

- [ ] **Step 5: Run to verify pass**
Run: `python -m pytest tests/test_mcp_tools.py tests/test_db_ingredients.py tests/test_combined_search.py tests/test_ingredient_search.py -q` → all pass.

- [ ] **Step 6: Commit**
`git commit -m "feat: add read-only MCP tools with database concurrency gate"` (stage the files above)

---

### Task 3: Mount the endpoint in FastAPI, advertise it, document it

**Files:**
- Create: `api/mcp_tools/endpoint.py`
- Modify: `api/main.py` (lifespan, route, root endpoint)
- Test: `tests/test_mcp_endpoint.py` (Docker; uses `test_client_with_data`)
- Modify: `api/README.md` (MCP section: URL, tools, how to add as a custom connector, browser-client limitation)
- Modify: `docs/operations-runbook.md` (post-deploy smoke test: `curl` JSON-RPC to `/api/v1/mcp` listing tools)
- Modify: `docs/IDEAS.md` "MCP Server" section, and the "Future" bullet in `docs/plans/2026-03-29-agent-discoverability-phase2.md`: point to the spec

**Interfaces:**
- Consumes: `build_mcp_server`, `DbGate` (Task 2); `get_database` from `db.database`; settings from Task 1.
- Produces: `class McpEndpoint(server_factory: Callable[[], MCPServer])`:
  - async context manager `running()`: builds a **fresh** server and calls `server.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, json_response=True, transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))`, then enters `server.session_manager.run()`, stores the app and yields; clears the app on exit.
  - ASGI `__call__(scope, receive, send)`: delegates to the stored app. If the endpoint isn't running, answers 503 with a JSON-RPC error body.
- In `api/main.py`: a module-level `mcp_endpoint = McpEndpoint(lambda: build_mcp_server(get_database, base_url=settings.base_url, gate=mcp_gate))`, with one module-level `mcp_gate` built from the settings. The lifespan wraps `yield` in `async with mcp_endpoint.running():`. Register with `app.add_route("/mcp", mcp_endpoint, methods=["GET", "POST", "DELETE"], include_in_schema=False)`. The root response gains top-level `"mcp": "/api/v1/mcp"`.

Test helper: `mcp_post(client, method, params, id=1)` POSTs JSON-RPC to `/mcp` with `Accept: application/json, text/event-stream` and `Content-Type: application/json`. If stateless legacy mode in 2.3.0 rejects `tools/list` without `initialize`, the helper sends `initialize` first. A fixture enters `main.mcp_endpoint.running()` around the test, because `ASGITransport` doesn't run lifespan.

- [ ] **Step 1: Write failing tests** in `tests/test_mcp_endpoint.py`:
  - `test_tools_list_over_http`: 200, exactly the four tool names.
  - `test_search_recipes_over_http_returns_seeded_recipe`: `search_recipes` with `{"query": "Old Fashioned"}` → structured content includes `"Test Old Fashioned"` with `url` starting `https://mixology.tools/recipe/` (or the test settings' `base_url`).
  - `test_get_recipe_over_http_has_no_private_fields`: response JSON text contains neither `created_by` nor `user_rating`.
  - `test_similar_over_http_with_seeded_similarity_row`: insert a `recipe_similarity` row for recipe 1 with one neighbour and a transport plan, then assert the neighbour name and swap.
  - `test_endpoint_restarts_cleanly`: enter and exit `running()` twice in a row and `tools/list` succeeds both times. (Review Focus 4.)
  - `test_not_running_returns_503_jsonrpc_error`: call without the fixture → 503, body has `"jsonrpc": "2.0"` and `error`.
  - `test_root_advertises_mcp`: `GET /` → `body["mcp"] == "/api/v1/mcp"`.

- [ ] **Step 2: Run to verify failure**
Run: `python -m pytest tests/test_mcp_endpoint.py -q` → FAIL.

- [ ] **Step 3: Implement** `endpoint.py` and the `main.py` changes.

- [ ] **Step 4: Run to verify pass**
Run: `python -m pytest tests/test_mcp_endpoint.py tests/test_fastapi.py tests/test_api_unit.py -q` → pass.

- [ ] **Step 5: Manual smoke** (record the output in the PR test plan). Run the app locally against the test DB, or just as `python -c` with uvicorn, and POST `tools/list` with `curl`. Note in the PR that a Claude custom connector and MCP Inspector were **not** tested here.

- [ ] **Step 6: Update docs** (files listed above), then commit:
`git commit -m "feat: serve public MCP endpoint at /mcp"`

---

### Task 4: Separate MCP rate-limit bucket with JSON-RPC 429

**Files:**
- Modify: `api/middleware/rate_limit.py`
- Modify: `api/main.py` (pass the MCP limit into the middleware)
- Modify: `api/core/config.py` (`api_description` "Rate Limits": mention the separate `/mcp` limit)
- Test: `tests/test_rate_limit.py`

**Interfaces:**
- Produces: `RateLimitMiddleware(app, max_requests: int = 60, window_seconds: int = 60, mcp_max_requests: int = 300, mcp_path: str = "/mcp")`. When `request.url.path == mcp_path`, requests are tracked under key `("mcp", ip)` with limit `mcp_max_requests`; everything else uses key `("api", ip)` with `max_requests`. On MCP overflow, return 429 with `Retry-After` and body `{"jsonrpc": "2.0", "id": None, "error": {"code": -32000, "message": "Rate limit exceeded. Please retry after N seconds."}}`. The non-MCP 429 body is unchanged.
- `main.py`: `app.add_middleware(RateLimitMiddleware, mcp_max_requests=settings.mcp_rate_limit_per_minute)`.

- [ ] **Step 1: Write failing tests.** Use a tiny Starlette app wrapped in the middleware, with routes `/stats` and `/mcp` returning 200, `max_requests=2` and `mcp_max_requests=3`, so the tests stay fast:
  - `test_mcp_and_api_buckets_are_independent`: exhaust `/stats` (3rd → 429), and `/mcp` still returns 200 three times; exhaust `/mcp` (4th → 429), and a fresh-IP `/stats` is unaffected. Also: after exhausting `/mcp`, `/stats` for the same IP still has its own remaining count.
  - `test_mcp_429_is_jsonrpc_shaped`: body `["jsonrpc"] == "2.0"`, `body["error"]["code"] == -32000`, and `Retry-After` is present.
  - `test_app_uses_configured_mcp_limit`: the `RateLimitMiddleware` instance on `api.main.app` (via `RateLimitMiddleware._instances`) has `mcp_max_requests == 300`.
  - The existing tests in `tests/test_rate_limit.py` still pass unchanged.

- [ ] **Step 2: Run to verify failure**
Run: `python -m pytest tests/test_rate_limit.py -q` → new tests FAIL.

- [ ] **Step 3: Implement** the middleware changes and the `main.py` / `config.py` edits.

- [ ] **Step 4: Run the full checks**
Run: `python -m pytest -q` → all pass (report any Docker-dependent tests that couldn't run as **not run**).
Run: `python -m pre_commit run --all-files` → clean.

- [ ] **Step 5: Commit**
`git commit -m "feat: give MCP endpoint its own rate-limit bucket"`
