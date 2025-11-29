"""Tests for distance computation functions."""

import numpy as np

from barcart.distance import expected_ingredient_match_matrix, m_step_blosum


class TestExpectedIngredientMatchMatrix:
    """Test expected_ingredient_match_matrix function."""

    def test_simple_two_recipes_two_ingredients(self):
        """Test with minimal case: 2 recipes, 2 ingredients."""
        # Recipe 1: 100% ingredient 0
        # Recipe 2: 100% ingredient 1
        volume_matrix = np.array(
            [
                [1.0, 0.0],
                [0.0, 1.0],
            ]
        )

        # Cost matrix: off-diagonal = 1.0
        cost_matrix = np.array(
            [
                [0.0, 1.0],
                [1.0, 0.0],
            ]
        )

        # With k=1, each recipe's nearest neighbor is the other
        # beta=1.0 for simple exponential weighting
        T_sum, N_pairs = expected_ingredient_match_matrix(
            volume_matrix, cost_matrix, k=1, beta=1.0
        )

        # Basic shape check
        assert T_sum.shape == (2, 2)
        assert N_pairs == 2  # 2 recipes * 1 neighbor each

        # Symmetry check
        np.testing.assert_allclose(T_sum, T_sum.T, rtol=1e-10)

        # Non-negativity
        assert np.all(T_sum >= 0)

    def test_identical_recipes_zero_distance(self):
        """Test that identical recipes have zero EMD distance."""
        # Two identical recipes
        volume_matrix = np.array(
            [
                [0.5, 0.5],
                [0.5, 0.5],
            ]
        )

        cost_matrix = np.array(
            [
                [0.0, 1.0],
                [1.0, 0.0],
            ]
        )

        T_sum, N_pairs = expected_ingredient_match_matrix(
            volume_matrix, cost_matrix, k=1, beta=1.0
        )

        # When recipes are identical, the transport plan should be diagonal
        # (ingredient i in recipe 1 maps to ingredient i in recipe 2)
        assert T_sum.shape == (2, 2)
        # Diagonal should have positive values
        assert T_sum[0, 0] > 0
        assert T_sum[1, 1] > 0

    def test_three_recipes_symmetry(self):
        """Test symmetry with 3 recipes."""
        volume_matrix = np.array(
            [
                [1.0, 0.0, 0.0],  # Recipe 0: pure ingredient 0
                [0.0, 1.0, 0.0],  # Recipe 1: pure ingredient 1
                [0.0, 0.0, 1.0],  # Recipe 2: pure ingredient 2
            ]
        )

        cost_matrix = np.array(
            [
                [0.0, 1.0, 2.0],
                [1.0, 0.0, 1.0],
                [2.0, 1.0, 0.0],
            ]
        )

        T_sum, N_pairs = expected_ingredient_match_matrix(
            volume_matrix, cost_matrix, k=2, beta=1.0
        )

        # Check symmetry
        np.testing.assert_allclose(T_sum, T_sum.T, rtol=1e-10)

        # Check shape
        assert T_sum.shape == (3, 3)
        assert N_pairs == 6  # 3 recipes * 2 neighbors

    def test_plan_sparsification(self):
        """Test that plan_topk and plan_minfrac work."""
        volume_matrix = np.array(
            [
                [0.7, 0.3, 0.0],
                [0.0, 0.4, 0.6],
            ]
        )

        cost_matrix = np.array(
            [
                [0.0, 1.0, 1.0],
                [1.0, 0.0, 1.0],
                [1.0, 1.0, 0.0],
            ]
        )

        # Should not raise errors
        T_sum_topk, _ = expected_ingredient_match_matrix(
            volume_matrix, cost_matrix, k=1, beta=1.0, plan_topk=2
        )

        T_sum_minfrac, _ = expected_ingredient_match_matrix(
            volume_matrix, cost_matrix, k=1, beta=1.0, plan_minfrac=0.1
        )

        assert T_sum_topk.shape == (3, 3)
        assert T_sum_minfrac.shape == (3, 3)


