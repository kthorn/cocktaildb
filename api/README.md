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

## MCP server

A public, read-only [Model Context Protocol](https://modelcontextprotocol.io/) server is served at `https://mixology.tools/api/v1/mcp` (streamable HTTP, stateless, JSON responses). No authentication is required and no user data is exposed. Design: `docs/superpowers/specs/2026-11-14-public-mcp-server-design.md`.

Tools:

- `search_recipes` - search recipes by name, ingredients, tags, and ABV range (at most 10 ingredient/tag names of 100 characters each; queries up to 200 characters)
- `get_recipe` - full recipe with ingredients, instructions, and ABV estimate
- `find_similar_recipes` - recipes similar to a given recipe, with ingredient swaps
- `find_ingredients` - look up canonical ingredient names and their hierarchy

To use it, add `https://mixology.tools/api/v1/mcp` as a custom connector in an assistant that supports remote MCP servers (for example Claude: Settings, Connectors, Add custom connector).

The endpoint has a separate per-IP limit of 300 requests/minute. Browser-based MCP clients are not supported: the API sends no CORS headers.

## Deployment

The API runs on EC2 with `uvicorn` and is typically reverse-proxied by Caddy. See `scripts/deploy-ec2.sh` and `infrastructure/ansible/` for deployment workflows.

## Development

Each endpoint currently returns a placeholder response. Implement the TODO sections in `main.py` with your actual business logic. 
