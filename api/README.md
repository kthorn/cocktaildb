# Cocktail DB API

A FastAPI application for managing cocktail recipes and ingredients, deployed on EC2.

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

## Deployment

The API runs on EC2 with `uvicorn` and is typically reverse-proxied by Caddy. See `scripts/deploy-ec2.sh` and `infrastructure/ansible/` for deployment workflows.

## Development

Each endpoint currently returns a placeholder response. Implement the TODO sections in `main.py` with your actual business logic. 