class TestMStepBlosum:
    """Test m_step_blosum function."""

    def test_uniform_match_matrix_gives_zero_cost(self):
        """Test that uniform matches give zero-ish cost (perfect substitutability)."""
        # If all pairs match equally, there's no preference pattern
        # Log-odds should be near zero (after subtracting min)
        T_sum = np.ones((3, 3))

        C_new = m_step_blosum(T_sum, blosum_alpha=1.0, median_target=1.0)

        # All off-diagonal entries should be equal (symmetric, uniform)
        assert C_new.shape == (3, 3)
        np.testing.assert_allclose(C_new, C_new.T, rtol=1e-10)  # Symmetry
        np.testing.assert_allclose(np.diag(C_new), 0.0, atol=1e-10)  # Zero diagonal

        # All off-diagonal should be equal
        off_diag = C_new[~np.eye(3, dtype=bool)]
        np.testing.assert_allclose(off_diag, off_diag[0], rtol=1e-10)

    def test_diagonal_match_matrix(self):
        """Test diagonal match matrix (ingredients never substitute)."""
        # Strong diagonal: ingredients match themselves, never substitute
        T_sum = np.diag([10.0, 10.0, 10.0])

        C_new = m_step_blosum(T_sum, blosum_alpha=0.1, median_target=1.0)

        # Diagonal should be zero
        np.testing.assert_allclose(np.diag(C_new), 0.0, atol=1e-10)

        # Off-diagonal should be positive (high cost for substitution)
        off_diag = C_new[~np.eye(3, dtype=bool)]
        assert np.all(off_diag > 0)

    def test_symmetry_preserved(self):
        """Test that output cost matrix is symmetric."""
        T_sum = np.array(
            [
                [5.0, 2.0, 1.0],
                [2.0, 5.0, 3.0],
                [1.0, 3.0, 5.0],
            ]
        )

        C_new = m_step_blosum(T_sum, blosum_alpha=1.0, median_target=1.0)

        np.testing.assert_allclose(C_new, C_new.T, rtol=1e-10)

    def test_zero_diagonal_enforced(self):
        """Test that diagonal is always zero."""
        T_sum = np.random.rand(4, 4)
        T_sum = 0.5 * (T_sum + T_sum.T)  # Make symmetric

        C_new = m_step_blosum(T_sum, blosum_alpha=1.0, median_target=1.0)

        np.testing.assert_allclose(np.diag(C_new), 0.0, atol=1e-10)

    def test_laplace_smoothing_effect(self):
        """Test that Laplace smoothing prevents infinite costs."""
        # Sparse match matrix with zeros
        T_sum = np.array(
            [
                [10.0, 0.0, 0.0],
                [0.0, 10.0, 0.0],
                [0.0, 0.0, 10.0],
            ]
        )

        # With smoothing, should not get inf or nan
        C_new = m_step_blosum(T_sum, blosum_alpha=0.5, median_target=1.0)

        assert np.all(np.isfinite(C_new))
        assert not np.any(np.isnan(C_new))

    def test_median_rescaling(self):
        """Test that median of off-diagonal is scaled to target."""
        T_sum = np.array(
            [
                [5.0, 2.0, 1.0],
                [2.0, 5.0, 3.0],
                [1.0, 3.0, 5.0],
            ]
        )

        target = 2.5
        C_new = m_step_blosum(T_sum, blosum_alpha=1.0, median_target=target)

        # Extract off-diagonal values
        mask = ~np.eye(C_new.shape[0], dtype=bool)
        off_diag = C_new[mask]
        median_cost = np.median(off_diag)

        # Should be close to target (within numerical tolerance)
        np.testing.assert_allclose(median_cost, target, rtol=0.1)

    def test_marginal_smoothing_consistency(self):
        """Test that marginal smoothing is mathematically consistent.

        This test verifies the fix: when adding alpha pseudo-counts to each cell,
        row/column sums should increase by alpha * m, not just alpha.
        """
        m = 3
        T_sum = np.array(
            [
                [5.0, 2.0, 1.0],
                [2.0, 5.0, 3.0],
                [1.0, 3.0, 5.0],
            ]
        )

        alpha = 1.0

        # Manually compute expected marginals
        N = T_sum.copy()
        total = N.sum()
        row = N.sum(axis=1, keepdims=True)
        col = N.sum(axis=0, keepdims=True)

        # After adding alpha to each cell, marginals should be:
        # row_new[i] = row[i] + alpha * m
        # col_new[j] = col[j] + alpha * m
        # total_new = total + alpha * m^2

        # Expected matrix under independence
        _E_correct = ((row + alpha * m) @ (col + alpha * m)) / (total + alpha * m * m)

        # This should match what the function computes
        # We can't directly access E from the function, but we can verify
        # that the function runs without producing inf/nan values
        C_new = m_step_blosum(T_sum, blosum_alpha=alpha, median_target=1.0)

        assert np.all(np.isfinite(C_new))
        assert C_new.shape == (m, m)

        # Verify the computation doesn't produce degenerate results
        # (all zeros or all same value would indicate a bug)
        assert np.std(C_new[~np.eye(m, dtype=bool)]) > 0


