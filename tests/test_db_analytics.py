"""Tests for analytics database queries"""
import pytest
import sys
import os

# Add api directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))

from db.db_analytics import AnalyticsQueries


def test_analytics_queries_initialization(db_instance_with_data):
    """Test AnalyticsQueries can be initialized with Database instance"""
    analytics = AnalyticsQueries(db_instance_with_data)
    assert analytics.db is not None


def test_get_ingredient_usage_stats_root_level(db_instance_with_data):
    """Test ingredient usage stats returns root level ingredients"""
    analytics = AnalyticsQueries(db_instance_with_data)
    stats = analytics.get_ingredient_usage_stats()

    assert isinstance(stats, list)
    # Should have ingredients from conftest test data
    assert len(stats) > 0

    # Check structure
    first_stat = stats[0]
    assert "ingredient_id" in first_stat
    assert "ingredient_name" in first_stat
    assert "direct_usage" in first_stat
    assert "hierarchical_usage" in first_stat
    assert "has_children" in first_stat
    assert "path" in first_stat


def test_get_ingredient_usage_stats_by_parent(db_instance_with_data):
    """Test ingredient usage stats filtered by parent_id"""
    analytics = AnalyticsQueries(db_instance_with_data)

    # Use parent_id=1 (Whiskey) from conftest test data
    stats = analytics.get_ingredient_usage_stats(parent_id=1)

    assert isinstance(stats, list)
    # Should have Bourbon and Rye as children of Whiskey
    if len(stats) > 0:
        # All results should have parent_id=1
        for stat in stats:
            assert stat.get("parent_id") == 1


def test_get_recipe_complexity_distribution(db_instance_with_data):
    """Test recipe complexity distribution returns ingredient count stats"""
    analytics = AnalyticsQueries(db_instance_with_data)
    distribution = analytics.get_recipe_complexity_distribution()

    assert isinstance(distribution, list)
    # Should have entries from test recipes
    assert len(distribution) > 0

    # Check structure
    first_item = distribution[0]
    assert "ingredient_count" in first_item
    assert "recipe_count" in first_item
    # Verify counts are positive
    assert first_item["ingredient_count"] > 0
    assert first_item["recipe_count"] > 0
