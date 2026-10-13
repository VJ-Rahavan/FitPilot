"""Utility tools end to end over MCP against the seeded test database.

Skipped without Postgres.
"""

import re
import time
import uuid
from datetime import UTC, datetime, timedelta
from datetime import time as clock_time
from decimal import Decimal

import httpx2
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.auth import DEMO_USER
from server.db import repository as repo
from server.db.models import ReadinessCheck, UserProfile
from server.db.session import make_engine
from server.services import workouts
from server.services.context import load_user_context
from server.services.resolver_cache import get_resolver
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
    assert text_of(result).startswith("Three cues for deadlift. First, bar over mid foot")
    unknown = await call(tools_url, "get_form_cues", {"exercise": "zumba"})
    assert unknown.is_error and "couldn't find" in text_of(unknown)


async def test_calculate_macros(tools_url):
    latest = await call(tools_url, "calculate_macros")
    assert re.match(
        r"For strength at your latest weigh-in of \d+\.\d pounds, aim for about ", text_of(latest)
    )
    given = await call(tools_url, "calculate_macros", {"bodyweight": 80, "unit": "kg"})
    assert text_of(given) == (
        "For strength at 80 kilograms, aim for about 2,750 calories a day. That's roughly "
        "145 grams of protein, 70 grams of fat and 385 grams of carbs. Treat it as a "
        "starting point."
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
    assert text.startswith(
        "Thanks for telling me. If something hurts, stop that exercise and see a doctor or "
        "physical therapist before doing it again."
    )
    assert "train as planned" not in text.lower()
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


async def _targets(sessionmaker):
    """Today's (or the next scheduled day's) targets, straight from the service."""
    async with sessionmaker() as db:
        ctx = await load_user_context(db, DEMO_USER.user_id)
        plan = await repo.get_active_plan(db, ctx.user_id)
        now = datetime.now(UTC)
        day, next_day = await workouts.pick_plan_day(db, ctx, plan, now.astimezone(ctx.tz).date())
        items, _, _ = await workouts.plan_day_targets(
            db, ctx, await get_resolver(db), day or next_day, now=now
        )
        return ctx, items


async def test_lightened_day_does_not_lower_progression(tools_url):
    engine = make_engine(TEST_DATABASE_URL)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        ctx, before = await _targets(sessionmaker)
        yesterday = datetime.now(ctx.tz).date() - timedelta(days=1)
        logged_at = datetime.combine(yesterday, clock_time(18), tzinfo=ctx.tz)
        async with sessionmaker() as db:
            for item in before:
                if item.suggestion.weight_kg:
                    await repo.add_logged_set(
                        db,
                        ctx.user_id,
                        exercise_id=item.exercise.id,
                        reps=item.reps,
                        weight_kg=item.suggestion.weight_kg * Decimal("0.8"),
                        logged_at=logged_at,
                        batch_id=str(uuid.uuid4()),
                    )
            await repo.upsert_readiness(db, ctx.user_id, yesterday, "light", False)
            await db.commit()

        _, after = await _targets(sessionmaker)
        assert [i.suggestion.weight_kg for i in after] == [i.suggestion.weight_kg for i in before]

        # Control: without the readiness record, the lighter day would drag targets down.
        async with sessionmaker() as db:
            await db.execute(delete(ReadinessCheck))
            await db.commit()
        _, control = await _targets(sessionmaker)
        assert [i.suggestion.weight_kg for i in control] != [i.suggestion.weight_kg for i in before]
    finally:
        await engine.dispose()


async def test_readiness_during_workout_lightens_remaining_exercises(tools_url):
    await call(tools_url, "end_session")
    await call(tools_url, "start_session")
    engine = make_engine(TEST_DATABASE_URL)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def sets_by_position():
        async with sessionmaker() as db:
            session = await repo.get_active_session_full(db, DEMO_USER.user_id)
            return [(e.position, e.sets, e.target_weight_kg) for e in session.exercises]

    try:
        before = await sets_by_position()
        check = await call(tools_url, "readiness_check", {"sleep_hours": 4.5})
        assert text_of(check).endswith("starting with the next exercise.")
        after = await sets_by_position()
        assert after[0] == before[0]  # the exercise in progress is untouched
        for (_, sets_b, weight_b), (_, sets_a, weight_a) in zip(before[1:], after[1:], strict=True):
            assert sets_a == max(1, sets_b - 1)
            if weight_b:
                assert weight_a <= weight_b  # equal only when floored at the bar
    finally:
        await engine.dispose()
        await call(tools_url, "end_session")
        await _db_execute(delete(ReadinessCheck))


async def test_set_preferences_bad_unit(tools_url):
    result = await call(tools_url, "set_preferences", {"unit": "stone"})
    assert result.is_error
    assert text_of(result) == "I can use pounds or kilograms. Which would you like?"
