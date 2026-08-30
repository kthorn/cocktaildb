"""Focused tests for the cocktail-space benchmark metrics."""

import numpy as np
import pandas as pd
import pytest

from scripts.test_constrained_em import (
    adjusted_cluster_agreement,
    build_manhattan_distance,
    build_parser,
    cluster_distance_matrix,
    complete_distance_matrix,
    constrained_em_fit,
    neighborhood_preservation,
    rank_umap_grid,
    run_full_em,
    run_umap_grid,
    summarize_clusters,
)


def test_exact_em_is_opt_in_and_candidate_grid_uses_current_wider_proxy():
    args = build_parser().parse_args([])

    assert args.include_full is False
    assert args.k_values == "293,391,780"
    assert args.cluster_min_size == 10
    assert args.cluster_min_samples == 1
    assert args.output_dir is None
    assert args.tune_umap_matrix is None
    assert args.umap_neighbors == "5,10,15,30,50"
    assert args.umap_min_dists == "0,0.01,0.05,0.1,0.25"
    assert args.umap_seeds == "0,1,42"


def test_complete_distance_matrix_replaces_unknown_pairs():
    distances = np.array(
        [
            [0.0, 1.0, np.inf],
            [1.0, 0.0, 2.0],
            [np.inf, 2.0, 0.0],
        ]
    )

    completed = complete_distance_matrix(distances)

    assert completed[0, 2] == 4.0
    assert completed[2, 0] == 4.0
    assert np.isfinite(completed).all()


def test_cluster_distance_matrix_finds_separated_compact_groups():
    distances = np.full((12, 12), 10.0)
    distances[:6, :6] = 0.1
    distances[6:, 6:] = 0.1
    np.fill_diagonal(distances, 0.0)

    labels = cluster_distance_matrix(distances, min_cluster_size=5, min_samples=1)

    assert len(set(labels) - {-1}) == 2
    assert -1 not in labels


def test_build_manhattan_distance_uses_recipe_registry_order():
    recipes = pd.DataFrame(
        [
            {"recipe_id": 2, "ingredient_id": 10, "volume_fraction": 0.5},
            {"recipe_id": 2, "ingredient_id": 11, "volume_fraction": 0.5},
            {"recipe_id": 1, "ingredient_id": 10, "volume_fraction": 1.0},
        ]
    )

    class Registry:
        def __len__(self):
            return 2

        def get_id(self, *, index):
            return str([1, 2][index])

    result = build_manhattan_distance(recipes, Registry())

    assert result.dtype == np.float32
    assert result.tolist() == [[0.0, 1.0], [1.0, 0.0]]


def test_constrained_full_candidate_matches_exact_em_smoothing():
    volume = np.array(
        [
            [0.8, 0.2],
            [0.3, 0.7],
            [0.5, 0.5],
        ],
        dtype=np.float32,
    )
    cost = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.float32)

    exact = run_full_em(volume, cost, n_ingredients=2, iters=1)
    _distance, constrained_cost, _log, _pairs = constrained_em_fit(
        volume, cost, n_ingredients=2, k=2, iters=1
    )

    assert constrained_cost == pytest.approx(exact.cost_matrix)


def test_run_full_em_disables_candidate_filtering(monkeypatch):
    def fake_em_fit(volume, cost, n_ingredients, **kwargs):
        assert kwargs["candidate_k"] is None
        return np.zeros((2, 2), dtype=np.float32), cost, {"delta": [0.0]}

    monkeypatch.setattr("barcart.em_fit", fake_em_fit)
    volume = np.eye(2, dtype=np.float32)
    cost = np.zeros((2, 2), dtype=np.float32)

    result = run_full_em(volume, cost, n_ingredients=2, iters=1)

    assert result.k_value is None
    assert result.iterations_run == 1
    assert result.process_peak_rss_mb > 0


def test_adjusted_cluster_agreement_reports_all_and_joint_membership():
    left = np.array([0, 0, 1, 1, -1, -1])
    right = np.array([2, 2, 3, 3, 4, -1])

    result = adjusted_cluster_agreement(left, right)

    assert result["ari_joint"] == pytest.approx(1.0)
    assert result["ami_joint"] == pytest.approx(1.0)
    assert result["jointly_clustered"] == 4
    assert result["ari_all"] < 1.0
    assert result["ami_all"] < 1.0


def test_summarize_clusters_handles_all_noise_and_one_cluster():
    distances = np.zeros((4, 4))

    all_noise = summarize_clusters(distances, np.full(4, -1))
    one_cluster = summarize_clusters(distances, np.zeros(4, dtype=int))

    assert all_noise["clusters"] == 0
    assert all_noise["minimum_size"] is None
    assert all_noise["silhouette"] is None
    assert one_cluster["clusters"] == 1
    assert one_cluster["minimum_size"] == 4
    assert one_cluster["silhouette"] is None


