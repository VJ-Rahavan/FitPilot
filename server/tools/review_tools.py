"""Tools that read training: get_todays_workout, get_weekly_summary, get_exercise_progress."""

from datetime import UTC, datetime
from typing import Annotated

from mcp.types import CallToolResult
from pydantic import Field

from server.presenters.workouts import (
    present_exercise_progress,
    present_todays_workout,
    present_weekly_summary,
)
from server.services import workouts
from server.services.resolver_cache import get_resolver
from server.tools.registry import WIDGET_URI, apps, run_tool


@apps.tool(
    resource_uri=WIDGET_URI,
    name="get_todays_workout",
    title="Today's workout",
    description="Today's planned workout with a suggested weight for each exercise.",
)
async def get_todays_workout() -> CallToolResult:
    async def handler(db, ctx):
        result = await workouts.get_todays_workout(
            db, ctx, await get_resolver(db), now=datetime.now(UTC)
        )
        return present_todays_workout(result)

    return await run_tool(handler)


@apps.tool(
    resource_uri=WIDGET_URI,
    name="get_weekly_summary",
    title="Weekly summary",
    description="Summary of a training week: sessions, volume trend, records and a coaching note.",
)
async def get_weekly_summary(
    weeks_ago: Annotated[
        int, Field(ge=0, le=52, description="0 for this week, 1 for last week, and so on")
    ] = 0,
) -> CallToolResult:
    async def handler(db, ctx):
        result = await workouts.get_weekly_summary(
            db, ctx, weeks_ago=weeks_ago, now=datetime.now(UTC)
        )
        return present_weekly_summary(result)

    return await run_tool(handler)


@apps.tool(
    resource_uri=WIDGET_URI,
    name="get_exercise_progress",
    title="Exercise progress",
    description="How one exercise has progressed: weight trend and best set.",
)
async def get_exercise_progress(
    exercise: Annotated[str, Field(description="Exercise name as spoken, e.g. 'squat'")],
    weeks: Annotated[int, Field(ge=1, le=104, description="How many weeks back to look")] = 8,
) -> CallToolResult:
    async def handler(db, ctx):
        result = await workouts.get_exercise_progress(
            db, ctx, await get_resolver(db), exercise=exercise, weeks=weeks, now=datetime.now(UTC)
        )
        return present_exercise_progress(result)

    return await run_tool(handler)
