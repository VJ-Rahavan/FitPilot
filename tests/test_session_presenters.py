"""Spoken text and components for the guided session tools (no DB)."""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

import pytest

from server.catalog.validation import validate_components
from server.presenters.sessions import present_complete, present_end, present_skip, present_start
from server.services.effort import Adjustment, Beat
from server.services.exercise_resolver import ExerciseEntry
from server.services.session_state import Position
from server.services.sessions import (
    CompleteResult,
    EndResult,
    SessionItem,
    SessionView,
    SkipResult,
    StartResult,
)
from server.services.units import to_kg

BENCH = ExerciseEntry(1, "Bench Press", equipment="barbell", form_cues=("Feet planted.",))
ROW = ExerciseEntry(2, "Barbell Row", equipment="barbell")
PULLUP = ExerciseEntry(3, "Pull-Up", equipment="bodyweight")
CURL = ExerciseEntry(4, "Dumbbell Curl", equipment="dumbbell")


def lb(x) -> Decimal:
    return to_kg(x, "lb")


def view(pos: Position, statuses=("pending",) * 4) -> SessionView:
    items = (
        SessionItem(BENCH, 4, 6, lb(185), statuses[0]),
        SessionItem(ROW, 4, 8, lb(145), statuses[1]),
        SessionItem(PULLUP, 3, 6, Decimal(0), statuses[2]),
        SessionItem(CURL, 3, 12, None, statuses[3]),
    )
    return SessionView("Upper A", "lb", items, pos)


def check(p, display="fragment"):
    validate_components(p.components, p.display)
    assert p.display == display
    assert p.text.strip().endswith((".", "!", "?"))
    return p.text


def types(p) -> list[str]:
    return [c["type"] for c in p.components]


# --- start ---------------------------------------------------------------------------------


def test_start_fresh():
    p = present_start(StartResult(view(Position(0, 0)), False, False, None))
    assert check(p, "full") == (
        "Starting Upper A, 4 exercises. First up: bench press, 4 sets of 6 at 185 pounds. "
        "Say done after each set."
    )
    assert "session_card" in types(p)
    buttons = [b for c in p.components if c["type"] == "layout" for b in c["children"]]
    assert [b["action"] for b in buttons] == ["complete_set", "skip_exercise", "end_session"]


def test_start_on_rest_day_and_after_stale():
    p = present_start(StartResult(view(Position(0, 0)), False, True, date(2026, 10, 9)))
    text = check(p, "full")
    assert text.startswith("I closed your unfinished workout from Friday.")
    assert "Today's a rest day, so let's do Upper A, 4 exercises." in text


def test_resume():
    p = present_start(StartResult(view(Position(0, 2)), True, False, None))
    assert check(p, "full") == (
        "Welcome back to Upper A. You're on bench press, set 3 of 4: 6 reps at 185 pounds."
    )


# --- complete_set ------------------------------------------------------------------------------


def _complete(
    set_number, reps, after: Position, pr=None, finished=False, ex=BENCH, w=185, target=185
):
    weight = Decimal(0) if ex is PULLUP else lb(w)
    target_kg = Decimal(0) if ex is PULLUP else (None if target is None else lb(target))
    return CompleteResult(ex, set_number, 4, reps, 6, weight, target_kg, pr, finished, view(after))


def test_complete_on_target_is_short():
    p = present_complete(_complete(1, 6, Position(0, 1)))
    assert check(p) == "Set 1 of 4 done."
    assert types(p) == ["session_card", "timer", "layout"]
    assert p.components[1]["seconds"] == 120


def test_complete_short_set_is_not_called_a_record():
    p = present_complete(_complete(2, 4, Position(0, 2), pr="weight"))
    assert check(p) == "Set 2 of 4 done: 4 reps."


def test_complete_changed_weight():
    p = present_complete(_complete(1, 6, Position(0, 1), w=190))
    assert check(p) == "Set 1 of 4 done at 190 pounds."
    first_time = present_complete(_complete(1, 5, Position(0, 1), w=95, target=None))
    assert check(first_time) == "Set 1 of 4 done: 5 reps at 95 pounds."


def test_complete_moves_to_next_exercise():
    p = present_complete(_complete(4, 6, Position(1, 0), finished=True))
    assert check(p) == (
        "Set 4 of 4 done. That's bench press done. Next up: barbell row, 4 sets of 8 at 145 pounds."
    )


def test_complete_next_needs_weight_choice_and_bodyweight():
    p = present_complete(_complete(3, 6, Position(3, 0), finished=True, ex=PULLUP))
    text = check(p)
    assert text.startswith("Set 3 of 4 done. That's pull-up done.")
    assert text.endswith("dumbbell curl, 3 sets of 12, choose your weight.")
    assert p.components[1]["seconds"] == 90


def test_complete_last_set():
    p = present_complete(_complete(3, 6, Position(4, 0), finished=True, ex=CURL, w=25, target=25))
    assert check(p) == "Set 3 of 4 done. That's the whole workout. Say end workout to wrap up."
    assert types(p) == ["alert"]


