import json
import os
from typing import Dict, Any


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda function to return the API Gateway URL
    """
    try:
        api_url = os.environ.get("API_GATEWAY_URL", "")
        return {"statusCode": 200, "body": json.dumps({"apiUrl": api_url})}
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
