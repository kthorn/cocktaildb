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
        self, parent_id: Optional[int] = None, all_ingredients: bool = False
    ) -> List[Dict[str, Any]]:
        """Get ingredient usage statistics with hierarchical aggregation

        Args:
            parent_id: Filter to children of specific ingredient (ignored if all_ingredients=True)
            all_ingredients: If True, return all ingredients without filtering

        Returns:
            List of ingredient usage statistics with direct and hierarchical counts
        """
        try:
            # Build WHERE clause for filtering
            if all_ingredients:
                where_clause = ""
                params = {}
            elif parent_id is None:
                where_clause = "WHERE i.parent_id IS NULL"
                params = {}
            else:
                where_clause = "WHERE i.parent_id = :parent_id"
                params = {"parent_id": parent_id}

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

    def compute_cocktail_space_umap(self) -> dict:
        """Compute UMAP embedding of recipe space with ingredient lists

        Returns dict with 'data' key containing list of:
            {recipe_id, recipe_name, x, y, ingredients: [sorted ingredient names]}
        """
        import numpy as np
        from sklearn.metrics import pairwise_distances
        from barcart import compute_umap_embedding

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
            embedding = compute_umap_embedding(
                distance_matrix,
                n_neighbors=5,
                min_dist=0.05,
                random_state=42,
            )

            # Build result list with UMAP coordinates
            result = []
            recipe_ids = []
            for idx in range(len(embedding)):
                recipe_id = recipe_id_map[idx]
                recipe_ids.append(recipe_id)
                result.append(
                    {
                        "recipe_id": recipe_id,
                        "recipe_name": recipe_names[idx],
                        "x": float(embedding[idx, 0]),
                        "y": float(embedding[idx, 1]),
                        "ingredients": [],  # Will populate below
                    }
                )

            # Query ingredients for all recipes in one go
            if recipe_ids:
                placeholders = ",".join(["?"] * len(recipe_ids))
                ingredient_query = f"""
                    SELECT
                        ri.recipe_id,
                        i.name as ingredient_name,
                        CASE
                            WHEN u.name = 'to top' THEN 90.0
                            WHEN u.name = 'to rinse' THEN 5.0
                            WHEN u.name = 'each' OR u.name = 'Each' THEN -1.0
                            WHEN u.conversion_to_ml IS NOT NULL AND ri.amount IS NOT NULL
                                THEN u.conversion_to_ml * ri.amount
                            WHEN ri.amount IS NOT NULL THEN ri.amount
                            ELSE 0.0
                        END as volume_ml
                    FROM recipe_ingredients ri
                    JOIN ingredients i ON ri.ingredient_id = i.id
                    LEFT JOIN units u ON ri.unit_id = u.id
                    WHERE ri.recipe_id IN ({placeholders})
                    ORDER BY ri.recipe_id
                """

                ingredient_rows = self.db.execute_query(
                    ingredient_query, tuple(recipe_ids)
                )

                # Group ingredients by recipe and sort by volume
                recipe_ingredients = {}
                for row in ingredient_rows:
                    recipe_id = row["recipe_id"]
                    if recipe_id not in recipe_ingredients:
                        recipe_ingredients[recipe_id] = []

                    # Use pre-computed volume from SQL
                    amount_ml = row["volume_ml"]

                    recipe_ingredients[recipe_id].append(
                        {"name": row["ingredient_name"], "amount_ml": amount_ml}
                    )

                # Sort ingredients by volume and add to results
                for item in result:
                    recipe_id = item["recipe_id"]
                    if recipe_id in recipe_ingredients:
                        # Sort by amount (DESC), with "each" units (-1) at end
                        sorted_ings = sorted(
                            recipe_ingredients[recipe_id],
                            key=lambda x: x["amount_ml"],
                            reverse=True,
                        )
                        item["ingredients"] = [ing["name"] for ing in sorted_ings]

            logger.info(
                f"UMAP computation complete: {len(result)} recipes with ingredients"
            )
            return result

        except Exception as e:
            logger.error(f"Error computing cocktail space UMAP: {str(e)}")
            raise

    def get_ingredients_for_tree(self) -> "pd.DataFrame":
        """Get all ingredient data needed for building the ingredient tree

        Returns:
            pandas DataFrame with columns: ingredient_id, ingredient_name,
            ingredient_path (from path field), substitution_level,
            direct_recipe_count (from direct_usage),
            hierarchical_recipe_count (from hierarchical_usage)
        """
        import pandas as pd

        try:
            # Reuse the ingredient usage stats query with all_ingredients=True
            rows = self.get_ingredient_usage_stats(all_ingredients=True)

            if not rows:
                logger.warning("No ingredient data found for tree building")
                return pd.DataFrame()

            # Convert to DataFrame and rename columns for tree building
            df = pd.DataFrame(rows)
            df = df.rename(
                columns={
                    "path": "ingredient_path",
                    "direct_usage": "direct_recipe_count",
                    "hierarchical_usage": "hierarchical_recipe_count",
                }
            )

            # Add substitution_level column (using default weight)
            df["substitution_level"] = 1.0

            logger.info(f"Retrieved {len(df)} ingredients for tree building")
            return df

        except Exception as e:
            logger.error(f"Error getting ingredients for tree: {str(e)}")
            raise
