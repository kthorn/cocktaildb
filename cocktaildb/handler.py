import json
import logging
import time
from typing import Any, Dict

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from db import Database  # Relative import

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Retry decorator for database operations
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(Exception),
    before_sleep=lambda retry_state: logger.warning(
        f"Retrying database operation after error: {retry_state.outcome.exception()}, "
        f"attempt {retry_state.attempt_number}"
    ),
)
def get_database():
    """Get database with retry logic"""
    return Database()


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda function to handle cocktail and ingredient operations
    """
    try:
        start_time = time.time()
        logger.info(f"Lambda handler started with event: {json.dumps(event)}")

        # Parse the HTTP method and path from the event
        http_method = event.get("httpMethod", "GET")
        path = event.get("path", "")
        logger.info(f"HTTP Method: {http_method}, Path: {path}")

        # Initialize database with retry
        logger.info("Initializing database connection...")
        db_init_start = time.time()

        try:
            db = get_database()
            db_init_duration = time.time() - db_init_start
            logger.info(f"Database connection initialized in {db_init_duration:.2f}s")
        except Exception as e:
            logger.error(f"Failed to connect to database after retries: {str(e)}")
            return {
                "statusCode": 500,
                "body": json.dumps({"error": "Database connection failed"}),
            }

        # Handle ingredients endpoints
        if path.startswith("/ingredients"):
            if http_method == "GET":
                # List all ingredients
                logger.info("Querying for all ingredients...")
                query_start = time.time()
                try:
                    ingredients = db.session.query(db.Ingredient).all()
                    query_duration = time.time() - query_start
                    logger.info(
                        f"Query completed in {query_duration:.2f}s. Found {len(ingredients)} ingredients."
                    )

                    response = {
                        "statusCode": 200,
                        "body": json.dumps(
                            [
                                {
                                    "id": i.id,
                                    "name": i.name,
                                    "category": i.category,
                                    "description": i.description,
                                }
                                for i in ingredients
                            ]
                        ),
                    }
                    logger.info(
                        f"Total execution time: {time.time() - start_time:.2f}s"
                    )
                    return response
                except Exception as e:
                    logger.error(f"Error querying ingredients: {str(e)}")
                    return {
                        "statusCode": 500,
                        "body": json.dumps(
                            {"error": f"Database query failed: {str(e)}"}
                        ),
                    }
            elif http_method == "POST":
                # Create new ingredient
                logger.info("Creating new ingredient...")
                body = json.loads(event.get("body", "{}"))
                ingredient = db.create_ingredient(body)
                logger.info(f"Ingredient created with ID: {ingredient.id}")
                return {
                    "statusCode": 201,
                    "body": json.dumps(
                        {
                            "id": ingredient.id,
                            "name": ingredient.name,
                            "category": ingredient.category,
                            "description": ingredient.description,
                        }
                    ),
                }
            elif http_method == "PUT":
                # Update ingredient
                ingredient_id = int(event.get("pathParameters", {}).get("id", 0))
                logger.info(f"Updating ingredient with ID: {ingredient_id}")
                body = json.loads(event.get("body", "{}"))
                ingredient = db.update_ingredient(ingredient_id, body)

                if ingredient:
                    logger.info(f"Ingredient {ingredient_id} updated successfully")
                    return {
                        "statusCode": 200,
                        "body": json.dumps(
                            {
                                "id": ingredient.id,
                                "name": ingredient.name,
                                "category": ingredient.category,
                                "description": ingredient.description,
                            }
                        ),
                    }
                else:
                    logger.warning(f"Ingredient {ingredient_id} not found")
                    return {
                        "statusCode": 404,
                        "body": json.dumps({"error": "Ingredient not found"}),
                    }
            elif http_method == "DELETE":
                # Delete ingredient
                ingredient_id = int(event.get("pathParameters", {}).get("id", 0))
                logger.info(f"Deleting ingredient with ID: {ingredient_id}")
                success = db.delete_ingredient(ingredient_id)

                if success:
                    logger.info(f"Ingredient {ingredient_id} deleted successfully")
                    return {"statusCode": 204, "body": ""}
                else:
                    logger.warning(f"Ingredient {ingredient_id} not found")
                    return {
                        "statusCode": 404,
                        "body": json.dumps({"error": "Ingredient not found"}),
                    }

        # Handle recipe endpoints
        elif path.startswith("/recipes"):
            if http_method == "GET":
                # List all recipes
                logger.info("Querying for all recipes...")
                query_start = time.time()
                try:
                    recipes = db.session.query(db.Recipe).all()
                    query_duration = time.time() - query_start
                    logger.info(
                        f"Query completed in {query_duration:.2f}s. Found {len(recipes)} recipes."
                    )

                    response = {
                        "statusCode": 200,
                        "body": json.dumps(
                            [
                                {
                                    "id": r.id,
                                    "name": r.name,
                                    "instructions": r.instructions,
                                    "description": r.description,
                                    "image_url": r.image_url,
                                    "ingredients": [
                                        {
                                            "id": ri.id,
                                            "name": ri.ingredient.name,
                                            "amount": ri.amount,
                                            "unit": ri.unit.name if ri.unit else None,
                                        }
                                        for ri in r.ingredients
                                    ],
                                }
                                for r in recipes
                            ]
                        ),
                    }
                    logger.info(
                        f"Total execution time: {time.time() - start_time:.2f}s"
                    )
                    return response
                except Exception as e:
                    logger.error(f"Error querying recipes: {str(e)}")
                    return {
                        "statusCode": 500,
                        "body": json.dumps(
                            {"error": f"Database query failed: {str(e)}"}
                        ),
                    }
            elif http_method == "POST":
                # Create new recipe
                logger.info("Creating new recipe...")
                body = json.loads(event.get("body", "{}"))
                recipe = db.create_recipe(body)
                logger.info(f"Recipe created with ID: {recipe.id}")
                return {
                    "statusCode": 201,
                    "body": json.dumps(
                        {
                            "id": recipe.id,
                            "name": recipe.name,
                            "instructions": recipe.instructions,
                            "description": recipe.description,
                            "image_url": recipe.image_url,
                        }
                    ),
                }
            elif http_method == "PUT":
                # Update recipe
                recipe_id = int(event.get("pathParameters", {}).get("id", 0))
                logger.info(f"Updating recipe with ID: {recipe_id}")
                body = json.loads(event.get("body", "{}"))
                recipe = db.update_recipe(recipe_id, body)

                if recipe:
                    logger.info(f"Recipe {recipe_id} updated successfully")
                    return {
                        "statusCode": 200,
                        "body": json.dumps(
                            {
                                "id": recipe.id,
                                "name": recipe.name,
                                "instructions": recipe.instructions,
                                "description": recipe.description,
                                "image_url": recipe.image_url,
                            }
                        ),
                    }
                else:
                    logger.warning(f"Recipe {recipe_id} not found")
                    return {
                        "statusCode": 404,
                        "body": json.dumps({"error": "Recipe not found"}),
                    }
            elif http_method == "DELETE":
                # Delete recipe
                recipe_id = int(event.get("pathParameters", {}).get("id", 0))
                logger.info(f"Deleting recipe with ID: {recipe_id}")
                success = db.delete_recipe(recipe_id)

                if success:
                    logger.info(f"Recipe {recipe_id} deleted successfully")
                    return {"statusCode": 204, "body": ""}
                else:
                    logger.warning(f"Recipe {recipe_id} not found")
                    return {
                        "statusCode": 404,
                        "body": json.dumps({"error": "Recipe not found"}),
                    }

        # Handle units endpoints
        elif path.startswith("/units"):
            if http_method == "GET":
                # List all units
                logger.info("Querying for all units...")
                try:
                    units = db.get_units()
                    response = {
                        "statusCode": 200,
                        "body": json.dumps(
                            [
                                {
                                    "id": u.id,
                                    "name": u.name,
                                    "abbreviation": u.abbreviation,
                                }
                                for u in units
                            ]
                        ),
                    }
                    return response
                except Exception as e:
                    logger.error(f"Error querying units: {str(e)}")
                    return {
                        "statusCode": 500,
                        "body": json.dumps(
                            {"error": f"Database query failed: {str(e)}"}
                        ),
                    }
            elif http_method == "POST":
                # Create new unit
                logger.info("Creating new unit...")
                body = json.loads(event.get("body", "{}"))
                try:
                    new_unit = db.Unit(
                        name=body.get("name"), abbreviation=body.get("abbreviation")
                    )
                    db.session.add(new_unit)
                    db.session.commit()
                    return {
                        "statusCode": 201,
                        "body": json.dumps(
                            {
                                "id": new_unit.id,
                                "name": new_unit.name,
                                "abbreviation": new_unit.abbreviation,
                            }
                        ),
                    }
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"Error creating unit: {str(e)}")
                    return {
                        "statusCode": 500,
                        "body": json.dumps(
                            {"error": f"Failed to create unit: {str(e)}"}
                        ),
                    }

        # Handle other endpoints (cocktails, etc.)
        elif path.startswith("/cocktails"):
            # TODO: Implement cocktail endpoints
            logger.info("Cocktail endpoints not implemented yet")
            return {
                "statusCode": 501,
                "body": json.dumps({"error": "Not implemented yet"}),
            }

        else:
            logger.warning(f"Unrecognized path: {path}")
            return {"statusCode": 404, "body": json.dumps({"error": "Not found"})}

    except Exception as e:
        logger.error(f"Error in lambda_handler: {str(e)}", exc_info=True)
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})} 