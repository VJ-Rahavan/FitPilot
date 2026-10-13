"""Utility tools end to end over MCP against the seeded test database.

Skipped without Postgres.
"""

import re
import time

import httpx2
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import delete

from server.auth import DEMO_USER
from server.db.models import ReadinessCheck, UserProfile
from server.db.session import make_engine
from tests.db_support import (
    LATENCY_BUDGET_MS,
    TEST_DATABASE_URL,
    assert_three_parts,
    call,
    text_of,
)


async def _db_execute(statement) -> None:
    engine = make_engine(TEST_DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await conn.execute(statement)
    finally:
        await engine.dispose()


def _weights(text: str) -> list[float]:
    return [float(w) for w in re.findall(r"at (\d+(?:\.\d+)?) pounds", text)]


async def test_plate_calculator(tools_url):
    result = await call(tools_url, "plate_calculator", {"weight": 225})
    assert text_of(result) == "For 225 pounds, put two 45s on each side of the 45-pound bar."
    assert_three_parts(result, "fragment")
    assert result.structured_content["components"][0]["type"] == "plate_diagram"

    kg = await call(tools_url, "plate_calculator", {"weight": 100, "unit": "kg"})
    assert text_of(kg) == (
        "For 100 kilograms, put a 25 and a 15 on each side of the 20-kilogram bar."
    )


async def test_get_form_cues(tools_url):
    result = await call(tools_url, "get_form_cues", {"exercise": "deadlifts"})
    assert text_of(result).startswith("Three cues for deadlift: bar over mid foot")
    unknown = await call(tools_url, "get_form_cues", {"exercise": "zumba"})
    assert unknown.is_error and "couldn't find" in text_of(unknown)


async def test_calculate_macros(tools_url):
    latest = await call(tools_url, "calculate_macros")
    assert text_of(latest).startswith("At your latest weigh-in of ")
    assert "and a goal of strength: about " in text_of(latest)
    given = await call(tools_url, "calculate_macros", {"bodyweight": 80, "unit": "kg"})
    assert text_of(given).startswith(
        "At 80 kilograms and a goal of strength: about 2,750 calories a day, with 145 grams "
        "of protein, 70 grams of fat and 385 grams of carbs."
    )


async def test_readiness_lightens_todays_workout(tools_url):
    before = await call(tools_url, "get_todays_workout")
    check = await call(tools_url, "readiness_check", {"sleep_hours": 4.5, "notes": "feeling flat"})
    assert text_of(check).startswith("With very little sleep, let's keep today light.")
    after = await call(tools_url, "get_todays_workout")
    if "rest day" in text_of(before):
        return  # nothing scheduled today, so there are no weights to compare
    assert "taken 20 percent off today's weights and dropped a set" in text_of(after)
    heavy_before, heavy_after = _weights(text_of(before)), _weights(text_of(after))
    assert heavy_after and all(a < b for a, b in zip(heavy_after, heavy_before, strict=True))
    await _db_execute(delete(ReadinessCheck))


async def test_readiness_pain_advice(tools_url):
    result = await call(tools_url, "readiness_check", {"notes": "my knee hurts when I squat"})
    text = text_of(result)
    assert text.endswith(
        "skip any exercise that hurts and check with a doctor or physical therapist "
        "before training it again."
    )
    await _db_execute(delete(ReadinessCheck))


async def test_set_preferences_changes_units(tools_url):
    to_kg = await call(tools_url, "set_preferences", {"unit": "kg"})
    assert text_of(to_kg) == "Done. I'll use kilograms."
    plates = await call(tools_url, "plate_calculator", {"weight": 60})
    assert "20-kilogram bar" in text_of(plates)  # standard bar moved with the unit
    back = await call(tools_url, "set_preferences", {"unit": "lb", "goal": "build muscle"})
    assert text_of(back) == "Done. I'll use pounds and focus on building muscle."
    bad = await call(tools_url, "set_preferences", {"timezone": "Mars/Olympus"})
    assert bad.is_error and "time zone" in text_of(bad)
    await call(tools_url, "set_preferences", {"goal": "strength"})


async def test_first_run_setup(tools_url):
    await _db_execute(delete(UserProfile).where(UserProfile.user_id == DEMO_USER.user_id))
    ask = await call(tools_url, "set_preferences")
    assert text_of(ask).startswith("Let's set you up.")
    created = await call(
        tools_url, "set_preferences", {"unit": "kg", "goal": "muscle", "days_per_week": 3}
    )
    assert text_of(created).startswith(
        "Done. I'll use kilograms, focus on building muscle and plan for 3 days a week."
    )


async def test_utility_latency_under_budget(tools_url):
    calls = [
        ("plate_calculator", {"weight": 315}),
        ("get_form_cues", {"exercise": "bench"}),
        ("readiness_check", {"sleep_hours": 7}),
        ("set_preferences", {"days_per_week": 4}),
        ("calculate_macros", {"bodyweight": 180}),
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
