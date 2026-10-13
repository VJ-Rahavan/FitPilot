"""Utility tools: plate_calculator, get_form_cues, readiness_check, set_preferences,
calculate_macros."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from mcp.types import CallToolResult
from pydantic import Field

from server.presenters.utilities import (
    present_form_cues,
    present_macros,
    present_plates,
    present_preferences,
    present_readiness,
)
from server.services import preferences, readiness, utilities
from server.services.resolver_cache import get_resolver
from server.tools.logging_tools import UNIT_DESCRIPTION, parse_unit_or_error
from server.tools.registry import WIDGET_URI, apps, run_tool


@apps.tool(
    resource_uri=WIDGET_URI,
    name="plate_calculator",
    title="Plate calculator",
    description="Which plates to load on each side of the bar for a target weight.",
)
async def plate_calculator(
    weight: Annotated[
        float,
        Field(gt=0, le=2000, description="Total weight on the bar, e.g. 'two twenty five' is 225"),
    ],
    unit: Annotated[str | None, Field(description=UNIT_DESCRIPTION)] = None,
) -> CallToolResult:
    async def handler(db, ctx):
        result = utilities.plate_calculator(
            ctx, weight=weight, unit=parse_unit_or_error(unit, ctx.unit)
        )
        return present_plates(result)

    return await run_tool(handler)


@apps.tool(
    resource_uri=WIDGET_URI,
    name="get_form_cues",
    title="Form cues",
    description="Short technique cues for an exercise. Use when the user asks how to do a lift.",
)
async def get_form_cues(
    exercise: Annotated[str, Field(description="Exercise name as spoken, e.g. 'deadlift'")],
) -> CallToolResult:
    async def handler(db, ctx):
        return present_form_cues(utilities.form_cues(await get_resolver(db), exercise))

    return await run_tool(handler)


@apps.tool(
    resource_uri=WIDGET_URI,
    name="readiness_check",
    title="Readiness check",
    description=(
        "Check how ready the user is to train today from sleep, soreness and energy, and "
        "lighten today's weights if needed."
    ),
)
async def readiness_check(
    sleep_hours: Annotated[
        float | None,
        Field(
            ge=0,
            le=16,
            description="Hours slept, only if a number was said ('slept six hours'). "
            "Otherwise put what they said, like 'slept badly', in notes.",
        ),
    ] = None,
    soreness: Annotated[
        Literal["none", "mild", "moderate", "severe"] | None,
        Field(
            description="'Fresh' is none, 'a bit stiff' is mild, 'pretty sore' is moderate, "
            "'legs are wrecked' or 'can barely walk' is severe."
        ),
    ] = None,
    energy: Annotated[
        Literal["low", "normal", "high"] | None,
        Field(description="'Exhausted' or 'dragging' is low; 'feeling great' is high."),
    ] = None,
    pain_mentioned: Annotated[
        bool,
        Field(description="True if the user mentioned any pain, injury or something hurting."),
    ] = False,
    notes: Annotated[
        str | None,
        Field(
            max_length=500,
            description="Anything else the user said, in their words. Always include any "
            "mention of pain or injury.",
        ),
    ] = None,
) -> CallToolResult:
    async def handler(db, ctx):
        result = await readiness.readiness_check(
            db,
            ctx,
            sleep_hours=sleep_hours,
            soreness=soreness,
            energy=energy,
            notes=notes,
            pain_mentioned=pain_mentioned,
            now=datetime.now(UTC),
        )
        return present_readiness(result)

    return await run_tool(handler)


@apps.tool(
    resource_uri=WIDGET_URI,
    name="set_preferences",
    title="Set preferences",
    description=(
        "Set the user's units, bar weight, goal, training days or time zone. "
        "Also used for first-time setup."
    ),
)
async def set_preferences(
    unit: Annotated[str | None, Field(description='"lb" or "kg"')] = None,
    bar_weight: Annotated[
        float | None, Field(gt=0, le=80, description="Bar weight, in the chosen unit")
    ] = None,
    goal: Annotated[
        str | None,
        Field(description="strength, muscle, fat loss or general fitness"),
    ] = None,
    days_per_week: Annotated[
        int | None, Field(ge=1, le=7, description="Training days per week")
    ] = None,
    timezone: Annotated[
        str | None,
        Field(
            description="Where the user is, as said: a city ('London', 'Mumbai'), a US zone "
            "('Eastern', 'Pacific') or an IANA name."
        ),
    ] = None,
) -> CallToolResult:
    async def handler(db, ctx):
        result = await preferences.set_preferences(
            db,
            ctx,
            unit=unit,
            bar_weight=bar_weight,
            goal=goal,
            days_per_week=days_per_week,
            timezone=timezone,
        )
        return present_preferences(result)

    return await run_tool(handler)


@apps.tool(
    resource_uri=WIDGET_URI,
    name="calculate_macros",
    title="Calculate macros",
    description="Estimate daily calories, protein, fat and carbs from bodyweight and goal.",
)
async def calculate_macros(
    bodyweight: Annotated[
        float | None,
        Field(gt=20, le=1000, description="Bodyweight. Omit to use the latest weigh-in."),
    ] = None,
    unit: Annotated[str | None, Field(description=UNIT_DESCRIPTION)] = None,
) -> CallToolResult:
    async def handler(db, ctx):
        result = await utilities.calculate_macros(
            db, ctx, bodyweight=bodyweight, unit=parse_unit_or_error(unit, ctx.unit)
        )
        return present_macros(result)

    return await run_tool(handler)
