import math
from typing import Any

import numpy as np
import ot
import pandas as pd
from tqdm.auto import tqdm

from barcart.registry import Registry


def build_ingredient_tree(
    df,
    id_col: str = "ingredient_id",
    name_col: str = "ingredient_name",
    path_col: str = "ingredient_path",
    weight_col: str = "substitution_level",
    root_id: str = "root",
    root_name: str = "root",
    default_edge_weight: float = 1.0,
) -> tuple[dict[str, Any], dict[str, tuple[str | None, float]]]:
    """
    Build a D3-compatible ingredient hierarchy tree and a parent map for weighted distances.

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame containing ingredient information, including IDs, names, hierarchical paths, and optional edge weights.
    id_col : str, default "ingredient_id"
        Name of the column containing ingredient node IDs.
    name_col : str, default "ingredient_name"
        Name of the column containing ingredient names.
    path_col : str, default "ingredient_path"
        Name of the column containing hierarchical ingredient paths (e.g., '/1/10/17/').
    weight_col : str, default "substitution_level"
        Name of the column specifying optional edge weights (between parent and child in the hierarchy).
    root_id : str, default "root"
        ID assigned to the artificial root node.
    root_name : str, default "root"
        Name assigned to the artificial root node.
    default_edge_weight : float, default 1.0
        Default substitution or edge weight if no value is found in the DataFrame.
        In particular, root to first child edge weight is default_edge_weight.

    Returns
    -------
    tree_dict : dict
        Nested dictionary representing the tree structure, suitable for D3 visualization. Each node has:
            - "id": str, node ID
            - "name": str, node or ingredient name
            - "children": list of child node dicts
            - each child node dict may include "edge_weight" (for the parent to child edge)
    parent_map : dict
        Mapping of node IDs (str) to tuples of (parent_id: Optional[str], edge_weight: float).
        For the root node, parent is None and edge_weight is 0.0.

    Examples
    --------
    >>> tree, parent_map = build_ingredient_tree(df)
    >>> root = tree['id']
    >>> parent_map[root]
    (None, 0.0)
    """
    # Pre-index names/weights by id (if present in df)
    name_by_id = {}
    weight_by_id = {}
    for _, row in df[[id_col, name_col, weight_col]].iterrows():
        cid = str(row[id_col])
        if cid not in name_by_id and isinstance(row[name_col], str):
            name_by_id[cid] = row[name_col]
        # weight applies to edge (parent -> this node)
        if row.get(weight_col) is not None and not (
            isinstance(row[weight_col], float) and math.isnan(row[weight_col])
        ):
            weight_by_id[cid] = float(row[weight_col])

    # Collect nodes and edges from paths
    nodes: dict[str, dict[str, Any]] = {}
    children_map: dict[str, set] = {}
    edge_w: dict[tuple[str, str], float] = {}
    parent_map: dict[str, tuple[str | None, float]] = {}

    def ensure_node(nid: str):
        if nid not in nodes:
            nodes[nid] = {"id": nid, "name": name_by_id.get(nid, nid)}
            children_map.setdefault(nid, set())

    # Create implicit root
    ensure_node(root_id)
    nodes[root_id]["name"] = root_name
    parent_map[root_id] = (None, 0.0)

    # Build structure from each path
    for _, row in df[[id_col, path_col]].iterrows():
        path = str(row[path_col]).strip()
        # split "/1/10/17/" -> ["1","10","17"]
        parts = [p for p in path.split("/") if p]
        if not parts:
            continue

        # Link root -> first
        prev = root_id
        for _idx, raw_id in enumerate(parts):
            nid = str(raw_id)
            ensure_node(nid)
            # connect prev -> nid
            if nid not in children_map[prev]:
                children_map[prev].add(nid)
            # assign edge weight (default first, overridden later if available)
            if (prev, nid) not in edge_w:
                edge_w[(prev, nid)] = default_edge_weight
            # set parent map if first time
            if nid not in parent_map:
                parent_map[nid] = (prev, edge_w[(prev, nid)])
            prev = nid

    # Now apply any specific weights from the df to override defaults
    # (weight is for edge parent->node; we need the immediate parent from parent_map)
    for child_id, (parent_id, _) in list(parent_map.items()):
        if parent_id is None:
            continue
        if child_id in weight_by_id:
            w = weight_by_id[child_id]
            edge_w[(parent_id, child_id)] = w
            parent_map[child_id] = (parent_id, w)

    # Build nested dict recursively for D3
    def build_subtree(pid: str) -> dict[str, Any]:
        node = {"id": pid, "name": nodes[pid]["name"]}
        kids = []
        for cid in children_map.get(pid, []):
            child = build_subtree(cid)
            # attach edge weight on the child (meaning parent->child)
            child["edge_weight"] = edge_w.get((pid, cid), default_edge_weight)
            kids.append(child)
        if kids:
            node["children"] = kids
        return node

    tree_dict = build_subtree(root_id)
    return tree_dict, parent_map


