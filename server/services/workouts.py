"""Workout domain operations behind the MVP tools. No LLM calls; all deterministic.

Each function takes the DB session, the user's context and `now`, and returns a plain
result object for the presenters. Problems the user can fix raise `UserFacingError`.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from server.config import get_settings
from server.db import repository as repo
from server.db.models import Plan, PlanDay
from server.services.context import UserContext, UserFacingError
from server.services.exercise_resolver import ExerciseEntry, ExerciseResolver
from server.services.insights import fallback_insight
from server.services.progression import Suggestion, group_sessions, suggest
from server.services.records import PRKind, detect_pr, estimated_1rm
from server.services.units import Unit, to_kg

DEDUPE_WINDOW = timedelta(seconds=60)
INSIGHT_JOB = "regenerate_weekly_insight"
HISTORY_FOR_SUGGESTIONS = timedelta(days=60)
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def resolve_exercise(resolver: ExerciseResolver, name: str) -> ExerciseEntry:
    r = resolver.resolve(name)
    if r.found:
        return resolver.get(r.exercise_id)
    if r.matched_by == "ambiguous" and r.suggestions:
        options = " or ".join(s.lower() for s in r.suggestions[:3])
        raise UserFacingError(f"Did you mean {options}?", r.suggestions)
    if r.suggestions:
        raise UserFacingError(
            f"I couldn't find an exercise called {name}. Did you mean {r.suggestions[0].lower()}?",
            r.suggestions,
        )
    raise UserFacingError(f"I couldn't find an exercise called {name}.")


def week_start_of(moment: datetime, ctx: UserContext) -> date:
    """Monday of the user's local week containing `moment`."""
    day = moment.astimezone(ctx.tz).date()
    return day - timedelta(days=day.weekday())


async def queue_insight(
    db: AsyncSession, ctx: UserContext, *, about: datetime, run_after: datetime
) -> None:
    """Refresh the weekly insight for the week containing `about` (after `run_after`)."""
    payload = {"week_start": week_start_of(about, ctx).isoformat()}
    await repo.enqueue_job(db, ctx.user_id, INSIGHT_JOB, payload, run_after=run_after)


def _local_day_start(day: date, ctx: UserContext) -> datetime:
    return datetime.combine(day, time.min, tzinfo=ctx.tz)


# --- log_workout -------------------------------------------------------------------------


@dataclass(frozen=True)
class LogWorkoutResult:
    exercise: ExerciseEntry
    sets: int
    reps: int
    weight_kg: Decimal
    unit: Unit
    pr: PRKind | None
    duplicate: bool
    previous_best_kg: Decimal | None


async def log_workout(
    db: AsyncSession,
    ctx: UserContext,
    resolver: ExerciseResolver,
    *,
    exercise: str,
    sets: int,
    reps: int,
    weight: float | None,
    unit: Unit,
    now: datetime,
) -> LogWorkoutResult:
    entry = resolve_exercise(resolver, exercise)
    bodyweight = entry.equipment == "bodyweight"
    if weight is None and not bodyweight:
        raise UserFacingError(f"What weight did you use for {entry.name.lower()}?")
    weight_kg = to_kg(weight or 0, unit)

    # Dedupe: the same log repeated within a minute (e.g. a retried voice request).
    last = await repo.get_last_batch(db, ctx.user_id)
    if (
        last
        and last[0].exercise_id == entry.id
        and len(last) == sets
        and all(s.reps == reps and s.weight_kg == weight_kg for s in last)
        and now - last[-1].logged_at <= DEDUPE_WINDOW
    ):
        return LogWorkoutResult(entry, sets, reps, weight_kg, unit, None, True, None)

    prev_max_weight, prev_max_reps = await repo.get_pr_baseline(
        db, ctx.user_id, entry.id, weight_kg
    )
    pr = detect_pr(
        weight_kg=weight_kg,
        reps=reps,
        previous_max_weight_kg=prev_max_weight,
        previous_max_reps_at_weight=prev_max_reps,
        bodyweight=bodyweight,
    )
    active = await repo.get_active_session(db, ctx.user_id)
    batch_id = str(uuid.uuid4())
    # Refresh the weekly insight once the user stops logging for a while.
    debounce = timedelta(minutes=get_settings().insight_debounce_minutes)
    await queue_insight(db, ctx, about=now, run_after=now + debounce)
    for i in range(sets):
        await repo.add_logged_set(
            db,
            ctx.user_id,
            exercise_id=entry.id,
            reps=reps,
            weight_kg=weight_kg,
            logged_at=now + timedelta(milliseconds=i),  # keeps set order stable
            batch_id=batch_id,
            session_id=active.id if active else None,
        )
    return LogWorkoutResult(entry, sets, reps, weight_kg, unit, pr, False, prev_max_weight)


