"""set_preferences: update the profile, or create it on first run."""

import re
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from zoneinfo import available_timezones

from sqlalchemy.ext.asyncio import AsyncSession

from server.db import repository as repo
from server.services.context import UserContext, UserFacingError
from server.services.units import Unit, display_weight, parse_unit, to_kg
from server.services.utilities import BAR_COUNTERPARTS, STANDARD_BAR

GOALS = ("strength", "muscle", "fat_loss", "general")
_GOAL_ALIASES = {
    "strength": "strength",
    "stronger": "strength",
    "get stronger": "strength",
    "power": "strength",
    "powerlifting": "strength",
    "muscle": "muscle",
    "build muscle": "muscle",
    "hypertrophy": "muscle",
    "size": "muscle",
    "bulk": "muscle",
    "gain muscle": "muscle",
    "fat loss": "fat_loss",
    "fat_loss": "fat_loss",
    "lose fat": "fat_loss",
    "lose weight": "fat_loss",
    "weight loss": "fat_loss",
    "cut": "fat_loss",
    "lean": "fat_loss",
    "general": "general",
    "general fitness": "general",
    "fitness": "general",
    "health": "general",
    "stay fit": "general",
}
BAR_RANGE_KG = (Decimal("5"), Decimal("35"))


def parse_goal(value: str) -> str:
    key = re.sub(r"\s+", " ", value.strip().lower().replace("-", " "))
    if key in _GOAL_ALIASES:
        return _GOAL_ALIASES[key]
    raise UserFacingError(
        "I can set your goal to strength, building muscle, fat loss or general fitness."
    )


# What people say, mapped to IANA names. Cities resolve on their own ("London", "Tokyo").
_TZ_ALIASES = {
    "eastern": "America/New_York",
    "eastern time": "America/New_York",
    "est": "America/New_York",
    "edt": "America/New_York",
    "central": "America/Chicago",
    "central time": "America/Chicago",
    "cst": "America/Chicago",
    "mountain": "America/Denver",
    "mountain time": "America/Denver",
    "pacific": "America/Los_Angeles",
    "pacific time": "America/Los_Angeles",
    "pst": "America/Los_Angeles",
    "alaska": "America/Anchorage",
    "hawaii": "Pacific/Honolulu",
    "gmt": "UTC",
    "utc": "UTC",
    "uk": "Europe/London",
    "britain": "Europe/London",
    "india": "Asia/Kolkata",
    "ist": "Asia/Kolkata",
    "mumbai": "Asia/Kolkata",
    "delhi": "Asia/Kolkata",
    "new delhi": "Asia/Kolkata",
    "bangalore": "Asia/Kolkata",
    "bengaluru": "Asia/Kolkata",
    "chennai": "Asia/Kolkata",
    "hyderabad": "Asia/Kolkata",
    "san francisco": "America/Los_Angeles",
    "seattle": "America/Los_Angeles",
    "boston": "America/New_York",
    "miami": "America/New_York",
    "dallas": "America/Chicago",
    "houston": "America/Chicago",
    "austin": "America/Chicago",
}
_NOT_USER_ZONES = {"Factory", "localtime", "posixrules"}


@lru_cache
def _zones() -> tuple[dict[str, str], dict[str, str]]:
    """(lowercase name → canonical name, lowercase city → canonical name)."""
    names = {z for z in available_timezones() if z not in _NOT_USER_ZONES}
    by_name = {z.lower(): z for z in names}
    by_city: dict[str, str] = {}
    for z in sorted(names):
        if "/" in z and not z.startswith("Etc/"):
            by_city.setdefault(z.rsplit("/", 1)[1].lower(), z)
    return by_name, by_city


def parse_timezone(value: str) -> str:
    """Spoken or written time zone → canonical IANA name (case-exact, so it works on Linux)."""
    key = re.sub(r"\s+", " ", value.strip().lower())
    by_name, by_city = _zones()
    found = (
        _TZ_ALIASES.get(key)
        or by_name.get(key.replace(" ", "_"))
        or by_city.get(key.replace(" ", "_"))
    )
    if found is None:
        raise UserFacingError(
            "I didn't catch that time zone. Try saying a nearby big city, like New York or London."
        )
    return found