def weighted_distance(
    u: str | int,
    v: str | int,
    parent_map: dict[str, tuple[str | None, float]],
) -> float:
    """
    Compute the weighted distance between two nodes in a tree.

    The distance is defined as the sum of edge weights from node `u` to their
    lowest common ancestor (LCA) and from node `v` to the same LCA, using the
    `parent_map` produced by `build_tree_for_d3`.

    Parameters
    ----------
    u : str or int
        The node ID or name of the first node.
    v : str or int
        The node ID or name of the second node.
    parent_map : dict of str to tuple (str or None, float)
        Dictionary mapping each node (as a string) to its parent and the edge weight
        connecting it (parent_id, edge_weight). Root nodes have parent_id as None.

    Returns
    -------
    float
        Weighted distance between `u` and `v` along the tree structure.

    Raises
    ------
    KeyError
        If the two nodes do not share a common ancestor (i.e., the input is not a tree
        or the nodes are not connected in the tree).
    """
    # Normalize inputs to match parent_map keys (which are strings)
    u_key = str(u)
    v_key = str(v)
    # Ancestors of u with cumulative cost to reach them
    anc_cost = {}
    cur, acc = u_key, 0.0
    while cur is not None:
        anc_cost[cur] = acc
        p, w = parent_map.get(cur, (None, 0.0))
        cur, acc = p, acc + (w if p is not None else 0.0)

    # Walk up from v until we hit an ancestor of u
    cur, acc = v_key, 0.0
    while cur is not None:
        if cur in anc_cost:
            return anc_cost[cur] + acc
        p, w = parent_map.get(cur, (None, 0.0))
        cur, acc = p, acc + (w if p is not None else 0.0)

    raise KeyError(
        f"Nodes do not share a common ancestor (is it a tree?). u={u_key}, v={v_key}"
    )


def build_ingredient_distance_matrix(
    parent_map: dict[str, tuple[str | None, float]],
    id_to_name: dict[str | int, str],
    root_id: str = "root",
) -> tuple[np.ndarray, "Registry"]:
    """
    Build a pairwise distance matrix and ingredient registry together.

    Computes the weighted distance between every pair of nodes (ingredients) in the tree,
    using the parent_map produced by `build_ingredient_tree`. The registry and matrix
    are constructed atomically to ensure they stay in sync. The root node is excluded
    from the matrix as it is an implicit structural node, not an actual ingredient.

    Parameters
    ----------
    parent_map : dict of str to tuple (str or None, float)
        Dictionary mapping each node (ingredient ID as a string) to a tuple of (parent_id, edge_weight),
        where parent_id is the parent node ID (or None for the root),
        and edge_weight is the cost to reach that parent.
    id_to_name : dict of str or int to str
        Mapping from ingredient ID to human-readable name.
    root_id : str, default "root"
        ID of the root node to exclude from the matrix. Should match the root_id
        used in build_ingredient_tree.

    Returns
    -------
    distance_matrix : np.ndarray
        A symmetric 2D array of shape (n, n) where n is the number of non-root nodes.
        Each entry (i, j) is the weighted tree distance between nodes i and j.
    registry : Registry
        Metadata for the n ingredients (excluding root), guaranteed to match matrix dimensions.

    Notes
    -----
    The function relies on `weighted_distance` to compute tree distances.
    The registry is built from the same ingredient ordering as the matrix.
    The root node is excluded as it's an implicit structural element, not an ingredient.
    """
    from barcart.registry import Registry

    # Exclude root node from ingredient list
    ingredient_ids = [id for id in parent_map.keys() if id != root_id]
    id_to_index = {id: i for i, id in enumerate(ingredient_ids)}

    # Normalize id_to_name to use string keys (handles int/str mismatch)
    id_to_name_normalized = {str(k): v for k, v in id_to_name.items()}

    # Build registry immediately (same construction, guaranteed consistent)
    ingredients = [
        (idx, str(ing_id), str(id_to_name_normalized.get(str(ing_id), f"id:{ing_id}")))
        for ing_id, idx in id_to_index.items()
    ]
    registry = Registry(ingredients)

    # Build distance matrix
    distance_matrix = np.zeros((len(ingredient_ids), len(ingredient_ids)))
    for i in range(len(ingredient_ids)):
        for j in range(i + 1, len(ingredient_ids)):
            distance_matrix[i, j] = weighted_distance(
                ingredient_ids[i], ingredient_ids[j], parent_map
            )
            distance_matrix[j, i] = distance_matrix[i, j]
    return distance_matrix, registry


