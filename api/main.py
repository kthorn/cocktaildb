"""
FastAPI application for CocktailDB API

This is the main FastAPI application that handles all cocktail database operations.
Deployed on EC2 with Caddy reverse proxy.
"""

import logging
import sys
import os
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import settings
from core.exceptions import CocktailDBException
from core.exception_handlers import (
    cocktail_db_exception_handler,
    starlette_http_exception_handler,
    validation_exception_handler,
    general_exception_handler,
)
from routes import ingredients, recipes, ratings, units, tags, auth, admin, user_ingredients, stats, analytics
from routes.tags import recipe_tags_router

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class CORSHeaderMiddleware(BaseHTTPMiddleware):
    """Add CORS headers to all responses"""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Add CORS headers to all responses
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type,Authorization,Accept"
        )

        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI application"""
    # Startup
    logger.info("Starting CocktailDB API")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Database: {settings.db_host}:{settings.db_port}/{settings.db_name}")

    yield

    # Shutdown
    logger.info("Shutting down CocktailDB API")


# Create FastAPI app
app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    debug=settings.debug,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware
app.add_middleware(CORSHeaderMiddleware)

# Add exception handlers
app.add_exception_handler(CocktailDBException, cocktail_db_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, starlette_http_exception_handler)

# Add routers (Caddy handles /api prefix via reverse proxy)
app.include_router(ingredients.router)
app.include_router(recipes.router)
app.include_router(ratings.router)
app.include_router(units.router)
app.include_router(tags.router)
app.include_router(recipe_tags_router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(user_ingredients.router)
app.include_router(stats.router)
app.include_router(analytics.router)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint returning self-describing API information for agent discovery"""
    return {
        "name": "Mixology Tools API",
        "description": "Public API for the Mixology Tools cocktail recipe database. "
                       "Search cocktails by name, ingredient, or category. "
                       "Hierarchical ingredient taxonomy with analytics.",
        "version": settings.api_version,
        "docs": "/api/v1/docs",
        "redoc": "/api/v1/redoc",
        "openapi": "/api/v1/openapi.json",
        "endpoints": {
            "search_recipes": "/api/v1/recipes/search",
            "get_recipe": "/api/v1/recipes/{id}",
            "ingredients": "/api/v1/ingredients",
            "get_ingredient": "/api/v1/ingredients/{id}",
            "search_ingredients": "/api/v1/ingredients/search",
            "stats": "/api/v1/stats",
            "units": "/api/v1/units",
            "public_tags": "/api/v1/tags/public",
            "analytics_ingredient_usage": "/api/v1/analytics/ingredient-usage",
            "analytics_recipe_complexity": "/api/v1/analytics/recipe-complexity",
            "analytics_cocktail_space": "/api/v1/analytics/cocktail-space",
            "analytics_ingredient_tree": "/api/v1/analytics/ingredient-tree",
            "analytics_recipe_similar": "/api/v1/analytics/recipe-similar",
        },
    }


# Health check endpoint
@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint for container orchestration."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


# For local development
if __name__ == "__main__":
    import uvicorn

    logger.info("Starting development server...")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.log_level.lower(),
    )
