#!/usr/bin/env python3
"""
Test script to evaluate constrained EM with different k values.

Compares full O(N²) EM vs constrained top-k approaches to measure:
1. Speed improvement
2. Quality impact on learned distances
3. Neighbor accuracy (do we still find the same nearest neighbors?)

Usage:
    # Fetch data from production API
    python scripts/test_constrained_em.py --api https://mixology.tools

    # Use cached data (after first run)
    python scripts/test_constrained_em.py --use-cache

    # Test specific k values
    python scripts/test_constrained_em.py --k-values 50,100,200
"""

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests
from scipy import sparse as sp
from scipy.spatial.distance import cdist

# Add project paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages", "barcart"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / ".cache"


@dataclass
class EMResult:
    """Results from an EM run."""
    distance_matrix: np.ndarray
    cost_matrix: np.ndarray
    elapsed_seconds: float
    pairs_computed: int
    k_value: Optional[int]  # None for full computation


def compute_manhattan_candidates(
    volume_matrix: np.ndarray | sp.spmatrix,
    k: int,
) -> dict[int, np.ndarray]:
    """
    Compute top-k nearest neighbors by Manhattan distance for each recipe.

    Returns dict mapping recipe index -> array of k candidate neighbor indices.
    """
    n_recipes = volume_matrix.shape[0]

    # Convert sparse to dense for distance computation
    if sp.issparse(volume_matrix):
        dense_matrix = volume_matrix.toarray()
    else:
        dense_matrix = volume_matrix

    # Compute full Manhattan distance matrix (cheap - just L1 norm)
    logger.info("Computing Manhattan distance matrix...")
    t0 = time.time()
    manhattan_dist = cdist(dense_matrix, dense_matrix, metric='cityblock')
    logger.info(f"Manhattan distances computed in {time.time() - t0:.2f}s")

    # For each recipe, find top-k nearest (excluding self)
    candidates = {}
    np.fill_diagonal(manhattan_dist, np.inf)

    for i in range(n_recipes):
        # Get indices of k smallest distances
        nearest_k = np.argpartition(manhattan_dist[i], k)[:k]
        candidates[i] = nearest_k

    return candidates, manhattan_dist


def compute_emd_candidates(
    distance_matrix: np.ndarray,
    k: int,
) -> dict[int, np.ndarray]:
    """
    Compute top-k nearest neighbors from previous EMD distances.

    Returns dict mapping recipe index -> array of k candidate neighbor indices.
    """
    n_recipes = distance_matrix.shape[0]
    candidates = {}

    dmat = distance_matrix.copy()
    np.fill_diagonal(dmat, np.inf)

    for i in range(n_recipes):
        nearest_k = np.argpartition(dmat[i], k)[:k]
        candidates[i] = nearest_k

    return candidates


def constrained_emd_matrix(
    volume_matrix: np.ndarray | sp.spmatrix,
    cost_matrix: np.ndarray,
    candidates: dict[int, np.ndarray],
    return_plans: bool = False,
) -> tuple[np.ndarray, dict] | np.ndarray:
    """
    Compute EMD only for candidate pairs (not full O(N²)).
    """
    from barcart.distance import compute_emd

    n_recipes = volume_matrix.shape[0]
    is_sparse = sp.issparse(volume_matrix)
    emd_dtype = cost_matrix.dtype

    # Initialize with inf (unknown distances)
    emd_mat = np.full((n_recipes, n_recipes), np.inf, dtype=emd_dtype)
    np.fill_diagonal(emd_mat, 0.0)

    # Precompute supports
    if is_sparse:
        supports = [volume_matrix.getrow(i).indices for i in range(n_recipes)]
    else:
        supports = [np.nonzero(volume_matrix[i] > 0)[0] for i in range(n_recipes)]

    plans = {} if return_plans else None
    pairs_computed = set()

    for i, neighbor_indices in candidates.items():
        for j in neighbor_indices:
            j = int(j)
            # Canonical ordering to avoid duplicate computation
            pair = (min(i, j), max(i, j))
            if pair in pairs_computed or i == j:
                continue
            pairs_computed.add(pair)

            union_idx = np.union1d(supports[i], supports[j])
            row_i = volume_matrix.getrow(i) if is_sparse else volume_matrix[i]
            row_j = volume_matrix.getrow(j) if is_sparse else volume_matrix[j]

            if return_plans:
                distance, plan = compute_emd(
                    row_i, row_j, cost_matrix,
                    return_plan=True, support_idx=union_idx
                )
                plans[pair] = plan
            else:
                distance = compute_emd(
                    row_i, row_j, cost_matrix,
                    return_plan=False, support_idx=union_idx
                )

            emd_mat[i, j] = emd_dtype.type(distance)
            emd_mat[j, i] = emd_dtype.type(distance)

    logger.info(f"Computed {len(pairs_computed)} EMD pairs (vs {n_recipes * (n_recipes - 1) // 2} full)")

    if return_plans:
        return emd_mat, plans
    return emd_mat


