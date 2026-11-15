"""PUT /ingredients/{id} must honour an explicit null for clearable fields (#146).

The edit form sends null to mean "empty": a cleared parent moves the
ingredient to the top level, and a cleared measured value removes it.
Fields that are left out of the request must stay unchanged.
"""

import pytest

VALUE_FIELDS = ("percent_abv", "sugar_g_per_l", "titratable_acidity_g_per_l")
VALUES = {
    "percent_abv": 40.0,
    "sugar_g_per_l": 250.0,
    "titratable_acidity_g_per_l": 6.0,
}


async def _create(client, name, **fields):
    response = await client.post("/ingredients", json={"name": name, **fields})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _get(client, ingredient_id):
    response = await client.get(f"/ingredients/{ingredient_id}")
    assert response.status_code == 200, response.text
    return response.json()


async def _put(client, ingredient_id, payload):
    response = await client.put(f"/ingredients/{ingredient_id}", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


async def _with_values(client, name):
    ingredient_id = await _create(client, name)
    await _put(client, ingredient_id, VALUES)
    return ingredient_id


@pytest.mark.asyncio
async def test_null_parent_moves_ingredient_and_descendants_to_top_level(
    editor_client,
):
    spirit = await _create(editor_client, "Spirit")
    gin = await _create(editor_client, "Gin", parent_id=spirit)
    london_dry = await _create(editor_client, "London Dry Gin", parent_id=gin)

    await _put(editor_client, gin, {"parent_id": None})

    moved = await _get(editor_client, gin)
    assert moved["parent_id"] is None
    assert moved["path"] == f"/{gin}/"
    child = await _get(editor_client, london_dry)
    assert child["parent_id"] == gin
    assert child["path"] == f"/{gin}/{london_dry}/"


@pytest.mark.asyncio
async def test_omitted_parent_keeps_parent(editor_client):
    spirit = await _create(editor_client, "Spirit")
    gin = await _create(editor_client, "Gin", parent_id=spirit)

    await _put(editor_client, gin, {"description": "Juniper spirit"})

    unchanged = await _get(editor_client, gin)
    assert unchanged["parent_id"] == spirit
    assert unchanged["path"] == f"/{spirit}/{gin}/"


@pytest.mark.asyncio
@pytest.mark.parametrize("field", VALUE_FIELDS)
async def test_null_value_clears_only_that_field(editor_client, field):
    syrup = await _with_values(editor_client, "Test Syrup")

    await _put(editor_client, syrup, {field: None})

    ingredient = await _get(editor_client, syrup)
    assert ingredient[field] is None
    for other in VALUE_FIELDS:
        if other != field:
            assert ingredient[other] == pytest.approx(VALUES[other])


@pytest.mark.asyncio
async def test_omitted_values_are_kept(editor_client):
    syrup = await _with_values(editor_client, "Test Syrup")

    await _put(editor_client, syrup, {"description": "Rich"})

    ingredient = await _get(editor_client, syrup)
    for field in VALUE_FIELDS:
        assert ingredient[field] == pytest.approx(VALUES[field])


@pytest.mark.asyncio
async def test_null_for_non_clearable_fields_is_ignored(editor_client):
    gin = await _create(
        editor_client, "Gin", description="Juniper", allow_substitution=True
    )

    await _put(
        editor_client,
        gin,
        {"name": None, "description": None, "allow_substitution": None},
    )

    ingredient = await _get(editor_client, gin)
    assert ingredient["name"] == "Gin"
    assert ingredient["description"] == "Juniper"
    assert ingredient["allow_substitution"] is True


def _form_payload(name, **fields):
    """The shape the ingredient edit form always sends."""
    return {
        "name": name,
        "description": "",
        "parent_id": None,
        "allow_substitution": False,
        "url": None,
        "percent_abv": None,
        "sugar_g_per_l": None,
        "titratable_acidity_g_per_l": None,
        **fields,
    }


@pytest.mark.asyncio
async def test_form_payload_for_top_level_leaf_keeps_values(editor_client):
    syrup = await _with_values(editor_client, "Test Syrup")

    await _put(editor_client, syrup, _form_payload("Test Syrup", **VALUES))

    ingredient = await _get(editor_client, syrup)
    assert ingredient["parent_id"] is None
    assert ingredient["path"] == f"/{syrup}/"
    for field in VALUE_FIELDS:
        assert ingredient[field] == pytest.approx(VALUES[field])


@pytest.mark.asyncio
async def test_form_payload_for_top_level_parent_keeps_paths(editor_client):
    # A parent's measured values are rolled up from its children by a
    # database trigger, so only the hierarchy is checked here.
    gin = await _create(editor_client, "Gin")
    london_dry = await _create(editor_client, "London Dry Gin", parent_id=gin)

    await _put(editor_client, gin, _form_payload("Gin"))

    ingredient = await _get(editor_client, gin)
    assert ingredient["parent_id"] is None
    assert ingredient["path"] == f"/{gin}/"
    child = await _get(editor_client, london_dry)
    assert child["parent_id"] == gin
    assert child["path"] == f"/{gin}/{london_dry}/"
