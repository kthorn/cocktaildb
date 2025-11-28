import numpy as np
from tqdm.auto import tqdm

from barcart.distance import emd_matrix, expected_ingredient_match_matrix, m_step_blosum


def em_fit(
    volume_matrix: np.ndarray,
    previous_cost_matrix: np.ndarray,
    n_ingredients: int,
    iters: int = 100,
    tolerance: float = 1e-3,
    verbose: bool = True,
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
        If True, print progress information during iterations (default: True).

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
    log = {"delta": []}
    outer_bar = tqdm(
        range(iters), disable=not verbose, desc="EM fit", position=0, leave=False
    )
    for t in outer_bar:
        distance_matrix, plans = emd_matrix(
            volume_matrix,
            previous_cost_matrix,
            return_plans=True,
            tqdm_cls=tqdm,
            tqdm_kwargs={"position": 1, "leave": False},
        )
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
