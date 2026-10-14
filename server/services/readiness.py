"""Readiness check: deterministic rules turn sleep, soreness and energy into how hard to
train today. Any mention of pain gets safety advice (stop, see a professional), never a
diagnosis. Notes are only scanned, never stored.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from server.db import repository as repo
from server.services.context import UserContext, UserFacingError
from server.services.progression import round_to_step, step_for
from server.services.units import Unit, display_weight, from_kg, to_kg

Level = Literal["full", "reduce", "light", "rest"]
Soreness = Literal["none", "mild", "moderate", "severe"]
Energy = Literal["low", "normal", "high"]

# How much each level scales today's suggested weights, and how many sets it drops.
WEIGHT_FACTOR: dict[str, Decimal] = {
    "full": Decimal("1"),
    "reduce": Decimal("0.9"),
    "light": Decimal("0.8"),
    "rest": Decimal("0.8"),  # if they train anyway, keep it light
}
SETS_DROPPED: dict[str, int] = {"full": 0, "reduce": 0, "light": 1, "rest": 1}
SEVERITY: tuple[str, ...] = ("full", "reduce", "light", "rest")

# Deliberately broad: a false positive only adds safety advice.
PAIN = re.compile(
    r"\b(pain\w*|hurt\w*|injur\w*|sharp|tweak\w*|pulled|strain\w*|sprain\w*|twinge\w*|"
    r"ach(e|es|ed|ing|y)|\w+aches?|throb\w*|pop(ped|ping)?|tender|swollen|swelling|"
    r"numb\w*|tingl\w*|rolled|twisted|killing me|can'?t (lift|bend|walk|move)|"
    r"bad (knee|back|shoulder|elbow|wrist|hip|ankle|neck))\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Assessment:
    level: Level
    reasons: tuple[str, ...] = field(default=())  # spoken fragments, e.g. "short sleep"
    pain_reported: bool = False
    energy_high: bool = False
    session_adjusted: bool = False  # the remaining exercises of today's workout were lightened
    kept_earlier: bool = False  # an earlier, more cautious check today still applies


def assess(
    *,
    sleep_hours: float | None,
    soreness: Soreness | None,
    energy: Energy | None,
    notes: str | None,
    pain_mentioned: bool = False,
) -> Assessment:
    if (
        sleep_hours is None
        and soreness is None
        and energy is None
        and not notes
        and not pain_mentioned
    ):
        raise UserFacingError(
            "Tell me how you slept, how sore you are, or how your energy is today. "
            "For example, say I slept five hours and my legs are sore."
        )
    points, reasons = 0, []
    if sleep_hours is not None:
        if sleep_hours < 5:
            points, reasons = points + 2, [*reasons, "very little sleep"]
        elif sleep_hours < 6.5:
            points, reasons = points + 1, [*reasons, "short sleep"]
    if soreness == "moderate":
        points, reasons = points + 1, [*reasons, "moderate soreness"]
    elif soreness == "severe":
        points, reasons = points + 2, [*reasons, "a lot of soreness"]
    if energy == "low":
        points, reasons = points + 1, [*reasons, "low energy"]
    elif energy == "high":
        points -= 1

    pain = pain_mentioned or bool(notes and PAIN.search(notes))
    if pain:
        points = max(points, 1)  # never "train as planned" when something hurts

    level: Level = "full"
    if points >= 4:
        level = "rest"
    elif points >= 2:
        level = "light"
    elif points == 1:
        level = "reduce"
    return Assessment(level, tuple(reasons), pain, energy_high=energy == "high")


def lighten(weight_kg: Decimal, level: str, equipment: str, unit: Unit, bar_kg: Decimal) -> Decimal:
    """A target weight scaled for readiness, on a loadable step, never below the empty bar."""
    step = step_for(equipment, unit)
    lighter = max(step, round_to_step(from_kg(weight_kg, unit) * WEIGHT_FACTOR[level], step))
    if equipment == "barbell":
        lighter = max(lighter, display_weight(bar_kg, unit))
    return to_kg(lighter, unit)


async def _lighten_active_session(db: AsyncSession, ctx: UserContext, level: str, today) -> bool:
    """Apply readiness to the not-yet-started exercises of today's active workout."""
    session = await repo.get_active_session_full(db, ctx.user_id)
    if session is None or session.started_at.astimezone(ctx.tz).date() != today:
        return False
    upcoming = [e for e in session.exercises if e.position > session.current_position]
    for row in upcoming:
        row.sets = max(1, row.sets - SETS_DROPPED[level])
        if row.target_weight_kg:
            equipment = await repo.get_exercise_equipment(db, row.exercise_id)
            row.target_weight_kg = lighten(
                row.target_weight_kg, level, equipment, ctx.unit, ctx.bar_weight_kg
            )
    await db.flush()
    return bool(upcoming)


async def readiness_check(
    db: AsyncSession,
    ctx: UserContext,
    *,
    sleep_hours: float | None,
    soreness: Soreness | None,
    energy: Energy | None,
    notes: str | None,
    pain_mentioned: bool,
    now: datetime,
) -> Assessment:
    result = assess(
        sleep_hours=sleep_hours,
        soreness=soreness,
        energy=energy,
        notes=notes,
        pain_mentioned=pain_mentioned,
    )
    today = now.astimezone(ctx.tz).date()
    earlier = await repo.get_readiness(db, ctx.user_id, today)
    earlier_level = earlier.level if earlier else "full"
    # A later check never makes the day less cautious (e.g. a pain report after "slept badly").
    level: Level = max(result.level, earlier_level, key=SEVERITY.index)
    pain = result.pain_reported or bool(earlier and earlier.pain_reported)
    await repo.upsert_readiness(db, ctx.user_id, today, level, pain)
    adjusted = False
    if level != "full" and earlier_level == "full":
        # Only the first lightening of the day touches the workout, so cuts never stack.
        adjusted = await _lighten_active_session(db, ctx, level, today)
    return Assessment(
        level,
        result.reasons,
        result.pain_reported,
        result.energy_high,
        adjusted,
        kept_earlier=SEVERITY.index(earlier_level) > SEVERITY.index(result.level),
    )
