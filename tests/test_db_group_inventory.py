from datetime import datetime
import pytest
from core.exceptions import CocktailDBException


def test_inventory_ancestors_bulk_and_isolation(db_instance_with_data):
    db = db_instance_with_data
    a = db.ensure_user_has_group("alice")
    b = db.ensure_user_has_group("bob")
    result = db.add_group_ingredient("alice", a["id"], 8)
    assert isinstance(result["added_at"], datetime)
    assert {r["ingredient_id"] for r in db.get_group_ingredients("alice", a["id"])} == {
        1,
        8,
    }
    assert db.get_group_ingredients("bob", b["id"]) == []
    with pytest.raises(ValueError, match="already exists"):
        db.add_group_ingredient("alice", a["id"], 8)
    with pytest.raises(ValueError, match="child ingredients"):
        db.remove_group_ingredient("alice", a["id"], 1)
    with pytest.raises(ValueError):
        db.remove_group_ingredients_bulk("alice", a["id"], [1])
    assert len(db.get_user_ingredients("alice")) == 2
    assert db.remove_group_ingredients_bulk("alice", a["id"], [1, 8, 999]) == {
        "removed_count": 2,
        "not_found_count": 1,
    }
    assert db.add_group_ingredients_bulk("alice", a["id"], [8, 8, 999]) == {
        "added_count": 1,
        "already_exists_count": 1,
        "failed_count": 1,
        "errors": ["Ingredient with ID 999 does not exist"],
    }
    assert {r["ingredient_id"] for r in db.get_user_ingredients("alice")} == {8}
    assert db.execute_query("SELECT * FROM user_ingredients") == []


@pytest.mark.parametrize(
    "method,args",
    [
        ("get_group_ingredients", ()),
        ("add_group_ingredient", (1,)),
        ("remove_group_ingredient", (1,)),
        ("add_group_ingredients_bulk", ([1],)),
        ("remove_group_ingredients_bulk", ([1],)),
        ("get_group_ingredient_recommendations", (10,)),
    ],
)
def test_inventory_authorization_all_methods(db_instance_with_data, method, args):
    group = db_instance_with_data.ensure_user_has_group("alice")
    with pytest.raises(CocktailDBException) as error:
        getattr(db_instance_with_data, method)("bob", group["id"], *args)
    assert error.value.status_code == 403


def test_shared_recommendations_match_legacy_wrapper(db_instance_with_data):
    db = db_instance_with_data
    group = db.ensure_user_has_group("alice")
    db.add_user_ingredients_bulk("alice", [8, 12])
    db.join_group_by_code("bob", group["invite_code"])
    result = db.get_group_ingredient_recommendations("bob", group["id"], 10)
    assert result and isinstance(result[0]["recipe_names"], list)
    assert result == db.get_ingredient_recommendations("alice", 10)