def constrained_em_fit(
    volume_matrix: np.ndarray | sp.spmatrix,
    initial_cost_matrix: np.ndarray,
    n_ingredients: int,
    k: int,
    iters: int = 5,
    tolerance: float = 1e-3,
) -> tuple[np.ndarray, np.ndarray, dict, int]:
    """
    Run EM with constrained pair selection.

    Iteration 1: Use Manhattan distance to select top-k candidates
    Iteration 2+: Use previous EMD distances to select top-k candidates
    """
    from barcart.distance import expected_ingredient_match_matrix, m_step_blosum

    if sp.issparse(volume_matrix):
        if volume_matrix.dtype != np.float32:
            volume_matrix = volume_matrix.astype(np.float32)
    else:
        volume_matrix = np.asarray(volume_matrix, dtype=np.float32)

    cost_matrix = np.asarray(initial_cost_matrix, dtype=np.float32)

    n_recipes = volume_matrix.shape[0]
    total_pairs = 0
    log = {"delta": []}

    # Iteration 1: Manhattan-based candidate selection
    logger.info(f"Iteration 1: Manhattan-based candidate selection (k={k})")
    candidates, _ = compute_manhattan_candidates(volume_matrix, k)

    distance_matrix, plans = constrained_emd_matrix(
        volume_matrix, cost_matrix, candidates, return_plans=True
    )
    total_pairs += len([p for p in plans.keys()])

    # M-step
    T_sum, n_pairs = expected_ingredient_match_matrix(
        distance_matrix, plans, n_ingredients,
        k=10, beta=1.0, plan_topk=3, plan_minfrac=0.05, symmetrize=True
    )
    new_cost_matrix = m_step_blosum(T_sum).astype(np.float32)

    delta = np.linalg.norm(new_cost_matrix - cost_matrix) / (np.linalg.norm(cost_matrix) + 1e-12)
    log["delta"].append(float(delta))
    logger.info(f"[iter 1] delta={delta:.4e}")
    cost_matrix = new_cost_matrix.copy()

    # Iterations 2+: EMD-based candidate selection
    for t in range(1, iters):
        if delta < tolerance:
            logger.info("Converged early.")
            break

        logger.info(f"Iteration {t+1}: EMD-based candidate selection (k={k})")
        candidates = compute_emd_candidates(distance_matrix, k)

        distance_matrix, plans = constrained_emd_matrix(
            volume_matrix, cost_matrix, candidates, return_plans=True
        )
        total_pairs += len([p for p in plans.keys()])

        # M-step
        T_sum, n_pairs = expected_ingredient_match_matrix(
            distance_matrix, plans, n_ingredients,
            k=10, beta=1.0, plan_topk=3, plan_minfrac=0.05, symmetrize=True
        )
        new_cost_matrix = m_step_blosum(T_sum).astype(np.float32)

        delta = np.linalg.norm(new_cost_matrix - cost_matrix) / (np.linalg.norm(cost_matrix) + 1e-12)
        log["delta"].append(float(delta))
        logger.info(f"[iter {t+1}] delta={delta:.4e}")
        cost_matrix = new_cost_matrix.copy()

    return distance_matrix, cost_matrix, log, total_pairs


def compare_neighbor_accuracy(
    full_distances: np.ndarray,
    constrained_distances: np.ndarray,
    k_neighbors: int = 10,
) -> dict:
    """
    Compare how well constrained version preserves true nearest neighbors.
    """
    n = full_distances.shape[0]

    # Get true k-nearest neighbors from full computation
    full_dmat = full_distances.copy()
    np.fill_diagonal(full_dmat, np.inf)
    true_neighbors = np.argsort(full_dmat, axis=1)[:, :k_neighbors]

    # Get neighbors from constrained computation
    const_dmat = constrained_distances.copy()
    np.fill_diagonal(const_dmat, np.inf)
    # Replace inf with large value for sorting
    const_dmat[np.isinf(const_dmat)] = 1e10
    constrained_neighbors = np.argsort(const_dmat, axis=1)[:, :k_neighbors]

    # Compute overlap
    overlaps = []
    for i in range(n):
        true_set = set(true_neighbors[i])
        const_set = set(constrained_neighbors[i])
        overlap = len(true_set & const_set) / k_neighbors
        overlaps.append(overlap)

    return {
        "mean_overlap": np.mean(overlaps),
        "min_overlap": np.min(overlaps),
        "std_overlap": np.std(overlaps),
        "perfect_matches": sum(1 for o in overlaps if o == 1.0) / n,
    }


