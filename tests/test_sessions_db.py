"""Guided session tools end to end over MCP against the seeded test database.

Today's plan day depends on the real date: on a rest day `start_session` starts the next
scheduled day, so assertions accept either opening. Skipped without Postgres.
"""

import re
import time
import uuid
from datetime import UTC, datetime, timedelta

import httpx2
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import func, select

from server.auth import DEMO_USER
from server.db.models import Exercise, Job, LoggedSet, WorkoutSession
from server.db.session import make_engine
from server.services import sessions
from server.services.sessions import ALL_EXERCISES_DONE, NO_ACTIVE_SESSION
from server.services.workouts import INSIGHT_JOB
from tests.db_support import (
    LATENCY_BUDGET_MS,
    TEST_DATABASE_URL,
    assert_three_parts,
    call,
    text_of,
)

SET_DONE = re.compile(r"^Set (\d+) of (\d+) done")
FIRST_UP = re.compile(r"First up: ([a-z\- ]+), ")


@pytest.fixture(autouse=True)
def no_retry_window(monkeypatch):
    """Tests send sets seconds apart; the retry guard would read them as repeats."""
    monkeypatch.setattr(sessions, "RETRY_WINDOW", timedelta(0))


async def _db_scalar(query):
    engine = make_engine(TEST_DATABASE_URL)
    try:
        async with engine.connect() as conn:
            return await conn.scalar(query)
    finally:
        await engine.dispose()


async def _end_if_active(url):
    """Leave no active session behind for the next test."""
    await call(url, "end_session")


async def test_complete_set_without_session(tools_url):
    await _end_if_active(tools_url)
    result = await call(tools_url, "complete_set")
    assert result.is_error and text_of(result) == NO_ACTIVE_SESSION
    skip = await call(tools_url, "skip_exercise")
    assert skip.is_error and text_of(skip) == NO_ACTIVE_SESSION


async def test_full_walk_through(tools_url):
    await _end_if_active(tools_url)
    start = await call(tools_url, "start_session")
    assert not start.is_error, text_of(start)
    assert text_of(start).startswith(("Starting ", "Today's a rest day, so let's do "))
    assert_three_parts(start, "full")

    first = await call(tools_url, "complete_set")
    assert SET_DONE.match(text_of(first)), text_of(first)
    # Only the short confirmation, maybe a record; never a read-back of the next set.
    assert "Next, set" not in text_of(first)
    assert_three_parts(first, "fragment")
    assert [c["type"] for c in first.structured_content["components"]][:2] == [
        "session_card",
        "timer",
    ]

    short = await call(tools_url, "complete_set", {"reps": 2})
    assert " done: 2 reps" in text_of(short)

    skip = await call(tools_url, "skip_exercise")
    assert text_of(skip).startswith("Moving on from ")  # two sets were done, so it's partial
    assert "Next up:" in text_of(skip)

    # Finish the remaining exercises; guard against loops.
    for _ in range(40):
        result = await call(tools_url, "complete_set")
        assert not result.is_error, text_of(result)
        if "That's the whole workout" in text_of(result):
            break
    else:
        pytest.fail("workout never finished")

    extra = await call(tools_url, "complete_set")
    assert extra.is_error and text_of(extra) == ALL_EXERCISES_DONE

    end = await call(tools_url, "end_session")
    text = text_of(end)
    assert text.startswith("Nice work. You finished ")
    assert " pounds lifted." in text
    assert "You skipped" not in text  # the skipped exercise had 2 sets logged
    assert_three_parts(end, "full")

    queued = await _db_scalar(
        select(func.count())
        .select_from(Job)
        .where(Job.user_id == DEMO_USER.user_id, Job.kind == INSIGHT_JOB, Job.status == "queued")
    )
    assert queued == 1

    again = await call(tools_url, "end_session")
    assert again.is_error and text_of(again) == NO_ACTIVE_SESSION


async def test_resume_and_weight_override(tools_url):
    await _end_if_active(tools_url)
    await call(tools_url, "start_session")
    heavier = await call(tools_url, "complete_set", {"weight": 500})
    assert text_of(heavier).startswith("Set 1 of ")
    assert "at 500 pounds" in text_of(heavier)

    resumed = await call(tools_url, "start_session")
    assert text_of(resumed).startswith("Welcome back to ")
    assert ", set 2 of " in text_of(resumed)
    assert "at 500 pounds" in text_of(resumed)  # the new weight carries to remaining sets
    await call(tools_url, "end_session")


