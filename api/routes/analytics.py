"""Analytics endpoints for the CocktailDB API"""

import logging
import os
from typing import Optional
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from dependencies.auth import UserInfo, get_current_user_optional
from db.database import get_database as get_db
from db.db_core import Database
from db.db_analytics import AnalyticsQueries
from core.exceptions import DatabaseException
from utils.analytics_cache import AnalyticsStorage
from utils.analytics_files import get_em_distance_matrix_path

# Configure logger (inherits from main.py configuration)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])

# Initialize storage manager
ANALYTICS_PATH = os.environ.get("ANALYTICS_PATH", "")
storage_manager = AnalyticsStorage(ANALYTICS_PATH) if ANALYTICS_PATH else None


@router.get("/ingredient-usage")
async def get_ingredient_usage_analytics(
    level: Optional[int] = None,
    parent_id: Optional[int] = None,
    db: Database = Depends(get_db),
    user: Optional[UserInfo] = Depends(get_current_user_optional),
):
    """Get ingredient usage statistics with hierarchical aggregation

    Root level data is cached in S3. Hierarchical drill-down data is computed on-the-fly.
    """
    try:
        # For root level (no filters), use cached data from S3
        if level is None and parent_id is None:
            if not storage_manager:
                raise DatabaseException("Analytics storage not configured")

            stored_data = storage_manager.get_analytics("ingredient-usage")
            if not stored_data:
                raise DatabaseException(
                    "Analytics not generated. Please trigger analytics refresh.",
                    detail="ingredient-usage data not found in storage"
                )

            return stored_data

        # For hierarchical drill-down, compute on-the-fly
        else:
            analytics_queries = AnalyticsQueries(db)
            # Note: level filtering happens at API level, function only supports parent_id
            result = analytics_queries.get_ingredient_usage_stats(parent_id=parent_id)

            # Return in same format as cached data
            return {
                "data": result,
                "metadata": {
                    "computed_on_the_fly": True,
                    "level": level,
                    "parent_id": parent_id
                }
            }

    except DatabaseException:
        raise
    except Exception as e:
        logger.error(f"Error getting ingredient usage analytics: {str(e)}")
        raise DatabaseException("Failed to retrieve ingredient usage analytics", detail=str(e))


@router.get("/recipe-complexity")
async def get_recipe_complexity_analytics(
    db: Database = Depends(get_db),
    user: Optional[UserInfo] = Depends(get_current_user_optional),
):
    """Get recipe complexity distribution"""
    try:
        storage_key = "recipe-complexity"

        if not storage_manager:
            raise DatabaseException("Analytics storage not configured")

        stored_data = storage_manager.get_analytics(storage_key)
        if not stored_data:
            raise DatabaseException(
                "Analytics not generated. Please trigger analytics refresh.",
                detail=f"{storage_key} data not found in storage"
            )

        return stored_data

    except DatabaseException:
        raise
    except Exception as e:
        logger.error(f"Error getting recipe complexity analytics: {str(e)}")
        raise DatabaseException("Failed to retrieve recipe complexity analytics", detail=str(e))


@router.get("/cocktail-space")
async def get_cocktail_space_analytics(
    db: Database = Depends(get_db),
    user: Optional[UserInfo] = Depends(get_current_user_optional),
):
    """Get UMAP embedding of recipe space based on ingredient similarity"""
    try:
        storage_key = "cocktail-space"

        if not storage_manager:
            raise DatabaseException("Analytics storage not configured")

        stored_data = storage_manager.get_analytics(storage_key)
        if not stored_data:
            raise DatabaseException(
                "Analytics not generated. Please trigger analytics refresh.",
                detail="cocktail-space data not found in storage"
            )

        return stored_data
    except DatabaseException:
        raise
    except Exception as e:
        logger.error(f"Error getting cocktail space analytics: {str(e)}")
        raise DatabaseException("Failed to retrieve cocktail space analytics", detail=str(e))


@router.get("/cocktail-space-em")
async def get_cocktail_space_em_analytics(
    db: Database = Depends(get_db),
    user: Optional[UserInfo] = Depends(get_current_user_optional),
):
    """Get UMAP embedding of recipe space based on EM-learned distances with ingredient rollup"""
    try:
        storage_key = "cocktail-space-em"

        if not storage_manager:
            raise DatabaseException("Analytics storage not configured")

        stored_data = storage_manager.get_analytics(storage_key)
        if not stored_data:
            raise DatabaseException(
                "Analytics not generated. Please trigger analytics refresh.",
                detail="cocktail-space-em data not found in storage"
            )

        return stored_data
    except DatabaseException:
        raise
    except Exception as e:
        logger.error(f"Error getting EM cocktail space analytics: {str(e)}")
        raise DatabaseException("Failed to retrieve EM cocktail space analytics", detail=str(e))


@router.get("/ingredient-tree")
async def get_ingredient_tree_analytics(
    db: Database = Depends(get_db),
    user: Optional[UserInfo] = Depends(get_current_user_optional),
):
    """Get hierarchical ingredient tree with recipe counts

    Returns a D3-compatible tree structure with recipe_count (direct usage)
    and hierarchical_recipe_count for each node, suitable for tooltips and
    tree visualizations.
    """
    try:
        storage_key = "ingredient-tree"

        if not storage_manager:
            raise DatabaseException("Analytics storage not configured")

        stored_data = storage_manager.get_analytics(storage_key)
        if not stored_data:
            raise DatabaseException(
                "Analytics not generated. Please trigger analytics refresh.",
                detail="ingredient-tree data not found in storage"
            )

        return stored_data
    except DatabaseException:
        raise
    except Exception as e:
        logger.error(f"Error getting ingredient tree analytics: {str(e)}")
        raise DatabaseException("Failed to retrieve ingredient tree analytics", detail=str(e))


@router.get("/recipe-distances-em/download")
async def download_em_recipe_distances(
    user: Optional[UserInfo] = Depends(get_current_user_optional),
):
    """Download the EM pairwise recipe distance matrix."""
    try:
        if not storage_manager:
            raise DatabaseException("Analytics storage not configured")

        file_path = get_em_distance_matrix_path(ANALYTICS_PATH)
        if not file_path.exists():
            raise DatabaseException(
                "Analytics not generated. Please trigger analytics refresh.",
                detail="recipe-distances-em file not found in storage"
            )

        return FileResponse(
            path=file_path,
            media_type="application/octet-stream",
            filename=file_path.name,
        )
    except DatabaseException:
        raise
    except Exception as e:
        logger.error(f"Error downloading EM distance matrix: {str(e)}")
        raise DatabaseException("Failed to download EM distance matrix", detail=str(e))
