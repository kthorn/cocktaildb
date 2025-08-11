"""Stats endpoints for the CocktailDB API"""

import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from db.database import get_database as get_db
from db.db_core import Database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stats", tags=["stats"])


class StatsResponse(BaseModel):
    """Response model for database statistics"""
    recipes_count: int
    ingredients_count: int


@router.get("", response_model=StatsResponse)
async def get_stats(
    db: Database = Depends(get_db)
) -> StatsResponse:
    """Get database statistics including total counts of recipes and ingredients"""
    try:
        recipes_count = db.get_recipes_count()
        ingredients_count = db.get_ingredients_count()
        
        return StatsResponse(
            recipes_count=recipes_count,
            ingredients_count=ingredients_count
        )
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        raise