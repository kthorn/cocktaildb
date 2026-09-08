"""Contract tests for paginated recipe search."""

import pytest
from pydantic import ValidationError


def assert_recipe_shape(recipe: dict) -> None:
    """Check the complete recipe shape returned by recipe search."""
    assert {
        "id",
        "name",
        "instructions",
        "description",
        "image_url",
        "source",
        "source_url",
        "avg_rating",
        "rating_count",
        "user_rating",
        "created_by",
        "ingredients",
        "tags",
        "public_tags",
        "private_tags",
    } <= recipe.keys()
    assert isinstance(recipe["ingredients"], list)
    assert isinstance(recipe["tags"], list)
    assert isinstance(recipe["public_tags"], list)
    assert isinstance(recipe["private_tags"], list)

    for ingredient in recipe["ingredients"]:
        assert {
            "ingredient_id",
            "ingredient_name",
            "ingredient_path",
            "full_name",
            "hierarchy",
            "amount",
            "unit_id",
            "unit_name",
            "unit_abbreviation",
        } <= ingredient.keys()

    for tag in recipe["tags"]:
        assert {"id", "name", "type"} <= tag.keys()


def assert_search_shape(data: dict) -> None:
    """Check the top-level /recipes/search response shape."""
    assert set(data) == {"recipes", "pagination", "query"}
    pagination = data["pagination"]
    assert set(pagination) == {
        "page",
        "limit",
        "total_count",
        "has_next",
        "has_previous",
        "next_cursor",
    }
    assert isinstance(data["recipes"], list)
    assert isinstance(pagination["page"], int)
    assert isinstance(pagination["limit"], int)
    assert isinstance(pagination["total_count"], int)
    assert isinstance(pagination["has_next"], bool)
    assert isinstance(pagination["has_previous"], bool)


class TestPaginationModels:
    """Validate the response models used by the search route."""

    def test_paginated_search_response_model(self):
        from api.models.responses import PaginatedSearchResponse

        response = PaginatedSearchResponse(
            recipes=[
                {
                    "id": 1,
                    "name": "Test Recipe",
                    "instructions": "Stir with ice",
                    "ingredients": [],
                    "tags": [],
                }
            ],
            pagination={
                "page": 1,
                "limit": 10,
                "total_count": 1,
                "has_next": False,
                "has_previous": False,
            },
            query="test",
        )

        assert response.recipes[0].name == "Test Recipe"
        assert response.pagination.total_count == 1
        assert response.query == "test"

    @pytest.mark.parametrize(
        "field,value",
        [("page", 0), ("limit", 0), ("limit", 1001), ("total_count", -1)],
    )
    def test_pagination_metadata_rejects_invalid_values(self, field, value):
        from api.models.responses import PaginationMetadata

        metadata = {
            "page": 1,
            "limit": 10,
            "total_count": 1,
            "has_next": False,
            "has_previous": False,
        }
        metadata[field] = value

        with pytest.raises(ValidationError):
            PaginationMetadata(**metadata)


