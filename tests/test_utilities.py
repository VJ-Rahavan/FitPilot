"""Utility tools: pure logic and spoken text (no DB)."""

from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from server.catalog.validation import validate_components
from server.presenters.utilities import (
    PAIN_ADVICE,
    present_form_cues,
    present_macros,
    present_plates,
    present_preferences,
    present_readiness,
)
from server.services.context import UserContext, UserFacingError
from server.services.exercise_resolver import ExerciseEntry
from server.services.preferences import PreferencesResult, parse_goal, parse_timezone
from server.services.readiness import Assessment, assess, lighten
from server.services.units import to_kg
from server.services.utilities import MacroResult, bar_for, macros_for, plates_for

D = Decimal


def check(p):
    validate_components(p.components, p.display)
    assert p.display == "fragment"
    assert p.text.endswith((".", "!", "?"))
    return p.text


# --- plates --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("weight", "unit", "bar", "per_side", "loadable"),
    [
        ("225", "lb", "45", ("45", "45"), "225"),
        ("185", "lb", "45", ("45", "25"), "185"),
        ("165", "lb", "45", ("45", "10", "5"), "165"),
        ("186", "lb", "45", ("45", "25"), "185"),
        ("50", "lb", "45", ("2.5",), "50"),
        ("100", "kg", "20", ("25", "15"), "100"),
        ("62.5", "kg", "20", ("20", "1.25"), "62.5"),
        ("61", "kg", "20", ("20",), "60"),
    ],
)
def test_plates_for(weight, unit, bar, per_side, loadable):
    r = plates_for(D(weight), unit, D(bar))
    assert r.per_side == tuple(D(p) for p in per_side)
    assert r.loadable == D(loadable)
    assert r.exact == (weight == loadable)


def test_plate_speech():
    assert check(present_plates(plates_for(D(225), "lb", D(45)))) == (
        "For 225 pounds, put two 45s on each side of the 45-pound bar."
    )
    assert check(present_plates(plates_for(D(165), "lb", D(45)))) == (
        "For 165 pounds, put a 45, a 10 and a 5 on each side of the 45-pound bar."
    )
    assert check(present_plates(plates_for(D(186), "lb", D(45)))) == (
        "I can't make exactly 186 pounds with standard plates. "
        "For 185 pounds, put a 45 and a 25 on each side of the 45-pound bar."
    )
    assert check(present_plates(plates_for(D(40), "lb", D(45)))) == (
        "40 pounds is lighter than the 45-pound bar."
    )
    assert check(present_plates(plates_for(D(45), "lb", D(45)))) == (
        "That's just the empty 45-pound bar."
    )
    assert check(present_plates(plates_for(D(100), "kg", D(20)))) == (
        "For 100 kilograms, put a 25 and a 15 on each side of the 20-kilogram bar."
    )
    diagram = present_plates(plates_for(D(186), "lb", D(45))).components[0]
    assert diagram["type"] == "plate_diagram" and diagram["remainder"] == 1.0


# --- form cues -----------------------------------------------------------------------------


def test_form_cues_speech():
    entry = ExerciseEntry(
        1,
        "Deadlift",
        form_cues=(
            "Bar over mid foot before you pull.",
            "Take the slack out of the bar first.",
            "Keep the bar close and push the floor away.",
        ),
    )
    assert check(present_form_cues(entry)) == (
        "Three cues for deadlift. First, bar over mid foot before you pull. Second, take the "
        "slack out of the bar first. Third, keep the bar close and push the floor away."
    )


# --- readiness -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "level"),
    [
        (dict(sleep_hours=8, soreness="none", energy="normal"), "full"),
        (dict(sleep_hours=6), "reduce"),
        (dict(soreness="moderate", energy="low"), "light"),
        (dict(sleep_hours=4.5), "light"),
        (dict(sleep_hours=4, soreness="severe"), "rest"),
        (dict(sleep_hours=6, energy="high"), "full"),  # high energy offsets short sleep
    ],
)
def test_assess_levels(kwargs, level):
    full = dict(sleep_hours=None, soreness=None, energy=None, notes=None) | kwargs
    assert assess(**full).level == level


@pytest.mark.parametrize(
    ("notes", "pain"),
    [
        ("my knee hurts a bit", True),
        ("sharp twinge in my shoulder", True),
        ("I think I tweaked my back", True),
        ("lower back pain", True),
        ("feeling great, a bit tired", False),
        ("legs are heavy", False),
    ],
)
def test_pain_detection(notes, pain):
    assert assess(sleep_hours=None, soreness=None, energy=None, notes=notes).pain_reported is pain


def test_assess_needs_input():
    with pytest.raises(UserFacingError):
        assess(sleep_hours=None, soreness=None, energy=None, notes=None)


def test_pain_alone_is_never_train_as_planned():
    a = assess(sleep_hours=8, soreness="none", energy="high", notes="my knee hurts")
    assert a.pain_reported and a.level == "reduce"
    flagged = assess(sleep_hours=None, soreness=None, energy=None, notes=None, pain_mentioned=True)
    assert flagged.pain_reported and flagged.level == "reduce"


