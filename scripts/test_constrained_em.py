#!/usr/bin/env python3
"""
Test script to evaluate constrained EM with different k values.

Compares constrained top-k EM settings and Manhattan distance to measure:
1. Runtime and memory proxies
2. Learned-cost and nearest-neighbor stability
3. HDBSCAN cluster coverage and adjusted agreement (ARI/AMI)
4. UMAP neighborhood and cluster preservation

Exact O(N²) EM is opt-in because of its runtime and transport-plan memory cost.

Usage:
    # Compare current, wider, and high-coverage candidate settings
    python scripts/test_constrained_em.py --use-cache --output-dir /tmp/em-benchmark

    # Tune UMAP after choosing a distance configuration
    python scripts/test_constrained_em.py \
        --tune-umap-matrix /tmp/em-benchmark/k-195.npz \
        --output-dir /tmp/umap-benchmark
"""

import argparse
import hashlib
import importlib.metadata
import json
import logging
import os
import resource
import statistics
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
    iterations_run: int
    process_peak_rss_mb: float


def compute_manhattan_candidates(
    volume_matrix: np.ndarray | sp.spmatrix,
    k: int,
) -> tuple[dict[int, np.ndarray], np.ndarray]:
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
                assert plans is not None
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


def complete_distance_matrix(distance_matrix: np.ndarray) -> np.ndarray:
    """Replace unknown distances with twice the largest computed distance."""
    completed = np.asarray(distance_matrix).copy()
    finite = completed[np.isfinite(completed)]
    replacement = float(finite.max() * 2) if finite.size else 0.0
    completed[~np.isfinite(completed)] = replacement
    return completed


def cluster_distance_matrix(
    distance_matrix: np.ndarray,
    min_cluster_size: int = 10,
    min_samples: int = 1,
) -> np.ndarray:
    """Find compact HDBSCAN clusters in a precomputed distance matrix."""
    from sklearn.cluster import HDBSCAN

    return HDBSCAN(
        metric="precomputed",
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        cluster_selection_method="leaf",
        n_jobs=-1,
    ).fit_predict(complete_distance_matrix(distance_matrix))


def summarize_clusters(distance_matrix: np.ndarray, labels: np.ndarray) -> dict:
    """Summarize HDBSCAN output without assuming any clusters exist."""
    from sklearn.metrics import silhouette_score

    clustered = labels >= 0
    cluster_ids, cluster_sizes = np.unique(labels[clustered], return_counts=True)
    return {
        "clusters": int(len(cluster_ids)),
        "clustered": int(clustered.sum()),
        "coverage": float(clustered.mean()),
        "noise": int((~clustered).sum()),
        "minimum_size": int(cluster_sizes.min()) if cluster_sizes.size else None,
        "median_size": float(np.median(cluster_sizes)) if cluster_sizes.size else None,
        "maximum_size": int(cluster_sizes.max()) if cluster_sizes.size else None,
        "silhouette": float(silhouette_score(
            distance_matrix[np.ix_(clustered, clustered)],
            labels[clustered],
            metric="precomputed",
        )) if len(cluster_ids) > 1 else None,
    }


def adjusted_cluster_agreement(left: np.ndarray, right: np.ndarray) -> dict:
    """Compare cluster labels, treating -1 as noise and also excluding it."""
    from sklearn.metrics import adjusted_mutual_info_score, adjusted_rand_score

    joint = (left >= 0) & (right >= 0)
    return {
        "ari_all": float(adjusted_rand_score(left, right)),
        "ami_all": float(adjusted_mutual_info_score(left, right)),
        "ari_joint": float(adjusted_rand_score(left[joint], right[joint])),
        "ami_joint": float(adjusted_mutual_info_score(left[joint], right[joint])),
        "jointly_clustered": int(joint.sum()),
    }


