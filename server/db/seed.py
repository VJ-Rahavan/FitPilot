"""Seed the exercise catalog and the demo user with 8 weeks of training history.

    uv run python -m server.db.seed            # create missing tables, reseed demo user
    uv run python -m server.db.seed --reset    # drop and recreate all tables first

Deterministic: the same `today` always produces the same history.
"""

import argparse
import asyncio
import random
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from server.auth import DEMO_USER
from server.config import get_settings
from server.db.init_db import create_schema, reset_schema
from server.db.models import (
    BodyMetric,
    Exercise,
    ExerciseAlias,
    LoggedSet,
    Plan,
    PlanDay,
    PlanExercise,
    User,
    UserProfile,
    WorkoutSession,
)
from server.db.seed_data import EXERCISES, PLAN_DAYS, PLAN_NAME, PlanExerciseSeed
from server.db.session import make_engine
from server.services.exercise_resolver import normalize
from server.services.units import to_kg

DEMO_EXTERNAL_KEY = "demo"
DEMO_TIMEZONE = "Asia/Kolkata"
HISTORY_WEEKS = 8
SKIPPED_SESSIONS = 4
STEP_LB = 5  # smallest weight jump the simulated lifter makes
SESSION_START = time(18, 0)
MINUTES_PER_SET = 3


# --- Pure history simulation (no DB) ------------------------------------------------------


@dataclass
class SimSet:
    exercise: str
    reps: int
    weight_lb: float


@dataclass
class SimSession:
    day_index: int
    on: date
    sets: list[SimSet] = field(default_factory=list)


@dataclass
class _LiftState:
    weight_lb: float
    capacity_lb: float
    hits_at_weight: int = 0
    misses_at_weight: int = 0


def _round_step(weight_lb: float) -> float:
    return max(STEP_LB, round(weight_lb / STEP_LB) * STEP_LB)


def _simulate_exercise(rng: random.Random, pe: PlanExerciseSeed, state: _LiftState | None):
    """One exercise in one session; returns its sets and updates `state` for next time."""
    sets: list[SimSet] = []
    if state is None:  # bodyweight: reps vary a little, no load progression
        for _ in range(pe.sets):
            reps = pe.reps if rng.random() > 0.2 else pe.reps - 1
            sets.append(SimSet(pe.exercise, reps, 0.0))
        return sets

    for i in range(pe.sets):
        effective = state.weight_lb * (1 + 0.015 * i)  # later sets are harder
        p_miss = min(0.9, max(0.02, 0.03 + (effective - state.capacity_lb) / state.capacity_lb * 6))
        reps = pe.reps - rng.randint(1, 2) if rng.random() < p_miss else pe.reps
        sets.append(SimSet(pe.exercise, reps, state.weight_lb))

    # Same progressive overload rule the server applies (Phase 3).
    if all(s.reps >= pe.reps for s in sets):
        state.hits_at_weight += 1
        state.misses_at_weight = 0
        if state.hits_at_weight >= 2:
            state.weight_lb += STEP_LB
            state.hits_at_weight = 0
    else:
        state.misses_at_weight += 1
        state.hits_at_weight = 0
        if state.misses_at_weight >= 2:
            state.weight_lb = _round_step(state.weight_lb * 0.9)
            state.misses_at_weight = 0
    state.capacity_lb *= 1.012  # slow real strength gain
    return sets


def simulate_history(today: date, seed: int = 42) -> list[SimSession]:
    """Training sessions for the `HISTORY_WEEKS` weeks before `today` (exclusive)."""
    rng = random.Random(seed)
    first_monday = today - timedelta(days=today.weekday()) - timedelta(weeks=HISTORY_WEEKS - 1)

    planned: list[tuple[int, date]] = []
    for week in range(HISTORY_WEEKS):
        for day_index, (_, weekday, _) in enumerate(PLAN_DAYS):
            on = first_monday + timedelta(weeks=week, days=weekday)
            if on < today:
                planned.append((day_index, on))
    skipped = set(rng.sample(range(len(planned)), SKIPPED_SESSIONS))

    states: dict[str, _LiftState] = {}
    for _, _, exercises in PLAN_DAYS:
        for pe in exercises:
            if pe.start_weight_lb > 0:
                states[pe.exercise] = _LiftState(pe.start_weight_lb, pe.start_weight_lb * 1.08)

    sessions: list[SimSession] = []
    for i, (day_index, on) in enumerate(planned):
        if i in skipped:
            continue
        session = SimSession(day_index, on)
        for pe in PLAN_DAYS[day_index][2]:
            session.sets.extend(_simulate_exercise(rng, pe, states.get(pe.exercise)))
        sessions.append(session)
    return sessions