def test_complete_duplicate():
    r = CompleteResult(BENCH, 0, 0, 6, 6, lb(185), None, None, False, view(Position(0, 2)), True)
    assert check(present_complete(r)) == (
        "I already logged that set. You're on bench press, set 3 of 4."
    )


# --- skip ---------------------------------------------------------------------------------------


def test_skip():
    p = present_skip(SkipResult(BENCH, view(Position(1, 0))))
    assert check(p) == "Skipped bench press. Next up: barbell row, 4 sets of 8 at 145 pounds."
    partial = present_skip(SkipResult(BENCH, view(Position(1, 0)), partial=True))
    assert check(partial).startswith("Moving on from bench press. Next up: barbell row")
    last = present_skip(SkipResult(CURL, view(Position(4, 0))))
    assert check(last) == (
        "Skipped dumbbell curl. That was the last exercise. Say end workout to wrap up."
    )


# --- end ----------------------------------------------------------------------------------------


def test_end_summary():
    r = EndResult(
        unit="lb",
        day_name="Upper A",
        cancelled=False,
        duration=timedelta(minutes=52, seconds=20),
        sets=14,
        volume_kg=lb(12_380),
        exercises_done=3,
        skipped=("Dumbbell Curl",),
        prs=(("Bench Press", lb(190)),),
    )
    p = present_end(r)
    assert check(p, "full") == (
        "Nice work. You finished Upper A in 52 minutes: 14 sets, about 12,400 pounds lifted. "
        "New records on bench press! You skipped dumbbell curl."
    )


def test_end_caps_long_lists():
    names = ("Bench Press", "Barbell Row", "Pull-Up", "Dumbbell Curl", "Back Squat")
    r = EndResult(
        "lb",
        "Upper A",
        False,
        timedelta(minutes=40),
        10,
        lb(9000),
        2,
        skipped=names,
        prs=tuple((n, lb(100)) for n in names),
    )
    text = check(present_end(r), "full")
    assert "New records on bench press, barbell row and 3 more!" in text
    assert "You skipped bench press, barbell row and 3 more." in text


def test_end_long_and_cancelled():
    r = EndResult("lb", "Lower B", False, timedelta(hours=1, minutes=5), 18, lb(20_000), 5)
    assert "in 1 hour 5 minutes" in check(present_end(r), "full")
    cancelled = present_end(EndResult("lb", "Lower B", cancelled=True))
    assert check(cancelled, "full") == "You hadn't logged any sets, so I cancelled the workout."


# --- effort and "beat last time" ------------------------------------------------------------


def _effort(adjustment=None, beat=None, effort=None, pr=None, finished=False, after=None):
    base = _complete(1, 6, after or Position(0, 1), pr=pr, finished=finished)
    return replace(base, adjustment=adjustment, beat=beat, effort=effort)


def test_easy_raises_next_set():
    r = _effort(Adjustment("up", lb(225)), effort="easy")
    assert check(present_complete(r)) == (
        "Set 1 of 4 done. That felt easy, so your next set is 225 pounds."
    )


@pytest.mark.parametrize(
    ("action", "weight", "spoken"),
    [
        ("capped", 230, "That felt easy. Let's stay at 230 pounds for now."),
        ("hold", 220, "Tough one, so let's hold 220 pounds."),
        ("down", 210, "That one was tough, so let's drop your next set to 210 pounds."),
    ],
)
def test_other_adjustments(action, weight, spoken):
    r = _effort(Adjustment(action, lb(weight)), effort="hard")
    assert check(present_complete(r)) == f"Set 1 of 4 done. {spoken}"


def test_beat_last_time_spoken_and_record_wins():
    reps = _effort(beat=Beat("reps", 2))
    assert check(present_complete(reps)) == "Set 1 of 4 done. That beats last time by 2 reps."
    heavier = _effort(beat=Beat("weight", lb(5)))
    assert check(present_complete(heavier)) == (
        "Set 1 of 4 done. That's 5 pounds more than last time."
    )
    with_pr = _effort(beat=Beat("weight", lb(5)), pr="weight")
    assert "than last time" not in check(present_complete(with_pr))


def test_short_set_is_not_celebrated():
    short = replace(
        _complete(2, 4, Position(0, 2), pr="weight"),
        effort="failed",
        adjustment=Adjustment("down", lb(215)),
        beat=Beat("weight", lb(5)),
    )
    assert check(present_complete(short)) == (
        "Set 2 of 4 done: 4 reps. That one was tough, so let's drop your next set to 215 pounds."
    )


def test_effort_on_last_set_adds_nothing():
    r = _effort(effort="hard", finished=True, after=Position(1, 0))
    assert check(present_complete(r)) == (
        "Set 1 of 4 done. That's bench press done. Next up: barbell row, 4 sets of 8 at 145 pounds."
    )


def test_session_card_shows_last_time():
    p = present_start(
        StartResult(replace(view(Position(0, 0)), last_time=(5, lb(215))), False, False, None)
    )
    card = next(c for c in p.components if c["type"] == "session_card")
    assert card["last_time"] == "215 lb × 5"