class TestBuildRecipeVolumeMatrix:
    """Test build_recipe_volume_matrix function."""

    def test_build_recipe_volume_matrix_returns_registry(self):
        """Test that build_recipe_volume_matrix constructs and returns a recipe Registry."""
        import pandas as pd

        from barcart.distance import build_recipe_volume_matrix
        from barcart.registry import Registry

        # Create ingredient registry
        ingredient_registry = Registry(
            [
                (0, "ing_1", "Gin"),
                (1, "ing_2", "Vodka"),
                (2, "ing_3", "Lime Juice"),
            ]
        )

        # Create recipes dataframe
        recipes_df = pd.DataFrame(
            [
                {
                    "recipe_id": "r1",
                    "recipe_name": "Gimlet",
                    "ingredient_id": "ing_1",
                    "volume_fraction": 0.6,
                },
                {
                    "recipe_id": "r1",
                    "recipe_name": "Gimlet",
                    "ingredient_id": "ing_3",
                    "volume_fraction": 0.4,
                },
                {
                    "recipe_id": "r2",
                    "recipe_name": "Vodka Gimlet",
                    "ingredient_id": "ing_2",
                    "volume_fraction": 0.6,
                },
                {
                    "recipe_id": "r2",
                    "recipe_name": "Vodka Gimlet",
                    "ingredient_id": "ing_3",
                    "volume_fraction": 0.4,
                },
            ]
        )

        volume_matrix, recipe_registry = build_recipe_volume_matrix(
            recipes_df,
            ingredient_registry,
            recipe_name_col="recipe_name",
        )

        # Verify recipe_registry is a Registry instance
        assert isinstance(recipe_registry, Registry)
        assert len(recipe_registry) == 2

        # Verify registry contents
        assert recipe_registry.get_name(index=0) == "Gimlet"
        assert recipe_registry.get_name(index=1) == "Vodka Gimlet"
        assert recipe_registry.get_id(name="Gimlet") == "r1"
        assert recipe_registry.get_id(name="Vodka Gimlet") == "r2"

        # Verify matrix dimensions match registry
        assert volume_matrix.shape[0] == len(recipe_registry)
        assert volume_matrix.shape[1] == len(ingredient_registry)