def neighborhood_preservation(
    source_distances: np.ndarray,
    embedding: np.ndarray,
    k: int,
) -> dict:
    """Measure local-neighbor recall, trustworthiness, and continuity."""
    from sklearn.metrics import pairwise_distances

    n = source_distances.shape[0]
    if source_distances.shape != (n, n) or embedding.shape[0] != n:
        raise ValueError("source distances and embedding must contain the same samples")
    if not 0 < k < n / 2:
        raise ValueError("trustworthiness requires 0 < k < n / 2")

    embedding_distances = pairwise_distances(embedding)
    source_distances = source_distances.copy()
    np.fill_diagonal(source_distances, np.inf)
    np.fill_diagonal(embedding_distances, np.inf)
    source_order = np.argsort(source_distances, axis=1, kind="stable")
    embedding_order = np.argsort(embedding_distances, axis=1, kind="stable")
    source_neighbors = source_order[:, :k]
    embedding_neighbors = embedding_order[:, :k]

    source_ranks = np.empty_like(source_order)
    embedding_ranks = np.empty_like(embedding_order)
    rows = np.arange(n)[:, None]
    source_ranks[rows, source_order] = np.arange(1, n + 1)
    embedding_ranks[rows, embedding_order] = np.arange(1, n + 1)

    recalls = []
    trust_penalty = 0
    continuity_penalty = 0
    for i in range(n):
        source_set = set(source_neighbors[i])
        embedding_set = set(embedding_neighbors[i])
        recalls.append(len(source_set & embedding_set) / k)
        trust_penalty += sum(source_ranks[i, j] - k for j in embedding_set - source_set)
        continuity_penalty += sum(
            embedding_ranks[i, j] - k for j in source_set - embedding_set
        )

    scale = 2 / (n * k * (2 * n - 3 * k - 1))
    return {
        "knn_recall": float(np.mean(recalls)),
        "trustworthiness": float(1 - scale * trust_penalty),
        "continuity": float(1 - scale * continuity_penalty),
    }


def run_umap_grid(
    distance_matrix: np.ndarray,
    neighbors: list[int],
    min_distances: list[float],
    seeds: list[int],
    neighborhood_sizes: list[int],
    cluster_min_size: int,
    cluster_min_samples: int,
) -> list[dict]:
    """Evaluate UMAP settings against source neighborhoods and clusters."""
    from barcart import compute_umap_embedding
    from sklearn.metrics import pairwise_distances, silhouette_score

    completed = complete_distance_matrix(distance_matrix)
    reference_labels = cluster_distance_matrix(
        completed,
        min_cluster_size=cluster_min_size,
        min_samples=cluster_min_samples,
    )
    reference_clustered = reference_labels >= 0
    results = []

    for n_neighbors in neighbors:
        for min_dist in min_distances:
            for seed in seeds:
                started = time.time()
                embedding_started = time.time()
                embedding = compute_umap_embedding(
                    completed,
                    n_neighbors=n_neighbors,
                    min_dist=min_dist,
                    random_state=seed,
                )
                embedding_seconds = time.time() - embedding_started
                embedding_distances = pairwise_distances(embedding)
                embedding_labels = cluster_distance_matrix(
                    embedding_distances,
                    min_cluster_size=cluster_min_size,
                    min_samples=cluster_min_samples,
                )
                neighborhoods = {
                    str(k): neighborhood_preservation(completed, embedding, k)
                    for k in neighborhood_sizes
                }
                cluster_agreement = adjusted_cluster_agreement(
                    reference_labels, embedding_labels
                )
                local_score = float(np.mean([
                    metric
                    for values in neighborhoods.values()
                    for metric in (
                        values["knn_recall"],
                        values["trustworthiness"],
                        values["continuity"],
                    )
                ]))
                reference_cluster_ids = np.unique(
                    reference_labels[reference_clustered]
                )
                reference_silhouette = (
                    float(silhouette_score(
                        embedding_distances[np.ix_(
                            reference_clustered, reference_clustered
                        )],
                        reference_labels[reference_clustered],
                        metric="precomputed",
                    ))
                    if len(reference_cluster_ids) > 1
                    else None
                )
                results.append({
                    "n_neighbors": n_neighbors,
                    "min_dist": min_dist,
                    "seed": seed,
                    "embedding_seconds": embedding_seconds,
                    "evaluation_seconds": time.time() - started - embedding_seconds,
                    "total_seconds": time.time() - started,
                    "local_preservation_score": local_score,
                    "neighborhoods": neighborhoods,
                    "cluster_agreement": cluster_agreement,
                    "reference_cluster_silhouette_in_embedding": reference_silhouette,
                })

    return results


