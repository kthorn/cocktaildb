"""Tests for analytics API endpoints"""
import pytest
import sys
import os

# Add api directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))


def test_get_ingredient_usage_no_filters(test_client_memory):
    """Test ingredient usage endpoint without filters"""
    response = test_client_memory.get("/analytics/ingredient-usage")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "metadata" in data
    assert isinstance(data["data"], list)


def test_get_ingredient_usage_with_parent_filter(test_client_memory):
    """Test ingredient usage endpoint with parent_id filter"""
    response = test_client_memory.get("/analytics/ingredient-usage?parent_id=1")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data


def test_get_recipe_complexity(test_client_memory):
    """Test recipe complexity endpoint"""
    response = test_client_memory.get("/analytics/recipe-complexity")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "metadata" in data
    assert isinstance(data["data"], list)