# --- undo_last_log -----------------------------------------------------------------------


@dataclass(frozen=True)
class UndoResult:
    exercise: str
    reps: tuple[int, ...]
    weight_kg: Decimal
    unit: Unit
    bodyweight: bool
    rewound_session: bool = False  # the guided session's position stepped back too


async def undo_last_log(db: AsyncSession, ctx: UserContext, *, now: datetime) -> UndoResult | None:
    batch = await repo.get_last_batch(db, ctx.user_id)
    if not batch:
        return None
    await repo.delete_batch(db, ctx.user_id, batch[0].batch_id)
    # A stored insight may mention the removed sets (e.g. a misheard record): refresh it.
    await queue_insight(db, ctx, about=batch[0].logged_at, run_after=now)
    rewound = await _rewind_session_for_undo(db, ctx, batch)
    return UndoResult(
        exercise=batch[0].exercise.name,
        reps=tuple(s.reps for s in batch),
        weight_kg=max(s.weight_kg for s in batch),
        unit=ctx.unit,
        bodyweight=batch[0].exercise.equipment == "bodyweight",
        rewound_session=rewound,
    )


async def _rewind_session_for_undo(db: AsyncSession, ctx: UserContext, batch) -> bool:
    """If the undone set came from `complete_set`, move the guided session back to it.

    Only `complete_set` records `session_exercise_id`, so free-form `log_workout` sets never
    move the session position.
    """
    row_id = batch[0].session_exercise_id
    if len(batch) != 1 or row_id is None:
        return False
    session = await repo.get_active_session_full(db, ctx.user_id)
    row = next((e for e in session.exercises if e.id == row_id), None) if session else None
    if row is None:
        return False
    remaining = await repo.count_sets_for_session_exercise(db, ctx.user_id, row_id)
    session.current_position, session.current_set = row.position, remaining
    row.status = "pending"
    await db.flush()
    return True


# --- log_body_metric ---------------------------------------------------------------------


@dataclass(frozen=True)
class BodyMetricResult:
    weight_kg: Decimal
    unit: Unit
    change_kg: Decimal | None  # vs ~a week ago (or the last weigh-in if none that old)
    compared_days: int | None
    goal: str | None


async def log_body_metric(
    db: AsyncSession, ctx: UserContext, *, bodyweight: float, unit: Unit, now: datetime
) -> BodyMetricResult:
    weight_kg = to_kg(bodyweight, unit)
    baseline = await repo.get_body_metric_on_or_before(db, ctx.user_id, now - timedelta(days=6))
    if baseline is None:
        recent = await repo.get_recent_body_metrics(db, ctx.user_id, limit=1)
        baseline = recent[0] if recent else None
    await repo.add_body_metric(db, ctx.user_id, bodyweight_kg=weight_kg, measured_at=now)
    if baseline is None:
        return BodyMetricResult(weight_kg, unit, None, None, ctx.goal)
    days = max(1, (now - baseline.measured_at).days)
    return BodyMetricResult(weight_kg, unit, weight_kg - baseline.bodyweight_kg, days, ctx.goal)


# --- get_todays_workout ------------------------------------------------------------------


@dataclass(frozen=True)
class PlannedExercise:
    exercise: ExerciseEntry
    sets: int
    reps: int
    suggestion: Suggestion


@dataclass(frozen=True)
class TodaysWorkout:
    unit: Unit
    has_plan: bool
    day_name: str | None = None  # None on a rest day
    items: tuple[PlannedExercise, ...] = ()
    next_day_name: str | None = None
    next_weekday: str | None = None
    already_trained_today: bool = False