def build_recipe_volume_matrix(
    recipes_df: pd.DataFrame,
    ingredient_registry: "Registry",
    recipe_id_col: str = "recipe_id",
    recipe_name_col: str = "recipe_name",
    ingredient_id_col: str = "ingredient_id",
    volume_col: str = "volume_fraction",
    volume_error_tolerance: float = 1e-6,
    sparse: bool = False,
    dtype: np.dtype | type = float,
) -> tuple[np.ndarray, "Registry"]:
    """
    Construct a matrix of recipe ingredient volume fractions and recipe registry.

    Builds a matrix of shape (n_recipes, m_ingredients) where each entry [i, j] is
    the volume fraction of ingredient j in recipe i from the supplied DataFrame.
    Also constructs a Registry for the recipes, guaranteeing matrix and metadata
    stay in sync.

    Parameters
    ----------
    recipes_df : pd.DataFrame
        DataFrame containing at least recipe IDs, recipe names, ingredient IDs, and volume fractions.
    ingredient_registry : Registry
        Ingredient metadata registry providing ID to matrix index mapping.
    recipe_id_col : str, optional
        Column name for recipe IDs. Default is "recipe_id".
    recipe_name_col : str, optional
        Column name for recipe names. Default is "recipe_name".
    ingredient_id_col : str, optional
        Column name for ingredient IDs. Default is "ingredient_id".
    volume_col : str, optional
        Column name for the ingredient volume fraction in the recipe. Default is "volume_fraction".
    volume_error_tolerance : float, optional
        Tolerance for checking that all rows of volume_matrix sum to 1. Default is 1e-6.

    Returns
    -------
    volume_matrix : np.ndarray
        Array of shape (n_recipes, m_ingredients); entry [i, j] is the volume fraction of ingredient j in recipe i.
        Rows correspond to recipes as dictated by recipe_registry;
        columns to ingredients as dictated by the ingredient_registry.
    recipe_registry : Registry
        Recipe metadata registry, guaranteed to match volume_matrix dimensions.

    Raises
    ------
    ValueError
        If the volume fraction column is missing or contains NaNs.

    Notes
    -----
    If a recipe does not include an ingredient, the corresponding matrix entry will be zero.
    Each row sums to at most 1, depending on whether all ingredient fractions for a recipe are included.
    """
    # Validate presence of volume_fraction and ensure no NaNs
    if volume_col not in recipes_df.columns:
        raise ValueError("recipes_df must contain a 'volume_fraction' column")
    if recipes_df[volume_col].isna().any():
        raise ValueError(
            f"recipes_df['{volume_col}'] contains NaNs; please clean first"
        )

    # Build recipe registry
    recipe_ids = sorted(recipes_df[recipe_id_col].unique())
    recipe_id_to_index = {str(rid): i for i, rid in enumerate(recipe_ids)}

    # Extract recipe names (take first occurrence per recipe ID)
    recipe_names = {}
    for _, row in recipes_df[[recipe_id_col, recipe_name_col]].iterrows():
        rid = str(row[recipe_id_col])
        if rid not in recipe_names:
            recipe_names[rid] = str(row[recipe_name_col])

    # Construct Registry
    recipes = [
        (idx, rid, recipe_names.get(rid, f"Recipe {rid}"))
        for rid, idx in recipe_id_to_index.items()
    ]
    recipe_registry = Registry(recipes)

    # Build volume matrix
    if sparse:
        from scipy import sparse as sp

        row_idx = []
        col_idx = []
        data = []
        for _, row in recipes_df.iterrows():
            row_idx.append(recipe_id_to_index[str(row[recipe_id_col])])
            col_idx.append(
                ingredient_registry.get_index(id=str(row[ingredient_id_col]))
            )
            data.append(float(row[volume_col]))
        volume_matrix = sp.coo_matrix(
            (data, (row_idx, col_idx)),
            shape=(len(recipe_registry), len(ingredient_registry)),
            dtype=dtype,
        ).tocsr()
        volume_matrix.sum_duplicates()
    else:
        volume_matrix = np.zeros(
            (len(recipe_registry), len(ingredient_registry)), dtype=dtype
        )
        for _, row in recipes_df.iterrows():
            recipe_index = recipe_id_to_index[str(row[recipe_id_col])]
            ingredient_index = ingredient_registry.get_index(
                id=str(row[ingredient_id_col])
            )
            volume_matrix[recipe_index, ingredient_index] = float(row[volume_col])

    # Check that all rows of volume_matrix sum to 1 within numerical error
    row_sums = volume_matrix.sum(axis=1)
    row_sums = np.asarray(row_sums).ravel()
    if not np.allclose(row_sums, 1.0, atol=volume_error_tolerance):
        bad_rows = np.where(
            ~np.isclose(row_sums, 1.0, atol=volume_error_tolerance)
        )[0]
        bad_recipe_ids = [str(recipe_ids[i]) for i in bad_rows]
        raise ValueError(
            f"Not all rows of volume_matrix sum to 1. "
            f"Offending rows: {bad_rows}. \n"
            f"Row sums: {row_sums[bad_rows]}; recipe ids: {bad_recipe_ids}"
        )

    return volume_matrix, recipe_registry