def simulate_bodyweight(today: date, seed: int = 7) -> list[tuple[date, float]]:
    """Twice-weekly weigh-ins (Mon, Thu), slowly trending up for a strength goal."""
    rng = random.Random(seed)
    first_monday = today - timedelta(days=today.weekday()) - timedelta(weeks=HISTORY_WEEKS - 1)
    out: list[tuple[date, float]] = []
    for week in range(HISTORY_WEEKS):
        for weekday in (0, 3):
            on = first_monday + timedelta(weeks=week, days=weekday)
            if on <= today:
                lb = 182.0 + 0.4 * (week + weekday / 7) + rng.uniform(-0.6, 0.6)
                out.append((on, round(lb * 5) / 5))  # scales show 0.2 lb steps
    return out


# --- Database writes ----------------------------------------------------------------------


async def upsert_exercises(db: AsyncSession) -> dict[str, Exercise]:
    """Insert missing exercises; refresh equipment, cues and aliases on existing ones."""
    existing = {
        e.name: e
        for e in await db.scalars(select(Exercise).options(selectinload(Exercise.aliases)))
    }
    for seed in EXERCISES:
        ex = existing.get(seed.name)
        if ex is None:
            ex = Exercise(name=seed.name, equipment=seed.equipment, aliases=[])
            db.add(ex)
            existing[seed.name] = ex
        ex.equipment = seed.equipment
        ex.form_cues = list(seed.form_cues)
        wanted = {normalize(a) for a in seed.aliases} - {normalize(seed.name)}
        ex.aliases = [a for a in ex.aliases if a.alias in wanted]
        have = {a.alias for a in ex.aliases}
        ex.aliases.extend(ExerciseAlias(alias=a) for a in sorted(wanted - have))
    await db.flush()
    return existing


async def seed_demo_user(db: AsyncSession, today: date) -> None:
    exercises = await upsert_exercises(db)

    # Rebuild the demo user from scratch (cascades to all of their rows).
    await db.execute(delete(User).where(User.external_key == DEMO_EXTERNAL_KEY))
    await db.flush()

    # Fixed id so get_current_user() needs no lookup until real auth exists.
    user = User(id=DEMO_USER.user_id, external_key=DEMO_EXTERNAL_KEY, name=DEMO_USER.name)
    user.profile = UserProfile(
        unit="lb",
        bar_weight_kg=to_kg(45, "lb"),
        goal="strength",
        days_per_week=4,
        timezone=DEMO_TIMEZONE,
    )
    db.add(user)
    await db.flush()
    await db.execute(
        text("SELECT setval(pg_get_serial_sequence('users', 'id'), (SELECT max(id) FROM users))")
    )

    plan = Plan(user_id=user.id, name=PLAN_NAME, is_active=True)
    for day_index, (day_name, weekday, items) in enumerate(PLAN_DAYS):
        day = PlanDay(day_index=day_index, name=day_name, weekday=weekday)
        day.exercises = [
            PlanExercise(exercise=exercises[pe.exercise], position=pos, sets=pe.sets, reps=pe.reps)
            for pos, pe in enumerate(items)
        ]
        plan.days.append(day)
    db.add(plan)
    await db.flush()

    tz = ZoneInfo(DEMO_TIMEZONE)
    for sim in simulate_history(today):
        start = datetime.combine(sim.on, SESSION_START, tzinfo=tz)
        session = WorkoutSession(
            user_id=user.id,
            plan_day_id=plan.days[sim.day_index].id,
            status="finished",
            current_position=len(PLAN_DAYS[sim.day_index][2]),
            current_set=0,
            started_at=start,
            finished_at=start + timedelta(minutes=MINUTES_PER_SET * len(sim.sets)),
        )
        db.add(session)
        await db.flush()
        # One batch per exercise per session, like a "log 4 sets of bench" request.
        batches = {name: str(uuid.uuid4()) for name in {s.exercise for s in sim.sets}}
        db.add_all(
            LoggedSet(
                user_id=user.id,
                exercise_id=exercises[s.exercise].id,
                session_id=session.id,
                batch_id=batches[s.exercise],
                reps=s.reps,
                weight_kg=to_kg(s.weight_lb, "lb"),
                logged_at=start + timedelta(minutes=MINUTES_PER_SET * i),
            )
            for i, s in enumerate(sim.sets)
        )

    db.add_all(
        BodyMetric(
            user_id=user.id,
            bodyweight_kg=to_kg(lb, "lb"),
            measured_at=datetime.combine(on, time(7, 0), tzinfo=tz),
        )
        for on, lb in simulate_bodyweight(today)
    )
    await db.flush()


async def run(database_url: str, *, reset: bool, today: date | None = None) -> None:
    engine = make_engine(database_url)
    try:
        await (reset_schema if reset else create_schema)(engine)
        today = today or datetime.now(ZoneInfo(DEMO_TIMEZONE)).date()
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            await seed_demo_user(db, today)
            await db.commit()
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reset", action="store_true", help="drop and recreate all tables")
    args = parser.parse_args()
    asyncio.run(run(get_settings().database_url, reset=args.reset))
    print("Seeded demo user and exercise catalog.")


if __name__ == "__main__":
    main()
