import json
import logging
import time
import os
import boto3
from typing import Any, Dict

from db import Database

logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger()

# CORS headers for all responses
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,Accept,Access-Control-Allow-Headers,Access-Control-Allow-Origin,Access-Control-Allow-Methods",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
    "Access-Control-Allow-Credentials": "true",
}

# Global database connection - persists between Lambda invocations in the same container
_DB_INSTANCE = None
_DB_INIT_TIME = 0

# Get Cognito configuration from environment variables or CloudFormation outputs
REGION = os.environ.get("AWS_REGION", "us-east-1")
USER_POOL_ID = os.environ.get("USER_POOL_ID", "")
APP_CLIENT_ID = os.environ.get("APP_CLIENT_ID", "")

# Initialize Cognito client if pool ID is available
if not USER_POOL_ID or not APP_CLIENT_ID:
    try:
        # Try to get the values from CloudFormation outputs
        cfn = boto3.client("cloudformation")
        stack_name = os.environ.get(
            "AWS_SAM_STACK_NAME",
            os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "").rsplit("-", 1)[0],
        )

        if stack_name:
            response = cfn.describe_stacks(StackName=stack_name)
            if (
                "Stacks" in response
                and response["Stacks"]
                and "Outputs" in response["Stacks"][0]
            ):
                outputs = response["Stacks"][0]["Outputs"]

                for output in outputs:
                    if "OutputKey" in output and "OutputValue" in output:
                        if output["OutputKey"] == "UserPoolId":
                            USER_POOL_ID = output["OutputValue"]
                        elif output["OutputKey"] == "UserPoolClientId":
                            APP_CLIENT_ID = output["OutputValue"]
    except Exception as e:
        logger.warning(
            f"Failed to retrieve Cognito config from CloudFormation: {str(e)}"
        )


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

    path = event.get("path", "").rstrip("/")
    http_method = event.get("httpMethod", "")
    query_params = event.get("queryStringParameters", {}) or {}

    if http_method == "OPTIONS":
        logger.info("Handling OPTIONS preflight request")
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    db = get_database()

    # Determine if auth is required by the API Gateway authorizer having run
    # (claims will be present if authorizer succeeded)
    authorizer_claims = (
        event.get("requestContext", {}).get("authorizer", {}).get("claims")
    )
    user_id = None
    username = None
    email = None
    groups = []

    if authorizer_claims:
        logger.info(f"Authorizer claims found: {json.dumps(authorizer_claims)}")
        user_id = authorizer_claims.get("sub")
        # Cognito provides username in different claims depending on token type/config
        username = authorizer_claims.get("username") or authorizer_claims.get(
            "cognito:username"
        )
        email = authorizer_claims.get("email")
        groups = authorizer_claims.get("cognito:groups", [])
        logger.info(
            f"Authenticated via API Gateway Authorizer. User: {username} (ID: {user_id})"
        )
    else:
        # Check if the route *should* have been protected
        # Note: This logic might need adjustment if some POST/PUT/DELETE are public
        is_write_operation = http_method in ["POST", "PUT", "DELETE"]
        # The /auth endpoint also requires auth based on template.yaml
        requires_auth_route = is_write_operation or path == "/auth"

        if requires_auth_route:
            # This should ideally not happen if API Gateway authorizer is configured correctly
            logger.warning(
                "Authorizer claims missing on a route that should be protected!"
            )
            return {
                "statusCode": 401,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {"error": "Unauthorized - Authorizer claims missing"}
                ),
            }
        else:
            logger.info(
                "Anonymous access allowed for this request (no authorizer claims found)."
            )

    # Ensure user_id is present for required routes *after* checking claims
    is_write_operation = http_method in ["POST", "PUT", "DELETE"]
    requires_auth_route = is_write_operation or path == "/auth"
    if requires_auth_route and not user_id:
        # This case covers if claims were present but 'sub' was missing (unlikely)
        # Or if logic above determined auth was required but claims were missing
        logger.error(
            "Authentication required but no valid user ID found after checking authorizer context."
        )
        return {
            "statusCode": 401,
            "headers": CORS_HEADERS,
            "body": json.dumps(
                {"error": "Unauthorized - User ID missing after auth check"}
            ),
        }

    try:
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
                                ingredient["ancestors"] = (
                                    db.get_ingredient_ancestors_by_path(
                                        ingredient["path"]
                                    )
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
            # Use pathParameters provided by API Gateway, safely handling None
            path_params = event.get(
                "pathParameters"
            )  # Get pathParameters, could be None
            recipe_id = (
                path_params.get("recipeId") if path_params else None
            )  # Only call .get() if path_params is a dict
            # recipe_id = event.get("pathParameters", {}).get("recipeId") # Old potentially unsafe method

            if (
                http_method == "POST" and not recipe_id
            ):  # POST is only for the collection path
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
                if recipe_id:  # GET specific recipe using path param
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
                else:  # GET all recipes (collection path)
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

            elif http_method == "DELETE" and recipe_id:
                logger.info(f"Deleting recipe {recipe_id}...")
                try:
                    if db.delete_recipe(int(recipe_id)):
                        return {
                            "statusCode": 204,
                            "headers": CORS_HEADERS,
                            "body": "",
                        }
                    return {
                        "statusCode": 404,
                        "headers": CORS_HEADERS,
                        "body": json.dumps({"error": "Recipe not found"}),
                    }
                except Exception as e:
                    logger.error(f"Error deleting recipe: {str(e)}")
                    return {
                        "statusCode": 400,
                        "headers": CORS_HEADERS,
                        "body": json.dumps({"error": str(e)}),
                    }

            elif http_method == "PUT" and recipe_id:
                logger.info(f"Updating recipe {recipe_id}...")
                try:
                    body = json.loads(event.get("body", "{}"))
                    recipe = db.update_recipe(int(recipe_id), body)
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
                    logger.error(f"Error updating recipe: {str(e)}")
                    return {
                        "statusCode": 400,
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

        # Handle auth endpoint
        elif path.startswith("/auth"):
            logger.info("Handling auth request...")
            # If we reached here and requires_auth_route was true, user_id must be present
            if http_method == "GET":
                if user_id:
                    return {
                        "statusCode": 200,
                        "headers": CORS_HEADERS,
                        "body": json.dumps(
                            {
                                "authenticated": True,
                                "user": {
                                    "id": user_id,
                                    "username": username,
                                    "email": email,
                                    "groups": groups,
                                },
                            }
                        ),
                    }
                else:
                    # This state should theoretically not be reached due to checks above
                    logger.error("Reached /auth GET endpoint without a valid user_id.")
                    return {
                        "statusCode": 401,
                        "headers": CORS_HEADERS,
                        "body": json.dumps({"error": "Unauthorized - User ID missing"}),
                    }

        # Handle ratings endpoints
        elif path.startswith("/ratings"):
            # Extract recipe_id from path parameters if present
            path_params = event.get("pathParameters")
            recipe_id = path_params.get("recipeId") if path_params else None

            # Fallback to manual path parsing if API Gateway doesn't provide pathParameters
            if not recipe_id:
                path_parts = path.split("/")
                if len(path_parts) > 2:  # /ratings/{recipeId}
                    recipe_id = path_parts[2]

            if http_method == "GET" and recipe_id:
                logger.info(f"Getting ratings for recipe {recipe_id}...")
                try:
                    ratings = db.get_recipe_ratings(int(recipe_id))
                    return {
                        "statusCode": 200,
                        "headers": CORS_HEADERS,
                        "body": json.dumps(ratings),
                    }
                except Exception as e:
                    logger.error(f"Error getting ratings: {str(e)}")
                    return {
                        "statusCode": 500,
                        "headers": CORS_HEADERS,
                        "body": json.dumps({"error": str(e)}),
                    }

            elif http_method in ["POST", "PUT"] and recipe_id:
                logger.info(f"Setting rating for recipe {recipe_id}...")
                # These routes require authentication
                if not user_id:
                    return {
                        "statusCode": 401,
                        "headers": CORS_HEADERS,
                        "body": json.dumps(
                            {"error": "Authentication required to set ratings"}
                        ),
                    }

                try:
                    body = json.loads(event.get("body", "{}"))
                    body["cognito_user_id"] = user_id
                    body["cognito_username"] = username
                    body["recipe_id"] = int(recipe_id)

                    result = db.set_rating(body)
                    status_code = 200 if http_method == "PUT" else 201
                    return {
                        "statusCode": status_code,
                        "headers": CORS_HEADERS,
                        "body": json.dumps(result),
                    }
                except Exception as e:
                    logger.error(f"Error setting rating: {str(e)}")
                    return {
                        "statusCode": 400,
                        "headers": CORS_HEADERS,
                        "body": json.dumps({"error": str(e)}),
                    }

            elif http_method == "DELETE" and recipe_id:
                logger.info(f"Deleting rating for recipe {recipe_id}...")
                # This route requires authentication
                if not user_id:
                    return {
                        "statusCode": 401,
                        "headers": CORS_HEADERS,
                        "body": json.dumps(
                            {"error": "Authentication required to delete ratings"}
                        ),
                    }

                try:
                    db.delete_rating(int(recipe_id), user_id)
                    return {
                        "statusCode": 204,
                        "headers": CORS_HEADERS,
                        "body": "",
                    }
                except Exception as e:
                    logger.error(f"Error deleting rating: {str(e)}")
                    return {
                        "statusCode": 400,
                        "headers": CORS_HEADERS,
                        "body": json.dumps({"error": str(e)}),
                    }

            elif http_method == "OPTIONS":
                return {
                    "statusCode": 200,
                    "headers": CORS_HEADERS,
                    "body": "",
                }

        # Handle not found
        return {
            "statusCode": 404,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": f"Endpoint not found: {path} {http_method}"}),
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
