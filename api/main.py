"""
FastAPI application for CocktailDB API

This is the main FastAPI application that handles all cocktail database operations.
It replaces the previous AWS Lambda handler with a modern FastAPI implementation.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from mangum import Mangum

# Handle both Lambda and local execution environments
import sys
import os

# Add current directory to Python path for Lambda
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import settings
from core.exceptions import CocktailDBException
from core.exception_handlers import (
    cocktail_db_exception_handler,
    http_exception_handler,
    starlette_http_exception_handler,
    validation_exception_handler,
    general_exception_handler,
)
from routes import ingredients, recipes, ratings, units, tags, auth, admin, user_ingredients, stats, analytics
from routes.tags import recipe_tags_router
from models.responses import MessageResponse

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class CORSHeaderMiddleware(BaseHTTPMiddleware):
    """Add CORS headers to all responses from Lambda"""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Add CORS headers to all responses
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type,Authorization,Accept,X-Amz-Date,X-Api-Key,X-Amz-Security-Token"
        )

        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI application"""
    # Startup
    logger.info("Starting CocktailDB API")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Database path: {settings.db_path}")

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

# Add CORS middleware for Lambda responses (API Gateway handles OPTIONS)
app.add_middleware(CORSHeaderMiddleware)

# Add exception handlers
app.add_exception_handler(CocktailDBException, cocktail_db_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, starlette_http_exception_handler)

# Add routers at root level (API Gateway handles /api prefix)
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

# OPTIONS handlers are explicitly defined in template.yaml as mock integrations
# This prevents CORS preflight requests from hitting Cognito authorization
# and ensures proper CORS headers are returned for all endpoints


# Root endpoint
@app.get("/", response_model=MessageResponse)
async def root():
    """Root endpoint returning API information"""
    return MessageResponse(
        message=f"CocktailDB API v{settings.api_version} - Environment: {settings.environment}"
    )


# Health check endpoint
@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint for container orchestration."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


# Legacy endpoints removed - now using FastAPI v1 endpoints only


# Create the Lambda handler for AWS deployment with custom scope
def lambda_handler(event, context):
    """Lambda handler that injects event into request scope"""
    # Create Mangum handler
    mangum_handler = Mangum(app, lifespan="off")

    # Store event in a way that can be accessed by dependencies
    import contextvars

    _lambda_event = contextvars.ContextVar("lambda_event")
    _lambda_event.set(event)

    # Store event globally for access in dependencies
    global _current_lambda_event
    _current_lambda_event = event

    return mangum_handler(event, context)


# Global variable to store current Lambda event
_current_lambda_event = None

# For backward compatibility, also export as handler
handler = lambda_handler


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
