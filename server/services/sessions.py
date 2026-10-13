"""Guided workout sessions: start, complete a set, skip, end.

The server owns the position (no IDs from the client). Targets are snapshotted into
`session_exercises` when a session starts, so defaults stay fixed for the whole workout.
"""

import uuid
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from server.db import repository as repo
from server.db.models import SessionExercise, WorkoutSession
from server.services.context import UserContext, UserFacingError
from server.services.effort import (
    Adjustment,
    Beat,
    Effort,
    adjust_remaining,
    beat_last_time,
    effective_effort,
)
from server.services.exercise_resolver import ExerciseEntry, ExerciseResolver
from server.services.records import PRKind, detect_pr
from server.services.session_state import Position, after_set, after_skip
from server.services.units import Unit, to_kg
from server.services.workouts import pick_plan_day, plan_day_targets, queue_insight

# A repeated complete_set this soon after the last one is a retried request, not a new set.
RETRY_WINDOW = timedelta(seconds=8)

NO_ACTIVE_SESSION = "You don't have a workout in progress. Say start my workout to begin."
ALL_EXERCISES_DONE = "You've finished every exercise. Say end workout to wrap up."
NO_PLAN = (
    "You don't have a training plan yet, so there's no workout to start. "
    "Once you have one, say start my workout."
)


# --- Views --------------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionItem:
    exercise: ExerciseEntry
    sets: int
    reps: int
    target_weight_kg: Decimal | None
    status: str

    @property
    def bodyweight(self) -> bool:
        return self.exercise.equipment == "bodyweight"


@dataclass(frozen=True)
class SessionView:
    """A session's exercises and the current position, ready for presenting."""

    day_name: str
    unit: Unit
    items: tuple[SessionItem, ...]
    position: Position
    # The same set in the previous session of the current exercise: (reps, weight_kg).
    last_time: tuple[int, Decimal] | None = None

    @property
    def finished(self) -> bool:
        return self.position.finished([i.sets for i in self.items])

    @property
    def current(self) -> SessionItem | None:
        return None if self.finished else self.items[self.position.exercise]

    @property
    def next_item(self) -> SessionItem | None:
        idx = self.position.exercise + 1
        return self.items[idx] if idx < len(self.items) else None


def _view(session: WorkoutSession, ctx: UserContext, resolver: ExerciseResolver) -> SessionView:
    items = tuple(
        SessionItem(resolver.get(e.exercise_id), e.sets, e.reps, e.target_weight_kg, e.status)
        for e in session.exercises
    )
    name = session.plan_day.name if session.plan_day else "your workout"
    return SessionView(
        name, ctx.unit, items, Position(session.current_position, session.current_set)
    )


def _set_position(session: WorkoutSession, pos: Position) -> None:
    session.current_position = pos.exercise
    session.current_set = pos.sets_done


async def _require_active(db: AsyncSession, ctx: UserContext) -> WorkoutSession:
    session = await repo.get_active_session_full(db, ctx.user_id)
    if session is None:
        raise UserFacingError(NO_ACTIVE_SESSION)
    return session


LAST_TIME_LOOKBACK = timedelta(days=60)


async def _previous_session_sets(
    db: AsyncSession, ctx: UserContext, exercise_id: int, today: date
) -> list[tuple[int, Decimal]]:
    """Sets (reps, weight_kg) of this exercise's most recent earlier session, in order.

    Days lightened by a readiness check are skipped: they aren't a fair comparison.
    """
    since = datetime.combine(today, time.min, tzinfo=ctx.tz) - LAST_TIME_LOOKBACK
    sets = await repo.get_sets_for_exercise(db, ctx.user_id, exercise_id, since=since)
    lightened = await repo.get_lightened_dates(db, ctx.user_id, since.date())
    by_day: dict[date, list[tuple[int, Decimal]]] = {}
    for s in sets:
        day = s.logged_at.astimezone(ctx.tz).date()
        if day < today and day not in lightened:
            by_day.setdefault(day, []).append((s.reps, s.weight_kg))
    return by_day[max(by_day)] if by_day else []


async def _with_last_time(
    db: AsyncSession,
    ctx: UserContext,
    view: SessionView,
    today: date,
    known: tuple[int, list[tuple[int, Decimal]]] | None = None,
) -> SessionView:
    """`known`: (exercise id, its previous-session sets), to skip the query when unchanged."""
    item = view.current
    if item is None:
        return view
    if known is not None and known[0] == item.exercise.id:
        previous = known[1]
    else:
        previous = await _previous_session_sets(db, ctx, item.exercise.id, today)
    index = view.position.sets_done
    last = previous[index] if index < len(previous) else None
    return replace(view, last_time=last)


# --- start_session ------------------------------------------------------------------------


@dataclass(frozen=True)
class StartResult:
    view: SessionView
    resumed: bool
    rest_day: bool  # started the next scheduled day because today is a rest day
    closed_stale_on: date | None  # an unfinished workout from this day was closed


