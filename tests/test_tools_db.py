"""MVP tools end to end over MCP against the seeded test database.

Skipped when Postgres (TEST_DATABASE_URL) is unreachable.
"""

import asyncio
import os
import time
from collections.abc import Iterator
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx2
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from server.config import Settings, get_settings
from server.db import session as db_session
from server.db.seed import DEMO_TIMEZONE
from server.db.seed import run as run_seed
from server.services.resolver_cache import clear_resolver_cache
from tests.conftest import _serve
from tests.test_db import TEST_DATABASE_URL

LATENCY_BUDGET_MS = 500


async def _db_reachable() -> bool:
    engine = db_session.make_engine(TEST_DATABASE_URL)
    try:
        async with engine.connect():
            return True
    except Exception:
        return False
    finally:
        await engine.dispose()


def _reset_db_caches() -> None:
    get_settings.cache_clear()
    db_session.get_engine.cache_clear()
    db_session.get_sessionmaker.cache_clear()
    clear_resolver_cache()


@pytest.fixture(scope="module")
def tools_url() -> Iterator[str]:
    if not asyncio.run(_db_reachable()):
        pytest.skip("Postgres not reachable at TEST_DATABASE_URL")
    today = datetime.now(ZoneInfo(DEMO_TIMEZONE)).date()
    asyncio.run(run_seed(TEST_DATABASE_URL, reset=True, today=today))

    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    _reset_db_caches()
    try:
        yield from _serve(Settings(auth_mode="none", database_url=TEST_DATABASE_URL))
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        _reset_db_caches()


async def call(url: str, name: str, args: dict | None = None):
    async with httpx2.AsyncClient() as http:
        async with streamable_http_client(url, http_client=http) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(name, args or {})


def text_of(result) -> str:
    return result.content[0].text


def assert_three_parts(result, display: str) -> None:
    assert result.content and result.content[0].type == "text"
    assert result.structured_content["display"] == display
    assert result.structured_content["components"]


async def test_log_workout_dedupe_and_undo(tools_url):
    args = {"exercise": "bench", "sets": 3, "reps": 5, "weight": 135}
    first = await call(tools_url, "log_workout", args)
    assert not first.is_error, text_of(first)
    assert text_of(first).startswith("Logged bench press: 3 sets of 5 at 135 pounds.")
    assert_three_parts(first, "fragment")

    again = await call(tools_url, "log_workout", args)
    assert "didn't log it twice" in text_of(again)

    undo = await call(tools_url, "undo_last_log")
    assert text_of(undo) == "Removed your last log: bench press, 3 sets of 5 at 135 pounds."
    assert_three_parts(undo, "fragment")


async def test_log_workout_pr(tools_url):
    result = await call(
        tools_url, "log_workout", {"exercise": "squats", "sets": 1, "reps": 1, "weight": 405}
    )
    assert "new personal record" in text_of(result)
    await call(tools_url, "undo_last_log")


async def test_log_workout_kg_and_bodyweight(tools_url):
    kg = await call(
        tools_url,
        "log_workout",
        {"exercise": "rdl", "sets": 2, "reps": 8, "weight": 60, "unit": "kilos"},
    )
    assert "at 60 kilograms" in text_of(kg)
    await call(tools_url, "undo_last_log")
    bw = await call(tools_url, "log_workout", {"exercise": "pullups", "sets": 3, "reps": 7})
    assert text_of(bw).startswith("Logged pull-up: 3 sets of 7.")
    await call(tools_url, "undo_last_log")


async def test_voice_errors(tools_url):
    unknown = await call(
        tools_url, "log_workout", {"exercise": "squatz jumps", "sets": 1, "reps": 5, "weight": 50}
    )
    assert unknown.is_error and "Did you mean" in text_of(unknown)
    assert_three_parts(unknown, "fragment")

    no_weight = await call(tools_url, "log_workout", {"exercise": "bench", "sets": 1, "reps": 5})
    assert no_weight.is_error
    assert text_of(no_weight) == "What weight did you use for bench press?"

    bad_unit = await call(tools_url, "log_body_metric", {"bodyweight": 80, "unit": "stone"})
    assert bad_unit.is_error and "pounds or kilograms" in text_of(bad_unit)


async def test_log_body_metric(tools_url):
    result = await call(tools_url, "log_body_metric", {"bodyweight": 185.4})
    assert text_of(result).startswith("Logged your bodyweight at 185.4 pounds.")
    assert " from " in text_of(result)  # trend vs the seeded weigh-ins
    assert_three_parts(result, "fragment")


async def test_get_todays_workout(tools_url):
    result = await call(tools_url, "get_todays_workout")
    assert not result.is_error
    assert text_of(result).startswith(("Today is", "You've already logged"))
    assert_three_parts(result, "full")


async def test_get_weekly_summary(tools_url):
    result = await call(tools_url, "get_weekly_summary", {"weeks_ago": 1})
    assert text_of(result).startswith("Last week you trained")
    assert "Coach's note:" in text_of(result)
    assert_three_parts(result, "full")


async def test_get_exercise_progress(tools_url):
    result = await call(tools_url, "get_exercise_progress", {"exercise": "squat", "weeks": 8})
    assert "your back squat" in text_of(result)
    assert "Your best set was" in text_of(result)
    assert_three_parts(result, "full")


async def test_latency_under_budget(tools_url):
    """Each tool call, end to end over HTTP, stays under 500 ms against local Postgres."""
    calls = [
        ("get_todays_workout", {}),
        ("get_weekly_summary", {}),
        ("get_exercise_progress", {"exercise": "bench"}),
        ("log_workout", {"exercise": "curl", "sets": 3, "reps": 12, "weight": 25}),
        ("undo_last_log", {}),
        ("log_body_metric", {"bodyweight": 184}),
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