def compute_emd(
    a: np.ndarray,
    b: np.ndarray,
    cost_matrix: np.ndarray,
    return_plan: bool = False,
    support_idx: np.ndarray | None = None,
    num_threads: int | str = 1,
) -> float | tuple[float, list[tuple[int, int, float, float]]]:
    """
    Compute the Earth Mover's Distance (EMD) between two distributions a and b.

    Parameters
    ----------
    a : np.ndarray
        Source distribution, shape (n,)
    b : np.ndarray
        Target distribution, shape (n,)
    cost_matrix : np.ndarray
        Cost matrix, shape (n, n)
    return_plan : bool, optional
        If True, also return the transport plan as a list of flows, by default False.
    support_idx : np.ndarray | None, optional
        Indices of the support of the distributions, shape (n,), by default None.
    num_threads : int | str, optional
        Number of threads to use for the computation, by default 1.
        Note: Multi-threading has significant overhead and is slower than single-threading
        for typical cocktail recipe problems. Use 1 for best performance.

    Returns
    -------
    distance : float
        The Earth Mover's Distance (total minimum cost) between the two distributions.
    transport_plan : list[tuple[int, int, float, float]]
        Only returned if return_plan is True.
        Each tuple is (from_idx, to_idx, amount, cost):
            - from_idx: Index in source a
            - to_idx: Index in target b
            - amount: mass transported (typically between 0 and 1)
            - cost: amount * per-unit cost for this flow
    """
    from scipy import sparse as sp

    n_ingredients = a.shape[1] if sp.issparse(a) else a.shape[0]
    b_len = b.shape[1] if sp.issparse(b) else len(b)
    if b_len != n_ingredients:
        raise ValueError(f"b must have {n_ingredients} ingredients")
    if cost_matrix.shape[0] != n_ingredients or cost_matrix.shape[1] != n_ingredients:
        raise ValueError(
            f"cost_matrix must be of shape ({n_ingredients}, {n_ingredients})"
        )

    # Reduce to the union of supports to dramatically shrink problem size
    if support_idx is None:
        if sp.issparse(a) or sp.issparse(b):
            a_idx = a.indices if sp.issparse(a) else np.nonzero(a > 0)[0]
            b_idx = b.indices if sp.issparse(b) else np.nonzero(b > 0)[0]
            support_idx = np.union1d(a_idx, b_idx)
        else:
            support_idx = np.nonzero((a > 0) | (b > 0))[0]

    if support_idx.size == 0:
        return 0.0 if not return_plan else (0.0, [])

    # Extract subsets and ensure float32 to reduce memory and match cost_matrix dtype
    target_dtype = cost_matrix.dtype
    if sp.issparse(a):
        a_sub = a[:, support_idx].toarray().ravel().astype(target_dtype, copy=False)
    else:
        a_sub = np.asarray(a[support_idx], dtype=target_dtype)
    if sp.issparse(b):
        b_sub = b[:, support_idx].toarray().ravel().astype(target_dtype, copy=False)
    else:
        b_sub = np.asarray(b[support_idx], dtype=target_dtype)
    cost_sub = cost_matrix[np.ix_(support_idx, support_idx)]

    if not return_plan:
        # Use ot.emd2 when only the objective value is needed (faster than full plan)
        distance = float(ot.emd2(a_sub, b_sub, cost_sub, numThreads=num_threads))
        return distance
    else:
        transport_matrix = ot.emd(a_sub, b_sub, cost_sub, numThreads=num_threads)
        distance = float(np.sum(transport_matrix * cost_sub))

        # Vectorized extraction of sparse transport plan (much faster than Python loop)
        rows, cols = np.nonzero(transport_matrix > 1e-10)
        flows = transport_matrix[rows, cols]
        flow_costs = flows * cost_sub[rows, cols]

        # Map back to original indices and convert to list of tuples
        transport_plan = list(
            zip(
                support_idx[rows].astype(int).tolist(),
                support_idx[cols].astype(int).tolist(),
                flows.astype(float).tolist(),
                flow_costs.astype(float).tolist(),
            )
        )

        return distance, transport_plan


