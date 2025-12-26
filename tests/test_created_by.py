"""Tests for created_by field on recipes and ingredients"""

import pytest
from api.models.responses import IngredientResponse


class TestIngredientCreatedByField:
    """Test created_by field on ingredient responses"""

    def test_ingredient_response_has_created_by_field(self):
        """IngredientResponse model should accept created_by field"""
        ingredient = IngredientResponse(
            id=1,
            name="Test Ingredient",
            allow_substitution=False,
            created_by="user-123"
        )
        assert ingredient.created_by == "user-123"

    def test_ingredient_response_created_by_optional(self):
        """created_by should be optional (None for legacy data)"""
        ingredient = IngredientResponse(
            id=1,
            name="Test Ingredient",
            allow_substitution=False
        )
        assert ingredient.created_by is None
