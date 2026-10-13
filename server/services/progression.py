"""Progressive overload: suggest the next working weight from recent sessions.

Rule: all prescribed reps hit in the last 2 sessions at the current weight → add one step;
missed reps in the last 2 sessions → reduce 10%; otherwise → hold. Spoken effort refines it:
a "failed" set counts as a miss, and a "hard" or "failed" top set in the last session holds
the weight instead of adding a step.
Step: 5 lb / 2.5 kg, or 2.5 lb / 1.25 kg for dumbbells (+5 lb is ~20% on a 25 lb dumbbell).
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, tzinfo
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from server.services.units import Unit, from_kg, to_kg

# "lighter": scaled down for today's readiness check.
Action = Literal["start", "increase", "hold", "decrease", "bodyweight", "lighter"]

DELOAD_FACTOR = Decimal("0.9")
WORKING_SET_FRACTION = Decimal("0.85")


def step_for(equipment: str, unit: Unit) -> Decimal:
    if unit == "lb":
        return Decimal("2.5") if equipment == "dumbbell" else Decimal("5")
    return Decimal("1.25") if equipment == "dumbbell" else Decimal("2.5")


@dataclass(frozen=True)
class SessionPerformance:
    """One past session of one exercise: its top working weight and the reps done at it."""

    on: datetime
    weight_kg: Decimal  # the day's top weight
    reps: tuple[int, ...]  # working sets, in order
    efforts: tuple[str | None, ...] = ()  # spoken effort of each working set

    def hit(self, target_sets: int, target_reps: int) -> bool:
        return (
            len(self.reps) >= target_sets
            and all(r >= target_reps for r in self.reps)
            and "failed" not in self.efforts
        )

    @property
    def felt_hard(self) -> bool:
        return bool(self.efforts) and self.efforts[-1] in ("hard", "failed")


@dataclass(frozen=True)
class Suggestion:
    action: Action
    weight_kg: Decimal | None  # None when there's no history to base it on


Row = tuple[datetime, int, Decimal, str | None]  # logged_at, reps, weight_kg, effort


def group_sessions(sets: list[Row], tz: tzinfo) -> list[SessionPerformance]:
    """Rows of one exercise → per-day performances, oldest first."""
    by_day: dict[object, list[Row]] = defaultdict(list)
    for row in sets:
        by_day[row[0].astimezone(tz).date()].append(row)
    out = []
    for day in sorted(by_day):
        rows = by_day[day]
        top = max(w for _, _, w, _ in rows)
        # Working sets: near the top weight, so warm-ups don't count but sets before a
        # mid-workout "that felt easy" bump do (otherwise the bump would read as a miss).
        working = [(r, e) for _, r, w, e in rows if w >= top * WORKING_SET_FRACTION]
        out.append(
            SessionPerformance(
                on=rows[0][0],
                weight_kg=top,
                reps=tuple(r for r, _ in working),
                efforts=tuple(e for _, e in working),
            )
        )
    return out


def round_to_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step


def suggest(
    history: list[SessionPerformance],
    *,
    target_sets: int,
    target_reps: int,
    equipment: str,
    unit: Unit,
) -> Suggestion:
    if equipment == "bodyweight":
        return Suggestion("bodyweight", Decimal("0"))
    if not history:
        return Suggestion("start", None)

    last = history[-1]
    current = last.weight_kg
    step = step_for(equipment, unit)
    current_in_unit = round_to_step(from_kg(current, unit), step)

    if len(history) >= 2:
        prev = history[-2]
        if (
            last.hit(target_sets, target_reps)
            and prev.hit(target_sets, target_reps)
            and prev.weight_kg >= current
            and not last.felt_hard
        ):
            return Suggestion("increase", to_kg(current_in_unit + step, unit))
        if not last.hit(target_sets, target_reps) and not prev.hit(target_sets, target_reps):
            reduced = max(step, round_to_step(current_in_unit * DELOAD_FACTOR, step))
            return Suggestion("decrease", to_kg(reduced, unit))
    return Suggestion("hold", to_kg(current_in_unit, unit))
