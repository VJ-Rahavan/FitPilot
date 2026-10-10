"""Spoken text and components for every tool, built from result objects (no DB)."""

from datetime import date
from decimal import Decimal

import pytest

from server.catalog.validation import validate_components
from server.presenters.speech import join_words, say_volume, sets_of_reps
from server.presenters.workouts import (
    present_body_metric,
    present_error,
    present_exercise_progress,
    present_log_workout,
    present_todays_workout,
    present_undo,
    present_weekly_summary,
)
from server.services.context import UserFacingError
from server.services.exercise_resolver import ExerciseEntry
from server.services.insights import fallback_insight
from server.services.progression import Suggestion
from server.services.units import to_kg
from server.services.workouts import (
    BodyMetricResult,
    ExerciseProgress,
    LogWorkoutResult,
    PlannedExercise,
    ProgressPoint,
    TodaysWorkout,
    UndoResult,
    WeeklySummary,
)

BENCH = ExerciseEntry(1, "Bench Press", equipment="barbell")
PULLUP = ExerciseEntry(2, "Pull-Up", equipment="bodyweight")
CURL = ExerciseEntry(3, "Dumbbell Curl", equipment="dumbbell")


def check(p, display="fragment"):
    """Every presentation must validate against the catalog and speak a full sentence."""
    validate_components(p.components, p.display)
    assert p.display == display
    assert p.text.strip().endswith((".", "!", "?"))
    assert "dashboard" not in p.text.lower() and "screen" not in p.text.lower()
    return p.text


def lb(x) -> Decimal:
    return to_kg(x, "lb")


# --- speech helpers ----------------------------------------------------------------------


def test_speech_helpers():
    assert join_words(["a"]) == "a"
    assert join_words(["a", "b", "c"]) == "a, b and c"
    assert sets_of_reps((5, 5, 5)) == "3 sets of 5"
    assert sets_of_reps((8, 8, 6)) == "3 sets of 8, 8 and 6"
    assert sets_of_reps((5,)) == "1 set of 5"
    assert say_volume(lb(24_460), "lb") == "about 24,500 pounds"
    assert say_volume(Decimal("455"), "kg") == "about 460 kilograms"


# --- log_workout -------------------------------------------------------------------------


def test_log_workout_plain():
    r = LogWorkoutResult(BENCH, 3, 5, lb(185), "lb", None, False, lb(190))
    assert check(present_log_workout(r)) == "Logged bench press: 3 sets of 5 at 185 pounds."


def test_log_workout_weight_pr():
    r = LogWorkoutResult(BENCH, 1, 3, lb(205), "lb", "weight", False, lb(200))
    text = check(present_log_workout(r))
    assert "new personal record, up from 200 pounds" in text


def test_log_workout_rep_pr_and_bodyweight():
    r = LogWorkoutResult(PULLUP, 4, 9, Decimal(0), "lb", "reps", False, Decimal(0))
    text = check(present_log_workout(r))
    assert text == "Logged pull-up: 4 sets of 9. That's a rep record at this weight!"


def test_log_workout_duplicate():
    r = LogWorkoutResult(BENCH, 3, 5, lb(185), "lb", None, True, None)
    assert "didn't log it twice" in check(present_log_workout(r))


def test_log_workout_kg_dumbbell_half_step():
    r = LogWorkoutResult(CURL, 3, 12, Decimal("11.25"), "kg", None, False, None)
    assert "at 11.25 kilograms" in check(present_log_workout(r))


# --- undo ---------------------------------------------------------------------------------


def test_undo():
    r = UndoResult("Bench Press", (8, 8, 6), lb(185), "lb", False)
    text = check(present_undo(r))
    assert text == "Removed your last log: bench press, 3 sets of 8, 8 and 6 at 185 pounds."
    assert check(present_undo(None)) == "There's nothing to undo yet."


# --- body metric ---------------------------------------------------------------------------


def test_body_metric_trend():
    r = BodyMetricResult(lb("184.2"), "lb", lb("1.4"), 7, "strength")
    p = present_body_metric(r)
    assert (
        check(p) == "Logged your bodyweight at 184.2 pounds. That's up 1.4 pounds from 7 days ago."
    )
    assert p.components[0]["good_direction"] == "up"


def test_body_metric_first_and_fat_loss():
    first = BodyMetricResult(Decimal("80"), "kg", None, None, "fat_loss")
    p = present_body_metric(first)
    assert check(p) == "Logged your bodyweight at 80 kilograms."
    assert p.components[0]["good_direction"] == "down"
    same = BodyMetricResult(Decimal("80"), "kg", Decimal("0.01"), 1, None)
    assert "same as yesterday" in check(present_body_metric(same))


# --- today --------------------------------------------------------------------------------


