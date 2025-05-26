"""Functions for handling rating endpoints"""

import json
import logging
from typing import Any, Dict, Optional

from db import Database
from utils import _return_data, _return_error, _return_empty


def handle_get_ratings(
    logger: logging.Logger, db: Database, recipe_id: str
) -> Dict[str, Any]:
    logger.info(f"Getting ratings for recipe {recipe_id}...")
    try:
        ratings = db.get_recipe_ratings(int(recipe_id))
        return _return_data(200, ratings)
    except Exception as e:
        logger.error(f"Error getting ratings: {str(e)}")
        return _return_error(500, str(e))


def handle_set_rating(
    logger: logging.Logger,
    db: Database,
    recipe_id: str,
    event: Dict[str, Any],
    http_method: str,
    user_id: Optional[str],
    username: str,
) -> Dict[str, Any]:
    logger.info(f"Setting rating for recipe {recipe_id}...")
    # These routes require authentication
    if not user_id:
        return _return_error(401, "Authentication required to set ratings")
    try:
        body = json.loads(event.get("body", "{}"))
        body["cognito_user_id"] = user_id
        body["cognito_username"] = username
        body["recipe_id"] = int(recipe_id)
        result = db.set_rating(body)
        status_code = 200 if http_method == "PUT" else 201
        return _return_data(status_code, result)
    except Exception as e:
        logger.error(f"Error setting rating: {str(e)}")
        return _return_error(400, str(e))


def handle_delete_rating(
    logger: logging.Logger, db: Database, recipe_id: str, user_id: Optional[str]
) -> Dict[str, Any]:
    logger.info(f"Deleting rating for recipe {recipe_id}...")
    # This route requires authentication
    if not user_id:
        return _return_error(401, "Authentication required to delete ratings")
    try:
        db.delete_rating(int(recipe_id), user_id)
        return _return_empty(204)
    except Exception as e:
        logger.error(f"Error deleting rating: {str(e)}")
        return _return_error(400, str(e))
