import pytest


@pytest.mark.asyncio
async def test_create_ingredient_with_metadata(editor_client):
    payload = {
        "name": "Test Vermouth",
        "description": "Sweet",
        "percent_abv": 15.5,
        "sugar_g_per_l": 120.0,
        "titratable_acidity_g_per_l": 5.0,
        "url": "https://example.com/vermouth",
    }

    response = await editor_client.post("/ingredients", json=payload)
    assert response.status_code == 201
    body = response.json()

    assert body["percent_abv"] == 15.5
    assert body["sugar_g_per_l"] == 120.0
    assert body["titratable_acidity_g_per_l"] == 5.0
    assert body["url"] == "https://example.com/vermouth"
