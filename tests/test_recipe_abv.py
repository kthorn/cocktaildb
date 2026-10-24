# ruff: noqa: FURB157
"""Recipe ABV text formatting from the SQL view columns."""

from decimal import Decimal

import pytest

from api.recipe_abv import display_text, format_recipe_abv


def bounds(
    status="calculated",
    lo="40",
    hi="40",
    display=(40, 40, False),
    narrow=True,
    unknown_reason=None,
):
    low, high, below_one = display
    return {
        "recipe_id": 1,
        "status": status,
        "unknown_reason": unknown_reason,
        "min_percent": None if lo is None else Decimal(lo),
        "max_percent": None if hi is None else Decimal(hi),
        "narrow": narrow,
        "display_low": low,
        "display_high": high,
        "display_below_one": below_one,
    }


def row(
    name="Gin",
    rule="measured",
    reason=None,
    volume="10",
    source="recorded",
    strength=(40, 40, False),
    ingredient_id=1,
):
    low, high, below_one = strength
    return {
        "recipe_id": 1,
        "ingredient_id": ingredient_id,
        "ingredient_name": name,
        "volume_rule": rule,
        "invalid_reason": reason,
        "volume_ml": None if volume is None else Decimal(volume),
        "strength_source": source,
        "contributes": rule in ("top", "rinse", "measured"),
        "strength_display_low": low,
        "strength_display_high": high,
        "strength_display_below_one": below_one,
    }


WIDE = {"narrow": False, "status": "estimated", "lo": "10", "hi": "20"}


def wide(**overrides):
    return bounds(**{**WIDE, "display": (10, 20, False), **overrides})


@pytest.mark.parametrize(
    ("args", "text"),
    [
        ((None, None, None), "Unknown"),
        ((0, 0, True), "<1%"),
        ((0, 0, False), "0%"),
        ((27, 27, False), "27%"),
        ((36, 45, False), "36–45%"),
    ],
)
def test_display_text_formats_sql_display_values(args, text):
    assert display_text(*args) == text


def test_calculated_point_result_converts_numbers_to_floats():
    result = format_recipe_abv(bounds(), [row()])
    assert result == {
        "status": "calculated",
        "min_percent": 40.0,
        "max_percent": 40.0,
        "display": "40%",
        "notes": [],
    }
    assert isinstance(result["min_percent"], float)


def test_zero_bound_is_json_zero():
    result = format_recipe_abv(bounds(lo="0", hi="0", display=(0, 0, False)), [row()])
    assert result["min_percent"] == 0.0
    assert result["display"] == "0%"


def test_below_one_point_displays_less_than_one():
    result = format_recipe_abv(
        bounds(lo="0.4", hi="0.4", display=(0, 0, True)), [row()]
    )
    assert result["display"] == "<1%"


@pytest.mark.parametrize(
    ("reason", "note"),
    [
        ("non_finite_amount", "Invalid quantity for Gin; ABV cannot be calculated."),
        ("negative_amount", "Invalid quantity for Gin; ABV cannot be calculated."),
        ("missing_unit", "Unknown volume for Gin; a volume unit is required."),
        ("missing_amount", "Unknown volume for Gin; an amount is required."),
        (
            "invalid_conversion",
            "Unknown volume for Gin; its conversion to mL is invalid.",
        ),
    ],
)
def test_invalid_rows_explain_their_reason(reason, note):
    result = format_recipe_abv(
        bounds(
            status="unknown",
            lo=None,
            hi=None,
            display=(None, None, None),
            narrow=None,
            unknown_reason="invalid_row",
        ),
        [row(rule="invalid", reason=reason, volume=None)],
    )
    assert result == {
        "status": "unknown",
        "min_percent": None,
        "max_percent": None,
        "display": "Unknown",
        "notes": [note],
    }


