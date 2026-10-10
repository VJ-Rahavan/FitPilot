from collections import defaultdict
from datetime import date, timedelta

from server.db.seed import (
    HISTORY_WEEKS,
    SKIPPED_SESSIONS,
    STEP_LB,
    simulate_bodyweight,
    simulate_history,
)
from server.db.seed_data import EXERCISES, PLAN_DAYS

TODAY = date(2026, 10, 10)  # a Saturday


def test_history_is_deterministic():
    assert simulate_history(TODAY) == simulate_history(TODAY)


def test_history_spans_eight_weeks_with_skips():
    sessions = simulate_history(TODAY)
    planned = HISTORY_WEEKS * len(PLAN_DAYS)  # Saturday: the whole current week is past
    assert len(sessions) == planned - SKIPPED_SESSIONS
    assert all(s.on < TODAY for s in sessions)
    assert min(s.on for s in sessions) >= TODAY - timedelta(weeks=HISTORY_WEEKS)


def test_sessions_fall_on_plan_weekdays():
    for s in simulate_history(TODAY):
        assert s.on.weekday() == PLAN_DAYS[s.day_index][1]


def test_weights_progress_gradually():
    equipment = {e.name: e.equipment for e in EXERCISES}
    by_exercise: dict[str, list[float]] = defaultdict(list)
    for s in simulate_history(TODAY):
        for st in s.sets:
            if st.weight_lb:
                by_exercise[st.exercise].append(st.weight_lb)
    for name, weights in by_exercise.items():
        gain = weights[-1] - weights[0]
        # Light dumbbell lifts may stall: +5 lb is a large jump on a 25 lb dumbbell.
        if equipment[name] == "barbell":
            assert gain > 0, f"{name} never progressed"
        assert gain >= -STEP_LB, f"{name} went backwards"
        assert gain <= 30, f"{name} progressed unrealistically"


def test_some_sets_miss_reps():
    prescribed = {pe.exercise: pe.reps for _, _, items in PLAN_DAYS for pe in items}
    sets = [st for s in simulate_history(TODAY) for st in s.sets]
    missed = [st for st in sets if st.reps < prescribed[st.exercise]]
    assert 0 < len(missed) < len(sets) * 0.3


def test_plan_uses_catalog_exercises():
    names = {e.name for e in EXERCISES}
    for _, _, items in PLAN_DAYS:
        for pe in items:
            assert pe.exercise in names


def test_bodyweight_trend():
    weigh_ins = simulate_bodyweight(TODAY)
    assert len(weigh_ins) == HISTORY_WEEKS * 2
    assert weigh_ins[-1][1] > weigh_ins[0][1]
