"""Rating enrichment for cocktail-space analytics."""
import os
import sys

import pytest
from fastapi import Response

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from dependencies.auth import UserInfo
from routes import analytics
from routes.analytics import add_cocktail_space_ratings


class FakeDatabase:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute_query(self, query, params):
        self.calls.append((query, params))
        return self.rows


def test_adds_average_ratings_for_anonymous_visitors():
    db = FakeDatabase([
        {"recipe_id": 1, "rating": 4.25},
        {"recipe_id": 2, "rating": None},
    ])
    stored = {
        "data": [{"recipe_id": 1}, {"recipe_id": 2}],
        "metadata": {"generated_at": "today"},
    }

    result = add_cocktail_space_ratings(stored, db, None)

    assert [point["rating"] for point in result["data"]] == [4.25, None]
    assert result["metadata"]["rating_source"] == "average"
    assert len(db.calls) == 1
    assert "avg_rating" in db.calls[0][0]


def test_treats_zero_average_as_unrated():
    db = FakeDatabase([{"recipe_id": 1, "rating": 0}])
    stored = {"data": [{"recipe_id": 1}], "metadata": {}}

    result = add_cocktail_space_ratings(stored, db, None)

    assert result["data"][0]["rating"] is None


def test_adds_only_the_current_users_ratings_when_authenticated():
    db = FakeDatabase([{"recipe_id": 1, "rating": 5}])
    stored = {
        "data": [{"recipe_id": 1}, {"recipe_id": 2}],
        "metadata": {},
    }

    result = add_cocktail_space_ratings(stored, db, UserInfo("user-123"))

    assert [point["rating"] for point in result["data"]] == [5, None]
    assert result["metadata"]["rating_source"] == "user"
    assert db.calls[0][1]["user_id"] == "user-123"
    assert "cognito_user_id" in db.calls[0][0]


class FakeStorage:
    def get_analytics(self, _storage_key):
        return {"data": [{"recipe_id": 1}], "metadata": {}}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint",
    [analytics.get_cocktail_space_analytics, analytics.get_cocktail_space_em_analytics],
)
async def test_cocktail_space_responses_are_not_cacheable(monkeypatch, endpoint):
    monkeypatch.setattr(analytics, "storage_manager", FakeStorage())
    response = Response()

    await endpoint(response=response, db=FakeDatabase([]), user=None)

    assert response.headers["Cache-Control"] == "private, no-store"