def fetch_ingredients(base_url: str) -> list:
    """Fetch all ingredients (not paginated)."""
    url = f"{base_url}/api/v1/ingredients"
    logger.info(f"Fetching {url}...")
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    logger.info(f"  Got {len(data)} ingredients")
    return data


def fetch_recipes_paginated(base_url: str, limit: int = 100) -> list:
    """Fetch all recipes with cursor-based pagination."""
    items = []
    cursor = None

    while True:
        url = f"{base_url}/api/v1/recipes/search?limit={limit}"
        if cursor:
            url += f"&cursor={cursor}"

        logger.info(f"Fetching recipes (cursor={'...' + cursor[-20:] if cursor else 'None'})...")
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        batch = data.get("recipes", [])
        if not batch:
            break

        items.extend(batch)
        logger.info(f"  Got {len(batch)} recipes (total: {len(items)})")

        # Check pagination - use cursor for next page
        pagination = data.get("pagination", {})
        if not pagination.get("has_next", False):
            break

        cursor = pagination.get("next_cursor")
        if not cursor:
            break

    return items


def load_data_from_api(api_base: str, use_cache: bool = False):
    """Load ingredient and recipe data from API."""
    CACHE_DIR.mkdir(exist_ok=True)
    ingredients_cache = CACHE_DIR / "ingredients.json"
    recipes_cache = CACHE_DIR / "recipes.json"

    # Try cache first
    if use_cache and ingredients_cache.exists() and recipes_cache.exists():
        logger.info("Loading from cache...")
        with open(ingredients_cache) as f:
            ingredients_raw = json.load(f)
        with open(recipes_cache) as f:
            recipes_raw = json.load(f)
    else:
        # Fetch from API
        logger.info(f"Fetching data from {api_base}...")

        # Get all ingredients (single request, not paginated)
        ingredients_raw = fetch_ingredients(api_base)

        # Get all recipes with ingredients (paginated)
        recipes_raw = fetch_recipes_paginated(api_base, limit=100)

        # Cache for next time
        with open(ingredients_cache, "w") as f:
            json.dump(ingredients_raw, f)
        with open(recipes_cache, "w") as f:
            json.dump(recipes_raw, f)
        logger.info(f"Cached data to {CACHE_DIR}")

    # Convert to DataFrames matching expected format
    ingredients_df = pd.DataFrame([
        {
            "ingredient_id": ing["id"],
            "ingredient_name": ing["name"],
            "ingredient_path": ing["path"],
            "substitution_level": 1.0,
            "allow_substitution": 1 if ing.get("allow_substitution") else 0,
        }
        for ing in ingredients_raw
    ])

    # Build recipe-ingredient rows with volume fractions
    recipe_rows = []
    for recipe in recipes_raw:
        recipe_id = recipe["id"]
        recipe_name = recipe["name"]

        # Calculate total volume for normalization
        total_volume = 0.0
        ingredient_volumes = []

        for ing in recipe.get("ingredients", []):
            amount = ing.get("amount", 1.0) or 1.0
            unit_name = (ing.get("unit_name") or "").lower()

            # Convert to ml (approximate)
            if unit_name in ("ounce", "oz"):
                volume_ml = amount * 30.0
            elif unit_name == "dash":
                volume_ml = amount * 1.0
            elif unit_name == "teaspoon":
                volume_ml = amount * 5.0
            elif unit_name == "tablespoon":
                volume_ml = amount * 15.0
            elif unit_name == "cup":
                volume_ml = amount * 240.0
            elif "top" in unit_name:
                volume_ml = 90.0
            elif "rinse" in unit_name:
                volume_ml = 5.0
            else:
                volume_ml = amount  # Assume ml or count

            ingredient_volumes.append({
                "ingredient_id": ing["ingredient_id"],
                "ingredient_name": ing["ingredient_name"],
                "ingredient_path": ing.get("ingredient_path", f"/{ing['ingredient_id']}/"),
                "volume_ml": volume_ml,
            })
            total_volume += volume_ml

        # Normalize to fractions
        for iv in ingredient_volumes:
            recipe_rows.append({
                "recipe_id": recipe_id,
                "recipe_name": recipe_name,
                "ingredient_id": iv["ingredient_id"],
                "ingredient_name": iv["ingredient_name"],
                "ingredient_path": iv["ingredient_path"],
                "volume_fraction": iv["volume_ml"] / total_volume if total_volume > 0 else 0.0,
            })

    recipes_df = pd.DataFrame(recipe_rows)

    logger.info(f"Loaded {len(ingredients_df)} ingredients, {recipes_df['recipe_id'].nunique()} recipes")
    return ingredients_df, recipes_df