def test_readiness_speech():
    assert check(present_readiness(Assessment("full"))) == (
        "You sound ready. Train as planned today."
    )
    light = check(present_readiness(Assessment("light", ("short sleep", "low energy"))))
    assert light == (
        "With short sleep and low energy, let's keep today light. "
        "I've taken 20 percent off today's weights and dropped a set."
    )
    rest = check(present_readiness(Assessment("rest", ("very little sleep", "a lot of soreness"))))
    assert rest.count("rest") == 1  # no repeated "rest day"
    pain = check(present_readiness(Assessment("reduce", (), pain_reported=True)))
    assert pain.startswith(f"Thanks for telling me. {PAIN_ADVICE}")
    assert "stop that exercise and see a doctor or physical therapist" in pain
    assert "train as planned" not in pain.lower() and "diagnos" not in pain.lower()
    in_session = check(
        present_readiness(Assessment("light", ("short sleep",), session_adjusted=True))
    )
    assert in_session.endswith("starting with the next exercise.")


def test_lighten_never_goes_below_the_bar():
    bar = to_kg(45, "lb")
    assert lighten(to_kg(45, "lb"), "light", "barbell", "lb", bar) == to_kg(45, "lb")
    assert lighten(to_kg(225, "lb"), "light", "barbell", "lb", bar) == to_kg(180, "lb")
    assert lighten(to_kg(25, "lb"), "light", "dumbbell", "lb", bar) == to_kg(20, "lb")


# --- preferences ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "goal"),
    [
        ("Strength", "strength"),
        ("build muscle", "muscle"),
        ("lose weight", "fat_loss"),
        ("fat-loss", "fat_loss"),
        ("general fitness", "general"),
    ],
)
def test_parse_goal(raw, goal):
    assert parse_goal(raw) == goal


def test_parse_goal_and_timezone_errors():
    with pytest.raises(UserFacingError):
        parse_goal("juggling")
    with pytest.raises(UserFacingError):
        parse_timezone("Mars/Olympus")
    with pytest.raises(UserFacingError):
        parse_timezone("Factory")


@pytest.mark.parametrize(
    ("spoken", "zone"),
    [
        ("America/New York", "America/New_York"),
        ("america/new_york", "America/New_York"),  # canonical case, so it works on Linux
        ("Eastern", "America/New_York"),
        ("pacific time", "America/Los_Angeles"),
        ("London", "Europe/London"),
        ("tokyo", "Asia/Tokyo"),
        ("Mumbai", "Asia/Kolkata"),
    ],
)
def test_parse_timezone(spoken, zone):
    assert parse_timezone(spoken) == zone


def test_bar_in_the_other_unit():
    def ctx(unit, bar_kg):
        return UserContext(1, unit, ZoneInfo("UTC"), None, None, bar_kg)

    assert bar_for(ctx("lb", to_kg(45, "lb")), "kg") == D(20)
    assert bar_for(ctx("kg", D(15)), "lb") == D(35)
    assert bar_for(ctx("kg", D(18)), "lb") == D(45)  # unknown bar: standard


def _prefs(**kw):
    base = dict(
        needs_setup=False,
        created=False,
        changes=(),
        unit="lb",
        bar_weight_kg=to_kg(45, "lb"),
        goal="strength",
        days_per_week=4,
        timezone="Asia/Kolkata",
    )
    return PreferencesResult(**(base | kw))


def test_preferences_speech():
    setup = check(present_preferences(_prefs(needs_setup=True)))
    assert setup.startswith("Let's set you up.")
    changed = check(
        present_preferences(
            _prefs(
                changes=("unit", "days_per_week"), unit="kg", bar_weight_kg=D(20), days_per_week=3
            )
        )
    )
    assert changed == (
        "Done. I'll use kilograms and plan for 3 days a week. "
        "Your current plan stays the same for now."
    )
    assert check(
        present_preferences(_prefs(changes=("bar_weight",), bar_weight_kg=to_kg(35, "lb")))
    ) == ("Done. I'll use a 35-pound bar.")
    assert check(present_preferences(_prefs())) == (
        "Those settings were already in place, so nothing changed."
    )


# --- macros --------------------------------------------------------------------------------


def test_macros_for():
    assert macros_for(D(80), "strength") == (2750, 145, 70, 385)
    calories, protein, *_ = macros_for(D(80), "fat_loss")
    assert calories == 2100 and protein == 175
    assert macros_for(D(80), None) == macros_for(D(80), "general")


def test_macros_speech():
    r = MacroResult(to_kg("184.2", "lb"), "lb", "strength", 2900, 150, 75, 400, True)
    assert check(present_macros(r)) == (
        "For strength at your latest weigh-in of 184.2 pounds, aim for about 2,900 calories "
        "a day. That's roughly 150 grams of protein, 75 grams of fat and 400 grams of carbs. "
        "Treat it as a starting point."
    )