def test_todays_workout():
    w = TodaysWorkout(
        "lb",
        True,
        day_name="Upper A",
        items=(
            PlannedExercise(BENCH, 4, 6, Suggestion("increase", lb(190))),
            PlannedExercise(PULLUP, 4, 6, Suggestion("bodyweight", Decimal(0))),
            PlannedExercise(CURL, 3, 12, Suggestion("start", None)),
        ),
    )
    text = check(present_todays_workout(w), "full")
    assert text.startswith("Today is Upper A, 3 exercises.")
    assert "Bench press, 4 sets of 6 at 190 pounds." in text
    assert "Pull-up, 4 sets of 6." in text
    assert "pick a weight you can do with good form" in text
    assert "earned more weight on bench press" in text


def test_rest_day_and_no_plan():
    rest = TodaysWorkout("lb", True, next_day_name="Lower B", next_weekday="Friday")
    assert check(present_todays_workout(rest), "full") == (
        "Today is a rest day. Your next session is Lower B on Friday."
    )
    assert "don't have a training plan" in check(
        present_todays_workout(TodaysWorkout("lb", False)), "full"
    )


# --- weekly summary --------------------------------------------------------------------------


def _summary(**kw):
    base = dict(
        unit="lb",
        weeks_ago=0,
        week_start=date(2026, 10, 5),
        sessions=3,
        planned=4,
        volume_kg=lb(24_460),
        prev_volume_kg=lb(22_650),
        daily_volume_kg=tuple((date(2026, 10, 5 + i), lb(8000 if i < 3 else 0)) for i in range(7)),
        prs=(("Bench Press", lb(190)),),
        insight="Fit in one more session next week.",
        insight_is_fallback=True,
    )
    base.update(kw)
    return WeeklySummary(**base)


def test_weekly_summary():
    text = check(present_weekly_summary(_summary()), "full")
    assert text.startswith(
        "This week you trained 3 of 4 planned days and lifted about 24,500 pounds"
    )
    assert "up 8 percent from the week before" in text
    assert "New records on bench press." in text
    assert text.endswith("Coach's note: Fit in one more session next week.")


def test_weekly_summary_empty_and_past():
    empty = _summary(sessions=0, volume_kg=Decimal(0), prs=())
    assert check(present_weekly_summary(empty), "full").startswith(
        "You haven't logged any training this week yet."
    )
    last = _summary(weeks_ago=1)
    assert check(present_weekly_summary(last), "full").startswith("Last week you trained")


def test_fallback_insight_is_two_sentences():
    for kw in (
        dict(sessions=0, planned=4, volume_kg=Decimal(0), prev_volume_kg=Decimal(0)),
        dict(sessions=2, planned=4, volume_kg=Decimal(100), prev_volume_kg=Decimal(100)),
        dict(sessions=4, planned=4, volume_kg=Decimal(80), prev_volume_kg=Decimal(100)),
        dict(sessions=4, planned=4, volume_kg=Decimal(120), prev_volume_kg=Decimal(100)),
        dict(sessions=4, planned=4, volume_kg=Decimal(100), prev_volume_kg=Decimal(100)),
    ):
        text = fallback_insight(**kw)
        assert text.count(".") == 2, text


# --- exercise progress -------------------------------------------------------------------------


def test_exercise_progress_weighted():
    pts = (
        ProgressPoint(date(2026, 8, 17), lb(165), 6, 24),
        ProgressPoint(date(2026, 10, 5), lb(180), 6, 24),
    )
    p = ExerciseProgress(BENCH, "lb", 8, pts, lb(180), 6, date(2026, 10, 5))
    text = check(present_exercise_progress(p), "full")
    assert text == (
        "Over the last 8 weeks, across 2 sessions, your bench press went from 165 to "
        "180 pounds. Your best set was 180 pounds for 6 reps on October 5."
    )


def test_exercise_progress_bodyweight_and_empty():
    pts = (
        ProgressPoint(date(2026, 9, 1), Decimal(0), 6, 24),
        ProgressPoint(date(2026, 10, 1), Decimal(0), 8, 30),
    )
    p = ExerciseProgress(PULLUP, "lb", 8, pts, Decimal(0), 8, date(2026, 10, 1))
    assert "went from 6 to 8 reps" in check(present_exercise_progress(p), "full")
    empty = ExerciseProgress(BENCH, "lb", 4, ())
    assert check(present_exercise_progress(empty), "full") == (
        "You haven't logged bench press in the last 4 weeks."
    )


# --- errors -----------------------------------------------------------------------------------


@pytest.mark.parametrize("suggestions", [(), ("Bench Press", "Overhead Press")])
def test_error(suggestions):
    p = present_error(UserFacingError("Did you mean bench press or overhead press?", suggestions))
    assert check(p) == "Did you mean bench press or overhead press?"
