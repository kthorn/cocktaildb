import json
import os
import boto3
from typing import Dict, Any
import sys
from pathlib import Path

# Add the src directory to the Python path
src_path = str(Path(__file__).parent.parent.parent.parent / "src")
sys.path.append(src_path)

from database.cocktail_db import Database


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda function to handle cocktail and ingredient operations
    """
    try:
        # Parse the HTTP method and path from the event
        http_method = event.get("httpMethod", "GET")
        path = event.get("path", "")

        # Initialize database
        db = Database()

        # Handle ingredients endpoints
        if path.startswith("/ingredients"):
            if http_method == "GET":
                # List all ingredients
                ingredients = db.session.query(db.Ingredient).all()
                return {
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
            elif http_method == "POST":
                # Create new ingredient
                body = json.loads(event.get("body", "{}"))
                ingredient = db.create_ingredient(body)
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
                body = json.loads(event.get("body", "{}"))
                ingredient = db.update_ingredient(ingredient_id, body)

                if ingredient:
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
                    return {
                        "statusCode": 404,
                        "body": json.dumps({"error": "Ingredient not found"}),
                    }
            elif http_method == "DELETE":
                # Delete ingredient
                ingredient_id = int(event.get("pathParameters", {}).get("id", 0))
                success = db.delete_ingredient(ingredient_id)

                if success:
                    return {"statusCode": 204, "body": ""}
                else:
                    return {
                        "statusCode": 404,
                        "body": json.dumps({"error": "Ingredient not found"}),
                    }

        # Handle other endpoints (cocktails, etc.)
        elif path.startswith("/cocktails"):
            # TODO: Implement cocktail endpoints
            return {
                "statusCode": 501,
                "body": json.dumps({"error": "Not implemented yet"}),
            }

        else:
            return {"statusCode": 404, "body": json.dumps({"error": "Not found"})}

    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
