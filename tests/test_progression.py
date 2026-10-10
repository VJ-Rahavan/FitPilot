from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from server.services.progression import SessionPerformance, group_sessions, step_for, suggest
from server.services.records import detect_pr, estimated_1rm
from server.services.units import display_weight, to_kg

T0 = datetime(2026, 9, 1, 18, tzinfo=UTC)


def perf(days: int, lb: float, reps: tuple[int, ...]) -> SessionPerformance:
    return SessionPerformance(T0 + timedelta(days=days), to_kg(lb, "lb"), reps)


def run(history, equipment="barbell", unit="lb", sets=3, reps=5):
    return suggest(history, target_sets=sets, target_reps=reps, equipment=equipment, unit=unit)


def lb(s) -> Decimal:
    return display_weight(s.weight_kg, "lb")


def test_no_history():
    s = run([])
    assert s.action == "start" and s.weight_kg is None


def test_bodyweight():
    assert run([perf(0, 0, (5, 5, 5))], equipment="bodyweight").action == "bodyweight"


def test_single_session_holds():
    s = run([perf(0, 185, (5, 5, 5))])
    assert s.action == "hold" and lb(s) == 185


def test_two_hits_increase_by_5_lb():
    s = run([perf(0, 185, (5, 5, 5)), perf(7, 185, (5, 5, 5))])
    assert s.action == "increase" and lb(s) == 190


def test_hit_after_weight_jump_holds():
    """The previous hit was at a lighter weight, so only one hit at the current weight."""
    s = run([perf(0, 180, (5, 5, 5)), perf(7, 185, (5, 5, 5))])
    assert s.action == "hold" and lb(s) == 185


def test_one_miss_holds():
    s = run([perf(0, 185, (5, 5, 5)), perf(7, 185, (5, 5, 4))])
    assert s.action == "hold" and lb(s) == 185


def test_two_misses_reduce_10_percent():
    s = run([perf(0, 200, (5, 4, 4)), perf(7, 200, (5, 5, 3))])
    assert s.action == "decrease" and lb(s) == 180


def test_fewer_sets_than_prescribed_is_a_miss():
    s = run([perf(0, 185, (5, 5)), perf(7, 185, (5, 5))])
    assert s.action == "decrease"


def test_dumbbell_step_is_smaller():
    s = run([perf(0, 25, (12, 12, 12)), perf(7, 25, (12, 12, 12))], equipment="dumbbell", reps=12)
    assert lb(s) == Decimal("27.5")
    assert step_for("dumbbell", "lb") == Decimal("2.5")


def test_kg_steps():
    hist = [
        SessionPerformance(T0, Decimal("100"), (5, 5, 5)),
        SessionPerformance(T0 + timedelta(days=7), Decimal("100"), (5, 5, 5)),
    ]
    s = run(hist, unit="kg")
    assert s.weight_kg == Decimal("102.500")
    assert step_for("barbell", "kg") == Decimal("2.5")
    assert step_for("dumbbell", "kg") == Decimal("1.25")


def test_group_sessions_uses_top_weight_per_local_day():
    tz = ZoneInfo("Asia/Kolkata")
    rows = [
        (T0, 5, to_kg(135, "lb")),  # warm-up
        (T0 + timedelta(minutes=5), 5, to_kg(185, "lb")),
        (T0 + timedelta(minutes=8), 4, to_kg(185, "lb")),
        (T0 + timedelta(days=7), 5, to_kg(185, "lb")),
    ]
    sessions = group_sessions(rows, tz)
    assert len(sessions) == 2
    assert display_weight(sessions[0].weight_kg, "lb") == 185
    assert sessions[0].reps == (5, 4)


def test_detect_pr():
    w = to_kg(185, "lb")
    assert (
        detect_pr(
            weight_kg=w, reps=5, previous_max_weight_kg=None, previous_max_reps_at_weight=None
        )
        is None
    )
    assert (
        detect_pr(
            weight_kg=w,
            reps=5,
            previous_max_weight_kg=to_kg(180, "lb"),
            previous_max_reps_at_weight=None,
        )
        == "weight"
    )
    assert (
        detect_pr(
            weight_kg=w,
            reps=6,
            previous_max_weight_kg=to_kg(190, "lb"),
            previous_max_reps_at_weight=5,
        )
        == "reps"
    )
    assert (
        detect_pr(
            weight_kg=w,
            reps=5,
            previous_max_weight_kg=to_kg(190, "lb"),
            previous_max_reps_at_weight=5,
        )
        is None
    )
    assert (
        detect_pr(
            weight_kg=Decimal(0),
            reps=10,
            previous_max_weight_kg=Decimal(0),
            previous_max_reps_at_weight=8,
            bodyweight=True,
        )
        == "reps"
    )


def test_estimated_1rm():
    assert estimated_1rm(Decimal(100), 1) == Decimal(100)
    assert estimated_1rm(Decimal(100), 5) > estimated_1rm(Decimal(100), 3)
