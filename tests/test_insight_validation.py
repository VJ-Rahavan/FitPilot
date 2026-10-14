from datetime import date
from decimal import Decimal

import pytest

from server.jobs.insights import (
    MAX_CHARS,
    InsightRejected,
    LiftTrend,
    WeeklyMetrics,
    render_prompt,
    validate_insight,
)
from server.services.units import to_kg

TERMS = ["Bench Press", "Barbell Row"]
GOOD = (
    "Your bench press hit a new best of 190 pounds this week. "
    "Next week, add one paused set to your barbell row to break the stall."
)


def test_valid_insight_passes_unchanged():
    assert validate_insight(GOOD, TERMS) == GOOD


def test_normalizes_for_speech():
    raw = (
        "“Volume rose 8% and you set a PR on bench press.” Add a 2‑set back-off on rows next week."
    )
    assert validate_insight(raw, TERMS) == (
        "Volume rose 8 percent and you set a personal record on bench press. "
        "Add a 2-set back-off on rows next week."
    )


def test_spells_out_units():
    raw = "Your 175 lb bench press beat 170lbs. Hold 80kg on rows and stay tight."
    assert validate_insight(raw, TERMS) == (
        "Your 175-pound bench press beat 170 pounds. Hold 80 kilograms on rows and stay tight."
    )


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("**Great week.** Keep it up on bench press.", "markdown"),
        ("- Bench went up.\n- Row stalled.", "markdown"),
        ("Good week. Bench press is up. Rows stalled at 145.", "3 sentences"),
        ("Bench press is up. Ease off if your knee hurts.", "avoid pain"),
        ("Bench press is up. Add more protein this week.", "avoid pain"),
        ("Training went well this week. Stay consistent 3 days.", "did not mention"),
        ("Bench press went up to 190 pounds. Keep going", "full sentence"),
        ("Great consistency this week. Keep up the good work next week.", "did not mention"),
        (f"Bench press {'x' * MAX_CHARS}. Row up.", "over the"),
    ],
)
def test_rejects(text, reason):
    with pytest.raises(InsightRejected, match=reason):
        validate_insight(text, TERMS)


def _metrics(**overrides) -> WeeklyMetrics:
    fields = dict(
        week_start=date(2026, 10, 5),
        unit="lb",
        goal="strength",
        sessions=3,
        planned=4,
        volume_kg=to_kg(24460, "lb"),
        volume_change_pct=8,
        week_complete=True,
        records=[("Bench Press", Decimal("190"))],
        lifts=[
            LiftTrend("Bench Press", Decimal("190"), 6, Decimal("175"), 1),
            LiftTrend("Barbell Row", Decimal("145"), 8, Decimal("145"), 4),
        ],
    )
    fields.update(overrides)
    return WeeklyMetrics(**fields)


def test_prompt_has_only_metrics_with_units():
    prompt = render_prompt(_metrics())
    assert prompt.splitlines() == [
        "Goal: strength.",
        "This week: 3 of 4 planned sessions, total volume about 24,500 pounds, "
        "up 8 percent vs last week.",
        "New personal records (already announced): Bench Press 190 pounds.",
        "Bench Press: top set 190 pounds for 6 reps, was 175 pounds 4 weeks ago.",
        "Barbell Row: top set 145 pounds for 8 reps, was 145 pounds 4 weeks ago, "
        "same top weight for 4 sessions.",
        "Improving lifts: Bench Press.",
        "Stalled lifts: Barbell Row.",
    ]
    lowered = prompt.lower()
    for private in ("demo", "user", "email", "@", "id"):
        assert private not in lowered.split(), private


def test_prompt_for_week_in_progress_has_no_comparison():
    prompt = render_prompt(_metrics(week_complete=False, volume_change_pct=None))
    assert prompt.splitlines()[1] == (
        "This week so far (the week is not over): 3 of 4 planned sessions, "
        "total volume about 24,500 pounds."
    )


def test_numbers_from_metrics_count_as_specific():
    m = _metrics()
    assert {"190", "175", "145", "6", "8", "3", "4"} <= m.numbers
    assert validate_insight("Hold steady at 145 pounds on your top set.", [], m.numbers)


LIFTS = ["Back Squat", "Romanian Deadlift", "Dumbbell Curl", "Bench Press"]
STALLED = ["Romanian Deadlift", "Dumbbell Curl"]


@pytest.mark.parametrize(
    "text",
    [
        # The real note from the browser test, right after a back squat record:
        "Focus on back squat form this week to break the stall. Stay consistent with all "
        "four sessions.",
        "Your squat is stuck at 225 pounds. Keep showing up.",
    ],
)
def test_rejects_stall_claims_about_lifts_that_are_not_stalled(text):
    with pytest.raises(InsightRejected, match="called Back Squat stalled"):
        validate_insight(text, LIFTS, set(), STALLED)


@pytest.mark.parametrize(
    "text",
    [
        "Your Romanian deadlift has stalled at 175 pounds, so slow the lowering. "
        "Keep your squat momentum going.",
        "Your curls have plateaued, so focus on control. Back squat keeps climbing.",
    ],
)
def test_accepts_correct_stall_claims(text):
    assert validate_insight(text, LIFTS, set(), STALLED)
