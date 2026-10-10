"""Process-wide exercise resolver, loaded from the DB once (exercises are static)."""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from server.db import repository as repo
from server.services.exercise_resolver import ExerciseResolver

_resolver: ExerciseResolver | None = None
_lock = asyncio.Lock()


async def get_resolver(db: AsyncSession) -> ExerciseResolver:
    global _resolver
    if _resolver is None:
        async with _lock:
            if _resolver is None:
                _resolver = ExerciseResolver(await repo.load_exercise_entries(db))
    return _resolver


def clear_resolver_cache() -> None:
    """Call after changing the exercise catalog (e.g. reseeding in tests)."""
    global _resolver
    _resolver = None