def emd_matrix(
    volume_matrix: np.ndarray,
    cost_matrix: np.ndarray,
    n_jobs: int = 1,
    return_plans: bool = False,
    *,
    tqdm_cls: Any | None = None,
    tqdm_kwargs: dict[str, Any] | None = None,
) -> np.ndarray:
    """
    Compute the Earth Mover's Distance matrix between all recipes in the volume matrix.

    If return_plans is True, also return a dict mapping (i, j) with i < j to the
    sparse transport plan as a list of (from_idx, to_idx, amount, cost) in global
    ingredient indices.
    """
    from scipy import sparse as sp

    n_recipes = volume_matrix.shape[0]
    emd_dtype = cost_matrix.dtype
    emd_matrix = np.zeros((n_recipes, n_recipes), dtype=emd_dtype)

    is_sparse = sp.issparse(volume_matrix)

    # Precompute supports for each recipe to avoid repeated nonzero scans
    if is_sparse:
        supports = [volume_matrix.getrow(i).indices for i in range(n_recipes)]
    else:
        supports = [np.nonzero(volume_matrix[i] > 0)[0] for i in range(n_recipes)]

    if n_jobs == 1:
        plans = {} if return_plans else None
        _tqdm = tqdm_cls if tqdm_cls is not None else tqdm
        _tk = {"desc": "Computing EMD matrix"}
        if tqdm_kwargs:
            _tk.update(tqdm_kwargs)
        for i in _tqdm(range(n_recipes), **_tk):
            for j in range(i + 1, n_recipes):
                union_idx = np.union1d(supports[i], supports[j])
                row_i = volume_matrix.getrow(i) if is_sparse else volume_matrix[i]
                row_j = volume_matrix.getrow(j) if is_sparse else volume_matrix[j]
                if return_plans:
                    distance, plan = compute_emd(
                        row_i,
                        row_j,
                        cost_matrix,
                        return_plan=True,
                        support_idx=union_idx,
                    )
                    plans[(i, j)] = plan
                else:
                    distance = compute_emd(
                        row_i,
                        row_j,
                        cost_matrix,
                        return_plan=False,
                        support_idx=union_idx,
                    )
                emd_matrix[i, j] = emd_dtype.type(distance)
                emd_matrix[j, i] = emd_dtype.type(distance)
        return (emd_matrix, plans) if return_plans else emd_matrix

    # Parallel path (shared memory threads to avoid copying large matrices)
    try:
        from joblib import Parallel, delayed
    except ImportError:
        # Fallback to sequential if joblib is not available
        plans = {} if return_plans else None
        _tqdm = tqdm_cls if tqdm_cls is not None else tqdm
        _tk = {"desc": "Computing EMD matrix"}
        if tqdm_kwargs:
            _tk.update(tqdm_kwargs)
        for i in _tqdm(range(n_recipes), **_tk):
            for j in range(i + 1, n_recipes):
                union_idx = np.union1d(supports[i], supports[j])
                row_i = volume_matrix.getrow(i) if is_sparse else volume_matrix[i]
                row_j = volume_matrix.getrow(j) if is_sparse else volume_matrix[j]
                if return_plans:
                    distance, plan = compute_emd(
                        row_i,
                        row_j,
                        cost_matrix,
                        return_plan=True,
                        support_idx=union_idx,
                    )
                    plans[(i, j)] = plan
                else:
                    distance = compute_emd(
                        row_i,
                        row_j,
                        cost_matrix,
                        return_plan=False,
                        support_idx=union_idx,
                    )
                emd_matrix[i, j] = emd_dtype.type(distance)
                emd_matrix[j, i] = emd_dtype.type(distance)
        return (emd_matrix, plans) if return_plans else emd_matrix

    # Log parallel execution configuration
    import logging

    logger = logging.getLogger(__name__)
    n_pairs = n_recipes * (n_recipes - 1) // 2
    logger.info(
        f"Computing EMD matrix: {n_recipes} recipes ({n_pairs} pairs) with n_jobs={n_jobs}"
    )

    pairs: list[tuple[int, int]] = [
        (i, j) for i in range(n_recipes) for j in range(i + 1, n_recipes)
    ]

    def _pair_distance_or_plan(i: int, j: int):
        union_idx = np.union1d(supports[i], supports[j])
        row_i = volume_matrix.getrow(i) if is_sparse else volume_matrix[i]
        row_j = volume_matrix.getrow(j) if is_sparse else volume_matrix[j]
        if return_plans:
            d, plan = compute_emd(
                row_i,
                row_j,
                cost_matrix,
                return_plan=True,
                support_idx=union_idx,
            )
            return i, j, float(d), plan
        else:
            d = compute_emd(
                row_i,
                row_j,
                cost_matrix,
                return_plan=False,
                support_idx=union_idx,
            )
            return i, j, float(d)

    results = Parallel(n_jobs=n_jobs, prefer="threads", require="sharedmem")(
        delayed(_pair_distance_or_plan)(i, j) for (i, j) in pairs
    )
    plans = {} if return_plans else None
    for item in results:
        if return_plans:
            i, j, d, plan = item
            plans[(i, j)] = plan
        else:
            i, j, d = item
        emd_matrix[i, j] = emd_dtype.type(d)
        emd_matrix[j, i] = emd_dtype.type(d)
    return (emd_matrix, plans) if return_plans else emd_matrix


