"""Functions for handling recipe endpoints"""

import json
import logging
from typing import Any, Dict, Optional

from db import Database
from utils import _return_data, _return_error, _return_empty


def handle_create_recipe(
    logger: logging.Logger, db: Database, event: Dict[str, Any]
) -> Dict[str, Any]:
    logger.info("Creating new recipe...")
    try:
        body = json.loads(event.get("body", "{}"))
        recipe = db.create_recipe(body)
        return _return_data(201, recipe)
    except Exception as e:
        logger.error(f"Error creating recipe: {str(e)}")
        return _return_error(400, str(e))


def handle_get_single_recipe(
    logger: logging.Logger, db: Database, recipe_id: str, user_id: Optional[str] = None
) -> Dict[str, Any]:
    logger.info(f"Getting recipe {recipe_id}...")
    try:
        # Pass user_id (which can be None if anonymous) to get_recipe
        logger.info(
            f"Calling db.get_recipe for recipe_id {recipe_id} with user_id: {user_id}"
        )
        recipe = db.get_recipe(int(recipe_id), user_id)
        if recipe:
            logger.info(f"Recipe {recipe_id} data with tags: {recipe}")
            return _return_data(200, recipe)
        logger.info(f"Recipe {recipe_id} not found by db.get_recipe.")
        return _return_error(404, "Recipe not found")
    except Exception as e:
        logger.error(f"Error getting recipe: {str(e)}")
        return _return_error(500, str(e))


def handle_get_all_recipes(logger: logging.Logger, db: Database) -> Dict[str, Any]:
    logger.info("Getting all recipes...")
    try:
        recipes = db.get_recipes()
        return _return_data(200, recipes)
    except Exception as e:
        logger.error(f"Error getting recipes: {str(e)}")
        return _return_error(500, str(e))


def handle_delete_recipe(
    logger: logging.Logger, db: Database, recipe_id: str
) -> Dict[str, Any]:
    logger.info(f"Deleting recipe {recipe_id}...")
    try:
        if db.delete_recipe(int(recipe_id)):
            return _return_empty(204)
        return _return_error(404, "Recipe not found")
    except Exception as e:
        logger.error(f"Error deleting recipe: {str(e)}")
        return _return_error(400, str(e))


def handle_update_recipe(
    logger: logging.Logger, db: Database, recipe_id: str, event: Dict[str, Any]
) -> Dict[str, Any]:
    logger.info(f"Updating recipe {recipe_id}...")
    try:
        body = json.loads(event.get("body", "{}"))
        recipe = db.update_recipe(int(recipe_id), body)
        if recipe:
            return _return_data(200, recipe)
        return _return_error(404, "Recipe not found")
    except Exception as e:
        logger.error(f"Error updating recipe: {str(e)}")
        return _return_error(400, str(e))


def handle_search_recipes(
    logger: logging.Logger, db: Database, query_params: Dict[str, Any]
) -> Dict[str, Any]:
    logger.info("Searching recipes...")
    try:
        search_params = {}
        # Extract query parameters
        if "name" in query_params:
            search_params["name"] = query_params.get("name")
        if "min_rating" in query_params:
            search_params["min_rating"] = float(query_params.get("min_rating"))
        # Handle tags (can be multiple)
        if "tags" in query_params:
            tags = query_params.get("tags")
            if isinstance(tags, list):
                search_params["tags"] = tags
            else:
                search_params["tags"] = [tags]
        # Handle ingredient queries through query parameters
        # Format: ingredients=ID:OPERATOR,ID:OPERATOR,...
        # Example: ingredients=12:MUST,34:MUST_NOT
        if "ingredients" in query_params:
            ingredients_param = query_params.get("ingredients")
            if ingredients_param:
                ingredients = []
                ingredient_parts = ingredients_param.split(",")
                for part in ingredient_parts:
                    if ":" in part:
                        id_op = part.split(":")
                        if len(id_op) == 2 and id_op[0].isdigit():
                            # Only accept MUST or MUST_NOT operators
                            operator = id_op[1]
                            if operator in ["MUST", "MUST_NOT"]:
                                ingredients.append(
                                    {
                                        "id": int(id_op[0]),
                                        "operator": operator,
                                    }
                                )
                if ingredients:
                    search_params["ingredients"] = ingredients

        # Perform the search
        recipes = db.search_recipes(search_params)
        return _return_data(200, recipes)
    except Exception as e:
        logger.error(f"Error searching recipes: {str(e)}")
        return _return_error(500, str(e))
