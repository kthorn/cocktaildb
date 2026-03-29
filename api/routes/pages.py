"""Server-rendered HTML pages for recipe and ingredient discoverability."""

import json
import logging
from typing import Optional
from xml.etree.ElementTree import Element, SubElement, tostring

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from core.config import settings
from db.database import get_database
from db.db_core import Database

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _safe_source_url(url: Optional[str]) -> Optional[str]:
    """Only allow http/https URLs for source links."""
    if url and url.startswith(("http://", "https://")):
        return url
    return None


def _ingredient_summary(ingredients: list) -> str:
    """Build a short ingredient summary for meta descriptions."""
    names = [ing.get("ingredient_name", "") for ing in ingredients[:5]]
    summary = ", ".join(n for n in names if n)
    if len(ingredients) > 5:
        summary += f", and {len(ingredients) - 5} more"
    return summary


def _build_recipe_json_ld(recipe: dict, base_url: str) -> dict:
    """Build schema.org/Recipe JSON-LD from recipe data."""
    ld = {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": recipe["name"],
        "recipeCategory": "Cocktail",
        "url": f"{base_url}/recipe/{recipe['id']}",
    }

    if recipe.get("description"):
        ld["description"] = recipe["description"]

    # Ingredients
    ingredient_strings = []
    for ing in recipe.get("ingredients", []):
        parts = []
        if ing.get("amount"):
            parts.append(str(ing["amount"]))
        if ing.get("unit_abbreviation"):
            parts.append(ing["unit_abbreviation"])
        parts.append(ing.get("ingredient_name", ""))
        ingredient_strings.append(" ".join(parts))
    if ingredient_strings:
        ld["recipeIngredient"] = ingredient_strings

    # Instructions
    if recipe.get("instructions"):
        steps = [s.strip() for s in recipe["instructions"].split("\n") if s.strip()]
        if not steps:
            steps = [recipe["instructions"]]
        ld["recipeInstructions"] = [
            {"@type": "HowToStep", "text": step} for step in steps
        ]

    # Tags as keywords
    tags = recipe.get("tags", [])
    public_tags = [t["name"] for t in tags if t.get("type") == "public"]
    if public_tags:
        ld["keywords"] = public_tags

    # Rating
    if recipe.get("avg_rating") and recipe.get("rating_count", 0) > 0:
        ld["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": recipe["avg_rating"],
            "ratingCount": recipe["rating_count"],
        }

    return ld


def _build_ingredient_json_ld(ingredient: dict, base_url: str) -> dict:
    """Build schema.org/Thing JSON-LD from ingredient data."""
    ld = {
        "@context": "https://schema.org",
        "@type": "Thing",
        "name": ingredient["name"],
        "url": f"{base_url}/ingredient/{ingredient['id']}",
    }
    if ingredient.get("description"):
        ld["description"] = ingredient["description"]
    return ld


@router.get("/recipe/by-name", response_class=HTMLResponse)
async def recipe_by_name(
    request: Request,
    name: str = Query(..., description="Recipe name to look up"),
    db: Database = Depends(get_database),
):
    """Look up a recipe by name and redirect to /recipe/{id}."""
    results = db.search_recipes_paginated(
        search_params={"name": name}, limit=1, offset=0
    )
    recipes = results.get("recipes", [])
    if recipes:
        recipe_id = recipes[0]["id"]
        return RedirectResponse(url=f"/recipe/{recipe_id}", status_code=302)

    return templates.TemplateResponse(
        "404.html",
        {"request": request, "message": f'Recipe "{name}" not found.'},
        status_code=404,
    )