def knn_matrix(
    distance_matrix: np.ndarray,
    k: int,
) -> np.ndarray:
    """
    Compute the k-nearest neighbors (kNN) indices and distances from a distance matrix.

    Given a symmetric pairwise distance matrix, this function finds the indices and
    corresponding distances of the k nearest neighbors (excluding self) for each row.

    Parameters
    ----------
    distance_matrix : np.ndarray
        A 2D array of shape (n, n) representing pairwise distances, where n is the number of samples.
    k : int
        The number of nearest neighbors to select for each item.

    Returns
    -------
    nn_idx : np.ndarray
        Array of shape (n, k) with indices of the k nearest neighbors for each item.
    nn_dist : np.ndarray
        Array of shape (n, k) with the distances to the k nearest neighbors for each item.

    Notes
    -----
    The diagonal (self-distances) and any non-finite values (NaN/-Inf) are replaced with +Inf
    so they are not selected as neighbors. The neighbor selection uses `np.argsort`;
    in the case of ties, the order is determined by the index order.
    """
    dmat = distance_matrix.copy()
    # Replace diagonal, NaN/-Inf with +Inf so they sort to the end
    np.fill_diagonal(dmat, np.inf)
    non_finite_mask = ~np.isfinite(dmat)
    if non_finite_mask.any():
        dmat[non_finite_mask] = np.inf
    nn_idx = np.argsort(dmat, axis=1)[:, :k]
    nn_dist = np.take_along_axis(dmat, nn_idx, axis=1)
    return nn_idx, nn_dist


def build_index_to_id(id_to_index: dict[str, int]) -> list[str]:
    """
    Build a list mapping matrix index -> ingredient ID (as str) from id_to_index.

    Parameters
    ----------
    id_to_index : dict[str, int]
        Mapping from ingredient ID (string) to its column/row index in a matrix.

    Returns
    -------
    list[str]
        List where position i gives the ingredient ID (as string) at matrix index i.
    """
    index_to_id = [""] * len(id_to_index)
    for ingredient_id, idx in id_to_index.items():
        index_to_id[int(idx)] = str(ingredient_id)
    return index_to_id


