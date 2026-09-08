"""Focused contracts for cache-backed analytics route loading."""

import os
import sys

import pytest
from fastapi import Response

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from core.exceptions import DatabaseException
from routes import analytics
from routes.analytics import (
    get_cocktail_space_analytics,
    get_cocktail_space_em_analytics,
    get_ingredient_tree_analytics,
    get_ingredient_usage_analytics,
)


class FakeStorage:
    def __init__(self, data=None, error=None):
        self.data = data
        self.error = error
        self.keys = []

    def get_analytics(self, storage_key):
        self.keys.append(storage_key)
        if self.error:
            raise self.error
        return self.data


class FakeDatabase:
    def __init__(self, rows=None):
        self.rows = rows or []

    def execute_query(self, _query, _params):
        return self.rows


def _endpoint_kwargs(endpoint):
    kwargs = {"db": FakeDatabase(), "user": None}
    if endpoint is get_ingredient_usage_analytics:
        kwargs.update({"level": None, "parent_id": None})
    if endpoint in {
        get_cocktail_space_analytics,
        get_cocktail_space_em_analytics,
    }:
        kwargs["response"] = Response()
    return kwargs


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "storage_key"),
    [
        (get_ingredient_usage_analytics, "ingredient-usage"),
        (analytics.get_recipe_complexity_analytics, "recipe-complexity"),
        (get_cocktail_space_analytics, "cocktail-space"),
        (get_cocktail_space_em_analytics, "cocktail-space-em"),
        (get_ingredient_tree_analytics, "ingredient-tree"),
    ],
)
async def test_cached_analytics_routes_return_stored_data(
    monkeypatch, endpoint, storage_key
):
    stored_data = {"data": [{"recipe_id": 1}], "metadata": {"source": "cache"}}
    storage = FakeStorage(stored_data)
    monkeypatch.setattr(analytics, "storage_manager", storage)

    result = await endpoint(**_endpoint_kwargs(endpoint))

    if endpoint in {get_cocktail_space_analytics, get_cocktail_space_em_analytics}:
        assert result["data"][0]["rating"] is None
    else:
        assert result == stored_data
    assert storage.keys == [storage_key]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint",
    [
        get_ingredient_usage_analytics,
        analytics.get_recipe_complexity_analytics,
        get_cocktail_space_analytics,
        get_cocktail_space_em_analytics,
        get_ingredient_tree_analytics,
    ],
)
async def test_cached_analytics_routes_report_unconfigured_storage(
    monkeypatch, endpoint
):
    monkeypatch.setattr(analytics, "storage_manager", None)

    with pytest.raises(DatabaseException) as error:
        await endpoint(**_endpoint_kwargs(endpoint))

    assert error.value.message == "Analytics storage not configured"
    assert error.value.detail is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "storage_key"),
    [
        (get_ingredient_usage_analytics, "ingredient-usage"),
        (analytics.get_recipe_complexity_analytics, "recipe-complexity"),
        (get_cocktail_space_analytics, "cocktail-space"),
        (get_cocktail_space_em_analytics, "cocktail-space-em"),
        (get_ingredient_tree_analytics, "ingredient-tree"),
    ],
)
async def test_cached_analytics_routes_report_missing_data(
    monkeypatch, endpoint, storage_key
):
    monkeypatch.setattr(analytics, "storage_manager", FakeStorage())

    with pytest.raises(DatabaseException) as error:
        await endpoint(**_endpoint_kwargs(endpoint))

    assert error.value.message == (
        "Analytics not generated. Please trigger analytics refresh."
    )
    assert error.value.detail == f"{storage_key} data not found in storage"


@pytest.mark.asyncio
async def test_ingredient_usage_drill_down_remains_computed(monkeypatch):
    monkeypatch.setattr(analytics, "storage_manager", None)

    class FakeQueries:
        def __init__(self, db):
            assert db is database

        def get_ingredient_usage_stats(self, parent_id):
            assert parent_id == 12
            return [{"ingredient_id": 13}]

    database = FakeDatabase()
    monkeypatch.setattr(analytics, "AnalyticsQueries", FakeQueries)

    result = await analytics.get_ingredient_usage_analytics(
        level=2, parent_id=12, db=database
    )

    assert result == {
        "data": [{"ingredient_id": 13}],
        "metadata": {"computed_on_the_fly": True, "level": 2, "parent_id": 12},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "wrapped_message"),
    [
        (
            get_ingredient_usage_analytics,
            "Failed to retrieve ingredient usage analytics",
        ),
        (
            analytics.get_recipe_complexity_analytics,
            "Failed to retrieve recipe complexity analytics",
        ),
        (get_cocktail_space_analytics, "Failed to retrieve cocktail space analytics"),
        (
            get_cocktail_space_em_analytics,
            "Failed to retrieve EM cocktail space analytics",
        ),
        (get_ingredient_tree_analytics, "Failed to retrieve ingredient tree analytics"),
    ],
)
async def test_cached_analytics_routes_wrap_storage_errors(
    monkeypatch, endpoint, wrapped_message
):
    monkeypatch.setattr(
        analytics,
        "storage_manager",
        FakeStorage(error=RuntimeError("storage read failed")),
    )

    with pytest.raises(DatabaseException) as error:
        await endpoint(**_endpoint_kwargs(endpoint))

    assert error.value.message == wrapped_message
    assert error.value.detail == "storage read failed"
