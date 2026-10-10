"""Database queries. Every user-owned query takes `user_id` explicitly; callers get it
from `get_current_user()`, never from tool input.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from server.db.models import (
    BodyMetric,
    Exercise,
    LoggedSet,
    Plan,
    PlanDay,
    PlanExercise,
    UserProfile,
    WorkoutSession,
)
from server.services.exercise_resolver import ExerciseEntry

# --- Shared reference data -------------------------------------------------------------


async def load_exercise_entries(db: AsyncSession) -> list[ExerciseEntry]:
    rows = await db.scalars(select(Exercise).options(selectinload(Exercise.aliases)))
    return [ExerciseEntry(e.id, e.name, tuple(a.alias for a in e.aliases)) for e in rows]


async def get_exercise(db: AsyncSession, exercise_id: int) -> Exercise | None:
    return await db.get(Exercise, exercise_id)


# --- Profile -----------------------------------------------------------------------------


async def get_profile(db: AsyncSession, user_id: int) -> UserProfile | None:
    return await db.get(UserProfile, user_id)


# --- Plans -------------------------------------------------------------------------------


async def get_active_plan(db: AsyncSession, user_id: int) -> Plan | None:
    return await db.scalar(
        select(Plan)
        .where(Plan.user_id == user_id, Plan.is_active)
        .options(
            selectinload(Plan.days)
            .selectinload(PlanDay.exercises)
            .selectinload(PlanExercise.exercise)
        )
    )


# --- Sessions ----------------------------------------------------------------------------


async def get_active_session(db: AsyncSession, user_id: int) -> WorkoutSession | None:
    return await db.scalar(
        select(WorkoutSession).where(
            WorkoutSession.user_id == user_id, WorkoutSession.status == "active"
        )
    )


async def get_last_finished_session(db: AsyncSession, user_id: int) -> WorkoutSession | None:
    return await db.scalar(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == user_id, WorkoutSession.status == "finished")
        .order_by(WorkoutSession.started_at.desc())
        .limit(1)
    )


# --- Logged sets -------------------------------------------------------------------------


async def add_logged_set(
    db: AsyncSession,
    user_id: int,
    *,
    exercise_id: int,
    reps: int,
    weight_kg: Decimal,
    logged_at: datetime,
    session_id: int | None = None,
) -> LoggedSet:
    row = LoggedSet(
        user_id=user_id,
        exercise_id=exercise_id,
        reps=reps,
        weight_kg=weight_kg,
        logged_at=logged_at,
        session_id=session_id,
    )
    db.add(row)
    await db.flush()
    return row


async def get_sets_for_exercise(
    db: AsyncSession, user_id: int, exercise_id: int, *, since: datetime | None = None
) -> list[LoggedSet]:
    """Oldest first."""
    query = select(LoggedSet).where(
        LoggedSet.user_id == user_id, LoggedSet.exercise_id == exercise_id
    )
    if since is not None:
        query = query.where(LoggedSet.logged_at >= since)
    return list(await db.scalars(query.order_by(LoggedSet.logged_at)))


async def get_sets_between(
    db: AsyncSession, user_id: int, start: datetime, end: datetime
) -> list[LoggedSet]:
    """Sets in [start, end), oldest first, with their exercise loaded."""
    return list(
        await db.scalars(
            select(LoggedSet)
            .where(
                LoggedSet.user_id == user_id,
                LoggedSet.logged_at >= start,
                LoggedSet.logged_at < end,
            )
            .options(selectinload(LoggedSet.exercise))
            .order_by(LoggedSet.logged_at)
        )
    )


async def get_last_logged_set(db: AsyncSession, user_id: int) -> LoggedSet | None:
    return await db.scalar(
        select(LoggedSet)
        .where(LoggedSet.user_id == user_id)
        .options(selectinload(LoggedSet.exercise))
        .order_by(LoggedSet.logged_at.desc(), LoggedSet.id.desc())
        .limit(1)
    )


async def delete_logged_set(db: AsyncSession, user_id: int, set_id: int) -> bool:
    result = await db.execute(
        delete(LoggedSet).where(LoggedSet.user_id == user_id, LoggedSet.id == set_id)
    )
    return result.rowcount > 0


# --- Body metrics ------------------------------------------------------------------------


async def add_body_metric(
    db: AsyncSession, user_id: int, *, bodyweight_kg: Decimal, measured_at: datetime
) -> BodyMetric:
    row = BodyMetric(user_id=user_id, bodyweight_kg=bodyweight_kg, measured_at=measured_at)
    db.add(row)
    await db.flush()
    return row


async def get_recent_body_metrics(
    db: AsyncSession, user_id: int, *, limit: int = 10
) -> list[BodyMetric]:
    """Newest first."""
    return list(
        await db.scalars(
            select(BodyMetric)
            .where(BodyMetric.user_id == user_id)
            .order_by(BodyMetric.measured_at.desc())
            .limit(limit)
        )
    )
