"""Analytics-specific database queries for CocktailDB"""

import logging
from typing import TYPE_CHECKING, Dict, List, Any, Optional, cast

if TYPE_CHECKING:
    import pandas as pd

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
        self, parent_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get ingredient usage statistics with hierarchical aggregation

        Args:
            parent_id: Filter to children of specific ingredient

        Returns:
            List of ingredient usage statistics with direct and hierarchical counts
        """
        try:
            # Build WHERE clause for parent_id filtering
            where_clause = (
                "WHERE i.parent_id IS NULL"
                if parent_id is None
                else "WHERE i.parent_id = :parent_id"
            )
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

    def get_recipe_ingredient_matrix(
        self,
    ) -> tuple[Dict[int, int], "pd.DataFrame", List[str]]:
        """Build normalized recipe-ingredient matrix for distance calculations

        Returns:
            Tuple of (recipe_id_map, normalized_matrix, recipe_names)
            - recipe_id_map: Dict mapping matrix row index to recipe ID
            - normalized_matrix: pandas DataFrame with normalized ingredient proportions
            - recipe_names: List of recipe names corresponding to matrix rows
        """
        import pandas as pd

        try:
            # Load all recipes with ingredients and amounts
            sql = """
            SELECT
                r.id as recipe_id,
                r.name as recipe_name,
                i.id as ingredient_id,
                i.name as ingredient_name,
                ri.amount,
                ri.unit_id,
                u.conversion_to_ml
            FROM recipes r
            JOIN recipe_ingredients ri ON r.id = ri.recipe_id
            JOIN ingredients i ON ri.ingredient_id = i.id
            LEFT JOIN units u ON ri.unit_id = u.id
            ORDER BY r.id, i.id
            """

            rows = self.db.execute_query(sql)
            if not rows:
                logger.warning("No recipe data found for matrix building")
                return {}, pd.DataFrame(), []

            df = pd.DataFrame(rows)

            # Convert amounts to ml where possible
            df["amount_ml"] = df.apply(
                lambda row: row["amount"] * row["conversion_to_ml"]
                if pd.notna(row["conversion_to_ml"]) and pd.notna(row["amount"])
                else row["amount"]
                if pd.notna(row["amount"])
                else 1.0,  # Default to 1 if no amount
                axis=1,
            )

            # Create pivot table for amounts
            amount_matrix = df.pivot_table(
                index="recipe_name",
                columns="ingredient_name",
                values="amount_ml",
                aggfunc="sum",
                fill_value=0,
            )

            # Normalize each recipe to sum to 1 (proportions)
            normalized_matrix = amount_matrix.div(amount_matrix.sum(axis=1), axis=0)
            normalized_matrix = normalized_matrix.fillna(0)

            # Remove recipes/ingredients that are all zeros
            normalized_matrix = normalized_matrix.loc[
                (normalized_matrix != 0).any(axis=1), :
            ]
            normalized_matrix = normalized_matrix.loc[
                :, (normalized_matrix != 0).any(axis=0)
            ]

            # Before pivot, create mapping from unique recipes
            recipe_id_to_name = df[["recipe_id", "recipe_name"]].drop_duplicates(
                "recipe_id"
            )
            recipe_id_to_name = dict(
                zip(recipe_id_to_name["recipe_name"], recipe_id_to_name["recipe_id"])
            )

            # Create mapping from matrix row index to recipe ID
            recipe_id_map = {}
            recipe_names = []
            for idx, recipe_name in enumerate(normalized_matrix.index):
                recipe_id_map[idx] = int(recipe_id_to_name[recipe_name])
                recipe_names.append(recipe_name)

            logger.info(
                f"Built recipe matrix: {normalized_matrix.shape[0]} recipes x {normalized_matrix.shape[1]} ingredients"
            )
            return recipe_id_map, normalized_matrix, recipe_names

        except Exception as e:
            logger.error(f"Error building recipe ingredient matrix: {str(e)}")
            raise

    def compute_cocktail_space_umap(self) -> List[Dict[str, Any]]:
        """Compute UMAP embedding of recipe space based on ingredient similarity

        Uses Manhattan distance on normalized ingredient proportions, then UMAP
        for 2D visualization.

        Returns:
            List of dicts with {recipe_id, recipe_name, x, y}
        """
        import numpy as np
        from sklearn.metrics import pairwise_distances
        import umap

        try:
            # Get normalized recipe-ingredient matrix
            recipe_id_map, normalized_matrix, recipe_names = (
                self.get_recipe_ingredient_matrix()
            )

            if normalized_matrix.empty:
                logger.warning("Empty recipe matrix, returning empty UMAP")
                return []

            # Compute pairwise Manhattan distances
            logger.info("Computing pairwise Manhattan distances")
            distance_matrix = pairwise_distances(normalized_matrix, metric="manhattan")

            # Run UMAP dimensionality reduction
            logger.info("Running UMAP dimensionality reduction")
            reducer = umap.UMAP(
                n_neighbors=5,
                min_dist=0.05,
                n_components=2,
                metric="precomputed",
                random_state=42,
            )

            embedding = reducer.fit_transform(distance_matrix)

            # Build result list
            result = []
            for idx in range(len(embedding)):
                result.append(
                    {
                        "recipe_id": recipe_id_map[idx],
                        "recipe_name": recipe_names[idx],
                        "x": float(embedding[idx, 0]),
                        "y": float(embedding[idx, 1]),
                    }
                )

            logger.info(f"UMAP computation complete: {len(result)} recipes")
            return result

        except Exception as e:
            logger.error(f"Error computing cocktail space UMAP: {str(e)}")
            raise