@pytest.mark.parametrize(
    ("rule", "volume", "note"),
    [
        ("top", "88.7205", "Assumed 88.7205 mL for to top ingredient Soda."),
        ("rinse", "1", "Assumed 1 mL for to rinse ingredient Soda."),
        (
            "counted",
            None,
            "Excluded counted ingredient Soda; no liquid volume was modeled.",
        ),
    ],
)
def test_volume_assumptions_are_disclosed_on_wider_ranges(rule, volume, note):
    result = format_recipe_abv(
        wide(), [row(name="Soda", rule=rule, volume=volume), row()]
    )
    assert result["display"] == "10–20%"
    assert result["notes"] == [note]


def test_unknown_and_family_strengths_are_disclosed_in_row_order():
    result = format_recipe_abv(
        wide(),
        [
            row(name="Blanc Vermouth", source="family", strength=(15, 16, False)),
            row(name="Vodka", source="family", strength=(40, 40, False)),
            row(name="Mystery", source="unknown", strength=(0, 100, False)),
            row(name="Tiny", source="family", strength=(0, 0, True)),
        ],
    )
    assert result["notes"] == [
        "Blanc Vermouth: 15–16%",
        "Vodka: 40%",
        "Unknown strength for Mystery; assuming 0–100%.",
        "Tiny: <1%",
    ]


def test_non_contributing_rows_have_no_strength_notes():
    result = format_recipe_abv(
        wide(),
        [
            row(name="Zero", rule="zero", volume="0", source="unknown"),
            row(name="Bad", rule="invalid", reason="missing_amount", source="family"),
            row(name="Garnish", rule="counted", volume=None, source="unknown"),
        ],
    )
    assert result["notes"] == [
        "Unknown volume for Bad; an amount is required.",
        "Excluded counted ingredient Garnish; no liquid volume was modeled.",
    ]


def test_duplicate_notes_appear_once():
    result = format_recipe_abv(
        wide(),
        [
            row(name="<Gin & Tonic>", rule="top", volume="88.7205", source="family"),
            row(name="<Gin & Tonic>", rule="top", volume="88.7205", source="family"),
        ],
    )
    assert result["notes"] == [
        "Assumed 88.7205 mL for to top ingredient <Gin & Tonic>.",
        "<Gin & Tonic>: 40%",
    ]


def test_missing_name_falls_back_to_ingredient_id():
    result = format_recipe_abv(
        wide(), [row(name=None, ingredient_id=42, source="unknown")]
    )
    assert result["notes"] == ["Unknown strength for Ingredient 42; assuming 0–100%."]


def test_narrow_results_clear_notes():
    result = format_recipe_abv(
        bounds(status="estimated"),
        [row(source="family"), row(name="Lime", rule="counted", volume=None)],
    )
    assert result["display"] == "40%"
    assert result["notes"] == []


def test_no_volume_is_disclosed():
    result = format_recipe_abv(
        bounds(
            status="unknown",
            lo=None,
            hi=None,
            display=(None, None, None),
            narrow=None,
            unknown_reason="no_volume",
        ),
        [row(name="Lime", rule="counted", volume=None)],
    )
    assert result["display"] == "Unknown"
    assert result["notes"] == [
        "Excluded counted ingredient Lime; no liquid volume was modeled.",
        "No positive modeled liquid volume was available.",
    ]


def test_ingredientless_recipe_is_no_volume():
    result = format_recipe_abv(
        bounds(
            status="unknown",
            lo=None,
            hi=None,
            display=(None, None, None),
            narrow=None,
            unknown_reason="no_volume",
        ),
        [],
    )
    assert result["notes"] == ["No positive modeled liquid volume was available."]


def test_too_wide_keeps_raw_bounds_and_explains():
    result = format_recipe_abv(
        bounds(
            status="unknown",
            lo="0",
            hi="50",
            display=(None, None, None),
            narrow=None,
            unknown_reason="too_wide",
        ),
        [row(name="Mystery", source="unknown", strength=(0, 100, False))],
    )
    assert result == {
        "status": "unknown",
        "min_percent": 0.0,
        "max_percent": 50.0,
        "display": "Unknown",
        "notes": [
            "Unknown strength for Mystery; assuming 0–100%.",
            "The ABV interval is wider than 20 percentage points.",
        ],
    }
