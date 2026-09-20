"""GET /recipes/{id} identity handling: private data in, personalised caching out."""

import os
import sys

import pytest
from fastapi import Response

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from dependencies.auth import UserInfo
from routes import recipes


class FakeRecipeDatabase:
    def __init__(self, recipe):
        self.recipe = recipe
        self.calls = []

    def get_recipe(self, recipe_id, user_id=None):
        self.calls.append((recipe_id, user_id))
        return self.recipe


def _recipe():
    return {
        "id": 7,
        "name": "Accidental Hipster",
        "ingredients": [],
        "tags": [{"id": 1, "name": "4-equal-parts", "type": "public"}],
    }


@pytest.mark.asyncio
async def test_authenticated_recipe_view_forwards_identity_and_disables_caching():
    db = FakeRecipeDatabase(_recipe())
    response = Response()

    result = await recipes.get_recipe(
        recipe_id=7,
        response=response,
        db=db,
        user=UserInfo("user-123"),
    )

    assert db.calls == [(7, "user-123")]
    assert result.id == 7
    assert response.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_anonymous_recipe_view_stays_public_and_cacheable():
    db = FakeRecipeDatabase(_recipe())
    response = Response()

    result = await recipes.get_recipe(recipe_id=7, response=response, db=db, user=None)

    assert db.calls == [(7, None)]
    assert result.id == 7
    assert "Cache-Control" not in response.headers