@pytest.mark.asyncio
class TestRecipePagination:
    """Test the implemented /recipes/search pagination contract."""

    async def test_default_pagination_response(self, test_client_with_data):
        client, _ = test_client_with_data

        response = await client.get("/recipes/search")

        assert response.status_code == 200
        data = response.json()
        assert_search_shape(data)
        assert data["query"] is None
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["limit"] == 20
        assert data["pagination"]["has_previous"] is False
        assert len(data["recipes"]) > 0
        for recipe in data["recipes"]:
            assert_recipe_shape(recipe)

    async def test_explicit_page_and_limit(self, test_client_with_data):
        client, _ = test_client_with_data

        response = await client.get("/recipes/search?page=2&limit=2")

        assert response.status_code == 200
        data = response.json()
        assert_search_shape(data)
        assert data["pagination"]["page"] == 2
        assert data["pagination"]["limit"] == 2
        assert data["pagination"]["has_previous"] is True
        assert len(data["recipes"]) == 2

    async def test_metadata_is_consistent_across_pages(
        self, test_client_with_data, db_with_test_data
    ):
        client, _ = test_client_with_data
        cursor = db_with_test_data.cursor()
        cursor.execute(
            """
            INSERT INTO recipes (name, instructions, description)
            VALUES ('Plain Cocktail', 'Stir with ice', 'Not a test recipe')
            """
        )
        db_with_test_data.commit()
        cursor.close()

        first_response = await client.get("/recipes/search?q=Test&page=1&limit=2")
        second_response = await client.get("/recipes/search?q=Test&page=2&limit=2")

        assert first_response.status_code == 200
        assert second_response.status_code == 200
        first = first_response.json()
        second = second_response.json()
        assert_search_shape(first)
        assert_search_shape(second)
        assert first["pagination"]["total_count"] == 2
        assert second["pagination"]["total_count"] == 2
        assert first["pagination"]["total_count"] == second["pagination"]["total_count"]
        assert first["pagination"]["has_next"] is True
        assert second["pagination"]["has_next"] is False

    async def test_search_filter_is_preserved_across_nonempty_pages(
        self, test_client_with_data, db_with_test_data
    ):
        client, _ = test_client_with_data
        cursor = db_with_test_data.cursor()
        cursor.execute(
            """
            INSERT INTO recipes (name, instructions, description)
            VALUES ('Plain Cocktail', 'Stir with ice', 'Not a test recipe')
            """
        )
        db_with_test_data.commit()
        cursor.close()

        first_response = await client.get("/recipes/search?q=Test&page=1&limit=1")
        second_response = await client.get("/recipes/search?q=Test&page=2&limit=1")

        assert first_response.status_code == 200
        assert second_response.status_code == 200
        first = first_response.json()
        second = second_response.json()
        assert first["query"] == "Test"
        assert second["query"] == "Test"
        assert len(first["recipes"]) == 1
        assert len(second["recipes"]) == 1
        assert first["recipes"][0]["id"] != second["recipes"][0]["id"]
        assert all("test" in recipe["name"].lower() for recipe in first["recipes"])
        assert all("test" in recipe["name"].lower() for recipe in second["recipes"])

    async def test_empty_search_result_has_consistent_metadata(
        self, test_client_with_data
    ):
        client, _ = test_client_with_data

        response = await client.get(
            "/recipes/search?q=nonexistentrecipe12345&page=1&limit=10"
        )

        assert response.status_code == 200
        data = response.json()
        assert_search_shape(data)
        assert data["query"] == "nonexistentrecipe12345"
        assert data["recipes"] == []
        assert data["pagination"]["total_count"] == 0
        assert data["pagination"]["has_next"] is False
        assert data["pagination"]["has_previous"] is False

    async def test_page_beyond_results_is_empty(self, test_client_with_data):
        client, _ = test_client_with_data

        response = await client.get("/recipes/search?page=9999&limit=10")

        assert response.status_code == 200
        data = response.json()
        assert_search_shape(data)
        assert data["recipes"] == []
        assert data["pagination"]["page"] == 9999
        assert data["pagination"]["has_next"] is False
        assert data["pagination"]["has_previous"] is True


@pytest.mark.asyncio
class TestRecipeSearchRequestValidation:
    """Validate query parameters without requiring a database connection."""

    @pytest.mark.parametrize(
        "query",
        ["page=0", "page=-1", "page=invalid", "limit=0", "limit=-1", "limit=1001"],
    )
    async def test_invalid_pagination_parameters_return_422(self, query, monkeypatch):
        import httpx

        from api.main import app
        from db.database import get_database

        monkeypatch.setitem(app.dependency_overrides, get_database, lambda: object())
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get(f"/recipes/search?{query}")

        assert response.status_code == 422