def rank_umap_grid(results: list[dict]) -> list[dict]:
    """Rank UMAP settings by worst-seed stability, then median quality."""
    grouped: dict[tuple[int, float], list[dict]] = {}
    for result in results:
        key = (result["n_neighbors"], result["min_dist"])
        grouped.setdefault(key, []).append(result)

    summaries = []
    for (n_neighbors, min_dist), runs in grouped.items():
        silhouettes = [
            run["reference_cluster_silhouette_in_embedding"]
            for run in runs
            if run["reference_cluster_silhouette_in_embedding"] is not None
        ]
        summaries.append({
            "n_neighbors": n_neighbors,
            "min_dist": min_dist,
            "seed_count": len(runs),
            "seeds": sorted(run["seed"] for run in runs),
            "worst_local_preservation_score": min(
                run["local_preservation_score"] for run in runs
            ),
            "median_local_preservation_score": statistics.median(
                run["local_preservation_score"] for run in runs
            ),
            "median_reference_cluster_silhouette_in_embedding": (
                statistics.median(silhouettes) if silhouettes else None
            ),
            "median_ari_all": statistics.median(
                run["cluster_agreement"]["ari_all"] for run in runs
            ),
            "median_ami_all": statistics.median(
                run["cluster_agreement"]["ami_all"] for run in runs
            ),
        })

    return sorted(
        summaries,
        key=lambda result: (
            result["worst_local_preservation_score"],
            result["median_local_preservation_score"],
            result["median_reference_cluster_silhouette_in_embedding"] or -1,
            result["median_ami_all"],
        ),
        reverse=True,
    )


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


