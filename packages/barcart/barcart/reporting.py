import numpy as np
import pandas as pd

from barcart.distance import knn_matrix
from barcart.registry import Registry


def report_neighbors(
    distance_matrix: np.ndarray,
    registry: "Registry",
    k: int,
) -> pd.DataFrame:
    """
    Report k nearest neighbors for each entity in the registry.

    Works for any entity type (ingredients, recipes, etc.) - the registry
    determines what entities are being compared.

    Parameters
    ----------
    distance_matrix : np.ndarray
        Pairwise distance matrix (n, n) where n = len(registry).
        For ingredients: typically tree-based cost matrix.
        For recipes: typically EMD-based distance matrix.
    registry : Registry
        Entity metadata registry with IDs and names.
    k : int
        Number of neighbors to report per entity (excluding self).

    Returns
    -------
    pd.DataFrame
        Columns: id, name, neighbor_id, neighbor_name, distance

        - id, name: The entity whose neighbors are being reported
        - neighbor_id, neighbor_name: The neighbor entity
        - distance: Distance value from the input matrix

    Examples
    --------
    >>> # Ingredient neighbors
    >>> cost_matrix, ingredient_registry = build_ingredient_distance_matrix(parent_map, id_to_name)
    >>> ingredient_neighbors = report_neighbors(cost_matrix, ingredient_registry, k=5)

    >>> # Recipe neighbors
    >>> volume_matrix, recipe_registry = build_recipe_volume_matrix(recipes_df, ingredient_registry)
    >>> emd_dist = emd_matrix(volume_matrix, cost_matrix)
    >>> recipe_neighbors = report_neighbors(emd_dist, recipe_registry, k=10)
    """

    # Validate matrix dimensions match registry
    registry.validate_matrix(distance_matrix)

    nn_idx, nn_dist = knn_matrix(distance_matrix, k)

    records: list[dict[str, str | float]] = []
    for idx in range(len(registry)):
        entity_id = registry.get_id(index=idx)
        entity_name = registry.get_name(index=idx)

        for neighbor_idx, dist in zip(nn_idx[idx], nn_dist[idx], strict=False):
            n_idx = int(neighbor_idx)
            neighbor_id = registry.get_id(index=n_idx)
            neighbor_name = registry.get_name(index=n_idx)

            records.append(
                {
                    "id": entity_id,
                    "name": entity_name,
                    "neighbor_id": neighbor_id,
                    "neighbor_name": neighbor_name,
                    "distance": float(dist),
                }
            )

    return pd.DataFrame.from_records(records)


def build_recipe_similarity(
    distance_matrix: np.ndarray,
    plans: dict[tuple[int, int], list[tuple[int, int, float, float]]],
    recipe_registry: "Registry",
    ingredient_registry: "Registry",
    k: int = 4,
    plan_topk: int = 3,
    candidate_pairs: set[tuple[int, int]] | None = None,
) -> list[dict[str, object]]:
    """Build recipe similarity entries with transport plan summaries."""
    recipe_registry.validate_matrix(distance_matrix)

    n_recipes = distance_matrix.shape[0]
    k = min(k, max(0, n_recipes - 1))
    nn_idx = None
    nn_dist = None

    if k > 0 and candidate_pairs is None:
        dmat = distance_matrix.copy()
        np.fill_diagonal(dmat, np.inf)
        nn_idx = np.argsort(dmat, axis=1)[:, :k]
        nn_dist = np.take_along_axis(dmat, nn_idx, axis=1)

    candidate_neighbors = None
    if candidate_pairs is not None:
        candidate_neighbors = {idx: [] for idx in range(n_recipes)}
        for i, j in candidate_pairs:
            candidate_neighbors[int(i)].append(int(j))
            candidate_neighbors[int(j)].append(int(i))

    results: list[dict[str, object]] = []
    for idx in range(n_recipes):
        recipe_id = int(recipe_registry.get_id(index=idx))
        recipe_name = recipe_registry.get_name(index=idx)
        neighbors: list[dict[str, object]] = []

        if k > 0 and candidate_neighbors is not None:
            neighbor_candidates = candidate_neighbors.get(idx, [])
            if neighbor_candidates:
                candidate_distances = [
                    (neighbor_idx, float(distance_matrix[idx, neighbor_idx]))
                    for neighbor_idx in neighbor_candidates
                ]
                candidate_distances.sort(key=lambda item: item[1])
                selected = candidate_distances[:k]
                for neighbor_idx, dist in selected:
                    neighbor_id = int(recipe_registry.get_id(index=neighbor_idx))
                    neighbor_name = recipe_registry.get_name(index=neighbor_idx)
                    i, j = (
                        (idx, neighbor_idx)
                        if idx < neighbor_idx
                        else (neighbor_idx, idx)
                    )
                    plan = plans.get((i, j), [])
                    plan_sorted = sorted(
                        plan, key=lambda item: item[2], reverse=True
                    )[:plan_topk]
                    transport_plan = [
                        {
                            "from_ingredient_id": int(
                                ingredient_registry.get_id(index=int(from_idx))
                            ),
                            "to_ingredient_id": int(
                                ingredient_registry.get_id(index=int(to_idx))
                            ),
                            "mass": float(amount),
                        }
                        for from_idx, to_idx, amount, _ in plan_sorted
                    ]

                    neighbors.append(
                        {
                            "neighbor_recipe_id": neighbor_id,
                            "neighbor_name": neighbor_name,
                            "distance": float(dist),
                            "transport_plan": transport_plan,
                        }
                    )
        elif k > 0 and nn_idx is not None and nn_dist is not None:
            for neighbor_idx, dist in zip(nn_idx[idx], nn_dist[idx], strict=False):
                neighbor_idx = int(neighbor_idx)
                neighbor_id = int(recipe_registry.get_id(index=neighbor_idx))
                neighbor_name = recipe_registry.get_name(index=neighbor_idx)
                i, j = (
                    (idx, neighbor_idx) if idx < neighbor_idx else (neighbor_idx, idx)
                )
                plan = plans.get((i, j), [])
                plan_sorted = sorted(
                    plan, key=lambda item: item[2], reverse=True
                )[:plan_topk]
                transport_plan = [
                    {
                        "from_ingredient_id": int(
                            ingredient_registry.get_id(index=int(from_idx))
                        ),
                        "to_ingredient_id": int(
                            ingredient_registry.get_id(index=int(to_idx))
                        ),
                        "mass": float(amount),
                    }
                    for from_idx, to_idx, amount, _ in plan_sorted
                ]

                neighbors.append(
                    {
                        "neighbor_recipe_id": neighbor_id,
                        "neighbor_name": neighbor_name,
                        "distance": float(dist),
                        "transport_plan": transport_plan,
                    }
                )

        results.append(
            {
                "recipe_id": recipe_id,
                "recipe_name": recipe_name,
                "neighbors": neighbors,
            }
        )

    return results
