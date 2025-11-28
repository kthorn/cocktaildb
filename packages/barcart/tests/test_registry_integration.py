"""Integration tests for Registry with distance matrix functions."""

import numpy as np
import pandas as pd
import pytest

from barcart import (
    Registry,
    build_ingredient_distance_matrix,
    build_ingredient_tree,
    report_neighbors,
)


@pytest.fixture
def sample_ingredient_df():
    """Create a sample ingredient DataFrame for testing."""
    data = {
        "ingredient_id": ["1", "2", "3", "4"],
        "ingredient_name": ["Spirit", "Gin", "Vodka", "Mixer"],
        "ingredient_path": ["/1/", "/1/2/", "/1/3/", "/4/"],
        "substitution_level": [1.0, 0.5, 0.5, 1.0],
    }
    return pd.DataFrame(data)


class TestBuildIngredientDistanceMatrixIntegration:
    """Test build_ingredient_distance_matrix with Registry."""

    def test_returns_matrix_and_registry(self, sample_ingredient_df):
        """Test that function returns both matrix and registry."""
        tree, parent_map = build_ingredient_tree(sample_ingredient_df)
        id_to_name = dict(
            zip(
                sample_ingredient_df["ingredient_id"],
                sample_ingredient_df["ingredient_name"], strict=False,
            )
        )

        result = build_ingredient_distance_matrix(parent_map, id_to_name)

        assert isinstance(result, tuple)
        assert len(result) == 2
        matrix, registry = result
        assert isinstance(matrix, np.ndarray)
        assert isinstance(registry, Registry)

    def test_handles_integer_ids_in_id_to_name(self, sample_ingredient_df):
        """Test that integer IDs in id_to_name are handled correctly."""
        tree, parent_map = build_ingredient_tree(sample_ingredient_df)

        # Create id_to_name with integer keys (common from DataFrames)
        # Include root since it's added by build_ingredient_tree
        id_to_name = {1: "Spirit", 2: "Gin", 3: "Vodka", 4: "Mixer", "root": "root"}

        matrix, registry = build_ingredient_distance_matrix(parent_map, id_to_name)

        # Should be able to look up by string ID (parent_map uses strings)
        assert registry.get_name(id="1") == "Spirit"
        assert registry.get_name(id="2") == "Gin"
        assert registry.get_name(id="3") == "Vodka"

        # Lookups should work without KeyError
        for i in range(len(registry)):
            ing_id = registry.get_id(index=i)
            name = registry.get_name(id=ing_id)
            assert isinstance(name, str)
            assert len(name) > 0

    def test_matrix_and_registry_dimensions_match(self, sample_ingredient_df):
        """Test that matrix dimensions match registry length."""
        tree, parent_map = build_ingredient_tree(sample_ingredient_df)
        id_to_name = dict(
            zip(
                sample_ingredient_df["ingredient_id"],
                sample_ingredient_df["ingredient_name"], strict=False,
            )
        )

        matrix, registry = build_ingredient_distance_matrix(parent_map, id_to_name)

        assert matrix.shape[0] == len(registry)
        assert matrix.shape[1] == len(registry)
        # Validate should not raise
        registry.validate_matrix(matrix)

    def test_registry_contains_all_ingredients(self, sample_ingredient_df):
        """Test that registry contains all expected ingredients (excluding root)."""
        tree, parent_map = build_ingredient_tree(sample_ingredient_df)
        id_to_name = dict(
            zip(
                sample_ingredient_df["ingredient_id"],
                sample_ingredient_df["ingredient_name"], strict=False,
            )
        )

        matrix, registry = build_ingredient_distance_matrix(parent_map, id_to_name)

        # Check that all non-root ingredients from parent_map are in registry
        for ing_id in parent_map.keys():
            if ing_id == "root":
                continue  # Root is excluded
            # Should not raise KeyError
            idx = registry.get_index(id=ing_id)
            name = registry.get_name(id=ing_id)
            assert isinstance(idx, int)
            assert isinstance(name, str)

    def test_registry_preserves_names(self, sample_ingredient_df):
        """Test that registry correctly maps IDs to names."""
        tree, parent_map = build_ingredient_tree(sample_ingredient_df)
        id_to_name = dict(
            zip(
                sample_ingredient_df["ingredient_id"],
                sample_ingredient_df["ingredient_name"], strict=False,
            )
        )

        matrix, registry = build_ingredient_distance_matrix(parent_map, id_to_name)

        # Check known mappings
        assert registry.get_name(id="2") == "Gin"
        assert registry.get_name(id="3") == "Vodka"
        assert registry.get_id(name="Gin") == "2"

    def test_matrix_values_symmetric(self, sample_ingredient_df):
        """Test that distance matrix is symmetric."""
        tree, parent_map = build_ingredient_tree(sample_ingredient_df)
        id_to_name = dict(
            zip(
                sample_ingredient_df["ingredient_id"],
                sample_ingredient_df["ingredient_name"], strict=False,
            )
        )

        matrix, registry = build_ingredient_distance_matrix(parent_map, id_to_name)

        # Check symmetry
        assert np.allclose(matrix, matrix.T)

    def test_diagonal_is_zero(self, sample_ingredient_df):
        """Test that distance from ingredient to itself is zero."""
        tree, parent_map = build_ingredient_tree(sample_ingredient_df)
        id_to_name = dict(
            zip(
                sample_ingredient_df["ingredient_id"],
                sample_ingredient_df["ingredient_name"], strict=False,
            )
        )

        matrix, registry = build_ingredient_distance_matrix(parent_map, id_to_name)

        # Diagonal should be all zeros
        assert np.allclose(np.diag(matrix), 0.0)

    def test_root_node_excluded(self, sample_ingredient_df):
        """Test that root node is excluded from matrix and registry."""
        tree, parent_map = build_ingredient_tree(sample_ingredient_df)
        id_to_name = dict(
            zip(
                sample_ingredient_df["ingredient_id"],
                sample_ingredient_df["ingredient_name"], strict=False,
            )
        )

        matrix, registry = build_ingredient_distance_matrix(parent_map, id_to_name)

        # Matrix should be smaller than parent_map (root excluded)
        assert len(parent_map) == len(registry) + 1

        # Root node should not be in registry
        with pytest.raises(KeyError, match="not found"):
            registry.get_name(id="root")

        # All non-root ingredients should be present
        for ing_id in sample_ingredient_df["ingredient_id"]:
            # Should not raise
            name = registry.get_name(id=str(ing_id))
            assert isinstance(name, str)


