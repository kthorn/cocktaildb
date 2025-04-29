import json
import logging
import time
from typing import Any, Dict

from db import Database

logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger()

# CORS headers for all responses
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
    "Access-Control-Allow-Credentials": "true",
}

# Global database connection - persists between Lambda invocations in the same container
_DB_INSTANCE = None
_DB_INIT_TIME = 0


def get_database():
    """Get database with connection pooling and metadata caching"""
    global _DB_INSTANCE, _DB_INIT_TIME
    current_time = time.time()

    # If DB instance exists and is less than 5 minutes old, reuse it
    if _DB_INSTANCE is not None and current_time - _DB_INIT_TIME < 300:
        logger.info(
            f"Reusing existing database connection (age: {current_time - _DB_INIT_TIME:.2f}s)"
        )
        return _DB_INSTANCE

    # Initialize a new database connection
    logger.info("Creating new database connection")
    _DB_INSTANCE = Database()
    _DB_INIT_TIME = current_time

    return _DB_INSTANCE


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda handler for the CocktailDB API"""
    start_time = time.time()
    logger.info(f"Received event: {json.dumps(event)}")

    # Get path and HTTP method
    path = event.get("path", "").rstrip("/")
    http_method = event.get("httpMethod", "")
    query_params = event.get("queryStringParameters", {}) or {}

    # Get database connection
    db = get_database()

    try:
        # Handle OPTIONS method for CORS preflight requests
        if http_method == "OPTIONS":
            logger.info("Handling OPTIONS preflight request")
            return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

        # Handle ingredient endpoints
        if path.startswith("/ingredients"):
            ingredient_id = path.split("/")[-1] if len(path.split("/")) > 2 else None

            if http_method == "POST":
                logger.info("Creating new ingredient...")
                try:
                    body = json.loads(event.get("body", "{}"))
                    ingredient = db.create_ingredient(body)
                    return {
                        "statusCode": 201,
                        "headers": CORS_HEADERS,
                        "body": json.dumps(ingredient),
                    }
                except Exception as e:
                    logger.error(f"Error creating ingredient: {str(e)}")
                    return {
                        "statusCode": 400,
                        "headers": CORS_HEADERS,
                        "body": json.dumps({"error": str(e)}),
                    }

            elif http_method == "PUT" and ingredient_id:
                logger.info(f"Updating ingredient {ingredient_id}...")
                try:
                    body = json.loads(event.get("body", "{}"))
                    ingredient = db.update_ingredient(int(ingredient_id), body)
                    if ingredient:
                        return {
                            "statusCode": 200,
                            "headers": CORS_HEADERS,
                            "body": json.dumps(ingredient),
                        }
                    return {
                        "statusCode": 404,
                        "headers": CORS_HEADERS,
                        "body": json.dumps({"error": "Ingredient not found"}),
                    }
                except Exception as e:
                    logger.error(f"Error updating ingredient: {str(e)}")
                    return {
                        "statusCode": 400,
                        "headers": CORS_HEADERS,
                        "body": json.dumps({"error": str(e)}),
                    }

            elif http_method == "DELETE" and ingredient_id:
                logger.info(f"Deleting ingredient {ingredient_id}...")
                try:
                    if db.delete_ingredient(int(ingredient_id)):
                        return {
                            "statusCode": 204,
                            "headers": CORS_HEADERS,
                            "body": "",
                        }
                    return {
                        "statusCode": 404,
                        "headers": CORS_HEADERS,
                        "body": json.dumps({"error": "Ingredient not found"}),
                    }
                except Exception as e:
                    logger.error(f"Error deleting ingredient: {str(e)}")
                    return {
                        "statusCode": 400,
                        "headers": CORS_HEADERS,
                        "body": json.dumps({"error": str(e)}),
                    }

            elif http_method == "GET":
                if ingredient_id:
                    logger.info(f"Getting ingredient {ingredient_id}...")
                    try:
                        ingredient = db.get_ingredient(int(ingredient_id))
                        if ingredient:
                            # Check if we need to include hierarchy information
                            include_descendants = (
                                query_params.get("descendants") == "true"
                            )
                            include_ancestors = query_params.get("ancestors") == "true"

                            if include_descendants:
                                ingredient["descendants"] = (
                                    db.get_ingredient_descendants(int(ingredient_id))
                                )
                            if include_ancestors:
                                ingredient["ancestors"] = db.get_ingredient_ancestors(
                                    int(ingredient_id)
                                )

                            return {
                                "statusCode": 200,
                                "headers": CORS_HEADERS,
                                "body": json.dumps(ingredient),
                            }
                        return {
                            "statusCode": 404,
                            "headers": CORS_HEADERS,
                            "body": json.dumps({"error": "Ingredient not found"}),
                        }
                    except Exception as e:
                        logger.error(f"Error getting ingredient: {str(e)}")
                        return {
                            "statusCode": 500,
                            "headers": CORS_HEADERS,
                            "body": json.dumps({"error": str(e)}),
                        }
                else:
                    logger.info("Getting all ingredients...")
                    try:
                        ingredients = db.get_ingredients()
                        return {
                            "statusCode": 200,
                            "headers": CORS_HEADERS,
                            "body": json.dumps(ingredients),
                        }
                    except Exception as e:
                        logger.error(f"Error getting ingredients: {str(e)}")
                        return {
                            "statusCode": 500,
                            "headers": CORS_HEADERS,
                            "body": json.dumps({"error": str(e)}),
                        }

        # Handle recipe endpoints
        elif path.startswith("/recipes"):
            recipe_id = path.split("/")[-1] if len(path.split("/")) > 2 else None

            if http_method == "POST":
                logger.info("Creating new recipe...")
                try:
                    body = json.loads(event.get("body", "{}"))
                    recipe = db.create_recipe(body)
                    return {
                        "statusCode": 201,
                        "headers": CORS_HEADERS,
                        "body": json.dumps(recipe),
                    }
                except Exception as e:
                    logger.error(f"Error creating recipe: {str(e)}")
                    return {
                        "statusCode": 400,
                        "headers": CORS_HEADERS,
                        "body": json.dumps({"error": str(e)}),
                    }

            elif http_method == "GET":
                if recipe_id:
                    logger.info(f"Getting recipe {recipe_id}...")
                    try:
                        recipe = db.get_recipe(int(recipe_id))
                        if recipe:
                            return {
                                "statusCode": 200,
                                "headers": CORS_HEADERS,
                                "body": json.dumps(recipe),
                            }
                        return {
                            "statusCode": 404,
                            "headers": CORS_HEADERS,
                            "body": json.dumps({"error": "Recipe not found"}),
                        }
                    except Exception as e:
                        logger.error(f"Error getting recipe: {str(e)}")
                        return {
                            "statusCode": 500,
                            "headers": CORS_HEADERS,
                            "body": json.dumps({"error": str(e)}),
                        }
                else:
                    logger.info("Getting all recipes...")
                    try:
                        recipes = db.get_recipes()
                        return {
                            "statusCode": 200,
                            "headers": CORS_HEADERS,
                            "body": json.dumps(recipes),
                        }
                    except Exception as e:
                        logger.error(f"Error getting recipes: {str(e)}")
                        return {
                            "statusCode": 500,
                            "headers": CORS_HEADERS,
                            "body": json.dumps({"error": str(e)}),
                        }

        # Handle units endpoint
        elif path == "/units":
            if http_method == "GET":
                logger.info("Getting all units...")
                try:
                    units = db.get_units()
                    return {
                        "statusCode": 200,
                        "headers": CORS_HEADERS,
                        "body": json.dumps(units),
                    }
                except Exception as e:
                    logger.error(f"Error getting units: {str(e)}")
                    return {
                        "statusCode": 500,
                        "headers": CORS_HEADERS,
                        "body": json.dumps({"error": str(e)}),
                    }

        # Handle unknown endpoints
        return {
            "statusCode": 404,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Endpoint not found"}),
        }

    except Exception as e:
        logger.error(f"Unhandled error: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Internal server error"}),
        }
    finally:
        logger.info(f"Total execution time: {time.time() - start_time:.2f}s")
