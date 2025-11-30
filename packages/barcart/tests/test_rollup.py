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

    def test_non_substitutable_ingredients_excluded(self):
        """Non-substitutable ingredients should not be rolled up."""
        ingredients = pd.DataFrame({
            'id': [1, 2, 3],
            'name': ['Parent', 'Non-Sub Child', 'Sub Child'],
            'allow_substitution': [0, 0, 1]
        })

        parent_map = {
            '2': ('1', 0.1),  # Non-substitutable child
            '3': ('1', 0.1)   # Substitutable child
        }

        rollup_map = create_rollup_mapping(ingredients, parent_map)

        assert rollup_map == {3: 1}  # Only substitutable child included
        assert 2 not in rollup_map

    def test_ingredients_without_parents_skipped(self):
        """Ingredients not in parent_map should be skipped."""
        ingredients = pd.DataFrame({
            'id': [1, 2],
            'allow_substitution': [1, 1]
        })

        parent_map = {
            '1': ('root', 0.0)  # Has parent but it's root
        }
        # ingredient 2 not in parent_map

        rollup_map = create_rollup_mapping(ingredients, parent_map)

        assert rollup_map == {}  # Root parent excluded, 2 has no parent

    def test_parent_ingredients_not_rolled_up(self):
        """Ingredients that are parents should not be rolled up."""
        ingredients = pd.DataFrame({
            'id': [1, 2, 3],
            'name': ['Grandparent', 'Parent', 'Child'],
            'allow_substitution': [0, 1, 1]  # Parent is substitutable but is also a parent
        })

        parent_map = {
            '2': ('1', 0.1),  # Parent -> Grandparent
            '3': ('2', 0.1)   # Child -> Parent
        }

        rollup_map = create_rollup_mapping(ingredients, parent_map)

        assert rollup_map == {3: 2}  # Only leaf (3) rolled up
        assert 2 not in rollup_map   # Parent not rolled up even though substitutable


class TestApplyRollupToRecipes:
    """Tests for apply_rollup_to_recipes function."""

    def test_basic_rollup_application(self):
        """Test basic rollup application to recipes."""
        recipes = pd.DataFrame({
            'recipe_id': [1, 1, 2],
            'ingredient_id': [10, 20, 10],
            'volume_fraction': [0.5, 0.5, 1.0]
        })

        rollup_map = {20: 100}  # Roll 20 -> 100

        result = apply_rollup_to_recipes(recipes, rollup_map)

        # recipe 1 should have ingredients 10 and 100 (rolled from 20)
        recipe1 = result[result['recipe_id'] == 1].sort_values('ingredient_id')
        assert len(recipe1) == 2
        assert recipe1.iloc[0]['ingredient_id'] == 10
        assert recipe1.iloc[1]['ingredient_id'] == 100
        assert recipe1.iloc[0]['volume_fraction'] == 0.5
        assert recipe1.iloc[1]['volume_fraction'] == 0.5
