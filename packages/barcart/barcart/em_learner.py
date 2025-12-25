import os
import numpy as np
from tqdm.auto import tqdm

from barcart.distance import emd_matrix, expected_ingredient_match_matrix, m_step_blosum


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
) -> tuple[np.ndarray, np.ndarray, dict]:
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

    Returns
    -------
    distance_matrix : np.ndarray
        Final recipe-by-recipe EMD distance matrix of shape (n_recipes, n_recipes).
    new_cost_matrix : np.ndarray
        Learned ingredient-by-ingredient cost matrix of shape (n_ingredients, n_ingredients).
    log : dict
        Dictionary containing convergence history with key 'delta' (list of relative changes).

    Notes
    -----
    The algorithm alternates between:
    1. E-step: Compute EMD distances and extract transport plans between recipes
    2. M-step: Aggregate expected ingredient matches and update cost matrix via BLOSUM

    Convergence is determined by the relative Frobenius norm change in the cost matrix.

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
    logger.info(f"EM fit parallelization: detected {cpu_count} CPUs, using n_jobs={n_jobs}")

    log = {"delta": []}
    outer_bar = tqdm(
        range(iters), disable=not verbose, desc="EM fit", position=0, leave=False
    )
    for t in outer_bar:
        # Show only outer loop progress (convergence), not inner loop (recipe pairs)
        logger.info("EM iter %s RSS before E-step: %.1f MB", t + 1, _rss_mb())
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

        # Free plans memory before next iteration
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

    return distance_matrix, new_cost_matrix, log
