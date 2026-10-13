"""Live autoregulation and "beat last time": pure rules, no DB.

Effort ("that felt easy", "brutal") adjusts the remaining sets of the current exercise.
Each finished set is compared with the same set of the previous session.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from server.services.progression import round_to_step, step_for
from server.services.units import Unit, display_weight, to_kg

Effort = Literal["easy", "ok", "hard", "failed"]

MAX_EASY_STEPS = 2  # per exercise per workout
FAILED_FACTOR = Decimal("0.95")


def effective_effort(effort: Effort | None, reps: int, target_reps: int) -> Effort | None:
    """Two or more reps short of the target counts as failed, whatever was said."""
    if reps <= target_reps - 2:
        return "failed"
    return effort


@dataclass(frozen=True)
class Adjustment:
    action: Literal["up", "capped", "hold", "down"]
    weight_kg: Decimal  # target for the remaining sets of this exercise


def adjust_remaining(
    *,
    effort: Effort | None,
    reps: int,
    target_reps: int,
    weight_kg: Decimal,
    equipment: str,
    unit: Unit,
    bar_kg: Decimal,
    easy_steps_used: int,
) -> Adjustment | None:
    """New target for the rest of this exercise, or None when nothing changes."""
    if effort in (None, "ok") or equipment == "bodyweight":
        return None
    step = step_for(equipment, unit)
    shown = display_weight(weight_kg, unit)  # rounded: no kg↔lb float noise in comparisons
    if effort == "easy":
        if reps < target_reps:
            return None  # "easy" but reps were missed: don't add weight
        if easy_steps_used >= MAX_EASY_STEPS:
            return Adjustment("capped", weight_kg)
        return Adjustment("up", to_kg(shown + step, unit))  # exactly one step up
    if effort == "hard":
        return Adjustment("hold", weight_kg)
    current = round_to_step(shown, step)
    lighter = min(current - step, round_to_step(current * FAILED_FACTOR, step))
    floor = display_weight(bar_kg, unit) if equipment == "barbell" else step
    new = min(shown, max(floor, lighter))  # never heavier than the set just done
    if new >= shown:
        return Adjustment("hold", weight_kg)  # already at the floor: nothing to drop
    return Adjustment("down", to_kg(new, unit))


@dataclass(frozen=True)
class Beat:
    kind: Literal["weight", "reps"]
    amount: Decimal | int  # extra kg, or extra reps


def beat_last_time(
    *,
    reps: int,
    weight_kg: Decimal,
    last_reps: int,
    last_weight_kg: Decimal,
    bodyweight: bool,
) -> Beat | None:
    """Did this set beat the same set last session? More weight for at least as many reps
    wins; otherwise more reps at the same weight or heavier."""
    if not bodyweight and weight_kg > last_weight_kg and reps >= last_reps:
        return Beat("weight", weight_kg - last_weight_kg)
    if (bodyweight or weight_kg >= last_weight_kg) and reps > last_reps:
        return Beat("reps", reps - last_reps)
    return None
