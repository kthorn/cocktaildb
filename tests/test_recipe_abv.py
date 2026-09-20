# ruff: noqa: FURB157

from decimal import Decimal

import pytest

from api.recipe_abv import calculate_recipe_abv


def row(i, amount, unit="ml", factor=1, name=None):
    return {
        "ingredient_id": i,
        "ingredient_name": name or f"Ingredient {i}",
        "amount": amount,
        "unit_name": unit,
        "conversion_to_ml": factor,
    }


def strength(lo, hi, source="recorded", family_id=1, family_name="Family"):
    return {
        "min_percent_abv": lo,
        "max_percent_abv": hi,
        "observation_count": 1 if source != "unknown" else 0,
        "family_id": family_id if source != "unknown" else None,
        "family_name": family_name if source != "unknown" else None,
        "source": source,
    }


def test_small_unknown_has_useful_integer_range():
    result = calculate_recipe_abv(
        [row(1, 60), row(2, 5)],
        {1: strength(40, 40), 2: strength(0, 100, "unknown")},
    )
    assert result["status"] == "estimated"
    assert result["display"] == "Estimated 36–45%"
    assert result["min_percent"] > 36


def test_exactly_twenty_points_is_displayable():
    result = calculate_recipe_abv(
        [row(1, 80), row(2, 20)],
        {1: strength(0, 0), 2: strength(0, 100, "unknown")},
    )
    assert result["display"] == "Estimated 0–20%"
    assert result["status"] == "estimated"


@pytest.mark.parametrize(
    ("value", "display"),
    [(Decimal("26.5"), "27%"), (0, "0%"), (0.4, "<1%")],
)
def test_point_display_rounds_half_up_and_protects_small_positive(value, display):
    result = calculate_recipe_abv([row(1, 10)], {1: strength(value, value)})
    assert result["display"] == display


@pytest.mark.parametrize(
    ("lo", "hi", "display"),
    [(Decimal("10.1"), Decimal("20.1"), "Estimated 10–21%"), (0, 0, "Estimated 0%")],
)
def test_interval_display_rounds_outward(lo, hi, display):
    result = calculate_recipe_abv([row(1, 10)], {1: strength(lo, hi, "family")})
    assert result["display"] == display


def test_decimal_float_and_int_inputs_are_combined_without_binary_drift():
    result = calculate_recipe_abv(
        [row(1, Decimal("10")), row(2, 10.0), row(3, 10)],
        {
            1: strength(10, 10),
            2: strength(20, 20),
            3: strength(30, 30),
        },
    )
    assert result["min_percent"] == pytest.approx(20)
    assert result["max_percent"] == pytest.approx(20)
    assert result["display"] == "20%"


@pytest.mark.parametrize(
    ("width", "status"),
    [(Decimal("19.9999"), "estimated"), (Decimal("20.0001"), "unknown")],
)
def test_width_cutoff_is_checked_before_display_rounding(width, status):
    result = calculate_recipe_abv([row(1, 100)], {1: strength(0, width, "unknown")})
    assert result["status"] == status


def test_inferred_point_is_estimated_even_when_endpoints_match_recorded_point():
    recorded = calculate_recipe_abv([row(1, 10)], {1: strength(40, 40)})
    inferred = calculate_recipe_abv([row(1, 10)], {1: strength(40, 40, "family")})
    assert recorded["status"] == "calculated"
    assert inferred["status"] == "estimated"
    assert recorded["display"] == "40%"
    assert inferred["display"] == "Estimated 40%"


@pytest.mark.parametrize("amount", [float("nan"), float("inf"), -1, Decimal("-0.1")])
def test_invalid_amount_returns_unknown_with_no_bounds(amount):
    result = calculate_recipe_abv([row(1, amount)], {1: strength(40, 40)})
    assert result["status"] == "unknown"
    assert result["min_percent"] is None
    assert result["max_percent"] is None
    assert any("quantity" in note.lower() for note in result["notes"])


@pytest.mark.parametrize("factor", [None, 0, -1, float("nan"), float("inf")])
def test_invalid_conversion_returns_unknown(factor):
    result = calculate_recipe_abv([row(1, 10, factor=factor)], {1: strength(40, 40)})
    assert result["status"] == "unknown"
    assert result["min_percent"] is None
    assert result["max_percent"] is None
    assert any("volume" in note.lower() for note in result["notes"])


@pytest.mark.parametrize(
    "ingredient",
    [row(1, 10, unit=None), row(1, None), row(1, 10, unit="pinch", factor=None)],
)
def test_missing_or_non_volume_rows_are_unknown(ingredient):
    result = calculate_recipe_abv([ingredient], {1: strength(40, 40)})
    assert result["status"] == "unknown"
    assert result["min_percent"] is None
    assert result["max_percent"] is None


