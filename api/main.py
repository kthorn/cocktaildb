"""
FastAPI application for CocktailDB API

This is the main FastAPI application that handles all cocktail database operations.
Deployed on EC2 with Caddy reverse proxy.
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime

import anyio.to_thread
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import settings
from core.exception_handlers import (
    cocktail_db_exception_handler,
    general_exception_handler,
    starlette_http_exception_handler,
    validation_exception_handler,
    value_error_handler,
)
from core.exceptions import CocktailDBException
from core.release_info import read_release_info
from db.database import get_database
from db.db_core import Database
from mcp_tools.endpoint import McpEndpoint
from mcp_tools.gate import DbGate
from mcp_tools.server import build_mcp_server
from middleware.rate_limit import RateLimitMiddleware
from routes import (
    analytics,
    auth,
    groups,
    ingredients,
    pages,
    ratings,
    recipes,
    stats,
    tags,
    units,
    user_ingredients,
)
from routes.tags import recipe_tags_router

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
# Stateless mode logs "Terminating session: None" at INFO on every request
logging.getLogger("mcp.server.streamable_http").setLevel(logging.WARNING)


# One gate for the process so the MCP DB-concurrency limit is shared across restarts
mcp_gate = DbGate(
    settings.mcp_max_concurrent_db_calls, settings.mcp_db_slot_timeout_seconds
)
mcp_endpoint = McpEndpoint(
    lambda: build_mcp_server(get_database, base_url=settings.base_url, gate=mcp_gate)
)


def configure_threadpool() -> None:
    """Bound concurrent sync handlers so they cannot exhaust the DB pool.

    Route handlers are sync (psycopg2 blocks), so FastAPI runs them in anyio's
    threadpool. psycopg2's pool raises rather than waits when exhausted.
    """
    limiter = anyio.to_thread.current_default_thread_limiter()
    limiter.total_tokens = (
        Database.POOL_MAX_CONNECTIONS // Database.MAX_CONNECTIONS_PER_REQUEST
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI application"""
    # Startup
    configure_threadpool()
    logger.info("Starting CocktailDB API")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Database: {settings.db_host}:{settings.db_port}/{settings.db_name}")
    pages.frontend_assets.validate()

    async with mcp_endpoint.running():
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

# The frontend, API, and MCP server share one origin behind Caddy, so the API
# sends no CORS headers; cross-origin browser access is unsupported (#138).
app.add_middleware(
    RateLimitMiddleware, mcp_max_requests=settings.mcp_rate_limit_per_minute
)

# Add exception handlers
app.add_exception_handler(CocktailDBException, cocktail_db_exception_handler)
app.add_exception_handler(ValueError, value_error_handler)
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
app.include_router(user_ingredients.router)
app.include_router(groups.router)
app.include_router(stats.router)
app.include_router(analytics.router)
app.include_router(pages.router)

# Public read-only MCP endpoint (Caddy strips /api/v1, so this is /api/v1/mcp)
# POST only: stateless mode has no server-initiated stream, so GET/DELETE get a 405
app.add_route("/mcp", mcp_endpoint, methods=["POST"], include_in_schema=False)
app.add_route("/mcp/", mcp_endpoint, methods=["POST"], include_in_schema=False)


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
        "mcp": "/api/v1/mcp",
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


# Read once at startup: the identity is fixed for the life of the image.
RELEASE_INFO = read_release_info()


# Health check endpoint
@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint for container orchestration."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "release": RELEASE_INFO,
    }


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
