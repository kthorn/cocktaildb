"""Tests for ingredient rollup functionality."""

import pandas as pd
import pytest
from barcart.rollup import create_rollup_mapping, apply_rollup_to_recipes


class TestCreateRollupMapping:
    """Tests for create_rollup_mapping function."""

    def test_basic_leaf_to_parent_mapping(self):
        """Test basic rollup mapping creation."""
        # Tanqueray (id=2, substitutable leaf) -> London Dry Gin (id=1, parent)
        ingredients = pd.DataFrame({
            'id': [1, 2],
            'name': ['London Dry Gin', 'Tanqueray'],
            'allow_substitution': [0, 1]
        })

        parent_map = {
            '2': ('1', 0.1)  # Tanqueray -> London Dry Gin
        }

        rollup_map = create_rollup_mapping(ingredients, parent_map)

        assert rollup_map == {2: 1}
        assert len(rollup_map) == 1


class TestApplyRollupToRecipes:
    """Tests for apply_rollup_to_recipes function."""

    pass
