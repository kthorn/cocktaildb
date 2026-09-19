"""Real independent transactions must behave like one serial ordering."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest.mock import patch
import pytest
from core.exceptions import CocktailDBException


def race(*operations):
    barrier = Barrier(len(operations))

    def run(operation):
        barrier.wait(timeout=5)
        try:
            return operation()
        except CocktailDBException as error:
            return error.status_code

    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        futures = [pool.submit(run, op) for op in operations]
        return [future.result(timeout=10) for future in futures]


def test_concurrent_ensure_creates_exactly_one_group(db_instance):
    db = db_instance
    results = race(
        lambda: db.ensure_user_has_group("alice"),
        lambda: db.ensure_user_has_group("alice"),
    )
    assert results[0]["id"] == results[1]["id"]
    assert len(db.execute_query("SELECT * FROM user_groups")) == 1
    assert len(db.execute_query("SELECT * FROM user_group_members")) == 1


def test_same_user_concurrent_joins_are_serial(db_instance_with_data):
    db = db_instance_with_data
    db.add_user_ingredients_bulk("alice", [1])
    b = db.ensure_user_has_group("bob")
    c = db.ensure_user_has_group("carol")
    results = race(
        lambda: db.join_group_by_code("alice", b["invite_code"]),
        lambda: db.join_group_by_code("alice", c["invite_code"]),
    )
    assert all(isinstance(result, dict) for result in results)
    assert {row["ingredient_id"] for row in db.get_user_ingredients("alice")} == {1}
    assert (
        len(
            db.execute_query(
                "SELECT * FROM user_group_members WHERE cognito_user_id=%s", ("alice",)
            )
        )
        == 1
    )


def test_reciprocal_kicks_only_one_succeeds(db_instance):
    db = db_instance
    group = db.ensure_user_has_group("alice")
    db.join_group_by_code("bob", group["invite_code"])
    results = race(
        lambda: db.remove_group_member("alice", group["id"], "bob"),
        lambda: db.remove_group_member("bob", group["id"], "alice"),
    )
    assert sorted(results) == [True, 403]
    assert len(db.execute_query("SELECT * FROM user_groups")) == 2


def test_rotation_and_join_use_one_serial_order(db_instance):
    db = db_instance
    group = db.ensure_user_has_group("alice")
    results = race(
        lambda: db.regenerate_invite_code("alice", group["id"]),
        lambda: db.join_group_by_code("bob", group["invite_code"]),
    )
    if results[1] == 404:
        assert db.get_user_group("bob") is None
    else:
        assert db.get_user_group("bob")["id"] == group["id"]


def test_stale_inventory_write_waits_for_kick_and_is_rejected(db_instance_with_data):
    db = db_instance_with_data
    group = db.ensure_user_has_group("alice")
    db.join_group_by_code("bob", group["invite_code"])
    moved = Event()
    release = Event()
    write_started = Event()
    original = db._move_membership

    def pause(cursor, user_id, source, destination):
        original(cursor, user_id, source, destination)
        moved.set()
        assert release.wait(5)

    def write():
        write_started.set()
        return db.add_group_ingredient("bob", group["id"], 2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        with patch.object(db, "_move_membership", side_effect=pause):
            kicked = pool.submit(db.remove_group_member, "alice", group["id"], "bob")
            assert moved.wait(5)
            added = pool.submit(write)
            assert write_started.wait(5)
            release.set()
            assert kicked.result(timeout=10)
            with pytest.raises(CocktailDBException) as error:
                added.result(timeout=10)
            assert error.value.status_code == 403
    assert db.get_user_ingredients("alice") == []
    assert db.get_user_ingredients("bob") == []


def test_join_and_write_copy_is_consistent(db_instance_with_data):
    db = db_instance_with_data
    source = db.ensure_user_has_group("alice")
    target = db.ensure_user_has_group("bob")
    results = race(
        lambda: db.join_group_by_code("alice", target["invite_code"]),
        lambda: db.add_group_ingredient("alice", source["id"], 2),
    )
    rows = db.get_user_ingredients("alice")
    assert {row["ingredient_id"] for row in rows} == (
        set() if results[1] == 403 else {2}
    )


def test_parent_remove_child_add_preserves_hierarchy(db_instance_with_data):
    db = db_instance_with_data
    group = db.ensure_user_has_group("alice")
    db.add_user_ingredient("alice", 1)

    def remove():
        try:
            return db.remove_group_ingredient("alice", group["id"], 1)
        except ValueError:
            return "blocked"

    race(remove, lambda: db.add_group_ingredient("alice", group["id"], 8))
    assert {row["ingredient_id"] for row in db.get_user_ingredients("alice")} == {1, 8}


def test_kick_and_join_do_not_lose_inventory_or_membership(db_instance_with_data):
    db = db_instance_with_data
    source = db.ensure_user_has_group("alice")
    destination = db.ensure_user_has_group("carol")
    db.add_user_ingredients_bulk("alice", [1, 2])
    db.join_group_by_code("bob", source["invite_code"])
    kicked, joined = race(
        lambda: db.remove_group_member("alice", source["id"], "bob"),
        lambda: db.join_group_by_code("bob", destination["invite_code"]),
    )
    assert kicked is True or kicked == 404
    assert joined["id"] == destination["id"]
    assert db.get_user_group("bob")["id"] == destination["id"]
    assert {r["ingredient_id"] for r in db.get_user_ingredients("bob")} == {1, 2}
    assert (
        len(
            db.execute_query(
                "SELECT * FROM user_group_members WHERE cognito_user_id=%s", ("bob",)
            )
        )
        == 1
    )
    assert len(db.execute_query("SELECT * FROM user_groups")) == (
        3 if kicked is True else 2
    )
