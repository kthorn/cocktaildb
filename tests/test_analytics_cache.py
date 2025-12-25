"""Tests for local analytics storage manager"""
import json
import sys
import os

# Add api directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))

from utils.analytics_cache import AnalyticsStorage


def test_analytics_storage_initialization(tmp_path):
    """Test AnalyticsStorage initializes and creates the version directory"""
    storage = AnalyticsStorage(str(tmp_path))
    assert storage.storage_path == tmp_path
    assert storage.storage_version == "v1"
    assert (tmp_path / "v1").is_dir()


def test_get_file_path_generation(tmp_path):
    """Test file path generation"""
    storage = AnalyticsStorage(str(tmp_path))
    file_path = storage._get_file_path("ingredient-usage")
    assert file_path == tmp_path / "v1" / "ingredient-usage.json"


def test_get_analytics_success(tmp_path):
    """Test retrieving analytics data from local storage"""
    storage = AnalyticsStorage(str(tmp_path))

    test_payload = {
        "data": [{"test": "value"}],
        "metadata": {"generated_at": "2025-01-01T00:00:00Z"}
    }
    file_path = tmp_path / "v1" / "ingredient-usage.json"
    file_path.write_text(json.dumps(test_payload), encoding="utf-8")

    result = storage.get_analytics("ingredient-usage")

    assert result is not None
    assert "data" in result
    assert result["data"][0]["test"] == "value"


def test_get_analytics_not_found(tmp_path):
    """Test retrieving non-existent analytics returns None"""
    storage = AnalyticsStorage(str(tmp_path))
    result = storage.get_analytics("nonexistent")
    assert result is None


def test_put_analytics_success(tmp_path):
    """Test storing analytics data in local storage"""
    storage = AnalyticsStorage(str(tmp_path))
    test_data = [{"ingredient_id": 1, "count": 10}]
    result = storage.put_analytics("ingredient-usage", test_data)

    assert result is True
    file_path = tmp_path / "v1" / "ingredient-usage.json"
    assert file_path.exists()

    body_data = json.loads(file_path.read_text(encoding="utf-8"))
    assert "data" in body_data
    assert "metadata" in body_data
    assert body_data["data"] == test_data


def test_put_then_get_analytics_round_trip(tmp_path):
    """Test stored analytics can be read back"""
    storage = AnalyticsStorage(str(tmp_path))
    test_data = [{"ingredient_id": 1}]

    result = storage.put_analytics("ingredient-usage", test_data)
    assert result is True

    stored = storage.get_analytics("ingredient-usage")
    assert stored is not None
    assert stored["data"] == test_data
