import pytest

from server.catalog.validation import ComponentValidationError, validate_components


def test_valid_components_round_trip():
    out = validate_components(
        [
            {"type": "metric", "label": "Sessions", "value": "3 / 4"},
            {
                "type": "session_card",
                "exercise": "Bench Press",
                "set_number": 2,
                "total_sets": 4,
                "target_reps": 6,
                "target_weight": 185,
                "unit": "lb",
            },
            {
                "type": "plate_diagram",
                "total_weight": 225,
                "bar_weight": 45,
                "plates_per_side": [45, 45],
            },
        ],
        "full",
    )
    assert out["display"] == "full"
    assert [c["type"] for c in out["components"]] == ["metric", "session_card", "plate_diagram"]
    assert "next_up" not in out["components"][1]  # None fields are dropped


def test_unknown_component_type_raises():
    with pytest.raises(ComponentValidationError):
        validate_components([{"type": "sparkle"}])


def test_unknown_key_raises():
    with pytest.raises(ComponentValidationError):
        validate_components([{"type": "text", "content": "hi", "colour": "red"}])


def test_empty_list_raises():
    with pytest.raises(ComponentValidationError):
        validate_components([])


def test_chart_keys_must_exist():
    with pytest.raises(ComponentValidationError):
        validate_components(
            [
                {
                    "type": "chart",
                    "chart_type": "line",
                    "data": [{"x": 1}],
                    "x_key": "x",
                    "series": [{"key": "missing"}],
                }
            ]
        )


def test_nesting_limit():
    node = {"type": "text", "content": "deep"}
    for _ in range(7):
        node = {"type": "card", "children": [node]}
    with pytest.raises(ComponentValidationError):
        validate_components([node])
