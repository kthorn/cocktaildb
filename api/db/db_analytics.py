"""Analytics-specific database queries for CocktailDB"""

import logging
from typing import Dict, List, Any, Optional, cast

logger = logging.getLogger(__name__)


class AnalyticsQueries:
    """Analytics database query methods - separate from core Database class"""

    def __init__(self, db):
        """Initialize with a Database instance

        Args:
            db: Database instance from db_core.py
        """
        self.db = db

    def get_ingredient_usage_stats(
        self, level: Optional[int] = None, parent_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get ingredient usage statistics with hierarchical aggregation

        Args:
            level: Hierarchy level (0=root, 1=first level children, etc.) - currently unused
            parent_id: Filter to children of specific ingredient

        Returns:
            List of ingredient usage statistics with direct and hierarchical counts
        """
        try:
            # Build WHERE clause for parent_id filtering
            where_clause = "WHERE i.parent_id IS NULL" if parent_id is None else "WHERE i.parent_id = :parent_id"
            params = {} if parent_id is None else {"parent_id": parent_id}

            sql = f"""
            SELECT
              i.id as ingredient_id,
              i.name as ingredient_name,
              i.path,
              i.parent_id,
              COUNT(DISTINCT ri.recipe_id) as direct_usage,
              (
                SELECT COUNT(DISTINCT ri2.recipe_id)
                FROM recipe_ingredients ri2
                INNER JOIN ingredients i2 ON ri2.ingredient_id = i2.id
                WHERE i2.path LIKE i.path || '%'
              ) as hierarchical_usage,
              EXISTS(SELECT 1 FROM ingredients WHERE parent_id = i.id) as has_children
            FROM ingredients i
            LEFT JOIN recipe_ingredients ri ON ri.ingredient_id = i.id
            {where_clause}
            GROUP BY i.id, i.name, i.path, i.parent_id
            ORDER BY hierarchical_usage DESC
            """

            result = cast(List[Dict[str, Any]], self.db.execute_query(sql, params))
            return result
        except Exception as e:
            logger.error(f"Error getting ingredient usage stats: {str(e)}")
            raise

    def get_recipe_complexity_distribution(self) -> List[Dict[str, Any]]:
        """Get recipe complexity distribution by ingredient count

        Returns:
            List of {ingredient_count, recipe_count} dictionaries
        """
        try:
            sql = """
            SELECT
              ingredient_count,
              COUNT(*) as recipe_count
            FROM (
              SELECT
                recipe_id,
                COUNT(DISTINCT ingredient_id) as ingredient_count
              FROM recipe_ingredients
              GROUP BY recipe_id
            ) counts
            GROUP BY ingredient_count
            ORDER BY ingredient_count
            """

            result = cast(List[Dict[str, Any]], self.db.execute_query(sql))
            return result
        except Exception as e:
            logger.error(f"Error getting recipe complexity distribution: {str(e)}")
            raise