@router.get("/recipe/{recipe_id:int}", response_class=HTMLResponse)
async def recipe_page(
    request: Request,
    recipe_id: int,
    db: Database = Depends(get_database),
):
    """Server-rendered recipe page for crawlers and agents."""
    recipe = db.get_recipe(recipe_id)
    if not recipe:
        return templates.TemplateResponse(
            "404.html",
            {"request": request, "message": "Recipe not found."},
            status_code=404,
        )

    base_url = settings.base_url
    ingredients = recipe.get("ingredients", [])
    tags = recipe.get("tags", [])
    public_tags = [t["name"] for t in tags if t.get("type") == "public"]

    # Get similar recipes if available
    similar = db.get_recipe_similarity(recipe_id)
    similar_recipes = similar.get("neighbors", []) if similar else []

    return templates.TemplateResponse(
        "recipe.html",
        {
            "request": request,
            "recipe": recipe,
            "base_url": base_url,
            "ingredient_summary": _ingredient_summary(ingredients),
            "public_tags": public_tags,
            "similar_recipes": similar_recipes,
            "json_ld": _build_recipe_json_ld(recipe, base_url),
        },
    )


@router.get("/ingredient/{ingredient_id:int}", response_class=HTMLResponse)
async def ingredient_page(
    request: Request,
    ingredient_id: int,
    db: Database = Depends(get_database),
):
    """Server-rendered ingredient page for crawlers and agents."""
    ingredient = db.get_ingredient(ingredient_id)
    if not ingredient:
        return templates.TemplateResponse(
            "404.html",
            {"request": request, "message": "Ingredient not found."},
            status_code=404,
        )

    base_url = settings.base_url

    # Build breadcrumb from path
    breadcrumb = []
    if ingredient.get("path"):
        # Path is like /1/8/ — each number is an ingredient ID
        path_ids = [
            int(p) for p in ingredient["path"].strip("/").split("/") if p
        ]
        for pid in path_ids:
            parent = db.get_ingredient(pid)
            if parent:
                breadcrumb.append({"id": parent["id"], "name": parent["name"]})

    # Get child ingredients
    all_ingredients = db.get_ingredients()
    children = [
        ing for ing in all_ingredients if ing.get("parent_id") == ingredient_id
    ]

    return templates.TemplateResponse(
        "ingredient.html",
        {
            "request": request,
            "ingredient": ingredient,
            "base_url": base_url,
            "breadcrumb": breadcrumb,
            "children": children,
            "json_ld": _build_ingredient_json_ld(ingredient, base_url),
        },
    )


@router.get("/sitemap.xml")
async def sitemap(db: Database = Depends(get_database)):
    """Dynamic sitemap generated from database content."""
    base_url = settings.base_url

    urlset = Element("urlset")
    urlset.set("xmlns", "http://www.sitemaps.org/schemas/sitemap/0.9")

    def add_url(loc: str, priority: str, changefreq: str = "weekly"):
        url_el = SubElement(urlset, "url")
        SubElement(url_el, "loc").text = loc
        SubElement(url_el, "priority").text = priority
        SubElement(url_el, "changefreq").text = changefreq

    # Static pages
    add_url(f"{base_url}/", "1.0")
    add_url(f"{base_url}/about.html", "0.7")
    add_url(f"{base_url}/search.html", "0.8")
    add_url(f"{base_url}/recipes.html", "0.7")
    add_url(f"{base_url}/analytics.html", "0.7")
    add_url(f"{base_url}/api/v1/docs", "0.9", "monthly")
    add_url(f"{base_url}/api/v1/openapi.json", "0.9", "monthly")

    # Recipe pages
    try:
        result = db.execute_query("SELECT id FROM recipes ORDER BY id")
        for row in result:
            add_url(f"{base_url}/recipe/{row['id']}", "0.8")
    except Exception as e:
        logger.error(f"Error fetching recipe IDs for sitemap: {e}")

    # Ingredient pages
    try:
        result = db.execute_query("SELECT id FROM ingredients ORDER BY id")
        for row in result:
            add_url(f"{base_url}/ingredient/{row['id']}", "0.7")
    except Exception as e:
        logger.error(f"Error fetching ingredient IDs for sitemap: {e}")

    xml_bytes = tostring(urlset, encoding="unicode", xml_declaration=False)
    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_bytes

    return Response(
        content=xml_str,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )
