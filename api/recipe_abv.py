"""Recipe ABV display text and notes from the SQL ABV views.

The views in migration 19 own every ABV rule and number; this module only
turns their columns into the API's display string and explanatory notes.
"""

from decimal import Decimal
from math import isfinite
from typing import Any

# Still read by the ignore-minor volume helper in sql_queries until it moves to
# the recipe_ingredient_volumes view.
TOP_UP_VOLUME_ML = Decimal("88.7205")
RINSE_VOLUME_ML = Decimal("1")

_INVALID_NOTES = {
    "non_finite_amount": "Invalid quantity for {label}; ABV cannot be calculated.",
    "negative_amount": "Invalid quantity for {label}; ABV cannot be calculated.",
    "missing_unit": "Unknown volume for {label}; a volume unit is required.",
    "missing_amount": "Unknown volume for {label}; an amount is required.",
    "invalid_conversion": "Unknown volume for {label}; its conversion to mL is invalid.",
}

_UNKNOWN_REASON_NOTES = {
    "no_volume": "No positive modeled liquid volume was available.",
    "too_wide": "The ABV interval is wider than 20 percentage points.",
}


def display_text(low: int | None, high: int | None, below_one: bool | None) -> str:
    """Render SQL's whole-percent display values."""
    if low is None or high is None:
        return "Unknown"
    if below_one:
        return "<1%"
    if low == high:
        return f"{low}%"
    return f"{low}–{high}%"


def _label(row: dict[str, Any]) -> str:
    name = row.get("ingredient_name")
    if name is not None:
        return str(name)
    return f"Ingredient {row.get('ingredient_id', 'unknown')}"


def _json_number(value: Decimal | None) -> float | None:
    if value is None:
        return None
    if value == 0:
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


def _row_notes(row: dict[str, Any]) -> list[str]:
    label = _label(row)
    rule = row["volume_rule"]
    if rule == "invalid":
        return [_INVALID_NOTES[row["invalid_reason"]].format(label=label)]
    if rule == "counted":
        return [f"Excluded counted ingredient {label}; no liquid volume was modeled."]

    notes = []
    if rule == "top":
        notes.append(f"Assumed {row['volume_ml']} mL for to top ingredient {label}.")
    elif rule == "rinse":
        notes.append(f"Assumed {row['volume_ml']} mL for to rinse ingredient {label}.")
    if row["contributes"]:
        source = row["strength_source"]
        if source == "unknown":
            notes.append(f"Unknown strength for {label}; assuming 0–100%.")
        elif source == "family":
            strength = display_text(
                row["strength_display_low"],
                row["strength_display_high"],
                row["strength_display_below_one"],
            )
            notes.append(f"{label}: {strength}")
    return notes


def format_recipe_abv(bounds: dict[str, Any], rows: list[dict[str, Any]]) -> dict:
    """Build the API ABV payload from one recipe_abv row and its contribution rows.

    ``rows`` must be in ingredient display order so notes dedupe on first use.
    """
    notes: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for note in _row_notes(row):
            _append_note(notes, seen, note)

    aggregate_note = _UNKNOWN_REASON_NOTES.get(bounds["unknown_reason"])
    if aggregate_note:
        _append_note(notes, seen, aggregate_note)
    if bounds["narrow"]:
        notes = []

    return {
        "status": bounds["status"],
        "min_percent": _json_number(bounds["min_percent"]),
        "max_percent": _json_number(bounds["max_percent"]),
        "display": display_text(
            bounds["display_low"], bounds["display_high"], bounds["display_below_one"]
        ),
        "notes": notes,
    }
