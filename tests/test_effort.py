"""Live autoregulation and "beat last time": pure rules (no DB)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from server.services.effort import adjust_remaining, beat_last_time, effective_effort
from server.services.progression import SessionPerformance, suggest
from server.services.units import display_weight, to_kg

BAR = to_kg(45, "lb")


def adjust(effort, *, reps=6, target=6, lb=220, equipment="barbell", used=0, unit="lb"):
    weight = to_kg(lb, unit) if unit == "lb" else Decimal(str(lb))
    return adjust_remaining(
        effort=effort,
        reps=reps,
        target_reps=target,
        weight_kg=weight,
        equipment=equipment,
        unit=unit,
        bar_kg=BAR,
        easy_steps_used=used,
    )


def lb(adjustment) -> Decimal:
    return display_weight(adjustment.weight_kg, "lb")


def test_effective_effort():
    assert effective_effort(None, 6, 6) is None
    assert effective_effort("easy", 6, 6) == "easy"
    assert effective_effort("easy", 4, 6) == "failed"  # two short counts as failed
    assert effective_effort("hard", 5, 6) == "hard"


def test_easy_adds_a_step_up_to_the_cap():
    up = adjust("easy")
    assert up.action == "up" and lb(up) == 225
    assert adjust("easy", equipment="dumbbell", lb=25).weight_kg == to_kg("27.5", "lb")
    assert adjust("easy", used=2).action == "capped"
    assert adjust("easy", reps=5) is None  # said easy but missed reps: no extra weight


def test_hard_holds_and_failed_drops():
    hold = adjust("hard")
    assert hold.action == "hold" and lb(hold) == 220
    down = adjust("failed")
    assert down.action == "down" and lb(down) == 210  # -5%, on a 5 lb step
    assert lb(adjust("failed", lb=50)) == 45  # at least one step down
    assert lb(adjust("failed", lb=45)) == 45  # never below the empty bar
    kg = adjust("failed", lb=100, unit="kg")
    assert kg.weight_kg == Decimal("95.000")


def test_no_change_cases():
    assert adjust(None) is None
    assert adjust("ok") is None
    assert adjust("easy", equipment="bodyweight", lb=0) is None


@pytest.mark.parametrize(
    ("now", "last", "expected"),
    [
        ((6, 225), (6, 220), ("weight", to_kg(225, "lb") - to_kg(220, "lb"))),
        ((7, 220), (6, 220), ("reps", 1)),
        ((5, 225), (6, 220), None),  # heavier but fewer reps: not clearly better
        ((6, 220), (6, 220), None),
        ((5, 215), (6, 220), None),
    ],
)
def test_beat_last_time(now, last, expected):
    beat = beat_last_time(
        reps=now[0],
        weight_kg=to_kg(now[1], "lb"),
        last_reps=last[0],
        last_weight_kg=to_kg(last[1], "lb"),
        bodyweight=False,
    )
    assert (beat.kind, beat.amount) == expected if expected else beat is None


def test_beat_last_time_bodyweight():
    beat = beat_last_time(
        reps=9, weight_kg=Decimal(0), last_reps=8, last_weight_kg=Decimal(0), bodyweight=True
    )
    assert (beat.kind, beat.amount) == ("reps", 1)


T0 = datetime(2026, 9, 1, 18, tzinfo=UTC)


def perf(days, reps, efforts=()):
    return SessionPerformance(T0 + timedelta(days=days), to_kg(185, "lb"), reps, efforts)


def run(history):
    return suggest(history, target_sets=3, target_reps=5, equipment="barbell", unit="lb")


def test_hard_top_set_holds_progression():
    assert run([perf(0, (5, 5, 5)), perf(7, (5, 5, 5))]).action == "increase"
    held = run([perf(0, (5, 5, 5)), perf(7, (5, 5, 5), (None, None, "hard"))])
    assert held.action == "hold"


def test_failed_set_counts_as_a_miss():
    two_fails = run([perf(0, (5, 5, 5), ("failed",)), perf(7, (5, 5, 5), (None, "failed"))])
    assert two_fails.action == "decrease"


def test_easy_bumps_never_cause_a_deload():
    """The reviewer's case: two weeks of 'easy' bumps must not read as missed sessions."""
    from server.services.progression import group_sessions

    kg = Decimal
    rows = []
    for week, weights in enumerate([(100, 100, 100), (100, 102.5, 105), (105, 107.5, 110)]):
        for i, w in enumerate(weights):
            effort = None if week == 0 or i == 2 else "easy"
            rows.append((T0 + timedelta(days=7 * week, minutes=3 * i), 5, kg(str(w)), effort))
    sessions = group_sessions(rows, UTC)
    assert all(s.hit(3, 5) for s in sessions)
    result = suggest(sessions, target_sets=3, target_reps=5, equipment="barbell", unit="kg")
    assert result.action != "decrease"
    assert result.weight_kg == kg("110.000")


def test_failed_never_raises_or_fakes_a_drop():
    at_bar = adjust("failed", lb=45)
    assert at_bar.action == "hold" and lb(at_bar) == 45
    below_bar = adjust_remaining(
        effort="failed",
        reps=6,
        target_reps=6,
        weight_kg=Decimal(15),
        equipment="barbell",
        unit="kg",
        bar_kg=Decimal(20),
        easy_steps_used=0,
    )
    assert below_bar.action == "hold" and below_bar.weight_kg == Decimal(15)


def test_easy_adds_exactly_one_step_from_an_off_step_weight():
    assert lb(adjust("easy", lb=103)) == 108