def neighbor_weight_matrix(
    distance_matrix: np.ndarray,
    k: int,
    beta: float,
    symmetrize: bool = True,
) -> tuple[np.ndarray, int]:
    """
    Build a neighbor-weighted matrix from a pairwise distance matrix using kNN.

    For each row r, pick its k nearest neighbors s with distances d_{rs},
    compute Boltzmann weights w_{rs} ∝ exp(-beta * (d_{rs} - min_s d_{rs})),
    and accumulate into a weight matrix W[r, s] += w_{rs}. Optionally symmetrize
    at the end via 0.5*(W + W.T).

    Parameters
    ----------
    distance_matrix : np.ndarray
        Precomputed pairwise distances between items (n x n), with zeros on the diagonal.
    k : int
        Number of nearest neighbors per item.
    beta : float
        Inverse temperature controlling sharpness of weights. Larger -> more focus on close neighbors.
    symmetrize : bool, default True
        If True, returns a symmetric matrix 0.5*(W + W.T).

    Returns
    -------
    W : np.ndarray
        Neighbor-weighted matrix of shape (n, n). If symmetrize=True, W is symmetric.
    N_pairs : int
        Number of directed neighbor pairs accumulated (n * k).
    """
    n = distance_matrix.shape[0]
    nn_idx, nn_dist = knn_matrix(distance_matrix, k)

    W = np.zeros_like(distance_matrix, dtype=distance_matrix.dtype)
    for r in range(n):
        d = nn_dist[r]
        # Boltzmann weights per row, stabilized by subtracting min
        w = np.exp(-beta * (d - d.min()))
        w /= w.sum() + 1e-12
        for w_rs, s in zip(w, nn_idx[r], strict=False):
            W[r, int(s)] += float(w_rs)

    if symmetrize:
        W = 0.5 * (W + W.T)

    return W, int(n * k)


### M-step code ###


def _sparsify_transport_plan(
    plan: list[tuple[int, int, float, float]],
    topk: int | None,
    min_fraction_of_max: float,
) -> list[tuple[int, int, float, float]]:
    """
    Keep only the largest transport flows by amount.

    Parameters
    ----------
    plan : list of tuples (i, j, amount, cost)
        Transport plan entries restricted to the support union.
    topk : int or None
        If provided, keep at most this many largest flows by amount.
    min_fraction_of_max : float
        Additionally keep any flow with amount >= min_fraction_of_max * max(amount).

    Returns
    -------
    list
        Filtered plan entries.
    """
    if not plan:
        return plan
    # Sort by amount descending
    sorted_plan = sorted(plan, key=lambda x: x[2], reverse=True)
    max_amount = sorted_plan[0][2]
    thresh = max_amount * float(min_fraction_of_max)
    filtered = [p for p in sorted_plan if p[2] >= thresh]
    if topk is not None and topk > 0:
        filtered = filtered[:topk]
    return filtered


def expected_ingredient_match_matrix(
    distance_matrix: np.ndarray,
    plans: dict[tuple[int, int], list[tuple[int, int, float, float]]],
    n_ingredients: int,
    k: int,
    beta: float,
    plan_topk: int | None = None,
    plan_minfrac: float = 0.0,
    symmetrize: bool = True,
) -> tuple[np.ndarray, int]:
    """
    Aggregate expected ingredient match counts (T_sum) from kNN recipe pairs.

    For each recipe r, pick its k nearest neighbor recipes under EMD with the
    provided ingredient cost_matrix, compute Boltzmann weights over neighbors,
    extract transport plans for (r, s), and accumulate weighted flows into an
    ingredient-by-ingredient count matrix T_sum.

    Parameters
    ----------
    distance_matrix : np.ndarray
        Array of shape (n_recipes, n_recipes) with pairwise distances between recipes.
    plans : dict[tuple[int, int], list[tuple[int, int, float, float]]]
        Transport plans between all recipe pairs.
    n_ingredients : int
        Number of ingredients.
    k : int
        Number of nearest neighbors per recipe.
    beta : float
        Inverse temperature for Boltzmann weights over neighbor distances.
    plan_topk : int, optional
        If set, keep at most this many largest flows per transport plan.
    plan_minfrac : float, default 0.0
        Additionally keep flows with amount >= plan_minfrac * max_flow.
    symmetrize : bool, default True
        If True, symmetrize the resulting T_sum via 0.5*(T_sum + T_sum.T).

    Returns
    -------
    T_sum : np.ndarray
        Ingredient-by-ingredient expected match counts, shape (m, m).
    N_pairs : int
        Number of directed neighbor pairs accumulated (n_recipes * k).
    """
    n_recipes = distance_matrix.shape[0]
    nn_idx, nn_dist = knn_matrix(distance_matrix, max(1, min(k, n_recipes - 1)))

    T_sum = np.zeros((n_ingredients, n_ingredients), dtype=distance_matrix.dtype)
    for r in range(n_recipes):
        d = nn_dist[r]
        # Boltzmann weights per row, stabilized by subtracting min
        w = np.exp(-beta * (d - d.min()))
        z = float(w.sum())
        if z > 0:
            w /= z
        for w_rs, s in zip(w, nn_idx[r], strict=False):
            i, j = (r, int(s)) if r < int(s) else (int(s), r)
            plan = plans.get((i, j), [])
            if plan_topk is not None or plan_minfrac > 0:
                plan = _sparsify_transport_plan(plan, plan_topk, plan_minfrac)
            for ii, jj, amount, _ in plan:
                T_sum[int(ii), int(jj)] += float(w_rs) * float(amount)

    if symmetrize:
        T_sum = 0.5 * (T_sum + T_sum.T)

    return T_sum, int(n_recipes * max(1, min(k, n_recipes - 1)))


