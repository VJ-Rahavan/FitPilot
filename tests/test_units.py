from decimal import Decimal

import pytest

from server.services.units import (
    display_weight,
    format_weight,
    from_kg,
    parse_unit,
    round_weight,
    to_kg,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("lb", "lb"),
        ("lbs", "lb"),
        ("Pounds", "lb"),
        ("pound", "lb"),
        ("kg", "kg"),
        ("KGs", "kg"),
        ("kilos", "kg"),
        ("kilograms", "kg"),
        ("kilo", "kg"),
        (None, "lb"),
        ("", "lb"),
        ("  ", "lb"),
    ],
)
def test_parse_unit(raw, expected):
    assert parse_unit(raw) == expected


def test_parse_unit_default_override():
    assert parse_unit(None, default="kg") == "kg"


def test_parse_unit_rejects_unknown():
    with pytest.raises(ValueError):
        parse_unit("stone")


def test_to_kg():
    assert to_kg(100, "kg") == Decimal("100.000")
    assert to_kg(225, "lb") == Decimal("102.058")
    assert to_kg(45, "lb") == Decimal("20.412")


@pytest.mark.parametrize("lb", [2.5, 5, 45, 135, 185, 225, 315, 405, 182.4])
def test_lb_round_trip_is_stable(lb):
    """Stored at 0.001 kg precision, pounds come back exactly after display rounding."""
    stored = to_kg(lb, "lb")
    assert abs(from_kg(stored, "lb") - Decimal(str(lb))) < Decimal("0.01")


def test_display_weight_rounding():
    assert display_weight(to_kg(225, "lb"), "lb") == Decimal("225")
    assert display_weight(Decimal("102.3"), "kg") == Decimal("102.5")
    assert display_weight(Decimal("102.2"), "kg") == Decimal("102")
    assert round_weight(Decimal("134.6"), "lb") == Decimal("135")


def test_format_weight():
    assert format_weight(to_kg(225, "lb"), "lb") == "225 pounds"
    assert format_weight(Decimal("102.5"), "kg") == "102.5 kilograms"
    assert format_weight(Decimal("100"), "kg") == "100 kilograms"
    assert format_weight(to_kg(1, "lb"), "lb") == "1 pound"
    assert format_weight(to_kg(225, "lb"), "lb", spoken=False) == "225 lb"
