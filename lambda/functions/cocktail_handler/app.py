import json
import os
import boto3
from typing import Dict, Any

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda function to handle cocktail-related operations
    """
    try:
        # Parse the HTTP method from the event
        http_method = event.get('httpMethod', 'GET')
        
        # Handle different HTTP methods
        if http_method == 'GET':
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Get cocktail data'
                })
            }
        elif http_method == 'POST':
            body = json.loads(event.get('body', '{}'))
            return {
                'statusCode': 201,
                'body': json.dumps({
                    'message': 'Cocktail created',
                    'data': body
                })
            }
        else:
            return {
                'statusCode': 405,
                'body': json.dumps({
                    'message': 'Method not allowed'
                })
            }
            
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Internal server error',
                'error': str(e)
            })
        } 