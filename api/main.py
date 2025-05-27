"""
FastAPI application for CocktailDB API

This is the main FastAPI application that handles all cocktail database operations.
It replaces the previous AWS Lambda handler with a modern FastAPI implementation.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
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
from routes import ingredients, recipes, ratings, units, tags, auth
from routes.tags import recipe_tags_router
from models.responses import MessageResponse

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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
    docs_url="/docs" if settings.environment == "dev" else None,
    redoc_url="/redoc" if settings.environment == "dev" else None,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_credentials,
    allow_methods=settings.cors_methods,
    allow_headers=settings.cors_headers,
)

# Add exception handlers
app.add_exception_handler(CocktailDBException, cocktail_db_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, starlette_http_exception_handler)

# Add routers with API v1 prefix
API_V1_PREFIX = "/api/v1"

app.include_router(ingredients.router, prefix=API_V1_PREFIX)
app.include_router(recipes.router, prefix=API_V1_PREFIX)
app.include_router(ratings.router, prefix=API_V1_PREFIX)
app.include_router(units.router, prefix=API_V1_PREFIX)
app.include_router(tags.router, prefix=API_V1_PREFIX)
app.include_router(recipe_tags_router, prefix=API_V1_PREFIX)
app.include_router(auth.router, prefix=API_V1_PREFIX)


# Root endpoint
@app.get("/", response_model=MessageResponse)
async def root():
    """Root endpoint returning API information"""
    return MessageResponse(
        message=f"CocktailDB API v{settings.api_version} - Environment: {settings.environment}"
    )


# Health check endpoint
@app.get("/health", response_model=MessageResponse)
async def health_check():
    """Health check endpoint"""
    return MessageResponse(message="API is healthy")


# Legacy endpoints for backward compatibility (without /api/v1 prefix)
# These maintain the same paths as the original Lambda handler

app.include_router(ingredients.router, prefix="", include_in_schema=False)
app.include_router(recipes.router, prefix="", include_in_schema=False)
app.include_router(ratings.router, prefix="", include_in_schema=False)
app.include_router(units.router, prefix="", include_in_schema=False)
app.include_router(tags.router, prefix="", include_in_schema=False)
app.include_router(recipe_tags_router, prefix="", include_in_schema=False)
app.include_router(auth.router, prefix="", include_in_schema=False)


# Create the Lambda handler for AWS deployment
handler = Mangum(app, lifespan="off")


# For local development
if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting development server...")
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.log_level.lower()
    )