async def test_undo_after_cut_short_skip(tools_url):
    await _end_if_active(tools_url)
    await call(tools_url, "start_session")
    await call(tools_url, "complete_set")
    await call(tools_url, "complete_set")
    skip = await call(tools_url, "skip_exercise")
    assert text_of(skip).startswith("Moving on from ")
    undo = await call(tools_url, "undo_last_log")
    assert text_of(undo).endswith("I've moved your workout back to that set.")
    resumed = await call(tools_url, "start_session")
    assert ", set 2 of " in text_of(resumed)  # one set of the first exercise is still logged
    await call(tools_url, "end_session")


async def test_free_form_log_during_session_does_not_rewind(tools_url):
    await _end_if_active(tools_url)
    start = await call(tools_url, "start_session")
    exercise = FIRST_UP.search(text_of(start)).group(1)
    await call(tools_url, "complete_set")
    await call(tools_url, "log_workout", {"exercise": exercise, "sets": 1, "reps": 3, "weight": 50})
    undo = await call(tools_url, "undo_last_log")
    assert "moved your workout back" not in text_of(undo)
    resumed = await call(tools_url, "start_session")
    assert ", set 2 of " in text_of(resumed)
    await call(tools_url, "end_session")


async def test_retried_complete_set_is_not_logged_twice(tools_url, monkeypatch):
    monkeypatch.setattr(sessions, "RETRY_WINDOW", timedelta(seconds=8))
    await _end_if_active(tools_url)
    await call(tools_url, "start_session")
    first = await call(tools_url, "complete_set")
    assert text_of(first).startswith("Set 1 of ")
    retry = await call(tools_url, "complete_set")
    assert text_of(retry).startswith("I already logged that set. You're on ")
    assert ", set 2 of " in text_of(retry)
    await call(tools_url, "end_session")


async def test_undo_rewinds_the_session(tools_url):
    await _end_if_active(tools_url)
    await call(tools_url, "start_session")
    await call(tools_url, "complete_set")
    undo = await call(tools_url, "undo_last_log")
    assert text_of(undo).endswith("I've moved your workout back to that set.")
    redo = await call(tools_url, "complete_set")
    assert text_of(redo).startswith("Set 1 of ")
    await call(tools_url, "end_session")


async def test_end_with_no_sets_cancels(tools_url):
    await _end_if_active(tools_url)
    await call(tools_url, "start_session")
    end = await call(tools_url, "end_session")
    assert text_of(end) == "You hadn't logged any sets, so I cancelled the workout."
    active = await _db_scalar(
        select(func.count())
        .select_from(WorkoutSession)
        .where(WorkoutSession.user_id == DEMO_USER.user_id, WorkoutSession.status == "active")
    )
    assert active == 0


async def test_stale_session_is_closed_on_start(tools_url):
    await _end_if_active(tools_url)
    two_days_ago = datetime.now(UTC) - timedelta(days=2)
    engine = make_engine(TEST_DATABASE_URL)
    try:
        async with engine.begin() as conn:
            bench = await conn.scalar(select(Exercise.id).where(Exercise.name == "Bench Press"))
            session_id = await conn.scalar(
                WorkoutSession.__table__.insert()
                .values(
                    user_id=DEMO_USER.user_id,
                    status="active",
                    current_position=0,
                    current_set=1,
                    started_at=two_days_ago,
                )
                .returning(WorkoutSession.id)
            )
            await conn.execute(
                LoggedSet.__table__.insert().values(
                    user_id=DEMO_USER.user_id,
                    exercise_id=bench,
                    session_id=session_id,
                    batch_id=str(uuid.uuid4()),
                    reps=5,
                    weight_kg=80,
                    logged_at=two_days_ago,
                )
            )
    finally:
        await engine.dispose()

    start = await call(tools_url, "start_session")
    assert text_of(start).startswith("I closed your unfinished workout from ")
    status = await _db_scalar(select(WorkoutSession.status).where(WorkoutSession.id == session_id))
    assert status == "finished"
    await call(tools_url, "end_session")


async def test_session_latency_under_budget(tools_url):
    await _end_if_active(tools_url)
    calls = [
        ("start_session", {}),
        ("complete_set", {}),
        ("complete_set", {"reps": 4}),
        ("skip_exercise", {}),
        ("undo_last_log", {}),
        ("end_session", {}),
    ]
    async with httpx2.AsyncClient() as http:
        async with streamable_http_client(tools_url, http_client=http) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool("ping", {})
                slow = {}
                for name, args in calls:
                    start = time.perf_counter()
                    result = await session.call_tool(name, args)
                    ms = (time.perf_counter() - start) * 1000
                    assert not result.is_error, (name, result.content[0].text)
                    if ms >= LATENCY_BUDGET_MS:
                        slow[name] = round(ms)
    assert not slow, f"over {LATENCY_BUDGET_MS} ms: {slow}"
