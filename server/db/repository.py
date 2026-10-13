"""Database queries. Every user-owned query takes `user_id` explicitly; callers get it
from `get_current_user()`, never from tool input.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
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
    ReadinessCheck,
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


async def get_exercise_equipment(db: AsyncSession, exercise_id: int) -> str:
    return await db.scalar(select(Exercise.equipment).where(Exercise.id == exercise_id))


async def get_exercise(db: AsyncSession, exercise_id: int) -> Exercise | None:
    return await db.get(Exercise, exercise_id)


# --- Profile -----------------------------------------------------------------------------


async def get_profile(db: AsyncSession, user_id: int) -> UserProfile | None:
    return await db.get(UserProfile, user_id)


async def create_profile(db: AsyncSession, user_id: int, **fields) -> UserProfile:
    profile = UserProfile(user_id=user_id, **fields)
    db.add(profile)
    await db.flush()
    return profile


# --- Readiness ---------------------------------------------------------------------------


async def upsert_readiness(
    db: AsyncSession, user_id: int, on_date: date, level: str, pain_reported: bool
) -> None:
    """The latest check of the day wins."""
    row = await get_readiness(db, user_id, on_date)
    if row is None:
        db.add(
            ReadinessCheck(
                user_id=user_id, on_date=on_date, level=level, pain_reported=pain_reported
            )
        )
    else:
        row.level, row.pain_reported = level, pain_reported
    await db.flush()


async def get_lightened_dates(db: AsyncSession, user_id: int, since: date) -> set[date]:
    """Days when readiness lightened training (excluded from progression history)."""
    rows = await db.scalars(
        select(ReadinessCheck.on_date).where(
            ReadinessCheck.user_id == user_id,
            ReadinessCheck.on_date >= since,
            ReadinessCheck.level != "full",
        )
    )
    return set(rows)


async def get_readiness(db: AsyncSession, user_id: int, on_date: date) -> ReadinessCheck | None:
    return await db.scalar(
        select(ReadinessCheck).where(
            ReadinessCheck.user_id == user_id, ReadinessCheck.on_date == on_date
        )
    )


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
    effort: str | None = None,
) -> LoggedSet:
    row = LoggedSet(
        user_id=user_id,
        effort=effort,
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

# Job ids queued in a transaction, dispatched to the queue after it commits (see run_tool).
ENQUEUED_JOBS = "enqueued_job_ids"


async def enqueue_job(
    db: AsyncSession,
    user_id: int,
    kind: str,
    payload: dict | None = None,
    *,
    run_after: datetime,
) -> int:
    """Queue a background job, or reschedule the user's queued job of this kind (debounce).

    One atomic upsert on the partial unique index, so it's safe against concurrent requests
    and against the worker claiming the job at the same moment: once claimed, the job is no
    longer "queued" and a fresh one is inserted.
    """
    stmt = pg_insert(Job).values(
        user_id=user_id,
        kind=kind,
        status="queued",
        attempts=0,
        payload=payload or {},
        run_after=run_after,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[Job.user_id, Job.kind],
        # A literal (not a bound parameter) so Postgres can match the partial index predicate.
        index_where=text("status = 'queued'"),
        set_={"run_after": stmt.excluded.run_after, "payload": stmt.excluded.payload},
    ).returning(Job.id)
    job_id = await db.scalar(stmt)
    db.info.setdefault(ENQUEUED_JOBS, []).append(job_id)
    return job_id


async def claim_job(db: AsyncSession, job_id: int, now: datetime) -> Job | None:
    """Atomically mark a due, queued job as running. None if gone, not due or taken."""
    claimed = await db.scalar(
        update(Job)
        .where(Job.id == job_id, Job.status == "queued", Job.run_after <= now)
        .values(status="running", attempts=Job.attempts + 1, updated_at=now)
        .returning(Job.id)
    )
    return await db.get(Job, claimed) if claimed is not None else None


async def due_job_ids(db: AsyncSession, now: datetime, *, limit: int = 20) -> list[int]:
    return list(
        await db.scalars(
            select(Job.id)
            .where(Job.status == "queued", Job.run_after <= now)
            .order_by(Job.run_after)
            .limit(limit)
        )
    )


async def requeue_job(db: AsyncSession, job_id: int, run_after: datetime, error: str) -> bool:
    """Put a failed attempt back in the queue. False if a newer queued job of the same kind
    already exists for the user (that one will cover it), in which case this one is failed."""
    job = await db.get(Job, job_id)
    newer = await db.scalar(
        select(Job.id).where(
            Job.user_id == job.user_id, Job.kind == job.kind, Job.status == "queued"
        )
    )
    job.error = error
    if newer is not None:
        job.status = "failed"
        job.error = f"{error} (superseded by job {newer})"
        return False
    job.status, job.run_after = "queued", run_after
    return True


async def requeue_stale_running(db: AsyncSession, before: datetime) -> int:
    """Jobs stuck in "running" since before `before` (worker died mid-job) go back to queued,
    unless a newer queued job of the same kind supersedes them."""
    stale = list(
        await db.scalars(select(Job).where(Job.status == "running", Job.updated_at < before))
    )
    for job in stale:
        await requeue_job(db, job.id, job.run_after, "worker stopped while running")
        await db.flush()
    return len(stale)


async def queued_job_ids(db: AsyncSession) -> list[int]:
    return list(await db.scalars(select(Job.id).where(Job.status == "queued")))


async def upsert_insight(
    db: AsyncSession, user_id: int, week_start: date, text: str, model_id: str
) -> None:
    insight = await get_insight(db, user_id, week_start)
    if insight is None:
        db.add(Insight(user_id=user_id, week_start=week_start, text=text, model_id=model_id))
    else:
        insight.text, insight.model_id = text, model_id
    await db.flush()
