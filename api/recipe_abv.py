"""Pure ingredient-only ABV calculation and display metadata."""

# ruff: noqa: FURB157

from decimal import (
    ROUND_CEILING,
    ROUND_FLOOR,
    ROUND_HALF_UP,
    Decimal,
    InvalidOperation,
    localcontext,
)
from math import isfinite
from typing import Any

TOP_UP_VOLUME_ML = Decimal("88.7205")
RINSE_VOLUME_ML = Decimal("1")
UNKNOWN_MIN_PERCENT = Decimal("0")
UNKNOWN_MAX_PERCENT = Decimal("100")
WIDTH_CUTOFF_PERCENT = Decimal("20")
ONE = Decimal("1")
ZERO = Decimal("0")


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _label(ingredient: dict[str, Any]) -> str:
    name = ingredient.get("ingredient_name")
    if name is not None:
        return str(name)
    return f"Ingredient {ingredient.get('ingredient_id', 'unknown')}"


def _unit_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    name = value.strip().casefold()
    return name or None


def _volume_for_ingredient(
    ingredient: dict[str, Any], label: str
) -> tuple[Decimal | None, bool, bool, str | None]:
    """Return modeled volume, estimate flag, invalid flag, and an explanation."""
    unit = _unit_name(ingredient.get("unit_name"))
    amount_value = ingredient.get("amount")
    amount = None

    if amount_value is not None:
        amount = _as_decimal(amount_value)
        if amount is None or amount < ZERO:
            return (
                None,
                False,
                True,
                f"Invalid quantity for {label}; ABV cannot be calculated.",
            )
        if amount == ZERO:
            return None, False, False, None

    if unit == "each":
        return (
            None,
            True,
            False,
            f"Excluded counted ingredient {label}; no liquid volume was modeled.",
        )
    if unit == "to top":
        return (
            TOP_UP_VOLUME_ML,
            True,
            False,
            f"Assumed {TOP_UP_VOLUME_ML} mL for to top ingredient {label}.",
        )
    if unit == "to rinse":
        return (
            RINSE_VOLUME_ML,
            True,
            False,
            f"Assumed {RINSE_VOLUME_ML} mL for to rinse ingredient {label}.",
        )
    if unit is None:
        return (
            None,
            False,
            True,
            f"Unknown volume for {label}; a volume unit is required.",
        )
    if amount is None:
        return (
            None,
            False,
            True,
            f"Unknown volume for {label}; an amount is required.",
        )

    conversion = _as_decimal(ingredient.get("conversion_to_ml"))
    if conversion is None or conversion <= ZERO:
        return (
            None,
            False,
            True,
            f"Unknown volume for {label}; its conversion to mL is invalid.",
        )
    with localcontext() as context:
        context.prec = 50
        volume = amount * conversion
    if not volume.is_finite() or volume <= ZERO:
        return (
            None,
            False,
            True,
            f"Unknown volume for {label}; its modeled volume is invalid.",
        )
    return volume, False, False, None


def _json_number(value: Decimal) -> float | None:
    if value == ZERO:
        return 0.0
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    return number if isfinite(number) else None


def _append_note(notes: list[str], seen: set[str], note: str) -> None:
    if note not in seen:
        seen.add(note)
        notes.append(note)


def _unknown(notes: list[str]) -> dict[str, Any]:
    return {
        "status": "unknown",
        "min_percent": None,
        "max_percent": None,
        "display": "Unknown",
        "notes": notes,
    }


def _point_display(value: Decimal) -> str:
    if ZERO < value < ONE:
        return "<1%"
    return f"{value.quantize(ONE, rounding=ROUND_HALF_UP):.0f}%"


def _interval_display(low: Decimal, high: Decimal) -> str:
    lower = low.quantize(ONE, rounding=ROUND_FLOOR)
    upper = high.quantize(ONE, rounding=ROUND_CEILING)
    return f"{lower:.0f}–{upper:.0f}%"


