import asyncio
import importlib
import unittest
from decimal import Decimal

bulk_update_ingredient_values = importlib.import_module(
    "api.db.db_bulk_values"
).bulk_update_ingredient_values
upload_ingredient_values = importlib.import_module(
    "api.routes.ingredients"
).upload_ingredient_values


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.rowcount = 0
        self.locked_ids = []
        self.update_count = 0
        self.selected_row = None

    def execute(self, sql, parameters):
        if "FOR UPDATE" in sql:
            ingredient_id = parameters["id"]
            self.locked_ids.append(ingredient_id)
            self.selected_row = self.rows.get(ingredient_id)
            self.rowcount = int(self.selected_row is not None)
        else:
            self.update_count += 1
            self.rowcount = 1

    def fetchone(self):
        return self.selected_row

    def close(self):
        pass


class FakeConnection:
    def __init__(self, rows):
        self.cursor_instance = FakeCursor(rows)
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class FakeDatabase:
    def __init__(self, rows):
        self.connection = FakeConnection(rows)

    def _get_connection(self):
        return self.connection

    def _return_connection(self, connection):
        assert connection is self.connection

    def get_ingredient(self, ingredient_id):
        row = self.connection.cursor_instance.rows.get(ingredient_id)
        if row is None:
            return None
        return {
            "id": ingredient_id,
            "name": row[0],
            "percent_abv": row[1],
            "sugar_g_per_l": row[2],
            "titratable_acidity_g_per_l": row[3],
        }


class TestBulkIngredientValueTransaction(unittest.TestCase):
    def test_expected_name_is_checked_inside_update_transaction(self):
        db = FakeDatabase({7: ("Stored Name", None, None, None)})

        with self.assertRaisesRegex(ValueError, "changed during validation"):
            bulk_update_ingredient_values(
                db,
                {7: {"percent_abv": Decimal("45")}},
                expected_names={7: "Uploaded Name"},
                expected_values={7: {"percent_abv": None}},
            )

        self.assertTrue(db.connection.rolled_back)
        self.assertFalse(db.connection.committed)

    def test_no_op_values_are_revalidated_before_any_write(self):
        db = FakeDatabase({7: ("Lime Juice", Decimal("46"), None, None)})

        with self.assertRaises(ValueError) as raised:
            bulk_update_ingredient_values(
                db,
                {7: {"sugar_g_per_l": Decimal("2")}},
                expected_names={7: "Lime Juice"},
                expected_values={
                    7: {
                        "percent_abv": Decimal("45"),
                        "sugar_g_per_l": None,
                    }
                },
            )

        self.assertEqual(
            str(raised.exception),
            "Lime Juice (7): percent_abv is 46, CSV requested 45",
        )
        self.assertEqual(db.connection.cursor_instance.update_count, 0)
        self.assertTrue(db.connection.rolled_back)

    def test_all_no_op_upload_is_transactionally_revalidated(self):
        db = FakeDatabase({7: ("Lime Juice", Decimal("45"), None, None)})

        response = asyncio.run(
            upload_ingredient_values(
                "ingredient_id,ingredient_name,field,value\n"
                "7,Lime Juice,percent_abv,45\n",
                db,
                None,
            )
        )

        self.assertEqual(
            response,
            {"updated_count": 0, "unchanged_count": 1, "errors": []},
        )
        self.assertEqual(db.connection.cursor_instance.locked_ids, [7])

    def test_ingredients_are_locked_in_sorted_order(self):
        db = FakeDatabase(
            {
                1: ("One", None, None, None),
                2: ("Two", None, None, None),
            }
        )

        bulk_update_ingredient_values(
            db,
            {
                2: {"percent_abv": Decimal("20")},
                1: {"percent_abv": Decimal("10")},
            },
            expected_names={2: "Two", 1: "One"},
            expected_values={
                2: {"percent_abv": None},
                1: {"percent_abv": None},
            },
        )

        self.assertEqual(db.connection.cursor_instance.locked_ids, [1, 2])
        self.assertTrue(db.connection.committed)


if __name__ == "__main__":
    unittest.main()