def build_manhattan_distance(recipes_df, recipe_registry) -> np.ndarray:
    """Build the unrolled Manhattan matrix in recipe-registry order."""
    from sklearn.metrics import pairwise_distances

    recipe_matrix = recipes_df.pivot_table(
        index="recipe_id",
        columns="ingredient_id",
        values="volume_fraction",
        aggfunc="sum",
        fill_value=0.0,
    )
    recipe_matrix.index = recipe_matrix.index.map(str)
    ordered_ids = [recipe_registry.get_id(index=i) for i in range(len(recipe_registry))]
    recipe_matrix = recipe_matrix.reindex(ordered_ids, fill_value=0.0)
    return pairwise_distances(recipe_matrix, metric="manhattan").astype(np.float32)


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
        iters=iters, verbose=True, candidate_k=None
    )

    elapsed = time.time() - t0
    return EMResult(
        distance_matrix=dist,
        cost_matrix=cost,
        elapsed_seconds=elapsed,
        pairs_computed=full_pairs * len(log["delta"]),
        k_value=None,
        iterations_run=len(log["delta"]),
        process_peak_rss_mb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
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
        k_value=k,
        iterations_run=len(log["delta"]),
        process_peak_rss_mb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Test constrained EM performance")
    parser.add_argument("--api", type=str, default="https://mixology.tools",
                        help="API base URL (default: https://mixology.tools)")
    parser.add_argument("--use-cache", action="store_true",
                        help="Use cached data from previous run")
    parser.add_argument("--iters", type=int, default=5, help="Maximum EM iterations")
    parser.add_argument("--k-values", type=str, default="293,391,780",
                        help="Comma-separated candidate counts to compare")
    parser.add_argument("--include-full", action="store_true",
                        help="Also run exact O(N²) EM (slow and memory intensive)")
    parser.add_argument("--cluster-min-size", type=int, default=10)
    parser.add_argument("--cluster-min-samples", type=int, default=1)
    parser.add_argument("--output-dir", type=Path,
                        help="Optional directory for matrices and JSON results")
    parser.add_argument("--tune-umap-matrix", type=Path,
                        help="Tune UMAP from a saved .npy or benchmark .npz matrix")
    parser.add_argument("--umap-neighbors", default="5,10,15,30,50")
    parser.add_argument("--umap-min-dists", default="0,0.01,0.05,0.1,0.25")
    parser.add_argument("--umap-seeds", default="0,1,42")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.tune_umap_matrix and args.include_full:
        parser.error("--include-full cannot be combined with --tune-umap-matrix")

    if args.tune_umap_matrix:
        saved = np.load(args.tune_umap_matrix)
        distance_matrix = (
            saved["distance_matrix"]
            if isinstance(saved, np.lib.npyio.NpzFile)
            else saved
        )
        umap_results = run_umap_grid(
            distance_matrix,
            neighbors=[int(value) for value in args.umap_neighbors.split(",")],
            min_distances=[float(value) for value in args.umap_min_dists.split(",")],
            seeds=[int(value) for value in args.umap_seeds.split(",")],
            neighborhood_sizes=[5, 10, 20],
            cluster_min_size=args.cluster_min_size,
            cluster_min_samples=args.cluster_min_samples,
        )
        ranked = rank_umap_grid(umap_results)
        for result in ranked[:10]:
            logger.info(
                "neighbors=%d min_dist=%.2f worst=%.3f median=%.3f silhouette=%s AMI=%.3f",
                result["n_neighbors"],
                result["min_dist"],
                result["worst_local_preservation_score"],
                result["median_local_preservation_score"],
                (
                    f'{result["median_reference_cluster_silhouette_in_embedding"]:.3f}'
                    if result["median_reference_cluster_silhouette_in_embedding"] is not None
                    else "n/a"
                ),
                result["median_ami_all"],
            )
        if args.output_dir:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            (args.output_dir / "umap-summary.json").write_text(
                json.dumps({
                    "source_matrix": str(args.tune_umap_matrix),
                    "source_sha256": hashlib.sha256(
                        args.tune_umap_matrix.read_bytes()
                    ).hexdigest(),
                    "completion_policy": "production-compatible imputed proxy: unknown distances become 2x the source matrix's maximum computed distance",
                    "software": {
                        package: importlib.metadata.version(package)
                        for package in ("numpy", "scikit-learn", "umap-learn")
                    },
                    "ranked_settings": ranked,
                    "results": umap_results,
                }, indent=2),
                encoding="utf-8",
            )
        return

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

    manhattan_started = time.time()
    manhattan_distances = build_manhattan_distance(recipes_df, recipe_registry)
    manhattan_seconds = time.time() - manhattan_started
    manhattan_peak_rss_mb = (
        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    )

    results: dict[str, EMResult] = {}

    # Exact EM is deliberately opt-in because it is slow and memory intensive.
    if args.include_full:
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

    reference_name = "full" if "full" in results else f"k={max(k_values)}"
    reference = results[reference_name]
    distance_matrices = {
        **{name: result.distance_matrix for name, result in results.items()},
        "manhattan": manhattan_distances,
    }
    labels = {
        name: cluster_distance_matrix(
            distances,
            min_cluster_size=args.cluster_min_size,
            min_samples=args.cluster_min_samples,
        )
        for name, distances in distance_matrices.items()
    }

    logger.info("\n%s", "=" * 60)
    logger.info("RESULTS COMPARISON (reference=%s)", reference_name)
    if not args.include_full:
        logger.warning(
            "%s is the widest-candidate proxy, not exact EM ground truth",
            reference_name,
        )
    logger.info("%s", "=" * 60)

    summary = {
        "reference": reference_name,
        "reference_kind": "exact" if args.include_full else "widest_candidate_proxy",
        "reference_warning": None if args.include_full else "Agreement with the widest candidate run is sensitivity analysis, not accuracy against ground truth.",
        "completion_policy": "production-compatible imputed proxy: unknown distances become 2x each matrix's maximum computed distance",
        "input": {
            "api": args.api,
            "used_cache": args.use_cache,
            "recipes": n_recipes,
            "ingredients_after_rollup": n_ingredients,
            "recipe_ids_sha256": hashlib.sha256("\n".join(
                recipe_registry.get_id(index=i) for i in range(len(recipe_registry))
            ).encode()).hexdigest(),
        },
        "software": {
            package: importlib.metadata.version(package)
            for package in ("numpy", "pandas", "scikit-learn", "umap-learn", "POT")
        },
        "exact_em_included": args.include_full,
        "cluster_min_size": args.cluster_min_size,
        "cluster_min_samples": args.cluster_min_samples,
        "results": {},
    }
    for name, distances in distance_matrices.items():
        completed = complete_distance_matrix(distances)
        result_labels = labels[name]
        cluster_stats = summarize_clusters(completed, result_labels)
        agreement = adjusted_cluster_agreement(labels[reference_name], result_labels)
        neighbor_metrics = {
            str(k): {
                key: float(value)
                for key, value in compare_neighbor_accuracy(
                    reference.distance_matrix,
                    distances,
                    k_neighbors=k,
                ).items()
            }
            for k in (10, 20, 50)
        }
        result_summary = {
            "clusters": cluster_stats,
            "agreement_with_reference": agreement,
            "neighbor_overlap_with_reference": neighbor_metrics,
            "unknown_distance_fraction": float((~np.isfinite(distances)).mean()),
        }
        if name in results:
            result = results[name]
            result_summary.update({
                "elapsed_seconds": result.elapsed_seconds,
                "pairs_computed": result.pairs_computed,
                "iterations_requested": args.iters,
                "iterations_run": result.iterations_run,
                "candidate_k": result.k_value,
                "process_peak_rss_mb_cumulative": result.process_peak_rss_mb,
            })
            cost_delta = np.linalg.norm(result.cost_matrix - reference.cost_matrix)
            result_summary["cost_relative_difference"] = float(
                cost_delta / (np.linalg.norm(reference.cost_matrix) + 1e-12)
            )
            result_summary["cost_correlation"] = float(np.corrcoef(
                result.cost_matrix.ravel(), reference.cost_matrix.ravel()
            )[0, 1])
        else:
            result_summary["elapsed_seconds"] = manhattan_seconds
            result_summary["pairs_computed"] = full_pairs
            result_summary["process_peak_rss_mb_cumulative"] = manhattan_peak_rss_mb

        summary["results"][name] = result_summary
        silhouette = cluster_stats["silhouette"]
        logger.info(
            "%s: clusters=%d coverage=%.1f%% silhouette=%s ARI=%.3f AMI=%.3f",
            name,
            cluster_stats["clusters"],
            cluster_stats["coverage"] * 100,
            f"{silhouette:.3f}" if silhouette is not None else "n/a",
            agreement["ari_all"],
            agreement["ami_all"],
        )

    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        recipe_ids = np.array([
            recipe_registry.get_id(index=i) for i in range(len(recipe_registry))
        ])
        ingredient_ids = np.array([
            ingredient_registry.get_id(index=i)
            for i in range(len(ingredient_registry))
        ])
        for name, result in results.items():
            np.savez_compressed(
                args.output_dir / f"{name.replace('=', '-')}.npz",
                distance_matrix=result.distance_matrix,
                cost_matrix=result.cost_matrix,
                labels=labels[name],
                recipe_ids=recipe_ids,
                ingredient_ids=ingredient_ids,
            )
        np.savez_compressed(
            args.output_dir / "manhattan.npz",
            distance_matrix=manhattan_distances,
            labels=labels["manhattan"],
            recipe_ids=recipe_ids,
        )
        (args.output_dir / "summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        logger.info("Wrote benchmark artifacts to %s", args.output_dir)


if __name__ == "__main__":
    main()
