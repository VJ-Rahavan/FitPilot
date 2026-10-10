"""Per-request user context and user-facing errors."""

from dataclasses import dataclass
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from server.db import repository as repo
from server.services.units import Unit, to_kg


@dataclass(frozen=True)
class UserContext:
    user_id: int
    unit: Unit
    tz: ZoneInfo
    goal: str | None
    days_per_week: int | None
    bar_weight_kg: Decimal


async def load_user_context(db: AsyncSession, user_id: int) -> UserContext:
    """Profile settings, with sensible defaults when the profile hasn't been set up."""
    profile = await repo.get_profile(db, user_id)
    if profile is None:
        return UserContext(user_id, "lb", ZoneInfo("UTC"), None, None, to_kg(45, "lb"))
    unit: Unit = "kg" if profile.unit == "kg" else "lb"
    return UserContext(
        user_id=user_id,
        unit=unit,
        tz=ZoneInfo(profile.timezone or "UTC"),
        goal=profile.goal,
        days_per_week=profile.days_per_week,
        bar_weight_kg=profile.bar_weight_kg,
    )


class UserFacingError(Exception):
    """A problem with the request that the user can fix; `message` is spoken as-is."""

    def __init__(self, message: str, suggestions: tuple[str, ...] = ()):
        super().__init__(message)
        self.message = message
        self.suggestions = suggestions