def spoken_timezone(name: str) -> str:
    """'America/New_York' → 'New York'."""
    return name.rsplit("/", 1)[-1].replace("_", " ")


@dataclass(frozen=True)
class PreferencesResult:
    needs_setup: bool  # no profile and nothing given: ask the setup questions
    created: bool
    changes: tuple[str, ...]  # field names that changed
    unit: Unit
    bar_weight_kg: Decimal
    goal: str | None
    days_per_week: int | None
    timezone: str


async def set_preferences(
    db: AsyncSession,
    ctx: UserContext,
    *,
    unit: str | None,
    bar_weight: float | None,
    goal: str | None,
    days_per_week: int | None,
    timezone: str | None,
) -> PreferencesResult:
    profile = await repo.get_profile(db, ctx.user_id)
    nothing_given = all(v is None for v in (unit, bar_weight, goal, days_per_week, timezone))
    if nothing_given:
        if profile is None:
            return PreferencesResult(
                True, False, (), ctx.unit, ctx.bar_weight_kg, None, None, "UTC"
            )
        raise UserFacingError(
            "What would you like to change? You can set units, bar weight, goal, "
            "training days or time zone."
        )

    # Validate everything before changing anything.
    new_unit: Unit | None = None
    if unit is not None:
        try:
            new_unit = parse_unit(unit)
        except ValueError:
            raise UserFacingError("I can use pounds or kilograms. Which would you like?") from None
    new_goal = parse_goal(goal) if goal is not None else None
    new_tz = parse_timezone(timezone) if timezone is not None else None
    target_unit: Unit = new_unit or (profile.unit if profile else "lb")
    new_bar_kg = None
    if bar_weight is not None:
        new_bar_kg = to_kg(bar_weight, target_unit)
        if not BAR_RANGE_KG[0] <= new_bar_kg <= BAR_RANGE_KG[1]:
            low, high = (int(display_weight(w, target_unit)) for w in BAR_RANGE_KG)
            word = "pounds" if target_unit == "lb" else "kilograms"
            raise UserFacingError(
                f"A bar usually weighs between {low} and {high} {word}, so I didn't change it. "
                "What does your bar weigh?"
            )

    created = profile is None
    if created:
        profile = await repo.create_profile(
            db,
            ctx.user_id,
            unit=target_unit,
            bar_weight_kg=to_kg(STANDARD_BAR[target_unit], target_unit),
            timezone="UTC",
        )
    changes = []
    if new_unit is not None and (created or new_unit != profile.unit):
        old_unit = profile.unit
        profile.unit = new_unit
        changes.append("unit")
        # Common bars have a counterpart in the other unit (45 lb ↔ 20 kg, 35 lb ↔ 15 kg).
        if new_bar_kg is None:
            old_bar = display_weight(profile.bar_weight_kg, old_unit)
            counterpart = BAR_COUNTERPARTS.get((old_unit, old_bar))
            if counterpart is not None:
                profile.bar_weight_kg = to_kg(counterpart, new_unit)
    if new_bar_kg is not None and new_bar_kg != profile.bar_weight_kg:
        profile.bar_weight_kg = new_bar_kg
        changes.append("bar_weight")
    if new_goal is not None and new_goal != profile.goal:
        profile.goal = new_goal
        changes.append("goal")
    if days_per_week is not None and days_per_week != profile.days_per_week:
        profile.days_per_week = days_per_week
        changes.append("days_per_week")
    if new_tz is not None and new_tz != profile.timezone:
        profile.timezone = new_tz
        changes.append("timezone")
    await db.flush()
    return PreferencesResult(
        needs_setup=False,
        created=created,
        changes=tuple(changes),
        unit="kg" if profile.unit == "kg" else "lb",
        bar_weight_kg=profile.bar_weight_kg,
        goal=profile.goal,
        days_per_week=profile.days_per_week,
        timezone=profile.timezone,
    )
