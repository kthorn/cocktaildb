"""Lambda function for regenerating pre-computed analytics"""
import json
import logging
import os
from typing import Dict, Any

from db.database import get_database
from db.db_analytics import AnalyticsQueries
from utils.analytics_cache import AnalyticsStorage

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def enrich_tree_with_recipe_counts(tree_node: Dict[str, Any], recipe_counts: Dict[str, Dict[str, int]]) -> Dict[str, Any]:
    """Recursively enrich tree nodes with recipe count data

    Args:
        tree_node: Tree node dictionary from build_ingredient_tree
        recipe_counts: Dict mapping ingredient_id to {direct, hierarchical} counts

    Returns:
        Enriched tree node with recipe_count and hierarchical_recipe_count fields
    """
    node_id = str(tree_node['id'])

    # Add recipe counts if available (skip for root node)
    if node_id in recipe_counts:
        tree_node['recipe_count'] = recipe_counts[node_id]['direct']
        tree_node['hierarchical_recipe_count'] = recipe_counts[node_id]['hierarchical']
    else:
        # Root node or missing data
        tree_node['recipe_count'] = 0
        tree_node['hierarchical_recipe_count'] = 0

    # Recursively process children
    if 'children' in tree_node:
        tree_node['children'] = [
            enrich_tree_with_recipe_counts(child, recipe_counts)
            for child in tree_node['children']
        ]

    return tree_node


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to regenerate and store pre-computed analytics.

    Generates:
    - Root-level ingredient usage statistics
    - Recipe complexity distribution

    Stores results in S3 via AnalyticsStorage.

    Returns:
        dict: Lambda response with statusCode and body
    """
    try:
        # Get environment configuration
        bucket_name = os.environ.get('ANALYTICS_BUCKET')
        if not bucket_name:
            raise ValueError("ANALYTICS_BUCKET environment variable not set")

        logger.info("Starting analytics regeneration")

        # Initialize components
        db = get_database()
        analytics_queries = AnalyticsQueries(db)
        storage = AnalyticsStorage(bucket_name)

        # Generate root-level ingredient usage stats
        logger.info("Generating ingredient usage statistics")
        ingredient_stats = analytics_queries.get_ingredient_usage_stats()

        # Generate recipe complexity distribution
        logger.info("Generating recipe complexity distribution")
        complexity_stats = analytics_queries.get_recipe_complexity_distribution()

        # Generate cocktail space UMAP
        logger.info("Generating cocktail space UMAP embedding")
        cocktail_space = analytics_queries.compute_cocktail_space_umap()

        # Generate ingredient tree
        logger.info("Generating ingredient tree with recipe counts")
        from barcart.distance import build_ingredient_tree

        # Get ingredient data for tree building
        ingredients_df = analytics_queries.get_ingredients_for_tree()

        if not ingredients_df.empty:
            # Build the tree structure
            tree_dict, parent_map = build_ingredient_tree(
                ingredients_df,
                id_col='ingredient_id',
                name_col='ingredient_name',
                path_col='ingredient_path',
                weight_col='substitution_level',
                root_id='root',
                root_name='All Ingredients',
                default_edge_weight=1.0
            )

            # Create recipe count lookup from DataFrame
            recipe_counts = {}
            for _, row in ingredients_df.iterrows():
                ing_id = str(row['ingredient_id'])
                recipe_counts[ing_id] = {
                    'direct': int(row['direct_recipe_count']),
                    'hierarchical': int(row['hierarchical_recipe_count'])
                }

            # Enrich tree with recipe counts
            enriched_tree = enrich_tree_with_recipe_counts(tree_dict, recipe_counts)

            logger.info(f"Built ingredient tree with {len(recipe_counts)} ingredients")
        else:
            logger.warning("No ingredient data available for tree building")
            enriched_tree = {
                "id": "root",
                "name": "All Ingredients",
                "recipe_count": 0,
                "hierarchical_recipe_count": 0,
                "children": []
            }

        # Store in S3
        logger.info("Storing analytics in S3")
        storage.put_analytics('ingredient-usage', ingredient_stats)
        storage.put_analytics('recipe-complexity', complexity_stats)
        storage.put_analytics('cocktail-space', cocktail_space)
        storage.put_analytics('ingredient-tree', enriched_tree)

        logger.info("Analytics regeneration completed successfully")

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Analytics regenerated successfully",
                "ingredient_stats_count": len(ingredient_stats),
                "complexity_stats_count": len(complexity_stats),
                "cocktail_space_count": len(cocktail_space.get('data', [])),
                "ingredient_tree_nodes": len(recipe_counts) if not ingredients_df.empty else 0
            })
        }

    except Exception as e:
        logger.error(f"Error regenerating analytics: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": "Failed to regenerate analytics",
                "details": str(e)
            })
        }