async def pick_plan_day(
    db: AsyncSession, ctx: UserContext, plan: Plan, today: date
) -> tuple[PlanDay | None, PlanDay | None]:
    """(today's scheduled day, or None on a rest day; the next scheduled day on a rest day).

    Plans without weekdays rotate: the day after the last finished session's day.
    """
    scheduled = [d for d in plan.days if d.weekday is not None]
    if scheduled:
        day = next((d for d in scheduled if d.weekday == today.weekday()), None)
        if day is not None:
            return day, None
        nxt = min(scheduled, key=lambda d: (d.weekday - today.weekday()) % 7)
        return None, nxt
    last = await repo.get_last_finished_session(db, ctx.user_id)
    ids = [d.id for d in plan.days]
    idx = 0
    if last and last.plan_day_id in ids:
        idx = (ids.index(last.plan_day_id) + 1) % len(ids)
    return plan.days[idx], None


async def plan_day_targets(
    db: AsyncSession,
    ctx: UserContext,
    resolver: ExerciseResolver,
    day: PlanDay,
    *,
    now: datetime,
) -> tuple[tuple[PlannedExercise, ...], bool]:
    """Each exercise of `day` with its suggested weight; and whether anything was logged today.

    Today's own sets are ignored, so suggestions stay stable during the day.
    """
    today = now.astimezone(ctx.tz).date()
    exercise_ids = [pe.exercise_id for pe in day.exercises]
    history = await repo.get_sets_for_exercises(
        db, ctx.user_id, exercise_ids, since=now - HISTORY_FOR_SUGGESTIONS
    )
    by_exercise: dict[int, list[tuple[datetime, int, Decimal]]] = defaultdict(list)
    trained_today = False
    for s in history:
        if s.logged_at.astimezone(ctx.tz).date() == today:
            trained_today = True
            continue
        by_exercise[s.exercise_id].append((s.logged_at, s.reps, s.weight_kg))

    items = []
    for pe in day.exercises:
        entry = resolver.get(pe.exercise_id)
        suggestion = suggest(
            group_sessions(by_exercise[pe.exercise_id], ctx.tz),
            target_sets=pe.sets,
            target_reps=pe.reps,
            equipment=entry.equipment,
            unit=ctx.unit,
        )
        items.append(PlannedExercise(entry, pe.sets, pe.reps, suggestion))
    return tuple(items), trained_today


async def get_todays_workout(
    db: AsyncSession, ctx: UserContext, resolver: ExerciseResolver, *, now: datetime
) -> TodaysWorkout:
    plan = await repo.get_active_plan(db, ctx.user_id)
    if plan is None or not plan.days:
        return TodaysWorkout(ctx.unit, has_plan=False)

    day, next_day = await pick_plan_day(db, ctx, plan, now.astimezone(ctx.tz).date())
    if day is None:
        return TodaysWorkout(
            ctx.unit, True, next_day_name=next_day.name, next_weekday=WEEKDAYS[next_day.weekday]
        )
    items, trained_today = await plan_day_targets(db, ctx, resolver, day, now=now)
    return TodaysWorkout(
        ctx.unit, True, day_name=day.name, items=items, already_trained_today=trained_today
    )


# --- get_weekly_summary ------------------------------------------------------------------


@dataclass(frozen=True)
class WeeklySummary:
    unit: Unit
    weeks_ago: int
    week_start: date
    sessions: int
    planned: int | None
    volume_kg: Decimal
    prev_volume_kg: Decimal
    daily_volume_kg: tuple[tuple[date, Decimal], ...]
    prs: tuple[tuple[str, Decimal], ...]  # (exercise, new best weight)
    insight: str
    insight_is_fallback: bool


def _volume(sets) -> Decimal:
    return sum((Decimal(s.reps) * s.weight_kg for s in sets), Decimal("0"))