class TestReportNeighborsIntegration:
    """Test report_neighbors with Registry."""

    def test_report_neighbors_produces_dataframe(self, sample_ingredient_df):
        """Test that report_neighbors returns a DataFrame."""
        tree, parent_map = build_ingredient_tree(sample_ingredient_df)
        id_to_name = dict(
            zip(
                sample_ingredient_df["ingredient_id"],
                sample_ingredient_df["ingredient_name"], strict=False,
            )
        )

        matrix, registry = build_ingredient_distance_matrix(parent_map, id_to_name)
        neighbors_df = report_neighbors(matrix, registry, k=2)

        assert isinstance(neighbors_df, pd.DataFrame)
        assert len(neighbors_df) > 0

    def test_report_neighbors_has_expected_columns(self, sample_ingredient_df):
        """Test that output DataFrame has expected columns."""
        tree, parent_map = build_ingredient_tree(sample_ingredient_df)
        id_to_name = dict(
            zip(
                sample_ingredient_df["ingredient_id"],
                sample_ingredient_df["ingredient_name"], strict=False,
            )
        )

        matrix, registry = build_ingredient_distance_matrix(parent_map, id_to_name)
        neighbors_df = report_neighbors(matrix, registry, k=2)

        expected_columns = {
            "id",
            "name",
            "neighbor_id",
            "neighbor_name",
            "distance",
        }
        assert set(neighbors_df.columns) == expected_columns

    def test_report_neighbors_correct_count(self, sample_ingredient_df):
        """Test that report produces k neighbors per ingredient."""
        tree, parent_map = build_ingredient_tree(sample_ingredient_df)
        id_to_name = dict(
            zip(
                sample_ingredient_df["ingredient_id"],
                sample_ingredient_df["ingredient_name"], strict=False,
            )
        )

        matrix, registry = build_ingredient_distance_matrix(parent_map, id_to_name)
        k = 2
        neighbors_df = report_neighbors(matrix, registry, k=k)

        # Each ingredient should have k neighbors
        assert len(neighbors_df) == len(registry) * k

    def test_report_neighbors_names_match_ids(self, sample_ingredient_df):
        """Test that reported names match the IDs in the registry."""
        tree, parent_map = build_ingredient_tree(sample_ingredient_df)
        id_to_name = dict(
            zip(
                sample_ingredient_df["ingredient_id"],
                sample_ingredient_df["ingredient_name"], strict=False,
            )
        )

        matrix, registry = build_ingredient_distance_matrix(parent_map, id_to_name)
        neighbors_df = report_neighbors(matrix, registry, k=2)

        # Verify that for each row, the ID → name mapping is correct
        for _, row in neighbors_df.iterrows():
            entity_id = row["id"]
            entity_name = row["name"]
            neighbor_id = row["neighbor_id"]
            neighbor_name = row["neighbor_name"]

            assert registry.get_name(id=entity_id) == entity_name
            assert registry.get_name(id=neighbor_id) == neighbor_name

    def test_mismatched_matrix_raises(self, sample_ingredient_df):
        """Test that mismatched matrix dimensions raise error."""
        tree, parent_map = build_ingredient_tree(sample_ingredient_df)
        id_to_name = dict(
            zip(
                sample_ingredient_df["ingredient_id"],
                sample_ingredient_df["ingredient_name"], strict=False,
            )
        )

        matrix, registry = build_ingredient_distance_matrix(parent_map, id_to_name)

        # Create a mismatched matrix
        wrong_matrix = np.zeros((len(registry) + 1, len(registry) + 1))

        with pytest.raises(ValueError, match="incompatible"):
            report_neighbors(wrong_matrix, registry, k=2)


