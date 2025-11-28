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
