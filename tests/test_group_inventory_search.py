import pytest
from core.exceptions import ValidationException


@pytest.mark.parametrize(
    "sort_by,paginate", [("name", False), ("name", True), ("random", True)]
)
def test_shared_inventory_search_binds_group(db_instance_with_data, sort_by, paginate):
    db = db_instance_with_data
    group = db.ensure_user_has_group("alice")
    db.add_user_ingredients_bulk("alice", [2, 11, 12])
    db.join_group_by_code("bob", group["invite_code"])
    result = db.search_recipes_paginated(
        {"inventory": True, "group_id": 999},
        user_id="bob",
        sort_by=sort_by,
        return_pagination=paginate,
    )
    recipes = result["recipes"] if paginate else result
    assert "Test Daiquiri" in {r["name"] for r in recipes}
    with pytest.raises(ValidationException):
        db.search_recipes_paginated({"inventory": True})
    assert db.search_recipes_paginated({"inventory": True}, user_id="empty") == []


def test_group_search_keeps_ratings_and_tags_private(db_instance_with_data):
    db = db_instance_with_data
    group = db.ensure_user_has_group("test-user-1")
    db.add_user_ingredients_bulk("test-user-1", [1, 8, 12, 13])
    db.join_group_by_code("test-user-2", group["invite_code"])
    first = db.search_recipes_paginated({"inventory": True}, user_id="test-user-1")
    second = db.search_recipes_paginated({"inventory": True}, user_id="test-user-2")
    a = next(r for r in first if r["id"] == 1)
    b = next(r for r in second if r["id"] == 1)
    assert a["user_rating"] == 4 and b["user_rating"] == 5
    assert any(tag["type"] == "private" for tag in a["tags"])
    assert not any(tag["type"] == "private" for tag in b["tags"])
    assert db.search_recipes_paginated(
        {"inventory": True, "tags": ["My Favorite"], "ingredients": ["Whiskey"]},
        user_id="test-user-1",
    )
    assert not db.search_recipes_paginated(
        {"inventory": True, "tags": ["My Favorite"]}, user_id="test-user-2"
    )


def test_inventory_search_one_connection(db_instance_with_data):
    from unittest.mock import patch

    db = db_instance_with_data
    db.add_user_ingredients_bulk("alice", [1, 8, 12, 13])
    with patch.object(db, "_get_connection", wraps=db._get_connection) as checked_out:
        db.search_recipes_paginated(
            {"inventory": True, "ingredients": ["Whiskey"], "tags": ["Classic"]},
            user_id="alice",
        )
    assert checked_out.call_count == 1


def test_shared_inventory_page_numbers_and_cursor_agree(db_instance_with_data):
    db = db_instance_with_data
    db.add_user_ingredients_bulk("alice", list(range(1, 14)))
    first = db.search_recipes_paginated(
        {"inventory": True}, user_id="alice", limit=2, return_pagination=True
    )
    second = db.search_recipes_paginated(
        {"inventory": True}, user_id="alice", limit=2, offset=2, return_pagination=True
    )
    cursor_page = db.search_recipes_paginated(
        {"inventory": True},
        user_id="alice",
        limit=2,
        cursor=first["next_cursor"],
        return_pagination=True,
    )
    assert {r["id"] for r in first["recipes"]}.isdisjoint(
        {r["id"] for r in second["recipes"]}
    )
    assert [r["id"] for r in second["recipes"]] == [
        r["id"] for r in cursor_page["recipes"]
    ]
    assert second["has_next"] is False
    assert (
        db.search_recipes_paginated(
            {"inventory": True}, user_id="alice", offset=999, return_pagination=True
        )["recipes"]
        == []
    )


@pytest.mark.parametrize("transition", ["leave", "kick"])
def test_personal_ratings_and_tags_survive_membership_changes(
    db_instance_with_data, transition
):
    db = db_instance_with_data
    group = db.ensure_user_has_group("test-user-1")
    db.add_user_ingredients_bulk("test-user-1", list(range(1, 14)))
    db.join_group_by_code("test-user-2", group["invite_code"])
    if transition == "leave":
        db.leave_group("test-user-2", group["id"], True)
    else:
        db.remove_group_member("test-user-1", group["id"], "test-user-2")
    for user, rating in [("test-user-1", 4), ("test-user-2", 5)]:
        recipes = db.search_recipes_paginated(
            {"inventory": True, "min_rating": rating, "max_rating": rating},
            user_id=user,
            rating_type="user",
            sort_by="avg_rating",
            return_pagination=True,
        )["recipes"]
        recipe = next(r for r in recipes if r["id"] == 1)
        assert recipe["user_rating"] == rating
        assert any(t["type"] == "private" for t in recipe["tags"]) == (
            user == "test-user-1"
        )
    assert not db.search_recipes_paginated(
        {"inventory": True, "tags": ["My Favorite"]}, user_id="test-user-2"
    )


def test_anonymous_search_does_not_create_membership(db_instance_with_data):
    db = db_instance_with_data
    assert db.search_recipes_paginated({})
    assert db.execute_query("SELECT * FROM user_groups") == []
    assert db.execute_query("SELECT * FROM user_group_members") == []