def prepare_matrices(ingredients_df, recipes_df):
    """Build cost matrix and volume matrix from dataframes."""
    import numpy as np
    from barcart import (
        build_ingredient_tree,
        build_ingredient_distance_matrix,
        build_recipe_volume_matrix,
    )
    from barcart.rollup import create_rollup_mapping, apply_rollup_to_recipes

    # Build ingredient tree
    tree_dict, parent_map = build_ingredient_tree(
        ingredients_df,
        id_col='ingredient_id',
        name_col='ingredient_name',
        path_col='ingredient_path',
        weight_col='substitution_level',
    )

    # Rollup
    ingredients_df = ingredients_df.rename(columns={'ingredient_id': 'id'})
    rollup_map = create_rollup_mapping(
        ingredients_df, parent_map, allow_substitution_col='allow_substitution'
    )
    recipes_rolled_df = apply_rollup_to_recipes(
        recipes_df, rollup_map,
        ingredient_id_col='ingredient_id',
        volume_col='volume_fraction'
    )

    # Get unique ingredients after rollup
    unique_ingredients = set(recipes_rolled_df['ingredient_id'].unique())

    # Find ancestors
    ingredients_with_ancestors = set(['root'])
    for ing_id in unique_ingredients:
        current_id = str(ing_id)
        while current_id in parent_map and current_id != 'root':
            ingredients_with_ancestors.add(current_id)
            parent_id, _ = parent_map[current_id]
            if parent_id is None or parent_id == 'root':
                break
            current_id = parent_id

    filtered_parent_map = {
        child_id: (parent_id, cost)
        for child_id, (parent_id, cost) in parent_map.items()
        if child_id in ingredients_with_ancestors
    }

    id_to_name = {
        str(ing_id): name
        for ing_id, name in zip(ingredients_df['id'], ingredients_df['ingredient_name'])
        if str(ing_id) in ingredients_with_ancestors or ing_id in unique_ingredients
    }

    cost_matrix, ingredient_registry = build_ingredient_distance_matrix(
        filtered_parent_map, id_to_name
    )
    cost_matrix = cost_matrix.astype(np.float32)

    volume_matrix, recipe_registry = build_recipe_volume_matrix(
        recipes_rolled_df,
        ingredient_registry,
        recipe_id_col='recipe_id',
        ingredient_id_col='ingredient_id',
        volume_col='volume_fraction',
        sparse=True,
        dtype=np.float32,
    )

    logger.info(f"Cost matrix: {cost_matrix.shape}, Volume matrix: {volume_matrix.shape}")
    return cost_matrix, volume_matrix, ingredient_registry, recipe_registry


def run_full_em(volume_matrix, cost_matrix, n_ingredients, iters=5) -> EMResult:
    """Run standard full O(N²) EM."""
    from barcart import em_fit

    n_recipes = volume_matrix.shape[0]
    full_pairs = n_recipes * (n_recipes - 1) // 2

    logger.info(f"Running FULL EM ({full_pairs:,} pairs per iteration)...")
    t0 = time.time()

    dist, cost, log = em_fit(
        volume_matrix, cost_matrix, n_ingredients,
        iters=iters, verbose=True
    )

    elapsed = time.time() - t0
    return EMResult(
        distance_matrix=dist,
        cost_matrix=cost,
        elapsed_seconds=elapsed,
        pairs_computed=full_pairs * iters,
        k_value=None
    )


