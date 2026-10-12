"""MVP tools end to end over MCP against the seeded test database.

Skipped when Postgres (TEST_DATABASE_URL) is unreachable.
"""

import time

import httpx2
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from tests.db_support import LATENCY_BUDGET_MS, assert_three_parts, call, text_of


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
