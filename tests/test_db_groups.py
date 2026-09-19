from unittest.mock import patch
import pytest
from core.exceptions import CocktailDBException


def inventory_ids(db, user):
    return {row["ingredient_id"] for row in db.get_user_ingredients(user)}


def test_personal_group_lifecycle(db_instance):
    db = db_instance
    group = db.ensure_user_has_group("alice")
    assert group["name"] == "My Bar"
    assert group["members"][0]["cognito_user_id"] == "alice"
    assert group["member_count"] == 1
    assert db.ensure_user_has_group("alice") == group
    assert db.get_user_group("unknown") is None
    other = db.create_group("bob", "Home", "a description")
    assert other["id"] != group["id"]
    with pytest.raises(CocktailDBException) as error:
        db.create_group("bob", "Replacement", None)
    assert error.value.status_code == 409
    assert db.get_user_group("bob")["id"] == other["id"]
    updated = db.update_group("bob", other["id"], {"description": None})
    assert updated["description"] is None
    assert updated["name"] == "Home"
    assert db.update_group("bob", other["id"], {}) == updated
    assert (
        db.regenerate_invite_code("bob", other["id"])["invite_code"]
        != other["invite_code"]
    )


@pytest.mark.parametrize(
    "method,args",
    [
        ("get_group_detail", ()),
        ("update_group", ({"name": "Stolen"},)),
        ("regenerate_invite_code", ()),
    ],
)
def test_group_requires_membership(db_instance, method, args):
    group = db_instance.ensure_user_has_group("alice")
    with pytest.raises(CocktailDBException) as error:
        getattr(db_instance, method)("bob", group["id"], *args)
    assert error.value.status_code == 403


def test_invalid_join_has_no_side_effects(db_instance):
    with pytest.raises(CocktailDBException) as error:
        db_instance.join_group_by_code("alice", "abcdef123456")
    assert error.value.status_code == 404
    assert db_instance.get_user_group("alice") is None
    assert db_instance.execute_query("SELECT * FROM user_groups") == []


def test_join_merge_and_same_group_noop(db_instance_with_data):
    db = db_instance_with_data
    a = db.ensure_user_has_group("alice")
    b = db.ensure_user_has_group("bob")
    db.add_user_ingredients_bulk("alice", [1, 2])
    db.add_user_ingredients_bulk("bob", [2, 3])
    original = db.execute_query(
        "SELECT * FROM group_ingredients WHERE group_id=%s AND ingredient_id=2",
        (b["id"],),
    )[0]
    joined = db.join_group_by_code("alice", b["invite_code"])
    assert joined["id"] == b["id"] and joined["member_count"] == 2
    assert inventory_ids(db, "alice") == {1, 2, 3}
    assert inventory_ids(db, "bob") == {1, 2, 3}
    assert (
        db.execute_query(
            "SELECT * FROM group_ingredients WHERE group_id=%s AND ingredient_id=2",
            (b["id"],),
        )[0]
        == original
    )
    assert db.join_group_by_code("alice", b["invite_code"]) == joined
    with pytest.raises(CocktailDBException) as error:
        db.join_group_by_code("bob", a["invite_code"])
    assert error.value.status_code == 404


@pytest.mark.parametrize("copy_inventory", [True, False])
def test_leave_inventory_choice(db_instance_with_data, copy_inventory):
    db = db_instance_with_data
    group = db.ensure_user_has_group("alice")
    db.add_user_ingredients_bulk("alice", [1, 2])
    db.join_group_by_code("bob", group["invite_code"])
    new = db.leave_group("bob", group["id"], copy_inventory)
    assert new["id"] != group["id"] and new["member_count"] == 1
    assert inventory_ids(db, "bob") == ({1, 2} if copy_inventory else set())
    assert inventory_ids(db, "alice") == {1, 2}
    with pytest.raises(CocktailDBException) as error:
        db.leave_group("bob", new["id"], True)
    assert error.value.status_code == 409


def test_kick_requires_actor_and_copies_inventory(db_instance_with_data):
    db = db_instance_with_data
    group = db.ensure_user_has_group("alice")
    db.add_user_ingredients_bulk("alice", [1, 2])
    db.join_group_by_code("bob", group["invite_code"])
    with pytest.raises(CocktailDBException) as error:
        db.remove_group_member("mallory", group["id"], "bob")
    assert error.value.status_code == 403
    with pytest.raises(CocktailDBException) as error:
        db.remove_group_member("alice", group["id"], "alice")
    assert error.value.status_code == 400
    db.remove_group_member("alice", group["id"], "bob")
    assert db.get_user_group("bob")["id"] != group["id"]
    assert inventory_ids(db, "bob") == {1, 2}
    with pytest.raises(CocktailDBException) as error:
        db.remove_group_member("alice", group["id"], "bob")
    assert error.value.status_code == 404


def test_transition_failure_rolls_back_copy_and_membership(db_instance_with_data):
    db = db_instance_with_data
    a = db.ensure_user_has_group("alice")
    b = db.ensure_user_has_group("bob")
    db.add_user_ingredients_bulk("alice", [1, 2])
    with patch.object(db, "_move_membership", side_effect=RuntimeError("injected")):
        with pytest.raises(RuntimeError):
            db.join_group_by_code("alice", b["invite_code"])
    assert db.get_user_group("alice")["id"] == a["id"]
    assert inventory_ids(db, "bob") == set()


def test_invite_collision_retry_and_connection_return(db_instance):
    db = db_instance
    original = db.ensure_user_has_group("alice")
    with patch(
        "api.db.group_inventory.secrets.token_hex",
        side_effect=[original["invite_code"], "123456abcdef"],
    ):
        with patch.object(
            db, "_return_connection", wraps=db._return_connection
        ) as returned:
            group = db.ensure_user_has_group("bob")
            assert returned.call_count == 1
    assert group["invite_code"] == "123456abcdef"


@pytest.mark.parametrize("outcome", ["success", "failure", "noop"])
def test_group_transaction_returns_one_idle_connection(db_instance, outcome):
    db = db_instance
    group = db.ensure_user_has_group("alice")
    states = []
    original_return = db._return_connection

    def returned(conn):
        states.append(conn.get_transaction_status())
        original_return(conn)

    with (
        patch.object(db, "_return_connection", side_effect=returned),
        patch.object(db, "_get_connection", wraps=db._get_connection) as acquired,
    ):
        if outcome == "failure":
            with patch.object(
                db,
                "_group_detail",
                side_effect=RuntimeError("injected response failure"),
            ):
                with pytest.raises(RuntimeError):
                    db.ensure_user_has_group("bob")
        elif outcome == "noop":
            assert db.join_group_by_code("alice", group["invite_code"]) == group
        else:
            assert db.get_group_detail("alice", group["id"]) == group
        assert acquired.call_count == 1
        assert states == [0]  # TRANSACTION_STATUS_IDLE: committed or rolled back.
    assert db.get_user_group("bob") is None
