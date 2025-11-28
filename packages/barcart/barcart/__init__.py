"""
Barcart: Backend code for cocktail analytics.

Provides tools for computing recipe and ingredient similarities using
hierarchical ingredient trees and Earth Mover's Distance.
"""

__version__ = "0.1.0"

from barcart.distance import (
    build_index_to_id,
    build_ingredient_distance_matrix,
    build_ingredient_tree,
    build_recipe_volume_matrix,
    compute_emd,
    emd_matrix,
    expected_ingredient_match_matrix,
    knn_matrix,
    m_step_blosum,
    neighbor_weight_matrix,
    weighted_distance,
)
from barcart.em_learner import em_fit
from barcart.registry import Registry
from barcart.reporting import report_neighbors

__all__ = [
    # Core types
    "Registry",
    # Tree building
    "build_ingredient_tree",
    # Distance computations
    "weighted_distance",
    "build_ingredient_distance_matrix",
    # Recipe analysis
    "build_recipe_volume_matrix",
    "compute_emd",
    "emd_matrix",
    # Neighborhood analysis
    "knn_matrix",
    "report_neighbors",
    "neighbor_weight_matrix",
    # Advanced analytics
    "expected_ingredient_match_matrix",
    "m_step_blosum",
    "em_fit",
    "build_index_to_id",
]