def calculate_recipe_abv(
    ingredients: list[dict], ranges: dict[int, dict]
) -> dict[str, Any]:
    """Calculate an ingredient-only, pre-dilution ABV interval."""
    notes: list[str] = []
    seen_notes: set[str] = set()
    contributions: list[tuple[Decimal, Decimal, Decimal]] = []
    estimated = False
    invalid = False

    for ingredient in ingredients:
        label = _label(ingredient)
        volume, row_estimated, row_invalid, volume_note = _volume_for_ingredient(
            ingredient, label
        )
        if volume_note:
            _append_note(notes, seen_notes, volume_note)
        estimated = estimated or row_estimated
        if row_invalid:
            invalid = True
            continue
        if volume is None:
            continue

        ingredient_id = ingredient.get("ingredient_id")
        try:
            strength = ranges.get(ingredient_id) if ingredient_id is not None else None
        except TypeError:
            strength = None
        if not isinstance(strength, dict):
            _append_note(
                notes,
                seen_notes,
                f"Missing strength data for {label}; no ABV bound was invented.",
            )
            invalid = True
            continue

        low = _as_decimal(strength.get("min_percent_abv"))
        high = _as_decimal(strength.get("max_percent_abv"))
        if (
            low is None
            or high is None
            or low < UNKNOWN_MIN_PERCENT
            or high > UNKNOWN_MAX_PERCENT
            or low > high
        ):
            _append_note(
                notes,
                seen_notes,
                f"Invalid strength data for {label}; no ABV bound was invented.",
            )
            invalid = True
            continue

        source = strength.get("source")
        if source != "recorded":
            estimated = True
            if source == "unknown":
                _append_note(
                    notes,
                    seen_notes,
                    f"Unknown strength for {label}; assuming 0–100%.",
                )
            else:
                ingredient_display = (
                    _point_display(low) if low == high else _interval_display(low, high)
                )
                _append_note(notes, seen_notes, f"{label}: {ingredient_display}")

        contributions.append((volume, low, high))

    if invalid:
        return _unknown(notes)

    with localcontext() as context:
        context.prec = 50
        total_volume = sum((volume for volume, _, _ in contributions), ZERO)
        if not total_volume.is_finite() or total_volume <= ZERO:
            _append_note(
                notes,
                seen_notes,
                "No positive modeled liquid volume was available.",
            )
            return _unknown(notes)

        low_sum = sum((volume * low for volume, low, _ in contributions), ZERO)
        high_sum = sum((volume * high for volume, _, high in contributions), ZERO)
        width_sum = sum(
            (volume * (high - low) for volume, low, high in contributions), ZERO
        )
        low_percent = low_sum / total_volume
        high_percent = high_sum / total_volume

        if (
            not low_percent.is_finite()
            or not high_percent.is_finite()
            or not width_sum.is_finite()
        ):
            _append_note(
                notes,
                seen_notes,
                "Calculated ABV bounds were not finite.",
            )
            return _unknown(notes)

        min_percent = _json_number(low_percent)
        max_percent = _json_number(high_percent)
        if min_percent is None or max_percent is None:
            _append_note(
                notes,
                seen_notes,
                "Calculated ABV bounds cannot be represented as finite JSON numbers.",
            )
            return _unknown(notes)

        if width_sum > WIDTH_CUTOFF_PERCENT * total_volume:
            _append_note(
                notes,
                seen_notes,
                "The ABV interval is wider than 20 percentage points.",
            )
            return {
                "status": "unknown",
                "min_percent": min_percent,
                "max_percent": max_percent,
                "display": "Unknown",
                "notes": notes,
            }

        narrow = width_sum <= total_volume
        display = (
            _point_display((low_percent + high_percent) / 2)
            if narrow
            else _interval_display(low_percent, high_percent)
        )
        if narrow:
            notes = []
        return {
            "status": "estimated" if estimated else "calculated",
            "min_percent": min_percent,
            "max_percent": max_percent,
            "display": display,
            "notes": notes,
        }
