"""Integration tests against a real Postgres (the `fitgen_test` database).

Skipped when TEST_DATABASE_URL is unreachable. The database is wiped and reseeded.
"""

import os
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.auth import DEMO_USER
from server.db import repository as repo
from server.db.models import (
    BodyMetric,
    Exercise,
    ExerciseAlias,
    LoggedSet,
    User,
    WorkoutSession,
)
from server.db.seed import run as run_seed
from server.db.seed import simulate_history
from server.db.seed_data import EXERCISES
from server.db.session import make_engine
from server.services.exercise_resolver import ExerciseResolver
from server.services.units import display_weight, to_kg

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://fitgen:fitgen@localhost:5433/fitgen_test"
)
TODAY = date(2026, 10, 10)

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def sessionmaker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = make_engine(TEST_DATABASE_URL)
    try:
        async with engine.connect():
            pass
    except (OSError, Exception) as e:  # connection refused, unknown DB, auth...
        await engine.dispose()
        pytest.skip(f"Postgres not reachable at TEST_DATABASE_URL: {e}")
    await run_seed(TEST_DATABASE_URL, reset=True, today=TODAY)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _count(db: AsyncSession, model, *where) -> int:
    return await db.scalar(select(func.count()).select_from(model).where(*where))


async def test_seed_counts(sessionmaker):
    expected_sessions = len(simulate_history(TODAY))
    async with sessionmaker() as db:
        assert await _count(db, Exercise) == len(EXERCISES)
        assert await _count(db, ExerciseAlias) > len(EXERCISES)
        assert await _count(db, WorkoutSession) == expected_sessions
        assert await _count(db, LoggedSet) > expected_sessions * 10
        assert await _count(db, BodyMetric) == 16


async def test_demo_user_and_profile(sessionmaker):
    async with sessionmaker() as db:
        user = await db.get(User, DEMO_USER.user_id)
        assert user is not None and user.external_key == "demo"
        profile = await repo.get_profile(db, DEMO_USER.user_id)
        assert profile.unit == "lb"
        assert profile.goal == "strength"
        assert profile.days_per_week == 4
        assert display_weight(profile.bar_weight_kg, "lb") == 45


async def test_active_plan(sessionmaker):
    async with sessionmaker() as db:
        plan = await repo.get_active_plan(db, DEMO_USER.user_id)
        assert [d.name for d in plan.days] == ["Upper A", "Lower A", "Upper B", "Lower B"]
        first = plan.days[0].exercises[0]
        assert (first.exercise.name, first.sets, first.reps) == ("Bench Press", 4, 6)


async def test_resolver_from_db(sessionmaker):
    async with sessionmaker() as db:
        resolver = ExerciseResolver(await repo.load_exercise_entries(db))
    assert resolver.resolve("squats").name == "Back Squat"
    assert resolver.resolve("bench").name == "Bench Press"


async def test_reseed_is_idempotent(sessionmaker):
    await run_seed(TEST_DATABASE_URL, reset=False, today=TODAY)
    async with sessionmaker() as db:
        assert await _count(db, Exercise) == len(EXERCISES)
        assert await _count(db, User) == 1
        assert await _count(db, WorkoutSession) == len(simulate_history(TODAY))


async def test_only_one_active_session_per_user(sessionmaker):
    now = datetime.now(UTC)
    async with sessionmaker() as db:
        db.add(WorkoutSession(user_id=DEMO_USER.user_id, status="active", started_at=now))
        await db.flush()
        db.add(WorkoutSession(user_id=DEMO_USER.user_id, status="active", started_at=now))
        with pytest.raises(IntegrityError):
            await db.flush()
        await db.rollback()


async def test_queries_are_scoped_by_user(sessionmaker):
    async with sessionmaker() as db:
        other = User(external_key="other-test-user", name="Other")
        db.add(other)
        await db.flush()
        squat_id = await db.scalar(select(Exercise.id).where(Exercise.name == "Back Squat"))
        await repo.add_logged_set(
            db,
            other.id,
            exercise_id=squat_id,
            reps=1,
            weight_kg=to_kg(500, "lb"),
            logged_at=datetime.now(UTC),
        )
        demo_sets = await repo.get_sets_for_exercise(db, DEMO_USER.user_id, squat_id)
        assert demo_sets and all(s.user_id == DEMO_USER.user_id for s in demo_sets)
        other_last = await repo.get_last_logged_set(db, other.id)
        assert other_last.reps == 1
        assert not await repo.delete_logged_set(db, DEMO_USER.user_id, other_last.id)
        await db.rollback()


async def test_last_logged_set_and_undo(sessionmaker):
    async with sessionmaker() as db:
        last = await repo.get_last_logged_set(db, DEMO_USER.user_id)
        assert last is not None and last.exercise is not None
        assert await repo.delete_logged_set(db, DEMO_USER.user_id, last.id)
        newer = await repo.get_last_logged_set(db, DEMO_USER.user_id)
        assert newer.id != last.id
        await db.rollback()