def test_neighborhood_preservation_is_perfect_for_unchanged_geometry():
    coordinates = np.array([[0.0], [1.0], [3.0], [7.0], [12.0]])
    distances = np.abs(coordinates - coordinates.T)

    result = neighborhood_preservation(distances, coordinates, k=2)

    assert result["knn_recall"] == pytest.approx(1.0)
    assert result["trustworthiness"] == pytest.approx(1.0)
    assert result["continuity"] == pytest.approx(1.0)


def test_neighborhood_preservation_excludes_self_when_distances_tie():
    source = np.array([[0.0], [0.0], [1.0], [2.0], [4.0], [8.0]])
    embedding = np.array(
        [
            [-0.28128742, -0.66804635],
            [-1.05515055, -0.39080098],
            [0.48194539, -0.23855361],
            [0.95775870, -0.19980213],
            [0.02425957, 1.54582085],
            [0.54510552, -0.50522874],
        ]
    )

    result = neighborhood_preservation(np.abs(source - source.T), embedding, k=2)

    assert result == pytest.approx(
        {
            "knn_recall": 7 / 12,
            "trustworthiness": 19 / 30,
            "continuity": 22 / 30,
        }
    )


def test_rank_umap_grid_prioritizes_worst_seed_then_median():
    agreement = {"ari_all": 0.4, "ami_all": 0.5}
    results = [
        {
            "n_neighbors": 5,
            "min_dist": 0.05,
            "seed": 0,
            "local_preservation_score": 0.70,
            "reference_cluster_silhouette_in_embedding": 0.6,
            "cluster_agreement": agreement,
        },
        {
            "n_neighbors": 5,
            "min_dist": 0.05,
            "seed": 1,
            "local_preservation_score": 0.90,
            "reference_cluster_silhouette_in_embedding": 0.6,
            "cluster_agreement": agreement,
        },
        {
            "n_neighbors": 10,
            "min_dist": 0.05,
            "seed": 0,
            "local_preservation_score": 0.78,
            "reference_cluster_silhouette_in_embedding": 0.5,
            "cluster_agreement": agreement,
        },
        {
            "n_neighbors": 10,
            "min_dist": 0.05,
            "seed": 1,
            "local_preservation_score": 0.80,
            "reference_cluster_silhouette_in_embedding": 0.5,
            "cluster_agreement": agreement,
        },
    ]

    ranked = rank_umap_grid(results)

    assert ranked[0]["n_neighbors"] == 10
    assert ranked[0]["seed_count"] == 2
    assert ranked[0]["worst_local_preservation_score"] == 0.78
    assert ranked[0]["median_local_preservation_score"] == 0.79


def test_run_umap_grid_reports_neighborhood_and_cluster_preservation(monkeypatch):
    embedding = np.concatenate(
        [
            np.arange(6, dtype=float)[:, None] / 100,
            10 + np.arange(6, dtype=float)[:, None] / 100,
        ]
    )
    distances = np.abs(embedding - embedding.T)

    monkeypatch.setattr(
        "barcart.compute_umap_embedding",
        lambda *_args, **_kwargs: embedding,
    )

    results = run_umap_grid(
        distances,
        neighbors=[5],
        min_distances=[0.1],
        seeds=[42],
        neighborhood_sizes=[2],
        cluster_min_size=5,
        cluster_min_samples=1,
    )

    assert len(results) == 1
    assert results[0]["n_neighbors"] == 5
    assert results[0]["min_dist"] == 0.1
    assert results[0]["seed"] == 42
    assert results[0]["neighborhoods"]["2"]["knn_recall"] == pytest.approx(1.0)
    assert results[0]["cluster_agreement"]["ari_joint"] == pytest.approx(1.0)


def test_run_umap_grid_handles_source_without_multiple_clusters(monkeypatch):
    coordinates = np.arange(6, dtype=float)[:, None]
    distances = np.abs(coordinates - coordinates.T)
    monkeypatch.setattr(
        "barcart.compute_umap_embedding",
        lambda *_args, **_kwargs: coordinates,
    )
    monkeypatch.setattr(
        "scripts.test_constrained_em.cluster_distance_matrix",
        lambda *_args, **_kwargs: np.zeros(6, dtype=int),
    )

    results = run_umap_grid(
        distances,
        neighbors=[3],
        min_distances=[0.1],
        seeds=[42],
        neighborhood_sizes=[2],
        cluster_min_size=5,
        cluster_min_samples=1,
    )

    assert results[0]["reference_cluster_silhouette_in_embedding"] is None


def test_neighborhood_preservation_detects_distortion():
    source = np.array([[0.0], [1.0], [3.0], [7.0], [12.0]])
    distorted = np.array([[0.0], [12.0], [3.0], [7.0], [1.0]])
    distances = np.abs(source - source.T)

    result = neighborhood_preservation(distances, distorted, k=2)

    assert result["knn_recall"] < 1.0
    assert result["trustworthiness"] < 1.0
    assert result["continuity"] < 1.0