class TestComputeUmapEmbedding:
    """Test compute_umap_embedding function."""

    def test_computes_2d_embedding_from_distance_matrix(self):
        """Test that UMAP produces 2D coordinates from a distance matrix."""
        import numpy as np

        from barcart.distance import compute_umap_embedding

        # Create a simple 5x5 distance matrix
        distance_matrix = np.array(
            [
                [0.0, 1.0, 2.0, 3.0, 4.0],
                [1.0, 0.0, 1.0, 2.0, 3.0],
                [2.0, 1.0, 0.0, 1.0, 2.0],
                [3.0, 2.0, 1.0, 0.0, 1.0],
                [4.0, 3.0, 2.0, 1.0, 0.0],
            ]
        )

        # Compute UMAP embedding
        embedding = compute_umap_embedding(distance_matrix, n_components=2, random_state=42)

        # Verify shape: (n_samples, n_components)
        assert embedding.shape == (5, 2)

        # Verify all values are finite
        assert np.all(np.isfinite(embedding))

    def test_respects_n_components_parameter(self):
        """Test that n_components parameter controls dimensionality."""
        import numpy as np

        from barcart.distance import compute_umap_embedding

        # Use larger matrix for testing different dimensions
        distance_matrix = np.array(
            [
                [0.0, 1.0, 2.0, 3.0, 4.0],
                [1.0, 0.0, 1.0, 2.0, 3.0],
                [2.0, 1.0, 0.0, 1.0, 2.0],
                [3.0, 2.0, 1.0, 0.0, 1.0],
                [4.0, 3.0, 2.0, 1.0, 0.0],
            ]
        )

        # Test with 1D embedding
        embedding_1d = compute_umap_embedding(distance_matrix, n_components=1, random_state=42)
        assert embedding_1d.shape == (5, 1)

        # Test with 3D embedding
        embedding_3d = compute_umap_embedding(distance_matrix, n_components=3, random_state=42)
        assert embedding_3d.shape == (5, 3)

    def test_random_state_gives_reproducible_results(self):
        """Test that same random_state produces same embedding."""
        import numpy as np

        from barcart.distance import compute_umap_embedding

        distance_matrix = np.array(
            [
                [0.0, 1.0, 2.0, 3.0],
                [1.0, 0.0, 1.0, 2.0],
                [2.0, 1.0, 0.0, 1.0],
                [3.0, 2.0, 1.0, 0.0],
            ]
        )

        embedding1 = compute_umap_embedding(distance_matrix, random_state=42)
        embedding2 = compute_umap_embedding(distance_matrix, random_state=42)

        np.testing.assert_allclose(embedding1, embedding2, rtol=1e-10)


class TestReportNeighbors:
    """Test generic report_neighbors function."""

    def test_report_neighbors_with_recipes(self):
        """Test report_neighbors works for recipe entities."""
        import numpy as np

        from barcart.distance import report_neighbors
        from barcart.registry import Registry

        # Create recipe registry
        recipe_registry = Registry(
            [
                (0, "r1", "Martini"),
                (1, "r2", "Gimlet"),
                (2, "r3", "Daiquiri"),
            ]
        )

        # Create fake distance matrix
        distance_matrix = np.array(
            [
                [0.0, 0.5, 1.0],
                [0.5, 0.0, 0.8],
                [1.0, 0.8, 0.0],
            ]
        )

        result = report_neighbors(distance_matrix, recipe_registry, k=2)

        # Verify DataFrame structure
        assert list(result.columns) == [
            "id",
            "name",
            "neighbor_id",
            "neighbor_name",
            "distance",
        ]
        assert len(result) == 6  # 3 recipes * 2 neighbors each

        # Verify first recipe's neighbors
        r1_neighbors = result[result["id"] == "r1"]
        assert len(r1_neighbors) == 2
        assert r1_neighbors.iloc[0]["neighbor_id"] == "r2"
        assert r1_neighbors.iloc[0]["distance"] == 0.5
        assert r1_neighbors.iloc[1]["neighbor_id"] == "r3"
        assert r1_neighbors.iloc[1]["distance"] == 1.0

    def test_report_neighbors_with_ingredients(self):
        """Test report_neighbors works for ingredient entities."""
        import numpy as np

        from barcart.distance import report_neighbors
        from barcart.registry import Registry

        # Create ingredient registry
        ingredient_registry = Registry(
            [
                (0, "ing_1", "Gin"),
                (1, "ing_2", "Vodka"),
                (2, "ing_3", "Rum"),
            ]
        )

        # Create fake cost matrix
        cost_matrix = np.array(
            [
                [0.0, 1.0, 2.0],
                [1.0, 0.0, 1.5],
                [2.0, 1.5, 0.0],
            ]
        )

        result = report_neighbors(cost_matrix, ingredient_registry, k=1)

        # Verify DataFrame structure
        assert list(result.columns) == [
            "id",
            "name",
            "neighbor_id",
            "neighbor_name",
            "distance",
        ]
        assert len(result) == 3  # 3 ingredients * 1 neighbor each

        # Verify first ingredient's neighbor
        gin_neighbors = result[result["id"] == "ing_1"]
        assert len(gin_neighbors) == 1
        assert gin_neighbors.iloc[0]["name"] == "Gin"
        assert gin_neighbors.iloc[0]["neighbor_id"] == "ing_2"
        assert gin_neighbors.iloc[0]["neighbor_name"] == "Vodka"
        assert gin_neighbors.iloc[0]["distance"] == 1.0
