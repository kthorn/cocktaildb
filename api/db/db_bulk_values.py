from decimal import Decimal

from .db_core import Database

ALLOWED_VALUE_FIELDS = {
    "percent_abv",
    "sugar_g_per_l",
    "titratable_acidity_g_per_l",
}


def bulk_update_ingredient_values(
    db: Database,
    updates: dict[int, dict[str, Decimal]],
    *,
    overwrite: bool = False,
    expected_names: dict[int, str] | None = None,
    expected_values: dict[int, dict[str, Decimal | None]] | None = None,
) -> None:
    """Atomically update measured values for multiple ingredients."""
    expected_names = expected_names or {}
    expected_values = expected_values or {}
    for fields in [*updates.values(), *expected_values.values()]:
        if not set(fields).issubset(ALLOWED_VALUE_FIELDS):
            raise ValueError("Unsupported ingredient value field")

    conn = None
    try:
        conn = db._get_connection()
        cursor = conn.cursor()
        field_indexes = {
            "percent_abv": 1,
            "sugar_g_per_l": 2,
            "titratable_acidity_g_per_l": 3,
        }
        ingredient_ids = sorted(
            set(updates) | set(expected_names) | set(expected_values)
        )
        for ingredient_id in ingredient_ids:
            cursor.execute(
                """
                SELECT name::text, percent_abv, sugar_g_per_l,
                       titratable_acidity_g_per_l
                FROM ingredients
                WHERE id = %(id)s
                FOR UPDATE
                """,
                {"id": ingredient_id},
            )
            ingredient = cursor.fetchone()
            if ingredient is None or (
                ingredient_id in expected_names
                and ingredient[0] != expected_names[ingredient_id]
            ):
                raise ValueError(
                    f"Ingredient {ingredient_id} changed during validation"
                )
            for field, expected_value in expected_values.get(ingredient_id, {}).items():
                current_value = ingredient[field_indexes[field]]
                if current_value != expected_value:
                    requested_value = updates.get(ingredient_id, {}).get(
                        field, expected_value
                    )
                    raise ValueError(
                        f"{ingredient[0]} ({ingredient_id}): {field} is {current_value}, "
                        f"CSV requested {requested_value}"
                    )

        for ingredient_id in sorted(updates):
            fields = updates[ingredient_id]
            if not fields:
                raise ValueError("Unsupported ingredient value field")
            for field in sorted(fields):
                parameters = {
                    "id": ingredient_id,
                    "value": fields[field],
                    "overwrite": overwrite,
                    "expected_name": expected_names.get(ingredient_id),
                }
                if field == "percent_abv":
                    cursor.execute(
                        """
                        UPDATE ingredients SET percent_abv = %(value)s
                        WHERE id = %(id)s
                          AND (%(overwrite)s OR percent_abv IS NULL)
                          AND (%(expected_name)s IS NULL OR name::text = %(expected_name)s)
                        """,
                        parameters,
                    )
                elif field == "sugar_g_per_l":
                    cursor.execute(
                        """
                        UPDATE ingredients SET sugar_g_per_l = %(value)s
                        WHERE id = %(id)s
                          AND (%(overwrite)s OR sugar_g_per_l IS NULL)
                          AND (%(expected_name)s IS NULL OR name::text = %(expected_name)s)
                        """,
                        parameters,
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE ingredients SET titratable_acidity_g_per_l = %(value)s
                        WHERE id = %(id)s
                          AND (%(overwrite)s OR titratable_acidity_g_per_l IS NULL)
                          AND (%(expected_name)s IS NULL OR name::text = %(expected_name)s)
                        """,
                        parameters,
                    )
                if cursor.rowcount != 1:
                    raise ValueError(
                        f"Ingredient {ingredient_id} changed during validation"
                    )
        conn.commit()
        cursor.close()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            db._return_connection(conn)
