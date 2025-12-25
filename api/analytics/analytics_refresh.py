"""Analytics regeneration - core logic for local batch job."""
import json
import logging
import os
import sys
from typing import Dict, Any

import pandas as pd

from db.database import get_database
from db.db_analytics import AnalyticsQueries
from utils.analytics_cache import AnalyticsStorage

# Configure logging
logger = logging.getLogger(__name__)


def enrich_tree_with_recipe_counts(
    tree_node: Dict[str, Any],
    recipe_counts: Dict[str, Dict[str, int]],
) -> Dict[str, Any]:
    """Recursively enrich tree nodes with recipe count data."""
    node_id = str(tree_node["id"])

    # Add recipe counts if available (skip for root node)
    if node_id in recipe_counts:
        tree_node["recipe_count"] = recipe_counts[node_id]["direct"]
        tree_node["hierarchical_recipe_count"] = recipe_counts[node_id]["hierarchical"]
    else:
        # Root node or missing data
        tree_node["recipe_count"] = 0
        tree_node["hierarchical_recipe_count"] = 0

    # Recursively process children
    if "children" in tree_node:
        tree_node["children"] = [
            enrich_tree_with_recipe_counts(child, recipe_counts)
            for child in tree_node["children"]
        ]

    return tree_node


def regenerate_analytics() -> Dict[str, Any]:
    """
    Core analytics regeneration logic.

    Generates:
    - Root-level ingredient usage statistics
    - Recipe complexity distribution
    - Cocktail space UMAP projections (Manhattan and EM-based)
    - Ingredient tree with recipe counts

    Stores results on local disk via AnalyticsStorage.
    """
    # Get environment configuration
    storage_path = os.environ.get("ANALYTICS_PATH")
    if not storage_path:
        raise ValueError("ANALYTICS_PATH environment variable not set")

    logger.info("Starting analytics regeneration")

    # Initialize components
    db = get_database()
    analytics_queries = AnalyticsQueries(db)
    storage = AnalyticsStorage(storage_path)

    # Query all ingredient data once (used for both stats and tree)
    logger.info("Querying all ingredient usage statistics")
    all_ingredient_stats = analytics_queries.get_ingredient_usage_stats(
        all_ingredients=True
    )

    # Filter to root-level ingredients for the ingredient-usage endpoint
    ingredient_stats = [
        ing for ing in all_ingredient_stats if ing["parent_id"] is None
    ]
    logger.info("Filtered to %s root-level ingredients", len(ingredient_stats))

    # Convert all ingredients to DataFrame for tree building
    ingredients_df = pd.DataFrame(all_ingredient_stats)
    if not ingredients_df.empty:
        ingredients_df = ingredients_df.rename(
            columns={
                "path": "ingredient_path",
                "direct_usage": "direct_recipe_count",
                "hierarchical_usage": "hierarchical_recipe_count",
            }
        )
        ingredients_df["substitution_level"] = 1.0

    # Generate recipe complexity distribution
    logger.info("Generating recipe complexity distribution")
    complexity_stats = analytics_queries.get_recipe_complexity_distribution()

    # Generate both cocktail space variants for comparison
    logger.info("Generating Manhattan-based cocktail space")
    cocktail_space_manhattan = analytics_queries.compute_cocktail_space_umap()

    logger.info("Generating EM-based cocktail space with rollup")
    cocktail_space_em = analytics_queries.compute_cocktail_space_umap_em()

    # Generate ingredient tree
    logger.info("Building ingredient tree with recipe counts")
    from barcart.distance import build_ingredient_tree

    if not ingredients_df.empty:
        # Build the tree structure
        tree_dict, parent_map = build_ingredient_tree(
            ingredients_df,
            id_col="ingredient_id",
            name_col="ingredient_name",
            path_col="ingredient_path",
            weight_col="substitution_level",
            root_id="root",
            root_name="All Ingredients",
            default_edge_weight=1.0,
        )

        # Create recipe count lookup from DataFrame
        recipe_counts = {}
        for _, row in ingredients_df.iterrows():
            ing_id = str(row["ingredient_id"])
            recipe_counts[ing_id] = {
                "direct": int(row["direct_recipe_count"]),
                "hierarchical": int(row["hierarchical_recipe_count"]),
            }

        # Enrich tree with recipe counts
        enriched_tree = enrich_tree_with_recipe_counts(tree_dict, recipe_counts)

        logger.info("Built ingredient tree with %s ingredients", len(recipe_counts))
    else:
        logger.warning("No ingredient data available for tree building")
        enriched_tree = {
            "id": "root",
            "name": "All Ingredients",
            "recipe_count": 0,
            "hierarchical_recipe_count": 0,
            "children": [],
        }
        recipe_counts = {}

    # Store on local disk
    logger.info("Storing analytics on local disk")
    storage.put_analytics("ingredient-usage", ingredient_stats)
    storage.put_analytics("recipe-complexity", complexity_stats)
    storage.put_analytics("cocktail-space", cocktail_space_manhattan)
    storage.put_analytics("cocktail-space-em", cocktail_space_em)
    storage.put_analytics("ingredient-tree", enriched_tree)

    logger.info("Analytics regeneration completed successfully")

    return {
        "ingredient_stats_count": len(ingredient_stats),
        "complexity_stats_count": len(complexity_stats),
        "cocktail_space_count": len(cocktail_space_manhattan),
        "cocktail_space_em_count": len(cocktail_space_em),
        "ingredient_tree_nodes": len(recipe_counts),
    }


def main() -> None:
    """CLI entrypoint for analytics regeneration."""
    # Configure logging for CLI
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        result = regenerate_analytics()
        print(
            json.dumps(
                {
                    "status": "success",
                    "message": "Analytics regenerated successfully",
                    **result,
                }
            )
        )
        sys.exit(0)
    except Exception as e:
        logger.error("Error regenerating analytics: %s", str(e), exc_info=True)
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": "Failed to regenerate analytics",
                    "details": str(e),
                }
            )
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
