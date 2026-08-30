import os
import numpy as np
from tqdm.auto import tqdm

from barcart.distance import (
    emd_matrix,
    emd_matrix_constrained,
    emd_candidates,
    expected_ingredient_match_matrix,
    manhattan_candidates,
    m_step_blosum,
)


def _rss_mb() -> float:
    """Best-effort RSS reporting for debugging."""
    try:
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except Exception:
        return -1.0


def _get_optimal_n_jobs() -> int:
    """
    Auto-detect optimal n_jobs for parallel EMD matrix computation.

    Detects available CPUs and reserves 1 for coordination overhead.
    Works automatically in Lambda based on memory allocation:
    - 1769 MB → 1 vCPU → returns 1 (sequential)
    - 3538 MB → 2 vCPUs → returns 1 (sequential)
    - 5307 MB → 3 vCPUs → returns 2 (parallel)
    - 10240 MB → 6 vCPUs → returns 5 (parallel)

    Returns:
        int: Optimal number of parallel jobs (minimum 1)
    """
    cpu_count = os.cpu_count()
    if cpu_count is None or cpu_count <= 1:
        return 1
    # Reserve 1 CPU for main thread coordination
    return max(1, cpu_count - 1)


class _DisabledTqdm:
    """A no-op tqdm replacement that disables progress bars."""
    def __init__(self, iterable, *args, **kwargs):
        self.iterable = iterable

    def __iter__(self):
        return iter(self.iterable)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def em_fit(
    volume_matrix: np.ndarray,
    previous_cost_matrix: np.ndarray,
    n_ingredients: int,
    iters: int = 100,
    tolerance: float = 1e-3,
    verbose: bool = False,
    n_jobs: int | None = None,
    candidate_k: int | None = 100,
    return_plans: bool = False,
) -> tuple[np.ndarray, np.ndarray, dict] | tuple[np.ndarray, np.ndarray, dict, dict]:
    """
    Run EM iterations to learn ingredient cost matrix from recipe data.

    This function implements an Expectation-Maximization (EM) algorithm to iteratively
    refine an ingredient cost matrix by analyzing recipe similarities. In each iteration,
    it computes Earth Mover's Distance (EMD) between recipes, aggregates expected ingredient
    matches from nearest neighbors, and updates the cost matrix using a BLOSUM-like log-odds
    approach.

    Parameters
    ----------
    volume_matrix : np.ndarray
        Recipe-by-ingredient volume matrix of shape (n_recipes, n_ingredients).
        Each row represents a recipe's ingredient composition.
    previous_cost_matrix : np.ndarray
        Initial ingredient-by-ingredient cost matrix of shape (n_ingredients, n_ingredients).
        Used as starting point for the EM algorithm.
    iters : int, optional
        Maximum number of EM iterations to run (default: 100).
    tolerance : float, optional
        Convergence threshold for relative change in cost matrix (default: 1e-3).
        Algorithm stops when relative change falls below this value.
    verbose : bool, optional
        If True, print progress information during iterations (default: False).
    n_jobs : int | None, optional
        Number of parallel jobs for EMD matrix computation (default: None).
        If None, auto-detects based on available CPUs (cpu_count - 1).
        Use 1 for sequential execution, >1 for parallel execution.
        Auto-detection adapts to Lambda memory allocation.
    candidate_k : int | None, optional
        Number of candidate neighbors per recipe for constrained EMD computation.
        If None, computes full O(N²) EMD matrix (slower but exact).
        Default is 100, which provides ~94% speedup with minimal accuracy loss.
        - Iteration 1: Uses Manhattan distance to select top-k candidates
        - Iterations 2+: Uses previous EMD distances to select top-k candidates

    Returns
    -------
    distance_matrix : np.ndarray
        Final recipe-by-recipe EMD distance matrix of shape (n_recipes, n_recipes).
        If candidate_k is set, non-candidate pairs will have value inf.
    new_cost_matrix : np.ndarray
        Learned ingredient-by-ingredient cost matrix of shape (n_ingredients, n_ingredients).
    log : dict
        Dictionary containing convergence history with key 'delta' (list of relative changes).
    plans : dict
        Transport plans from the final E-step, only returned if return_plans is True.

    Notes
    -----
    The algorithm alternates between:
    1. E-step: Compute EMD distances and extract transport plans between recipes
    2. M-step: Aggregate expected ingredient matches and update cost matrix via BLOSUM

    Convergence is determined by the relative Frobenius norm change in the cost matrix.

    When candidate_k is set, the algorithm uses constrained pair selection:
    - Iteration 1: Manhattan distance (cheap) selects top-k candidates per recipe
    - Iterations 2+: Previous EMD distances select top-k candidates per recipe
    This reduces computation from O(N²) to O(N*k) pairs per iteration.

    Examples
    --------
    >>> volume_matrix = np.array([[0.5, 0.3, 0.2], [0.4, 0.4, 0.2]])
    >>> initial_cost = np.eye(3)
    >>> dist_matrix, cost_matrix, log = em_fit(volume_matrix, initial_cost, iters=10)
    >>> print(f"Converged after {len(log['delta'])} iterations")
    """
    # Auto-detect optimal n_jobs if not specified
    if n_jobs is None:
        n_jobs = _get_optimal_n_jobs()

    progress_enabled = os.environ.get("EM_PROGRESS", "").lower() in {"1", "true", "yes"}
    if progress_enabled:
        verbose = True

    from scipy import sparse as sp

    if sp.issparse(volume_matrix):
        if volume_matrix.dtype != np.float32:
            volume_matrix = volume_matrix.astype(np.float32)
    else:
        volume_matrix = np.asarray(volume_matrix, dtype=np.float32)
    previous_cost_matrix = np.asarray(previous_cost_matrix, dtype=np.float32)

    # Log parallelization configuration for diagnostics
    import logging
    logger = logging.getLogger(__name__)
    cpu_count = os.cpu_count() or 1
    n_recipes = volume_matrix.shape[0]
    full_pairs = n_recipes * (n_recipes - 1) // 2

    if candidate_k is not None:
        constrained_pairs = n_recipes * candidate_k // 2  # Approximate unique pairs
        logger.info(
            f"EM fit: {n_recipes} recipes, candidate_k={candidate_k} "
            f"(~{constrained_pairs:,} pairs vs {full_pairs:,} full, "
            f"~{100 * (1 - constrained_pairs / full_pairs):.0f}% reduction)"
        )
    else:
        logger.info(f"EM fit: {n_recipes} recipes, full O(N²) mode ({full_pairs:,} pairs)")
    logger.info(f"EM fit parallelization: detected {cpu_count} CPUs, using n_jobs={n_jobs}")

    log = {"delta": []}
    outer_bar = tqdm(
        range(iters), disable=not verbose, desc="EM fit", position=0, leave=False
    )
    last_plans = None
    for t in outer_bar:
        # Show only outer loop progress (convergence), not inner loop (recipe pairs)
        logger.info("EM iter %s RSS before E-step: %.1f MB", t + 1, _rss_mb())

        # E-step: Compute EMD distances (constrained or full)
        if candidate_k is not None:
            # Constrained mode: compute EMD only for candidate pairs
            if t == 0:
                # First iteration: use Manhattan distance to select candidates
                logger.info("EM iter 1: selecting candidates via Manhattan distance (k=%d)", candidate_k)
                candidates = manhattan_candidates(volume_matrix, candidate_k)
            else:
                # Subsequent iterations: use previous EMD distances
                logger.info("EM iter %d: selecting candidates via previous EMD (k=%d)", t + 1, candidate_k)
                candidates = emd_candidates(distance_matrix, candidate_k)

            distance_matrix, plans = emd_matrix_constrained(
                volume_matrix,
                previous_cost_matrix,
                candidates,
                return_plans=True,
            )
        else:
            # Full O(N²) mode
            distance_matrix, plans = emd_matrix(
                volume_matrix,
                previous_cost_matrix,
                n_jobs=n_jobs,
                return_plans=True,
                tqdm_cls=tqdm if progress_enabled else _DisabledTqdm,
                tqdm_kwargs=None,
            )

        logger.info(
            "EM iter %s: plans=%s total_plan_entries=%s avg_entries=%.2f RSS after E-step: %.1f MB",
            t + 1,
            len(plans),
            sum(len(plan) for plan in plans.values()),
            (sum(len(plan) for plan in plans.values()) / max(1, len(plans))),
            _rss_mb(),
        )
        if distance_matrix.dtype != np.float32:
            distance_matrix = distance_matrix.astype(np.float32, copy=False)
        T_sum, n_pairs = expected_ingredient_match_matrix(
            distance_matrix,
            plans,
            n_ingredients,
            k=10,
            beta=1.0,
            plan_topk=3,
            plan_minfrac=0.05,
            symmetrize=True,
        )

        new_cost_matrix = m_step_blosum(T_sum)
        new_cost_matrix = new_cost_matrix.astype(np.float32, copy=False)

        if return_plans:
            last_plans = plans

        # Free plans memory before next iteration
        if not return_plans:
            del plans
        del T_sum
        import gc
        gc.collect()
        logger.info("EM iter %s RSS after gc: %.1f MB", t + 1, _rss_mb())

        # Convergence check
        num = np.linalg.norm(new_cost_matrix - previous_cost_matrix)
        den = np.linalg.norm(previous_cost_matrix) + 1e-12
        delta = num / den
        log["delta"].append(float(delta))
        previous_cost_matrix = new_cost_matrix.copy()

        if verbose:
            print(f"[iter {t + 1:02d}] pairs={n_pairs} delta={delta:.4e}")

        if delta < tolerance:
            if verbose:
                print("Converged.")
            break

    if return_plans:
        return distance_matrix, new_cost_matrix, log, (last_plans or {})
    return distance_matrix, new_cost_matrix, log
