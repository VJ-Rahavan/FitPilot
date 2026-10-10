"""Weight units. Stored in kilograms; pounds are the default for display and input."""

import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

Unit = Literal["lb", "kg"]

KG_PER_LB = Decimal("0.45359237")  # exact by definition

_UNIT_ALIASES: dict[str, Unit] = {
    "lb": "lb",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    "kg": "kg",
    "kgs": "kg",
    "kilo": "kg",
    "kilos": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
}


def parse_unit(value: str | None, default: Unit = "lb") -> Unit:
    """Map spoken or written unit names to "lb" or "kg". None/empty → `default`."""
    if value is None or not value.strip():
        return default
    key = re.sub(r"[^a-z]", "", value.lower())
    try:
        return _UNIT_ALIASES[key]
    except KeyError:
        raise ValueError(f"Unknown weight unit: {value!r}") from None


def to_kg(weight: float | Decimal, unit: Unit) -> Decimal:
    w = Decimal(str(weight))
    kg = w if unit == "kg" else w * KG_PER_LB
    return kg.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def from_kg(weight_kg: float | Decimal, unit: Unit) -> Decimal:
    kg = Decimal(str(weight_kg))
    return kg if unit == "kg" else kg / KG_PER_LB


def round_weight(weight: Decimal, unit: Unit) -> Decimal:
    """Round to a sensible spoken precision: whole pounds, or the nearest 0.5 kg."""
    if unit == "lb":
        return weight.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return (weight * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / 2


def display_weight(weight_kg: float | Decimal, unit: Unit) -> Decimal:
    """Stored kg → rounded value in the user's unit."""
    return round_weight(from_kg(weight_kg, unit), unit)


def _fmt_number(value: Decimal) -> str:
    """Decimal → plain string without trailing zeros: 225.0 → "225", 102.50 → "102.5"."""
    s = f"{value:f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def format_weight(weight_kg: float | Decimal, unit: Unit, *, spoken: bool = True) -> str:
    """e.g. "225 pounds", "102.5 kilograms" (spoken) or "225 lb" (short)."""
    value = display_weight(weight_kg, unit)
    number = _fmt_number(value)
    if not spoken:
        return f"{number} {unit}"
    if unit == "lb":
        word = "pound" if value == 1 else "pounds"
    else:
        word = "kilogram" if value == 1 else "kilograms"
    return f"{number} {word}"
