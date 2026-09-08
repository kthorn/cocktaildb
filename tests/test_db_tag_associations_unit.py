"""Tag insertion contracts at the database execution boundary."""

from unittest.mock import Mock

import pytest

from api.db.db_core import Database


@pytest.mark.parametrize("is_private", [False, True])
@pytest.mark.parametrize("row_count", [0, 1])
def test_tag_association_reports_whether_a_row_was_inserted(is_private, row_count):
    db = Database.__new__(Database)
    db.execute_query = Mock(return_value={"rowCount": row_count})

    result = db.add_recipe_tag(11, 23, is_private, "owner")

    assert result is bool(row_count)
    db.execute_query.assert_called_once()
    sql, parameters = db.execute_query.call_args.args
    assert "ON CONFLICT(recipe_id, tag_id) DO NOTHING" in sql
    assert parameters == {"recipe_id": 11, "tag_id": 23}


@pytest.mark.parametrize("is_private", [False, True])
def test_tag_association_preserves_database_errors(is_private):
    db = Database.__new__(Database)
    error = RuntimeError("database unavailable")
    db.execute_query = Mock(side_effect=error)

    with pytest.raises(RuntimeError) as raised:
        db.add_recipe_tag(11, 23, is_private, "owner")

    assert raised.value is error
