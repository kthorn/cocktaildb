"""The public, read-only MCP server and its four tools."""

from collections.abc import Callable
from typing import Annotated, Literal

from db.db_core import Database
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field, StringConstraints

from .gate import DbGate
from .models import (
    IngredientMatch,
    IngredientSearchResult,
    RecipeDetail,
    RecipeSearchResult,
    SimilarRecipesResult,
)
from .shaping import (
    hierarchy_names,
    ingredient_url,
    path_ids,
    to_detail,
    to_similar,
    to_summary,
)

INSTRUCTIONS = (
    "Mixology Tools is a cocktail recipe database. Use it to find cocktails, "
    "read full recipes, and suggest similar drinks. Typical flow: call "
    'find_ingredients to turn a user\'s words ("rye", "Campari") into canonical '
    "ingredient names, pass those names to search_recipes to find candidates, "
    "then call get_recipe for the full recipe. Use find_similar_recipes to "
    "recommend alternatives to a recipe the user likes. Every result includes a "
    "url to share with the user. All tools are read-only."
)

_READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)

_SORTS = {
    "name": ("name", "asc"),
    "rating": ("avg_rating", "desc"),
    "random": ("random", "asc"),
}


Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


def build_mcp_server(
    get_db: Callable[[], Database], *, base_url: str, gate: DbGate
) -> MCPServer:
    server = MCPServer(name="Mixology Tools", instructions=INSTRUCTIONS)

    @server.tool(
        name="search_recipes",
        description=(
            "Find cocktail recipes by name, ingredients, tags and ABV. "
            "Use this to recommend drinks: for example, recipes containing gin "
            "but no vermouth, or low-ABV drinks sorted by rating. Ingredient "
            "names are matched case-insensitively against the database; use "
            "find_ingredients first if you are unsure of the exact name. Names "
            "that match nothing are listed in unresolved_ingredients (an "
            "unmatched include name yields no recipes). When query is given, "
            "recipes whose whole name equals it are returned first in "
            "exact_matches (for example the classic Negroni rather than its "
            "variations). Returns compact summaries; call get_recipe with an "
            "id for the full recipe. Page with offset while has_more is true."
        ),
        annotations=_READ_ONLY,
    )
    async def search_recipes(
        query: Annotated[
            str | None,
            Field(max_length=200, description="Text to match in recipe names"),
        ] = None,
        include_ingredients: Annotated[
            list[Name] | None,
            Field(
                max_length=10,
                description="Ingredient names the recipe must contain (max 10)",
            ),
        ] = None,
        exclude_ingredients: Annotated[
            list[Name] | None,
            Field(
                max_length=10,
                description="Ingredient names the recipe must not contain (max 10)",
            ),
        ] = None,
        tags: Annotated[
            list[Name] | None,
            Field(max_length=10, description="Public tag names to filter by (max 10)"),
        ] = None,
        min_abv: Annotated[
            int | None, Field(ge=0, le=100, description="Minimum ABV percent")
        ] = None,
        max_abv: Annotated[
            int | None, Field(ge=0, le=100, description="Maximum ABV percent")
        ] = None,
        sort: Annotated[
            Literal["name", "rating", "random"],
            Field(description="Sort order; rating is highest first"),
        ] = "name",
        limit: Annotated[
            int, Field(ge=1, le=25, description="Maximum recipes to return")
        ] = 10,
        offset: Annotated[
            int,
            Field(
                ge=0,
                le=1000,
                description=(
                    "Number of results to skip. Offset paging is not stable "
                    'with sort="random" (each call is a fresh draw)'
                ),
            ),
        ] = 0,
    ) -> RecipeSearchResult:
        if min_abv is not None and max_abv is not None and min_abv > max_abv:
            raise ToolError("min_abv cannot be greater than max_abv.")

        def fetch() -> tuple[dict | None, list[str], list[dict]]:
            db = get_db()
            requested = [(n, True) for n in include_ingredients or []] + [
                (n, False) for n in exclude_ingredients or []
            ]
            found = (
                db.search_ingredients_batch([n for n, _ in requested])
                if requested
                else {}
            )
            specs: list[str] = []
            unresolved: list[str] = []
            include_missing = False
            for name, is_include in requested:
                row = found.get(name)
                if row is None:
                    unresolved.append(name)
                    include_missing = include_missing or is_include
                    continue
                spec = f"{row['name']}:{'MUST' if is_include else 'MUST_NOT'}"
                if spec not in specs:
                    specs.append(spec)

            if include_missing:
                return None, unresolved, []

            search_params: dict = {}
            if query:
                search_params["q"] = query
            if specs:
                search_params["ingredients"] = specs
            if tags:
                search_params["tags"] = tags
            if min_abv is not None:
                search_params["min_abv"] = min_abv
            if max_abv is not None:
                search_params["max_abv"] = max_abv

            sort_by, sort_order = _SORTS[sort]
            result = db.search_recipes_paginated(
                search_params,
                limit=limit,
                offset=offset,
                sort_by=sort_by,
                sort_order=sort_order,
                user_id=None,
                return_pagination=True,
            )
            exact: list[dict] = []
            if query and query.strip():
                exact_ids = db.get_recipe_ids_by_exact_name(query.strip())
                if exact_ids:
                    # Exact matches never repeat in the paged list, on any page.
                    result["recipes"] = [
                        r for r in result["recipes"] if r["id"] not in exact_ids
                    ]
                    if offset == 0:
                        exact = [
                            recipe
                            for recipe_id in exact_ids
                            if (recipe := db.get_recipe(recipe_id, None)) is not None
                        ]
            return result, unresolved, exact

        result, unresolved, exact = await gate.run(fetch)
        if result is None:
            return RecipeSearchResult(
                recipes=[],
                has_more=False,
                offset=offset,
                unresolved_ingredients=unresolved,
            )
        return RecipeSearchResult(
            exact_matches=[to_summary(r, base_url) for r in exact],
            recipes=[to_summary(r, base_url) for r in result["recipes"]],
            has_more=bool(result.get("has_next")),
            offset=offset,
            unresolved_ingredients=unresolved,
        )

    @server.tool(
        name="get_recipe",
        description=(
            "Get the full recipe for one cocktail: ingredients with amounts and "
            "units, instructions, ABV estimate, rating, tags and source. Use "
            "after search_recipes or find_similar_recipes to show the details "
            "of a recipe the user is interested in."
        ),
        annotations=_READ_ONLY,
    )
    async def get_recipe(
        recipe_id: Annotated[int, Field(ge=1, description="Recipe id")],
    ) -> RecipeDetail:
        recipe = await gate.run(lambda: get_db().get_recipe(recipe_id, None))
        if recipe is None:
            raise ToolError(
                f"No recipe with id {recipe_id}. Use search_recipes to find recipe ids."
            )
        return to_detail(recipe, base_url)

    @server.tool(
        name="find_similar_recipes",
        description=(
            "Suggest recipes similar to a given recipe, closest first. Use it "
            "when a user likes a drink and wants alternatives or variations. "
            "distance is an ingredient-based Earth Mover's distance: 0 means "
            "the same ingredient profile and lower means more similar. It "
            "reflects ingredients only, not taste notes or technique. Each "
            "result lists swaps, read as 'swap from_ingredient for "
            "to_ingredient', with weight = the fraction of the drink's volume "
            "moved. Only swaps of at least 5% are listed; an empty swaps list "
            "means the recipes differ mainly in proportions, not ingredients."
        ),
        annotations=_READ_ONLY,
    )
    async def find_similar_recipes(
        recipe_id: Annotated[int, Field(ge=1, description="Id of the original recipe")],
        limit: Annotated[
            int, Field(ge=1, le=10, description="Maximum similar recipes")
        ] = 5,
    ) -> SimilarRecipesResult:
        row = await gate.run(lambda: get_db().get_recipe_similarity(recipe_id))
        if not row:
            raise ToolError(
                f"Similarity data isn't available for recipe {recipe_id}. "
                "Check the id with search_recipes or get_recipe."
            )
        return to_similar(row, base_url, limit)

    @server.tool(
        name="find_ingredients",
        description=(
            "Look up ingredients by name and get their canonical names, ids, "
            "place in the ingredient hierarchy (broadest first) and ABV. Use "
            'this to map a user\'s words ("rye", "Campari") to the database\'s '
            "ingredient names before filtering search_recipes by ingredient."
        ),
        annotations=_READ_ONLY,
    )
    async def find_ingredients(
        query: Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
            Field(description="Ingredient name or part of one"),
        ],
        limit: Annotated[
            int, Field(ge=1, le=25, description="Maximum ingredients to return")
        ] = 10,
    ) -> IngredientSearchResult:
        def fetch() -> tuple[list[dict], dict[int, str]]:
            db = get_db()
            rows = db.search_ingredients(query)[:limit]
            ids = {i for row in rows for i in path_ids(row.get("path"))}
            return rows, db.get_ingredient_names(ids)

        rows, names = await gate.run(fetch)

        return IngredientSearchResult(
            ingredients=[
                IngredientMatch(
                    id=row["id"],
                    name=row["name"],
                    url=ingredient_url(base_url, row["id"]),
                    hierarchy=hierarchy_names(row.get("path"), names),
                    description=row.get("description"),
                    percent_abv=row.get("percent_abv"),
                )
                for row in rows
            ]
        )

    return server
