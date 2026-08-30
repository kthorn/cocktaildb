import importlib
import unittest
from decimal import Decimal

parse_bulk_ingredient_values = importlib.import_module(
    "api.bulk_ingredient_values"
).parse_bulk_ingredient_values


class TestBulkIngredientValueParsing(unittest.TestCase):
    def test_accepts_candidate_csv_and_ignores_extra_columns(self):
        csv_text = (
            "ingredient_id,ingredient_name,field,value,unit,confidence,acid_equivalent,note\n"
            "431,Maker's Mark Bourbon,percent_abv,45,percent,high,,Official 90 proof\n"
        )

        self.assertEqual(
            parse_bulk_ingredient_values(csv_text),
            [
                {
                    "ingredient_id": 431,
                    "ingredient_name": "Maker's Mark Bourbon",
                    "field": "percent_abv",
                    "value": Decimal("45"),
                }
            ],
        )

    def test_preserves_ingredient_name_for_exact_matching(self):
        row = parse_bulk_ingredient_values(
            "ingredient_id,ingredient_name,field,value\n1,Lime Juice ,percent_abv,1\n"
        )[0]

        self.assertEqual(row["ingredient_name"], "Lime Juice ")

    def test_rejects_duplicate_headers(self):
        with self.assertRaisesRegex(ValueError, "duplicate columns"):
            parse_bulk_ingredient_values(
                "ingredient_id,ingredient_name,field,value,value\n"
                "1,Lime Juice,percent_abv,1,2\n"
            )

    def test_rejects_malformed_header_as_validation_error(self):
        with self.assertRaisesRegex(ValueError, "Invalid CSV"):
            parse_bulk_ingredient_values('"ingredient_id,ingredient_name,field,value\n')

    def test_rejects_rows_missing_ignored_extra_cells(self):
        with self.assertRaisesRegex(ValueError, "row 2"):
            parse_bulk_ingredient_values(
                "ingredient_id,ingredient_name,field,value,unit\n"
                "1,Lime Juice,percent_abv,1\n"
            )

    def test_rejects_rows_longer_than_header(self):
        with self.assertRaisesRegex(ValueError, "row 2"):
            parse_bulk_ingredient_values(
                "ingredient_id,ingredient_name,field,value\n"
                "1,Lime Juice,percent_abv,1,unexpected\n"
            )

    def test_rejects_short_rows_as_validation_errors(self):
        with self.assertRaisesRegex(ValueError, "row 2"):
            parse_bulk_ingredient_values(
                "ingredient_id,ingredient_name,field,value\n1,Lime Juice\n"
            )

    def test_rejects_unsupported_or_out_of_range_values(self):
        for field, value in (
            ("percent_abv", "101"),
            ("sugar_g_per_l", "1001"),
            ("titratable_acidity_g_per_l", "101"),
            ("url", "1"),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "row 2"):
                parse_bulk_ingredient_values(
                    "ingredient_id,ingredient_name,field,value\n"
                    f"1,Lime Juice,{field},{value}\n"
                )


if __name__ == "__main__":
    unittest.main()