def _median_rescale(cost_matrix: np.ndarray, target: float = 1.0) -> np.ndarray:
    mask = ~np.eye(cost_matrix.shape[0], dtype=bool)
    med = np.median(cost_matrix[mask])
    scale = (med / (target + 1e-12)) if med > 0 else 1.0
    return cost_matrix / (scale + 1e-12)


def m_step_blosum(
    T_sum: np.ndarray,
    blosum_alpha: float = 1.0,
    median_target: float = 1.0,
) -> np.ndarray:
    """
    Perform a BLOSUM-like log-odds update, converting expected matches to a cost matrix.

    This function updates a cost matrix using expected match counts (T_sum) in a way analogous
    to how BLOSUM substitution matrices are computed. Expected row and column marginals are
    estimated under independence, Laplace smoothing is applied, and the log-ratio is taken.
    The result is stabilized by blending with a prior and applying exponential moving average (EMA).
    Cost constraints (symmetry, zero diagonal, clamping) and median rescaling are enforced.

    Parameters
    ----------
    T_sum : np.ndarray
        Ingredient-by-ingredient expected match counts, shape (m, m). Do not pass
        a recipe-by-recipe matrix here.
    blosum_alpha : float
        Laplace smoothing parameter (pseudo-counts).
    median_target : float, optional
        Value to which the median off-diagonal entry is scaled (defaults to 1.0).

    Returns
    -------
    np.ndarray
        The updated, projected, and rescaled cost matrix.
    """
    N = T_sum.copy()
    # Laplace smoothing
    alpha = blosum_alpha
    total = N.sum()
    row = N.sum(axis=1, keepdims=True)
    col = N.sum(axis=0, keepdims=True)
    # Expected under independence
    E = ((row + alpha * N.shape[0]) @ (col + alpha * N.shape[0])) / (
        total + alpha * N.size
    )
    S = (N + alpha) / (E + 1e-12)
    C_new = -np.log(S + 1e-12)
    C_new = C_new - C_new.min()
    np.fill_diagonal(C_new, 0.0)

    # Prior blend and EMA smoothing (stability)
    # C_out = (1.0 - prior_blend) * C_new + prior_blend * cost_matrix

    # Keep scale consistent
    C_new = _median_rescale(C_new, median_target)
    return C_new


def compute_umap_embedding(
    distance_matrix: np.ndarray,
    n_components: int = 2,
    n_neighbors: int = 15,
    min_dist: float = 0.01,
    random_state: int | None = None,
) -> np.ndarray:
    """
    Compute UMAP embedding from a precomputed distance matrix.

    Uses UMAP (Uniform Manifold Approximation and Projection) for dimensionality
    reduction, projecting high-dimensional distance relationships into a lower-dimensional
    space while preserving local and global structure.

    Parameters
    ----------
    distance_matrix : np.ndarray
        Precomputed pairwise distance matrix of shape (n_samples, n_samples).
        Should be symmetric with zeros on the diagonal.
    n_components : int, default 2
        Number of dimensions in the embedded space.
    n_neighbors : int, default 5
        Number of neighboring points used in local approximations of manifold structure.
        Larger values result in more global views, smaller values more local.
    min_dist : float, default 0.05
        Minimum distance between points in the embedded space. Controls how tightly
        UMAP packs points together.
    random_state : int or None, default None
        Random seed for reproducibility.

    Returns
    -------
    np.ndarray
        Embedded coordinates of shape (n_samples, n_components).

    Notes
    -----
    The distance matrix is used with metric='precomputed' in UMAP, meaning the
    input is treated as pairwise distances rather than raw feature vectors.
    """
    import umap

    reducer = umap.UMAP(
        n_neighbors=n_neighbors,
        min_dist=min_dist,
        n_components=n_components,
        metric="precomputed",
        random_state=random_state,
    )

    embedding = reducer.fit_transform(distance_matrix)
    return embedding