async def _close_stale(
    db: AsyncSession, ctx: UserContext, session: WorkoutSession, now: datetime
) -> bool:
    """Finish an old active session (or delete it if empty). True if it had sets."""
    sets = await repo.get_session_sets(db, ctx.user_id, session.id)
    if not sets:
        await repo.delete_session(db, ctx.user_id, session.id)
        await db.flush()
        return False
    session.status = "finished"
    session.finished_at = sets[-1].logged_at
    await queue_insight(db, ctx, about=sets[-1].logged_at, run_after=now)
    await db.flush()
    return True


async def start_session(
    db: AsyncSession, ctx: UserContext, resolver: ExerciseResolver, *, now: datetime
) -> StartResult:
    today = now.astimezone(ctx.tz).date()
    closed_on = None
    active = await repo.get_active_session_full(db, ctx.user_id)
    if active is not None:
        started_on = active.started_at.astimezone(ctx.tz).date()
        if started_on == today:
            view = await _with_last_time(db, ctx, _view(active, ctx, resolver), today)
            return StartResult(view, True, False, None)
        if await _close_stale(db, ctx, active, now):
            closed_on = started_on

    plan = await repo.get_active_plan(db, ctx.user_id)
    if plan is None or not plan.days:
        raise UserFacingError(NO_PLAN)
    day, next_day = await pick_plan_day(db, ctx, plan, today)
    rest_day = day is None
    day = day or next_day
    if not day.exercises:
        raise UserFacingError(f"{day.name} doesn't have any exercises in your plan yet.")
    targets, _, _ = await plan_day_targets(db, ctx, resolver, day, now=now)

    session = WorkoutSession(
        user_id=ctx.user_id,
        plan_day_id=day.id,
        status="active",
        current_position=0,
        current_set=0,
        started_at=now,
    )
    session.exercises = [
        SessionExercise(
            position=i,
            exercise_id=t.exercise.id,
            sets=t.sets,
            reps=t.reps,
            target_weight_kg=t.suggestion.weight_kg,
            status="pending",
        )
        for i, t in enumerate(targets)
    ]
    session.plan_day = day
    db.add(session)
    await db.flush()
    view = await _with_last_time(db, ctx, _view(session, ctx, resolver), today)
    return StartResult(view, False, rest_day, closed_on)


# --- complete_set -------------------------------------------------------------------------


@dataclass(frozen=True)
class CompleteResult:
    exercise: ExerciseEntry
    set_number: int
    total_sets: int
    reps: int
    target_reps: int
    weight_kg: Decimal
    target_weight_kg: Decimal | None  # the target before this set (to tell if weight changed)
    pr: PRKind | None
    exercise_finished: bool
    view: SessionView  # after advancing (unchanged for a duplicate)
    duplicate: bool = False  # a retried request; nothing new was logged
    effort: Effort | None = None  # as said, or "failed" when 2+ reps short
    adjustment: Adjustment | None = None  # new target for the rest of this exercise
    beat: Beat | None = None  # this set vs the same set last session


async def complete_set(
    db: AsyncSession,
    ctx: UserContext,
    resolver: ExerciseResolver,
    *,
    reps: int | None,
    weight: float | None,
    unit: Unit,
    now: datetime,
    effort: Effort | None = None,
) -> CompleteResult:
    session = await _require_active(db, ctx)
    view = _view(session, ctx, resolver)

    last = await repo.get_last_logged_set(db, ctx.user_id)
    if (
        last is not None
        and last.session_exercise_id in {e.id for e in session.exercises}
        and now - last.logged_at <= RETRY_WINDOW
        and (reps is None or reps == last.reps)
        and (weight is None or to_kg(weight, unit) == last.weight_kg)
    ):
        if effort and last.effort is None:
            last.effort = effort  # effort said with a retried request: keep it, no adjustment
            await db.flush()
        entry = resolver.get(last.exercise_id)
        return CompleteResult(
            entry, 0, 0, last.reps, last.reps, last.weight_kg, None, None, False, view, True
        )

    item = view.current
    if item is None:
        raise UserFacingError(ALL_EXERCISES_DONE)
    row = session.exercises[view.position.exercise]
    target_before = item.target_weight_kg

    if weight is not None:
        weight_kg = to_kg(weight, unit)
    elif item.target_weight_kg is not None:
        weight_kg = item.target_weight_kg
    elif item.bodyweight:
        weight_kg = Decimal("0")
    else:
        raise UserFacingError(f"What weight are you using for {item.exercise.name.lower()}?")
    if not item.bodyweight:
        row.target_weight_kg = weight_kg  # a changed weight carries to the remaining sets
    done_reps = reps if reps is not None else item.reps

    effort = effective_effort(effort, done_reps, item.reps)
    today = now.astimezone(ctx.tz).date()
    previous = await _previous_session_sets(db, ctx, item.exercise.id, today)
    set_index = view.position.sets_done
    beat = None
    if set_index < len(previous):
        last_reps, last_weight = previous[set_index]
        beat = beat_last_time(
            reps=done_reps,
            weight_kg=weight_kg,
            last_reps=last_reps,
            last_weight_kg=last_weight,
            bodyweight=item.bodyweight,
        )

    prev_max_weight, prev_max_reps = await repo.get_pr_baseline(
        db, ctx.user_id, item.exercise.id, weight_kg
    )
    pr = detect_pr(
        weight_kg=weight_kg,
        reps=done_reps,
        previous_max_weight_kg=prev_max_weight,
        previous_max_reps_at_weight=prev_max_reps,
        bodyweight=item.bodyweight,
    )
    await repo.add_logged_set(
        db,
        ctx.user_id,
        exercise_id=item.exercise.id,
        reps=done_reps,
        weight_kg=weight_kg,
        logged_at=now,
        batch_id=str(uuid.uuid4()),
        session_id=session.id,
        session_exercise_id=row.id,
        effort=effort,
    )

    set_number = view.position.sets_done + 1
    new_pos = after_set(view.position, [i.sets for i in view.items])
    exercise_finished = new_pos.exercise != view.position.exercise
    adjustment = None
    if exercise_finished:
        row.status = "done"
    else:
        adjustment = adjust_remaining(
            effort=effort,
            reps=done_reps,
            target_reps=item.reps,
            weight_kg=weight_kg,
            equipment=item.exercise.equipment,
            unit=ctx.unit,
            bar_kg=ctx.bar_weight_kg,
            easy_steps_used=row.easy_steps,
        )
        if adjustment is not None:
            row.target_weight_kg = adjustment.weight_kg
            if adjustment.action == "up":
                row.easy_steps += 1
    _set_position(session, new_pos)
    await db.flush()
    return CompleteResult(
        exercise=item.exercise,
        set_number=set_number,
        total_sets=item.sets,
        reps=done_reps,
        target_reps=item.reps,
        weight_kg=weight_kg,
        target_weight_kg=target_before,
        pr=pr,
        exercise_finished=exercise_finished,
        view=await _with_last_time(
            db, ctx, _view(session, ctx, resolver), today, known=(item.exercise.id, previous)
        ),
        effort=effort,
        adjustment=adjustment,
        beat=beat,
    )


