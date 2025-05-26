# Cocktail DB API

A FastAPI application for managing cocktail recipes and ingredients, deployable to AWS Lambda.

## Installation

```bash
pip install -r requirements.txt
```

## Running Locally

To run the API locally:

```bash
python main.py
```

The API will be available at `http://localhost:8000`

### API Documentation

When running locally, you can access:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Endpoints

- `GET /ingredients` - Get all ingredients
- `GET /ingredients/{id}` - Get a specific ingredient
- `GET /ratings/{recipe_id}` - Get ratings for a recipe
- `GET /recipes` - Get all recipes
- `GET /recipes?search=true` - Search recipes
- `GET /recipes/{id}` - Get a specific recipe
- `GET /recipes/{recipe_id}/private_tags` - Get private tags for a recipe
- `POST /recipes/{recipe_id}/private_tags` - Add a private tag to a recipe
- `GET /recipes/{recipe_id}/private_tags/{tag_id}` - Get a specific private tag
- `PUT /recipes/{recipe_id}/private_tags/{tag_id}` - Update a private tag
- `DELETE /recipes/{recipe_id}/private_tags/{tag_id}` - Delete a private tag
- `GET /recipes/{recipe_id}/public_tags` - Get public tags for a recipe
- `POST /recipes/{recipe_id}/public_tags` - Add a public tag to a recipe
- `GET /recipes/{recipe_id}/public_tags/{tag_id}` - Get a specific public tag
- `PUT /recipes/{recipe_id}/public_tags/{tag_id}` - Update a public tag
- `DELETE /recipes/{recipe_id}/public_tags/{tag_id}` - Delete a public tag
- `GET /units` - Get all units
- `GET /units?type={type}` - Get units filtered by type

## AWS Lambda Deployment

The application uses Mangum to adapt FastAPI for AWS Lambda. The `handler` function in `main.py` is the Lambda entry point.

### Deployment Steps

1. Package your application and dependencies
2. Create a Lambda function with Python 3.9+ runtime
3. Set the handler to `main.handler`
4. Configure API Gateway to route requests to your Lambda function

### Example serverless.yml (for Serverless Framework)

```yaml
service: cocktaildb-api

provider:
  name: aws
  runtime: python3.9
  region: us-east-1

functions:
  api:
    handler: main.handler
    events:
      - http:
          path: /{proxy+}
          method: ANY
      - http:
          path: /
          method: ANY
```

## Development

Each endpoint currently returns a placeholder response. Implement the TODO sections in `main.py` with your actual business logic. 