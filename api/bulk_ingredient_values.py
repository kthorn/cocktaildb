import csv
import io
from decimal import Decimal, InvalidOperation

BULK_VALUE_LIMITS = {
    "percent_abv": 100,
    "sugar_g_per_l": 1000,
    "titratable_acidity_g_per_l": 100,
}


def parse_bulk_ingredient_values(csv_text: str) -> list[dict]:
    """Parse and validate ingredient value rows from CSV."""
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")), strict=True)
    required = {"ingredient_id", "ingredient_name", "field", "value"}
    try:
        fieldnames = reader.fieldnames
        csv_rows = list(reader)
    except csv.Error as error:
        raise ValueError(f"Invalid CSV: {error}") from None
    if not fieldnames or not required.issubset(fieldnames):
        raise ValueError(f"CSV must include columns: {', '.join(sorted(required))}")
    if len(fieldnames) != len(set(fieldnames)):
        raise ValueError("CSV cannot contain duplicate columns")
    if len(csv_rows) > 200:
        raise ValueError("CSV cannot contain more than 200 ingredient values")

    values = []
    for row_number, row in enumerate(csv_rows, start=2):
        try:
            if None in row or any(cell is None for cell in row.values()):
                raise ValueError
            ingredient_id = int(row["ingredient_id"] or "")
            ingredient_name = row["ingredient_name"] or ""
            field = (row["field"] or "").strip()
            value = Decimal(row["value"] or "")
            if ingredient_id <= 0 or not ingredient_name.strip():
                raise ValueError
            if field not in BULK_VALUE_LIMITS:
                raise ValueError
            if not value.is_finite() or not 0 <= value <= BULK_VALUE_LIMITS[field]:
                raise ValueError
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError(f"Invalid ingredient value at row {row_number}") from None
        values.append(
            {
                "ingredient_id": ingredient_id,
                "ingredient_name": ingredient_name,
                "field": field,
                "value": value,
            }
        )

    if not values:
        raise ValueError("CSV must contain at least one ingredient value")
    return values
