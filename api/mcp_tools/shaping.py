"""Pure helpers that turn database dicts into public MCP output models."""

from .models import (
    IngredientSwap,
    RecipeDetail,
    RecipeIngredientLine,
    RecipeSummary,
    SimilarRecipe,
    SimilarRecipesResult,
)

# Transport-plan mass is the fraction of the drink's volume moved between two
# ingredients. Below this, a "swap" is a proportion tweak, not a substitution.
MIN_SWAP_WEIGHT = 0.05


def recipe_url(base_url: str, recipe_id: int) -> str:
    return f"{base_url.rstrip('/')}/recipe/{recipe_id}"


def ingredient_url(base_url: str, ingredient_id: int) -> str:
    return f"{base_url.rstrip('/')}/ingredient/{ingredient_id}"


def _public_tags(recipe: dict) -> list[str]:
    return [t["name"] for t in recipe.get("tags") or [] if t.get("type") == "public"]


def _abv_display(recipe: dict) -> str | None:
    abv = recipe.get("abv")
    return abv.get("display") if abv else None


def to_summary(recipe: dict, base_url: str) -> RecipeSummary:
    return RecipeSummary(
        id=recipe["id"],
        name=recipe["name"],
        url=recipe_url(base_url, recipe["id"]),
        ingredients=[i["ingredient_name"] for i in recipe.get("ingredients") or []],
        abv=_abv_display(recipe),
        avg_rating=recipe.get("avg_rating"),
        rating_count=recipe.get("rating_count") or 0,
        tags=_public_tags(recipe),
    )


def to_detail(recipe: dict, base_url: str) -> RecipeDetail:
    abv = recipe.get("abv") or {}
    return RecipeDetail(
        id=recipe["id"],
        name=recipe["name"],
        url=recipe_url(base_url, recipe["id"]),
        description=recipe.get("description"),
        instructions=recipe.get("instructions"),
        ingredients=[
            RecipeIngredientLine(
                ingredient_id=i["ingredient_id"],
                name=i["ingredient_name"],
                url=ingredient_url(base_url, i["ingredient_id"]),
                amount=i.get("amount"),
                unit=i.get("unit_abbreviation") or i.get("unit_name"),
            )
            for i in recipe.get("ingredients") or []
        ],
        abv=abv.get("display"),
        abv_notes=list(abv.get("notes") or []),
        avg_rating=recipe.get("avg_rating"),
        rating_count=recipe.get("rating_count") or 0,
        tags=_public_tags(recipe),
        source=recipe.get("source"),
        source_url=recipe.get("source_url"),
    )


def to_similar(row: dict, base_url: str, limit: int) -> SimilarRecipesResult:
    neighbors = sorted(row.get("neighbors") or [], key=lambda n: n["distance"])
    similar = [
        SimilarRecipe(
            id=n["neighbor_recipe_id"],
            name=n["neighbor_name"],
            url=recipe_url(base_url, n["neighbor_recipe_id"]),
            distance=n["distance"],
            swaps=[
                IngredientSwap(
                    from_ingredient=s["from_ingredient_name"],
                    to_ingredient=s["to_ingredient_name"],
                    weight=s["mass"],
                )
                for s in sorted(
                    n.get("transport_plan") or [], key=lambda s: s["mass"], reverse=True
                )
                if s["mass"] >= MIN_SWAP_WEIGHT
                and s["from_ingredient_name"] != s["to_ingredient_name"]
            ],
        )
        for n in neighbors[:limit]
    ]
    return SimilarRecipesResult(
        recipe_id=row["recipe_id"],
        recipe_name=row["recipe_name"],
        recipe_url=recipe_url(base_url, row["recipe_id"]),
        similar=similar,
    )


def path_ids(path: str | None) -> list[int]:
    return [int(p) for p in (path or "").split("/") if p]


def hierarchy_names(path: str | None, names: dict[int, str]) -> list[str]:
    return [names[i] for i in path_ids(path) if i in names]
