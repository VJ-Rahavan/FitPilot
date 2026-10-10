"""Personal records."""

from decimal import Decimal
from typing import Literal

PRKind = Literal["weight", "reps"]


def detect_pr(
    *,
    weight_kg: Decimal,
    reps: int,
    previous_max_weight_kg: Decimal | None,
    previous_max_reps_at_weight: int | None,
    bodyweight: bool = False,
) -> PRKind | None:
    """Compare a new set against history (excluding itself).

    "weight": heavier than ever. "reps": more reps than ever at this weight or heavier.
    The first-ever log of an exercise is not a PR (there's nothing to beat).
    """
    if previous_max_weight_kg is None:
        return None
    if not bodyweight and weight_kg > previous_max_weight_kg:
        return "weight"
    if previous_max_reps_at_weight is not None and reps > previous_max_reps_at_weight:
        return "reps"
    return None


def estimated_1rm(weight_kg: Decimal, reps: int) -> Decimal:
    """Epley formula; used to rank sets of different weight and reps."""
    if reps <= 1:
        return weight_kg
    return weight_kg * (1 + Decimal(reps) / 30)
