"""Unit tests for parent resolution inside one bulk ingredient upload.

These tests drive the route function directly with a fake database so the
same-batch parent rules are covered without needing a PostgreSQL container.
"""

from types import SimpleNamespace
from typing import Any

import pytest
from db.db_core import IngredientBatchInsertError
from ingredient_hierarchy import MAX_INGREDIENT_DEPTH
from models.requests import BulkIngredientUpload
from routes.ingredients import bulk_upload_ingredients

EDITOR = SimpleNamespace(user_id="editor-1")


class FakeBulkIngredientDB:
    """Minimal stand-in for Database covering the bulk upload code path.

    ``existing`` maps ingredient names to materialized paths such as
    ``"/1/7/"``; the last path segment is the ingredient's id.
    """

    def __init__(
        self,
        existing: dict[str, str] | None = None,
        fail_on: set[str] | None = None,
    ):
        self.rows: dict[int, dict[str, Any]] = {}
        for name, path in (existing or {}).items():
            ingredient_id = int(path.strip("/").split("/")[-1])
            self.rows[ingredient_id] = {"id": ingredient_id, "name": name, "path": path}
        self.fail_on = fail_on or set()
        self.created: list[dict[str, Any]] = []
        self._next_id = 100

    def _find(self, name: str) -> dict[str, Any] | None:
        return next(
            (row for row in self.rows.values() if row["name"].lower() == name.lower()),
            None,
        )

    def check_ingredient_names_batch(self, names: list[str]) -> dict[str, bool]:
        return {name: self._find(name) is not None for name in names}

    def search_ingredients_batch(self, names: list[str]) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        for name in names:
            row = self._find(name)
            if row is not None:
                results[name] = dict(row)
        return results

    def execute_query(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        raise AssertionError("bulk upload should not issue per-row queries")

    def _insert(self, data: dict[str, Any], staged: dict[int, dict]) -> dict:
        if data["name"] in self.fail_on:
            raise RuntimeError(f"insert failed for {data['name']}")
        all_rows = {**self.rows, **staged}
        if any(r["name"].lower() == data["name"].lower() for r in all_rows.values()):
            raise RuntimeError(f"duplicate key value: {data['name']}")
        ingredient_id = self._next_id
        self._next_id += 1
        parent_id = data.get("parent_id")
        parent_path = all_rows[parent_id]["path"] if parent_id else "/"
        return {
            "id": ingredient_id,
            "name": data["name"],
            "description": data.get("description"),
            "parent_id": parent_id,
            "path": f"{parent_path}{ingredient_id}/",
            "allow_substitution": bool(data.get("allow_substitution")),
            "percent_abv": None,
            "sugar_g_per_l": None,
            "titratable_acidity_g_per_l": None,
            "url": None,
            "created_by": data.get("created_by"),
        }

    def create_ingredients_batch(self, rows: list[dict[str, Any]]) -> list[dict]:
        """All-or-nothing, like the real transaction."""
        staged: dict[int, dict] = {}
        result: list[dict] = []
        for index, data in enumerate(rows):
            parent_index = data.get("parent_index")
            if parent_index is not None:
                data = {**data, "parent_id": result[parent_index]["id"]}
            try:
                row = self._insert(data, staged)
            except RuntimeError as e:
                raise IngredientBatchInsertError(index, e) from e
            staged[row["id"]] = row
            result.append(row)
        self.rows.update(staged)
        self.created.extend(result)
        return result


async def _upload(db: FakeBulkIngredientDB, ingredients: list[dict[str, Any]]) -> Any:
    request = BulkIngredientUpload(ingredients=ingredients)
    return await bulk_upload_ingredients(request, db=db, user=EDITOR)


@pytest.mark.asyncio
async def test_parent_defined_earlier_in_batch_resolves():
    db = FakeBulkIngredientDB()

    response = await _upload(
        db,
        [
            {"name": "Cat"},
            {"name": "Brand", "parent_name": "Cat"},
        ],
    )

    assert response.uploaded_count == 2
    assert response.validation_errors == []
    cat = next(i for i in response.uploaded_ingredients if i.name == "Cat")
    brand = next(i for i in response.uploaded_ingredients if i.name == "Brand")
    assert brand.parent_id == cat.id


@pytest.mark.asyncio
async def test_parent_defined_later_in_batch_is_created_first():
    db = FakeBulkIngredientDB()

    response = await _upload(
        db,
        [
            {"name": "Brand", "parent_name": "Cat"},
            {"name": "Cat"},
        ],
    )

    assert response.uploaded_count == 2
    assert response.validation_errors == []
    assert [row["name"] for row in db.created] == ["Cat", "Brand"]
    assert db.created[1]["parent_id"] == db.created[0]["id"]
    # The response follows request order, not creation order.
    assert [i.name for i in response.uploaded_ingredients] == ["Brand", "Cat"]


@pytest.mark.asyncio
async def test_parent_from_database_still_resolves():
    db = FakeBulkIngredientDB({"Vodka": "/7/"})

    response = await _upload(db, [{"name": "Premium Vodka", "parent_name": "Vodka"}])

    assert response.uploaded_count == 1
    assert response.validation_errors == []
    assert response.uploaded_ingredients[0].parent_id == 7


@pytest.mark.asyncio
async def test_unknown_parent_is_still_rejected():
    db = FakeBulkIngredientDB()

    response = await _upload(db, [{"name": "Brand", "parent_name": "Missing"}])

    assert response.uploaded_count == 0
    assert [e.error_type for e in response.validation_errors] == ["parent_not_found"]
    assert db.created == []


@pytest.mark.asyncio
async def test_circular_parent_reference_is_rejected():
    db = FakeBulkIngredientDB()

    response = await _upload(
        db,
        [
            {"name": "A", "parent_name": "B"},
            {"name": "B", "parent_name": "A"},
        ],
    )

    assert response.uploaded_count == 0
    assert {e.error_type for e in response.validation_errors} == {"invalid_parent"}
    assert db.created == []


def _errors_by_index(response: Any) -> dict[int, tuple[str, str]]:
    return {
        e.ingredient_index: (e.error_type, e.error_message)
        for e in response.validation_errors
    }


@pytest.mark.asyncio
async def test_same_batch_parent_matches_case_insensitively():
    db = FakeBulkIngredientDB()

    response = await _upload(
        db,
        [
            {"name": "Cat"},
            {"name": "Brand", "parent_name": "cAT"},
        ],
    )

    assert response.validation_errors == []
    assert db.created[1]["parent_id"] == db.created[0]["id"]


@pytest.mark.asyncio
async def test_name_repeated_in_batch_is_rejected_before_creating_anything():
    db = FakeBulkIngredientDB()

    response = await _upload(
        db,
        [
            {"name": "Cat"},
            {"name": "cat", "parent_name": "Cat"},
        ],
    )

    errors = _errors_by_index(response)
    assert list(errors) == [1]
    assert errors[1][0] == "duplicate_name"
    assert "more than once" in errors[1][1]
    assert response.failed_count == 1
    assert db.created == []


@pytest.mark.asyncio
async def test_self_parent_is_rejected():
    db = FakeBulkIngredientDB()

    response = await _upload(db, [{"name": "A", "parent_name": "a"}])

    assert [e.error_type for e in response.validation_errors] == ["invalid_parent"]
    assert db.created == []


@pytest.mark.asyncio
async def test_row_below_a_cycle_is_not_reported_as_part_of_it():
    db = FakeBulkIngredientDB()

    response = await _upload(
        db,
        [
            {"name": "A", "parent_name": "B"},
            {"name": "B", "parent_name": "A"},
            {"name": "C", "parent_name": "A"},
        ],
    )

    errors = _errors_by_index(response)
    assert "Circular" in errors[0][1]
    assert "Circular" in errors[1][1]
    assert errors[2][0] == "invalid_parent"
    assert "Circular" not in errors[2][1]
    assert "'A'" in errors[2][1]
    assert db.created == []


@pytest.mark.asyncio
async def test_child_of_invalid_batch_parent_is_also_reported():
    db = FakeBulkIngredientDB()

    response = await _upload(
        db,
        [
            {"name": "Brand", "parent_name": "Cat"},
            {"name": "Cat", "parent_name": "Missing"},
        ],
    )

    errors = _errors_by_index(response)
    assert errors[1][0] == "parent_not_found"
    assert errors[0][0] == "invalid_parent"
    assert "'Cat'" in errors[0][1]
    assert response.failed_count == 2
    assert db.created == []


@pytest.mark.asyncio
async def test_long_same_batch_chain_is_rejected_without_recursion_error():
    db = FakeBulkIngredientDB()
    count = 1000
    # Row i is the child of row i + 1; the last row is top level.
    rows = [
        {"name": f"Level {i}", "parent_name": f"Level {i + 1}"}
        for i in range(count - 1)
    ] + [{"name": f"Level {count - 1}"}]

    response = await _upload(db, rows)

    errors = _errors_by_index(response)
    # The ten rows nearest the top fit within the depth limit.
    assert set(errors) == set(range(count - MAX_INGREDIENT_DEPTH))
    assert errors[count - MAX_INGREDIENT_DEPTH - 1][0] == "depth_exceeded"
    assert db.created == []


@pytest.mark.asyncio
async def test_depth_limit_counts_existing_ancestors():
    # "Deep" is already at the maximum depth minus one.
    deep_path = "/" + "/".join(str(i) for i in range(1, MAX_INGREDIENT_DEPTH)) + "/"
    db = FakeBulkIngredientDB({"Deep": deep_path})

    response = await _upload(
        db,
        [
            {"name": "At Limit", "parent_name": "Deep"},
            {"name": "Too Deep", "parent_name": "At Limit"},
        ],
    )

    errors = _errors_by_index(response)
    assert list(errors) == [1]
    assert errors[1][0] == "depth_exceeded"
    assert db.created == []


@pytest.mark.asyncio
async def test_failed_insert_creates_nothing_from_the_upload():
    db = FakeBulkIngredientDB(fail_on={"Cat"})

    response = await _upload(
        db,
        [
            {"name": "Other"},
            {"name": "Brand", "parent_name": "Cat"},
            {"name": "Cat"},
        ],
    )

    errors = _errors_by_index(response)
    assert list(errors) == [2]
    assert errors[2][0] == "creation_error"
    assert "No ingredients from this upload were created" in errors[2][1]
    assert response.uploaded_count == 0
    assert response.uploaded_ingredients == []
    assert db.created == []