async def get_weekly_summary(
    db: AsyncSession, ctx: UserContext, *, weeks_ago: int, now: datetime
) -> WeeklySummary:
    today = now.astimezone(ctx.tz).date()
    week_start = today - timedelta(days=today.weekday(), weeks=weeks_ago)
    start = _local_day_start(week_start, ctx)
    end = _local_day_start(week_start + timedelta(days=7), ctx)
    prev_start = _local_day_start(week_start - timedelta(days=7), ctx)

    week_sets = await repo.get_sets_between(db, ctx.user_id, start, end)
    prev_sets = await repo.get_sets_between(db, ctx.user_id, prev_start, start)

    daily: dict[date, Decimal] = {week_start + timedelta(days=i): Decimal("0") for i in range(7)}
    best_in_week: dict[int, tuple[str, Decimal]] = {}
    for s in week_sets:
        day = s.logged_at.astimezone(ctx.tz).date()
        daily[day] += Decimal(s.reps) * s.weight_kg
        if s.weight_kg > 0 and s.weight_kg > best_in_week.get(s.exercise_id, ("", Decimal(-1)))[1]:
            best_in_week[s.exercise_id] = (s.exercise.name, s.weight_kg)
    sessions = len({s.logged_at.astimezone(ctx.tz).date() for s in week_sets})

    before = await repo.get_max_weights_before(db, ctx.user_id, list(best_in_week), start)
    prs = tuple(
        (name, weight)
        for ex_id, (name, weight) in best_in_week.items()
        if ex_id in before and weight > before[ex_id]
    )

    volume, prev_volume = _volume(week_sets), _volume(prev_sets)
    stored = await repo.get_insight(db, ctx.user_id, week_start)
    insight = (
        stored.text
        if stored
        else fallback_insight(
            sessions=sessions,
            planned=ctx.days_per_week,
            volume_kg=volume,
            # No volume comparison while the current week is still in progress.
            prev_volume_kg=prev_volume if weeks_ago > 0 else Decimal("0"),
        )
    )
    return WeeklySummary(
        unit=ctx.unit,
        weeks_ago=weeks_ago,
        week_start=week_start,
        sessions=sessions,
        planned=ctx.days_per_week,
        volume_kg=volume,
        prev_volume_kg=prev_volume,
        daily_volume_kg=tuple(sorted(daily.items())),
        prs=prs,
        insight=insight,
        insight_is_fallback=stored is None,
    )


# --- get_exercise_progress ---------------------------------------------------------------


@dataclass(frozen=True)
class ProgressPoint:
    on: date
    top_weight_kg: Decimal
    reps_at_top: int
    total_reps: int


@dataclass(frozen=True)
class ExerciseProgress:
    exercise: ExerciseEntry
    unit: Unit
    weeks: int
    points: tuple[ProgressPoint, ...] = ()
    best_weight_kg: Decimal | None = None
    best_reps: int | None = None
    best_on: date | None = None

    @property
    def bodyweight(self) -> bool:
        return self.exercise.equipment == "bodyweight"


async def get_exercise_progress(
    db: AsyncSession,
    ctx: UserContext,
    resolver: ExerciseResolver,
    *,
    exercise: str,
    weeks: int,
    now: datetime,
) -> ExerciseProgress:
    entry = resolve_exercise(resolver, exercise)
    sets = await repo.get_sets_for_exercise(
        db, ctx.user_id, entry.id, since=now - timedelta(weeks=weeks)
    )
    if not sets:
        return ExerciseProgress(entry, ctx.unit, weeks)

    by_day: dict[date, list] = defaultdict(list)
    for s in sets:
        by_day[s.logged_at.astimezone(ctx.tz).date()].append(s)
    points = []
    for day in sorted(by_day):
        rows = by_day[day]
        top = max(r.weight_kg for r in rows)
        points.append(
            ProgressPoint(
                on=day,
                top_weight_kg=top,
                reps_at_top=max(r.reps for r in rows if r.weight_kg == top),
                total_reps=sum(r.reps for r in rows),
            )
        )
    if entry.equipment == "bodyweight":
        best = max(sets, key=lambda s: (s.reps, s.logged_at))
    else:
        best = max(sets, key=lambda s: (estimated_1rm(s.weight_kg, s.reps), s.logged_at))
    return ExerciseProgress(
        entry,
        ctx.unit,
        weeks,
        points=tuple(points),
        best_weight_kg=best.weight_kg,
        best_reps=best.reps,
        best_on=best.logged_at.astimezone(ctx.tz).date(),
    )
