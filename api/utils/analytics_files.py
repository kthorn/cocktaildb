"""Helpers for analytics file storage paths."""

from pathlib import Path
from typing import Any

from utils.analytics_cache import AnalyticsStorage

EM_DISTANCE_MATRIX_FILENAME = "recipe-distances-em.npy"
EM_INGREDIENT_DISTANCE_MATRIX_FILENAME = "ingredient-distances-em.npy"


def get_em_distance_matrix_path(storage_path: str) -> Path:
    """Return the file path for the EM recipe distance matrix."""
    storage = AnalyticsStorage(storage_path)
    return storage.storage_path / storage.storage_version / EM_DISTANCE_MATRIX_FILENAME


def save_em_distance_matrix(storage_path: str, distance_matrix: Any) -> Path:
    """Persist the EM recipe distance matrix to analytics storage."""
    import numpy as np

    file_path = get_em_distance_matrix_path(storage_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(file_path, distance_matrix)
    return file_path


def get_em_ingredient_distance_matrix_path(storage_path: str) -> Path:
    """Return the file path for the EM ingredient distance matrix."""
    storage = AnalyticsStorage(storage_path)
    return (
        storage.storage_path
        / storage.storage_version
        / EM_INGREDIENT_DISTANCE_MATRIX_FILENAME
    )


def save_em_ingredient_distance_matrix(storage_path: str, distance_matrix: Any) -> Path:
    """Persist the EM ingredient distance matrix to analytics storage."""
    import numpy as np

    file_path = get_em_ingredient_distance_matrix_path(storage_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(file_path, distance_matrix)
    return file_path
