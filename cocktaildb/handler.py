import json
import logging
import os
import time
from typing import Any, Dict

import boto3
from db import Database
from handler_recipes import (
    handle_create_recipe,
    handle_delete_recipe,
    handle_get_all_recipes,
    handle_get_single_recipe,
    handle_search_recipes,
    handle_update_recipe,
)
from utils import _return_data, _return_empty, _return_error, _return_message

logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger()


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
        return _return_empty(200)

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
            return _return_error(401, "Unauthorized - Authorizer claims missing")
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
        return _return_error(401, "Unauthorized - User ID missing after auth check")

    try:
        # Handle ingredient endpoints
        if path.startswith("/ingredients"):
            ingredient_id = None  # Initialize
            # Prioritize pathParameters from API Gateway
            path_parameters_from_event = event.get("pathParameters")
            if isinstance(path_parameters_from_event, dict):
                ingredient_id = path_parameters_from_event.get("ingredientId")
            # Fallback: if not found via pathParameters (or pathParameters was not a dict/None),
            # and the path structure suggests an item ID.
            if not ingredient_id:
                path_parts = path.split("/")
                if (
                    len(path_parts) == 3
                    and path_parts[1] == "ingredients"
                    and path_parts[2]
                ):
                    ingredient_id = path_parts[2]

            if http_method == "POST":
                logger.info("Creating new ingredient...")
                try:
                    body = json.loads(event.get("body", "{}"))
                    ingredient = db.create_ingredient(body)
                    return _return_data(201, ingredient)
                except Exception as e:
                    logger.error(f"Error creating ingredient: {str(e)}")
                    return _return_error(400, str(e))

            elif http_method == "PUT" and ingredient_id:
                logger.info(f"Updating ingredient {ingredient_id}...")
                try:
                    body = json.loads(event.get("body", "{}"))
                    ingredient = db.update_ingredient(int(ingredient_id), body)
                    if ingredient:
                        return _return_data(200, ingredient)
                    return _return_error(404, "Ingredient not found")
                except Exception as e:
                    logger.error(f"Error updating ingredient: {str(e)}")
                    return _return_error(400, str(e))

            elif http_method == "DELETE" and ingredient_id:
                logger.info(f"Deleting ingredient {ingredient_id}...")
                try:
                    if db.delete_ingredient(int(ingredient_id)):
                        return _return_empty(204)
                    return _return_error(404, "Ingredient not found")
                except Exception as e:
                    logger.error(f"Error deleting ingredient: {str(e)}")
                    return _return_error(400, str(e))

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

                            return _return_data(200, ingredient)
                        return _return_error(404, "Ingredient not found")
                    except Exception as e:
                        logger.error(f"Error getting ingredient: {str(e)}")
                        return _return_error(500, str(e))
                else:
                    logger.info("Getting all ingredients...")
                    try:
                        ingredients = db.get_ingredients()
                        return _return_data(200, ingredients)
                    except Exception as e:
                        logger.error(f"Error getting ingredients: {str(e)}")
                        return _return_error(500, str(e))

        # /recipes/{recipeId}/public_tags/{tagId}
        # /recipes/{recipeId}/private_tags
        # /recipes/{recipeId}/private_tags/{tagId}
        elif path.startswith("/recipes/") and (
            "public_tags" in path or "private_tags" in path
        ):  # More specific than general /recipes/
            path_parts = path.strip("/").split(
                "/"
            )  # recipes, recipe_id_val, tags_type, tag_id_val?
            if (
                len(path_parts) >= 3
                and path_parts[0] == "recipes"
                and path_parts[2].endswith("_tags")
            ):
                recipe_id_str = path_parts[1]
                tag_type = path_parts[2]  # "public_tags" or "private_tags"
                tag_id_str = path_parts[3] if len(path_parts) > 3 else None

                if not recipe_id_str.isdigit():
                    return _return_error(400, "Invalid recipe ID")
                recipe_id_int = int(recipe_id_str)

                # All tag association operations require authentication
                if not user_id:
                    return _return_error(401, "Authentication required")

                if (
                    http_method == "POST" and not tag_id_str
                ):  # Add tag to recipe: POST /recipes/{id}/<type>_tags
                    logger.info(f"Adding {tag_type} to recipe {recipe_id_int}...")
                    try:
                        body = json.loads(event.get("body", "{}"))
                        tag_name_to_add = body.get("name")
                        tag_id_to_add = body.get("id")

                        if not tag_name_to_add and not tag_id_to_add:
                            raise ValueError(
                                "Either tag 'name' or 'id' must be provided."
                            )

                        final_tag_id = None
                        if tag_id_to_add:
                            final_tag_id = int(tag_id_to_add)
                        elif tag_name_to_add:
                            if tag_type == "public_tags":
                                tag_obj = db.get_public_tag_by_name(tag_name_to_add)
                                if not tag_obj:
                                    tag_obj = db.create_public_tag(tag_name_to_add)
                                final_tag_id = tag_obj["id"]
                            elif tag_type == "private_tags":
                                tag_obj = db.get_private_tag_by_name_and_user(
                                    tag_name_to_add, user_id
                                )
                                if not tag_obj:
                                    if not username:
                                        raise ValueError(
                                            "Username not found for private tag creation"
                                        )
                                    tag_obj = db.create_private_tag(
                                        tag_name_to_add, user_id, username
                                    )
                                final_tag_id = tag_obj["id"]
                            else:
                                raise ValueError("Invalid tag type specified")

                        if final_tag_id is None:
                            raise ValueError("Could not determine tag ID to add.")

                        success = False
                        if tag_type == "public_tags":
                            success = db.add_public_tag_to_recipe(
                                recipe_id_int, final_tag_id
                            )
                        elif tag_type == "private_tags":
                            # Ensure the private tag belongs to the user before associating
                            private_tag_check = (
                                db.get_private_tag_by_name_and_user(
                                    tag_name_to_add, user_id
                                )
                                if tag_name_to_add
                                else db.execute_query(
                                    "SELECT id FROM private_tags WHERE id = :id AND cognito_user_id = :user_id",
                                    {"id": final_tag_id, "user_id": user_id},
                                )
                            )
                            if not private_tag_check:
                                return _return_error(
                                    403,
                                    "Private tag does not exist or does not belong to user",
                                )
                            success = db.add_private_tag_to_recipe(
                                recipe_id_int, final_tag_id
                            )

                        if success:
                            return _return_message(
                                201,
                                f"{tag_type.replace('_tags', '')} tag added to recipe",
                            )
                        else:
                            # Could be due to ON CONFLICT DO NOTHING if already exists
                            return _return_message(
                                200,
                                f"{tag_type.replace('_tags', '')} tag already associated or failed to add",
                            )

                    except ValueError as ve:
                        return _return_error(400, str(ve))
                    except Exception as e:
                        logger.error(
                            f"Error adding tag to recipe: {str(e)}", exc_info=True
                        )
                        return _return_error(500, "Failed to add tag to recipe")

                elif (
                    http_method == "DELETE" and tag_id_str and tag_id_str.isdigit()
                ):  # Remove tag from recipe: DELETE /recipes/{id}/<type>_tags/{tag_id}
                    tag_id_int = int(tag_id_str)
                    logger.info(
                        f"Removing {tag_type} (ID: {tag_id_int}) from recipe {recipe_id_int}..."
                    )
                    try:
                        success = False
                        if tag_type == "public_tags":
                            success = db.remove_public_tag_from_recipe(
                                recipe_id_int, tag_id_int
                            )
                        elif tag_type == "private_tags":
                            success = db.remove_private_tag_from_recipe(
                                recipe_id_int, tag_id_int, user_id
                            )

                        if success:
                            return _return_empty(204)
                        else:
                            return _return_error(
                                404,
                                "Tag association not found or not authorized to remove",
                            )
                    except Exception as e:
                        logger.error(
                            f"Error removing tag from recipe: {str(e)}", exc_info=True
                        )
                        return _return_error(500, "Failed to remove tag from recipe")
                else:
                    return _return_error(
                        405, "Method not allowed or invalid path structure for tags"
                    )
            # Fall through if not matched to more specific recipe routes like /recipes/{id} itself

        # Handle recipe endpoints
        elif path.startswith("/recipes"):
            # Use pathParameters provided by API Gateway, which can be None
            path_params = event.get("pathParameters")
            recipe_id = path_params.get("recipeId") if path_params else None
            # POST without recipe_id is for creating a new recipe
            if http_method == "POST" and not recipe_id:
                return handle_create_recipe(logger, db, event, context)
            elif http_method == "GET":
                if recipe_id:
                    return handle_get_single_recipe(logger, db, recipe_id, user_id)
                else:
                    # Check if this is a search request
                    if query_params and query_params.get("search") == "true":
                        return handle_search_recipes(logger, db, query_params)
                    else:
                        return handle_get_all_recipes(logger, db)
            elif http_method == "DELETE" and recipe_id:
                return handle_delete_recipe(logger, db, recipe_id)
            elif http_method == "PUT" and recipe_id:
                return handle_update_recipe(logger, db, recipe_id, event)
            elif http_method == "OPTIONS":
                return _return_empty(200)
            else:
                return _return_error(
                    405, "Method not allowed. Use GET for recipe search."
                )

        # Handle units endpoint
        elif path == "/units":
            if http_method == "GET":
                logger.info("Getting all units...")
                try:
                    units = db.get_units()
                    return _return_data(200, units)
                except Exception as e:
                    logger.error(f"Error getting units: {str(e)}")
                    return _return_error(500, str(e))

        # Handle auth endpoint
        elif path.startswith("/auth"):
            logger.info("Handling auth request...")
            # If we reached here and requires_auth_route was true, user_id must be present
            if http_method == "GET":
                if user_id:
                    return _return_data(
                        200,
                        {
                            "authenticated": True,
                            "user": {
                                "id": user_id,
                                "username": username,
                                "email": email,
                                "groups": groups,
                            },
                        },
                    )
                else:
                    # This state should theoretically not be reached due to checks above
                    logger.error("Reached /auth GET endpoint without a valid user_id.")
                    return _return_error(401, "Unauthorized - User ID missing")

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
                    return _return_data(200, ratings)
                except Exception as e:
                    logger.error(f"Error getting ratings: {str(e)}")
                    return _return_error(500, str(e))

            elif http_method in ["POST", "PUT"] and recipe_id:
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

            elif http_method == "DELETE" and recipe_id:
                logger.info(f"Deleting rating for recipe {recipe_id}...")
                # This route requires authentication
                if not user_id:
                    return _return_error(
                        401, "Authentication required to delete ratings"
                    )

                try:
                    db.delete_rating(int(recipe_id), user_id)
                    return _return_empty(204)
                except Exception as e:
                    logger.error(f"Error deleting rating: {str(e)}")
                    return _return_error(400, str(e))

            elif http_method == "OPTIONS":
                return _return_empty(200)

        # Handle tags endpoint (public)
        elif path == "/tags/public":
            if http_method == "GET":
                logger.info("Getting all public tags...")
                try:
                    tags = db.get_public_tags()
                    return _return_data(200, tags)
                except Exception as e:
                    logger.error(f"Error getting public tags: {str(e)}")
                    return _return_error(500, str(e))
            elif http_method == "POST":
                if not user_id:  # Assuming creating public tags requires auth
                    return _return_error(401, "Authentication required")
                logger.info("Creating new public tag...")
                try:
                    body = json.loads(event.get("body", "{}"))
                    tag_name = body.get("name")
                    if not tag_name:
                        raise ValueError("Tag name is required")

                    tag = db.create_public_tag(tag_name)
                    return _return_data(201, tag)
                except ValueError as ve:
                    return _return_error(400, str(ve))
                except Exception as e:
                    logger.error(f"Error creating public tag: {str(e)}")
                    # Handle specific integrity error for duplicate names if db.create_public_tag doesn't already
                    if "UNIQUE constraint failed" in str(e) or "already exists" in str(
                        e
                    ):
                        return _return_error(
                            409, f"Public tag '{tag_name}' already exists."
                        )
                    return _return_error(500, str(e))

        # Handle tags endpoint (private)
        elif path == "/tags/private":
            if not user_id:
                return _return_error(401, "Authentication required")
            if http_method == "GET":
                logger.info(f"Getting private tags for user {user_id}...")
                try:
                    tags = db.get_private_tags(user_id)
                    return _return_data(200, tags)
                except Exception as e:
                    logger.error(f"Error getting private tags: {str(e)}")
                    return _return_error(500, str(e))
            elif http_method == "POST":
                logger.info(f"Creating new private tag for user {user_id}...")
                try:
                    body = json.loads(event.get("body", "{}"))
                    tag_name = body.get("name")
                    if not tag_name:
                        raise ValueError("Tag name is required")
                    if not username:  # Username should be available if user_id is
                        raise ValueError("Username not found for authenticated user.")

                    tag = db.create_private_tag(tag_name, user_id, username)
                    return _return_data(201, tag)
                except ValueError as ve:
                    return _return_error(400, str(ve))
                except Exception as e:
                    logger.error(f"Error creating private tag: {str(e)}")
                    if "UNIQUE constraint failed" in str(e) or "already exists" in str(
                        e
                    ):
                        return _return_error(
                            409,
                            f"Private tag '{tag_name}' for this user already exists.",
                        )
                    return _return_error(500, str(e))

        # Handle not found
        return _return_error(404, f"Endpoint not found: {path} {http_method}")

    except Exception as e:
        logger.error(f"Unhandled error: {str(e)}", exc_info=True)
        return _return_error(500, "Internal server error")
    finally:
        logger.info(f"Total execution time: {time.time() - start_time:.2f}s")