def run_constrained_em(volume_matrix, cost_matrix, n_ingredients, k, iters=5) -> EMResult:
    """Run constrained EM with top-k candidate selection."""
    logger.info(f"Running CONSTRAINED EM (k={k})...")
    t0 = time.time()

    dist, cost, log, total_pairs = constrained_em_fit(
        volume_matrix, cost_matrix, n_ingredients,
        k=k, iters=iters
    )

    elapsed = time.time() - t0
    return EMResult(
        distance_matrix=dist,
        cost_matrix=cost,
        elapsed_seconds=elapsed,
        pairs_computed=total_pairs,
        k_value=k
    )


def main():
    parser = argparse.ArgumentParser(description="Test constrained EM performance")
    parser.add_argument("--api", type=str, default="https://mixology.tools",
                        help="API base URL (default: https://mixology.tools)")
    parser.add_argument("--use-cache", action="store_true",
                        help="Use cached data from previous run")
    parser.add_argument("--iters", type=int, default=3, help="EM iterations")
    parser.add_argument("--k-values", type=str, default="50,100,200",
                        help="Comma-separated k values to test")
    parser.add_argument("--skip-full", action="store_true",
                        help="Skip full O(N²) baseline (for quick testing)")
    args = parser.parse_args()

    k_values = [int(k) for k in args.k_values.split(",")]

    # Load data from API
    ingredients_df, recipes_df = load_data_from_api(args.api, use_cache=args.use_cache)
    cost_matrix, volume_matrix, ingredient_registry, recipe_registry = prepare_matrices(
        ingredients_df, recipes_df
    )

    n_recipes = volume_matrix.shape[0]
    n_ingredients = len(ingredient_registry)
    full_pairs = n_recipes * (n_recipes - 1) // 2

    logger.info(f"\n{'='*60}")
    logger.info(f"DATASET: {n_recipes} recipes, {n_ingredients} ingredients")
    logger.info(f"FULL PAIRS: {full_pairs:,} per iteration")
    logger.info(f"{'='*60}\n")

    results: dict[str, EMResult] = {}

    # Run full EM baseline (unless skipped)
    if not args.skip_full:
        results["full"] = run_full_em(
            volume_matrix, cost_matrix, n_ingredients, iters=args.iters
        )
        logger.info(f"FULL EM: {results['full'].elapsed_seconds:.1f}s")

    # Run constrained EM for each k value
    for k in k_values:
        key = f"k={k}"
        results[key] = run_constrained_em(
            volume_matrix, cost_matrix, n_ingredients, k=k, iters=args.iters
        )
        logger.info(f"CONSTRAINED k={k}: {results[key].elapsed_seconds:.1f}s")

    # Compare results
    logger.info(f"\n{'='*60}")
    logger.info("RESULTS COMPARISON")
    logger.info(f"{'='*60}")

    for name, result in results.items():
        speedup = ""
        if "full" in results and name != "full":
            speedup = f" (speedup: {results['full'].elapsed_seconds / result.elapsed_seconds:.1f}x)"
        logger.info(f"{name:12s}: {result.elapsed_seconds:7.1f}s, {result.pairs_computed:,} pairs{speedup}")

    # Neighbor accuracy comparison
    if "full" in results:
        logger.info(f"\n{'='*60}")
        logger.info("NEIGHBOR ACCURACY (vs full computation)")
        logger.info(f"{'='*60}")

        for name, result in results.items():
            if name == "full":
                continue

            accuracy = compare_neighbor_accuracy(
                results["full"].distance_matrix,
                result.distance_matrix,
                k_neighbors=10
            )
            logger.info(
                f"{name:12s}: mean={accuracy['mean_overlap']:.1%}, "
                f"min={accuracy['min_overlap']:.1%}, "
                f"perfect={accuracy['perfect_matches']:.1%}"
            )

    # Cost matrix similarity
    if "full" in results:
        logger.info(f"\n{'='*60}")
        logger.info("COST MATRIX SIMILARITY")
        logger.info(f"{'='*60}")

        full_cost = results["full"].cost_matrix
        for name, result in results.items():
            if name == "full":
                continue

            # Frobenius norm of difference
            diff_norm = np.linalg.norm(result.cost_matrix - full_cost)
            full_norm = np.linalg.norm(full_cost)
            rel_diff = diff_norm / (full_norm + 1e-12)

            # Correlation
            corr = np.corrcoef(full_cost.flatten(), result.cost_matrix.flatten())[0, 1]

            logger.info(f"{name:12s}: rel_diff={rel_diff:.4f}, correlation={corr:.4f}")


if __name__ == "__main__":
    main()