def test_unknown_strength_mapping_is_not_silently_turned_into_zero_to_hundred():
    result = calculate_recipe_abv([row(42, 10)], {})
    assert result["status"] == "unknown"
    assert result["min_percent"] is None
    assert result["max_percent"] is None
    assert any(
        "Ingredient 42" in note and "strength" in note for note in result["notes"]
    )


@pytest.mark.parametrize("unit", [" TO TOP ", "To Top"])
def test_top_uses_the_approved_per_row_volume(unit):
    result = calculate_recipe_abv(
        [row(1, 99, unit=unit), row(2, 10)],
        {1: strength(40, 40), 2: strength(0, 0)},
    )
    expected = Decimal("88.7205") * Decimal("40") / (Decimal("88.7205") + Decimal("10"))
    assert result["min_percent"] == pytest.approx(float(expected))
    assert result["max_percent"] == pytest.approx(float(expected))
    assert any("88.7205" in note for note in result["notes"])


def test_rinse_uses_one_ml_per_row_without_multiplying_positive_amount():
    result = calculate_recipe_abv(
        [row(1, 99, unit=" tO rInSe "), row(2, 10)],
        {1: strength(40, 40), 2: strength(0, 0)},
    )
    expected = Decimal("40") / Decimal("11")
    assert result["min_percent"] == pytest.approx(float(expected))
    assert result["max_percent"] == pytest.approx(float(expected))
    assert any("1 mL" in note for note in result["notes"])


@pytest.mark.parametrize("amount", [None, 0, 1])
def test_each_is_excluded_for_missing_zero_or_positive_amount(amount):
    result = calculate_recipe_abv(
        [row(1, amount, unit=" EACH "), row(2, 10)],
        {2: strength(40, 40)},
    )
    expected_status = "estimated" if amount in (None, 1) else "calculated"
    assert result["status"] == expected_status
    assert result["display"] == (
        "Estimated 40%" if expected_status == "estimated" else "40%"
    )
    if amount in (1, None):
        assert any("counted" in note.lower() for note in result["notes"])


@pytest.mark.parametrize("unit", ["each", "to top", "to rinse"])
def test_special_units_with_explicit_zero_contribute_nothing(unit):
    result = calculate_recipe_abv(
        [row(1, 0, unit=unit), row(2, 10)],
        {2: strength(40, 40)},
    )
    assert result["status"] == "calculated"
    assert result["display"] == "40%"


def test_top_missing_amount_is_permitted_but_regular_missing_amount_is_not():
    top = calculate_recipe_abv([row(1, None, unit="to top")], {1: strength(40, 40)})
    regular = calculate_recipe_abv([row(1, None)], {1: strength(40, 40)})
    assert top["status"] == "estimated"
    assert regular["status"] == "unknown"


@pytest.mark.parametrize(
    "ingredients",
    [[], [row(1, 0)], [row(1, 1, unit="each")]],
)
def test_empty_zero_and_all_excluded_recipes_have_no_denominator(ingredients):
    result = calculate_recipe_abv(ingredients, {1: strength(40, 40)})
    assert result["status"] == "unknown"
    assert result["min_percent"] is None
    assert result["max_percent"] is None
    assert result["display"] == "Unknown"


def test_names_are_preserved_as_text_and_duplicate_notes_are_deduplicated():
    name = "<Gin & Tonic>"
    result = calculate_recipe_abv(
        [row(1, None, unit="to top", name=name), row(1, 2, unit="to top", name=name)],
        {1: strength(40, 40)},
    )
    assert any(name in note for note in result["notes"])
    assert len(result["notes"]) == len(set(result["notes"]))


def test_wide_interval_preserves_raw_bounds_and_reports_unknown():
    result = calculate_recipe_abv(
        [row(1, 30), row(2, 30)],
        {1: strength(0, 100, "unknown"), 2: strength(0, 0)},
    )
    assert result["status"] == "unknown"
    assert result["min_percent"] == 0
    assert result["max_percent"] == pytest.approx(50)
    assert result["display"] == "Unknown"


def test_invalid_strength_is_unknown_without_invented_bounds():
    result = calculate_recipe_abv([row(1, 10)], {1: strength(float("nan"), 40)})
    assert result["status"] == "unknown"
    assert result["min_percent"] is None
    assert result["max_percent"] is None
    assert any("strength" in note.lower() for note in result["notes"])