# --- skip_exercise ------------------------------------------------------------------------


@dataclass(frozen=True)
class SkipResult:
    skipped: ExerciseEntry
    view: SessionView  # after skipping
    partial: bool = False  # some sets were done before moving on


async def skip_exercise(
    db: AsyncSession, ctx: UserContext, resolver: ExerciseResolver, *, now: datetime
) -> SkipResult:
    session = await _require_active(db, ctx)
    view = _view(session, ctx, resolver)
    item = view.current
    if item is None:
        raise UserFacingError(ALL_EXERCISES_DONE)
    row = session.exercises[view.position.exercise]
    # Some sets done counts as done (cut short); none done counts as skipped.
    partial = view.position.sets_done > 0
    row.status = "done" if partial else "skipped"
    _set_position(session, after_skip(view.position))
    await db.flush()
    today = now.astimezone(ctx.tz).date()
    view = await _with_last_time(db, ctx, _view(session, ctx, resolver), today)
    return SkipResult(item.exercise, view, partial)


# --- end_session --------------------------------------------------------------------------


@dataclass(frozen=True)
class EndResult:
    unit: Unit
    day_name: str
    cancelled: bool  # no sets were logged, so the session was discarded
    duration: timedelta = timedelta()
    sets: int = 0
    volume_kg: Decimal = Decimal("0")
    exercises_done: int = 0
    skipped: tuple[str, ...] = ()  # planned exercises with no sets (skipped or not reached)
    prs: tuple[tuple[str, Decimal], ...] = ()  # (exercise, new best weight)


async def end_session(
    db: AsyncSession, ctx: UserContext, resolver: ExerciseResolver, *, now: datetime
) -> EndResult:
    session = await _require_active(db, ctx)
    view = _view(session, ctx, resolver)
    sets = await repo.get_session_sets(db, ctx.user_id, session.id)
    if not sets:
        await repo.delete_session(db, ctx.user_id, session.id)
        return EndResult(ctx.unit, view.day_name, cancelled=True)

    session.status = "finished"
    session.finished_at = now

    best: dict[int, tuple[str, Decimal]] = {}
    for s in sets:
        if s.weight_kg > 0 and s.weight_kg > best.get(s.exercise_id, ("", Decimal(-1)))[1]:
            best[s.exercise_id] = (resolver.get(s.exercise_id).name, s.weight_kg)
    before = await repo.get_max_weights_before(db, ctx.user_id, list(best), session.started_at)
    prs = tuple(
        (name, w) for ex_id, (name, w) in best.items() if ex_id in before and w > before[ex_id]
    )
    trained = {s.exercise_id for s in sets}
    await queue_insight(db, ctx, about=session.started_at, run_after=now)
    await db.flush()
    return EndResult(
        unit=ctx.unit,
        day_name=view.day_name,
        cancelled=False,
        duration=now - session.started_at,
        sets=len(sets),
        volume_kg=sum((Decimal(s.reps) * s.weight_kg for s in sets), Decimal("0")),
        exercises_done=len(trained),
        skipped=tuple(i.exercise.name for i in view.items if i.exercise.id not in trained),
        prs=prs,
    )