class TestEndToEndWorkflow:
    """Test complete workflow from tree building to neighbor reporting."""

    def test_full_pipeline(self, sample_ingredient_df):
        """Test the complete pipeline with Registry."""
        # Step 1: Build tree
        tree, parent_map = build_ingredient_tree(sample_ingredient_df)

        # Step 2: Create id_to_name mapping
        id_to_name = dict(
            zip(
                sample_ingredient_df["ingredient_id"],
                sample_ingredient_df["ingredient_name"], strict=False,
            )
        )

        # Step 3: Build matrix and registry atomically
        matrix, registry = build_ingredient_distance_matrix(parent_map, id_to_name)

        # Step 4: Verify consistency (root is excluded)
        assert len(registry) == len(parent_map) - 1  # Root excluded
        registry.validate_matrix(matrix)

        # Step 5: Generate neighbor report
        neighbors_df = report_neighbors(matrix, registry, k=2)

        # Step 6: Verify output quality
        assert len(neighbors_df) == len(registry) * 2
        assert neighbors_df["distance"].min() >= 0  # Distances are non-negative
        assert not neighbors_df.isnull().any().any()  # No missing values

    def test_can_query_registry_after_creation(self, sample_ingredient_df):
        """Test that registry can be queried for metadata."""
        tree, parent_map = build_ingredient_tree(sample_ingredient_df)
        id_to_name = dict(
            zip(
                sample_ingredient_df["ingredient_id"],
                sample_ingredient_df["ingredient_name"], strict=False,
            )
        )

        matrix, registry = build_ingredient_distance_matrix(parent_map, id_to_name)

        # Test various access patterns
        idx_gin = registry.get_index(name="Gin")
        assert registry.get_id(index=idx_gin) == "2"
        assert registry[idx_gin] == ("2", "Gin")

        idx_vodka = registry.get_index(id="3")
        assert registry.get_name(index=idx_vodka) == "Vodka"
