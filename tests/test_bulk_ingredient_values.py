import pytest


@pytest.mark.asyncio
async def test_bulk_values_updates_multiple_fields_for_existing_ingredients(
    editor_client, db_instance
):
    db_instance.execute_query(
        "INSERT INTO ingredients (name, path) VALUES (%(name)s, %(path)s)",
        {"name": "Test Bourbon", "path": "/1/"},
    )
    ingredient = db_instance.execute_query(
        "SELECT id FROM ingredients WHERE name = %(name)s",
        {"name": "Test Bourbon"},
    )[0]
    csv_text = (
        "ingredient_id,ingredient_name,field,value,unit,note\n"
        f"{ingredient['id']},Test Bourbon,percent_abv,45,percent,ignored\n"
        f"{ingredient['id']},Test Bourbon,sugar_g_per_l,2.5,g/L,ignored\n"
    )

    response = await editor_client.post(
        "/ingredients/bulk-values",
        content=csv_text,
        headers={"Content-Type": "text/csv"},
    )

    assert response.status_code == 200
    assert response.json() == {"updated_count": 2, "unchanged_count": 0, "errors": []}
    updated = db_instance.get_ingredient(ingredient["id"])
    assert updated["percent_abv"] == 45
    assert updated["sugar_g_per_l"] == 2.5


@pytest.mark.asyncio
async def test_bulk_values_conflict_rolls_back_every_value(editor_client, db_instance):
    db_instance.execute_query(
        """
        INSERT INTO ingredients (name, path, percent_abv) VALUES
        ('Blank Ingredient', '/1/', NULL),
        ('Curated Ingredient', '/2/', 40)
        """
    )
    ingredients = db_instance.execute_query(
        "SELECT id, name FROM ingredients ORDER BY name"
    )
    ingredient_ids = {
        ingredient["name"]: ingredient["id"] for ingredient in ingredients
    }
    csv_text = (
        "ingredient_id,ingredient_name,field,value\n"
        f"{ingredient_ids['Blank Ingredient']},Blank Ingredient,percent_abv,20\n"
        f"{ingredient_ids['Curated Ingredient']},Curated Ingredient,percent_abv,45\n"
    )

    response = await editor_client.post(
        "/ingredients/bulk-values",
        content=csv_text,
        headers={"Content-Type": "text/csv"},
    )

    assert response.status_code == 409
    assert "already has percent_abv=40" in response.json()["detail"]
    blank = db_instance.get_ingredient(ingredient_ids["Blank Ingredient"])
    assert blank["percent_abv"] is None


@pytest.mark.asyncio
async def test_bulk_values_rejects_mismatched_ingredient_name(
    editor_client, db_instance
):
    db_instance.execute_query(
        "INSERT INTO ingredients (name, path) VALUES ('Lime Juice', '/1/')"
    )
    ingredient = db_instance.execute_query(
        "SELECT id FROM ingredients WHERE name = 'Lime Juice'"
    )[0]
    csv_text = (
        "ingredient_id,ingredient_name,field,value\n"
        f"{ingredient['id']},Lemon Juice,titratable_acidity_g_per_l,46\n"
    )

    response = await editor_client.post(
        "/ingredients/bulk-values",
        content=csv_text,
        headers={"Content-Type": "text/csv"},
    )

    assert response.status_code == 400
    assert "does not match" in response.json()["detail"]


@pytest.mark.asyncio
async def test_bulk_values_requires_editor_access(test_client_memory):
    response = await test_client_memory.post(
        "/ingredients/bulk-values",
        content="ingredient_id,ingredient_name,field,value\n1,Lime Juice,percent_abv,1\n",
        headers={"Content-Type": "text/csv"},
    )

    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_single_ingredient_update_persists_measurement_fields(
    editor_client, db_instance
):
    db_instance.execute_query(
        "INSERT INTO ingredients (name, path) VALUES ('Test Vermouth', '/1/')"
    )
    ingredient = db_instance.execute_query(
        "SELECT id FROM ingredients WHERE name = 'Test Vermouth'"
    )[0]

    response = await editor_client.put(
        f"/ingredients/{ingredient['id']}",
        json={
            "percent_abv": 15.5,
            "sugar_g_per_l": 120,
            "titratable_acidity_g_per_l": 5,
        },
    )

    assert response.status_code == 200
    updated = db_instance.get_ingredient(ingredient["id"])
    assert updated["percent_abv"] == 15.5
    assert updated["sugar_g_per_l"] == 120
    assert updated["titratable_acidity_g_per_l"] == 5
