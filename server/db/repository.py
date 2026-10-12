"""Database queries. Every user-owned query takes `user_id` explicitly; callers get it
from `get_current_user()`, never from tool input.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from server.db.models import (
    BodyMetric,
    Exercise,
    Insight,
    Job,
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
    return [
        ExerciseEntry(
            e.id,
            e.name,
            tuple(a.alias for a in e.aliases),
            equipment=e.equipment,
            form_cues=tuple(e.form_cues or ()),
        )
        for e in rows
    ]


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


async def get_active_session_full(db: AsyncSession, user_id: int) -> WorkoutSession | None:
    """The active session with its exercise snapshot (and each exercise) loaded."""
    return await db.scalar(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == user_id, WorkoutSession.status == "active")
        .options(selectinload(WorkoutSession.exercises), selectinload(WorkoutSession.plan_day))
    )


async def get_session_sets(db: AsyncSession, user_id: int, session_id: int) -> list[LoggedSet]:
    """Oldest first."""
    return list(
        await db.scalars(
            select(LoggedSet)
            .where(LoggedSet.user_id == user_id, LoggedSet.session_id == session_id)
            .order_by(LoggedSet.logged_at, LoggedSet.id)
        )
    )


async def count_sets_for_session_exercise(
    db: AsyncSession, user_id: int, session_exercise_id: int
) -> int:
    return await db.scalar(
        select(func.count())
        .select_from(LoggedSet)
        .where(LoggedSet.user_id == user_id, LoggedSet.session_exercise_id == session_exercise_id)
    )


async def delete_session(db: AsyncSession, user_id: int, session_id: int) -> None:
    await db.execute(
        delete(WorkoutSession).where(
            WorkoutSession.user_id == user_id, WorkoutSession.id == session_id
        )
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
    batch_id: str,
    session_id: int | None = None,
    session_exercise_id: int | None = None,
) -> LoggedSet:
    row = LoggedSet(
        user_id=user_id,
        batch_id=batch_id,
        session_exercise_id=session_exercise_id,
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


async def get_last_batch(db: AsyncSession, user_id: int) -> list[LoggedSet]:
    """All sets of the most recently logged batch (one log request), oldest first."""
    last = await get_last_logged_set(db, user_id)
    if last is None:
        return []
    return list(
        await db.scalars(
            select(LoggedSet)
            .where(LoggedSet.user_id == user_id, LoggedSet.batch_id == last.batch_id)
            .options(selectinload(LoggedSet.exercise))
            .order_by(LoggedSet.id)
        )
    )


async def delete_batch(db: AsyncSession, user_id: int, batch_id: str) -> int:
    result = await db.execute(
        delete(LoggedSet).where(LoggedSet.user_id == user_id, LoggedSet.batch_id == batch_id)
    )
    return result.rowcount


async def get_sets_for_exercises(
    db: AsyncSession, user_id: int, exercise_ids: list[int], *, since: datetime
) -> list[LoggedSet]:
    """Oldest first."""
    return list(
        await db.scalars(
            select(LoggedSet)
            .where(
                LoggedSet.user_id == user_id,
                LoggedSet.exercise_id.in_(exercise_ids),
                LoggedSet.logged_at >= since,
            )
            .order_by(LoggedSet.logged_at, LoggedSet.id)
        )
    )


async def get_pr_baseline(
    db: AsyncSession, user_id: int, exercise_id: int, weight_kg: Decimal
) -> tuple[Decimal | None, int | None]:
    """(heaviest weight ever, most reps ever at `weight_kg` or heavier) for one exercise."""
    mine = (LoggedSet.user_id == user_id, LoggedSet.exercise_id == exercise_id)
    max_weight = await db.scalar(select(func.max(LoggedSet.weight_kg)).where(*mine))
    max_reps = await db.scalar(
        select(func.max(LoggedSet.reps)).where(*mine, LoggedSet.weight_kg >= weight_kg)
    )
    return max_weight, max_reps


async def get_max_weights_before(
    db: AsyncSession, user_id: int, exercise_ids: list[int], before: datetime
) -> dict[int, Decimal]:
    rows = await db.execute(
        select(LoggedSet.exercise_id, func.max(LoggedSet.weight_kg))
        .where(
            LoggedSet.user_id == user_id,
            LoggedSet.exercise_id.in_(exercise_ids),
            LoggedSet.logged_at < before,
        )
        .group_by(LoggedSet.exercise_id)
    )
    return {ex_id: weight for ex_id, weight in rows}


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


async def get_body_metric_on_or_before(
    db: AsyncSession, user_id: int, when: datetime
) -> BodyMetric | None:
    return await db.scalar(
        select(BodyMetric)
        .where(BodyMetric.user_id == user_id, BodyMetric.measured_at <= when)
        .order_by(BodyMetric.measured_at.desc())
        .limit(1)
    )


# --- Insights ----------------------------------------------------------------------------


async def get_insight(db: AsyncSession, user_id: int, week_start: date) -> Insight | None:
    return await db.scalar(
        select(Insight).where(Insight.user_id == user_id, Insight.week_start == week_start)
    )


# --- Jobs --------------------------------------------------------------------------------


async def enqueue_job(
    db: AsyncSession, user_id: int, kind: str, payload: dict | None = None
) -> bool:
    """Queue a background job unless the same kind is already queued for the user."""
    already = await db.scalar(
        select(Job.id).where(Job.user_id == user_id, Job.kind == kind, Job.status == "queued")
    )
    if already is not None:
        return False
    db.add(Job(user_id=user_id, kind=kind, status="queued", payload=payload or {}))
    await db.flush()
    return True
