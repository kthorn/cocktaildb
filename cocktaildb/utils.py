import json
from typing import Any, Dict

# CORS headers for all responses
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,Accept,Access-Control-Allow-Headers,Access-Control-Allow-Origin,Access-Control-Allow-Methods",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
    "Access-Control-Allow-Credentials": "true",
}


# Helper functions for standard responses
def _return_data(status_code: int, data: Any) -> Dict[str, Any]:
    """Generates a response with JSON data in the body."""
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(data),
    }


def _return_error(status_code: int, error_message: str) -> Dict[str, Any]:
    """Generates a response with a JSON error object."""
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps({"error": error_message}),
    }


def _return_empty(status_code: int) -> Dict[str, Any]:
    """Generates a response with an empty body."""
    return {"statusCode": status_code, "headers": CORS_HEADERS, "body": ""}


def _return_message(status_code: int, message: str) -> Dict[str, Any]:
    """Generates a response with a JSON message object."""
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps({"message": message}),
    }
