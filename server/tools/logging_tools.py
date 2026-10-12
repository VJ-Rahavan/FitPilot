"""Tools that record training: log_workout, log_body_metric, undo_last_log."""

from datetime import UTC, datetime
from typing import Annotated

from mcp.types import CallToolResult
from pydantic import Field

from server.presenters.workouts import (
    present_body_metric,
    present_log_workout,
    present_undo,
)
from server.services import workouts
from server.services.context import UserFacingError
from server.services.resolver_cache import get_resolver
from server.services.units import parse_unit
from server.tools.registry import WIDGET_URI, apps, run_tool

UNIT_DESCRIPTION = 'Weight unit, "lb" or "kg". Omit to use the user\'s preferred unit.'


def parse_unit_or_error(value: str | None, default):
    try:
        return parse_unit(value, default=default)
    except ValueError:
        raise UserFacingError(
            f"I can log weights in pounds or kilograms, but not {value}."
        ) from None


@apps.tool(
    resource_uri=WIDGET_URI,
    name="log_workout",
    title="Log workout",
    description=(
        "Log sets of an exercise, e.g. '3 sets of 5 squats at 225'. Reports personal records."
    ),
)
async def log_workout(
    exercise: Annotated[str, Field(description="Exercise name as spoken, e.g. 'bench'")],
    sets: Annotated[int, Field(ge=1, le=20, description="Number of sets")],
    reps: Annotated[int, Field(ge=1, le=100, description="Reps per set")],
    weight: Annotated[
        float | None,
        Field(ge=0, le=2000, description="Weight per rep. Omit for bodyweight exercises."),
    ] = None,
    unit: Annotated[str | None, Field(description=UNIT_DESCRIPTION)] = None,
) -> CallToolResult:
    async def handler(db, ctx):
        result = await workouts.log_workout(
            db,
            ctx,
            await get_resolver(db),
            exercise=exercise,
            sets=sets,
            reps=reps,
            weight=weight,
            unit=parse_unit_or_error(unit, ctx.unit),
            now=datetime.now(UTC),
        )
        return present_log_workout(result)

    return await run_tool(handler)


@apps.tool(
    resource_uri=WIDGET_URI,
    name="log_body_metric",
    title="Log bodyweight",
    description="Log the user's bodyweight and report how it changed over the last week.",
)
async def log_body_metric(
    bodyweight: Annotated[float, Field(gt=20, le=1000, description="Bodyweight")],
    unit: Annotated[str | None, Field(description=UNIT_DESCRIPTION)] = None,
) -> CallToolResult:
    async def handler(db, ctx):
        result = await workouts.log_body_metric(
            db,
            ctx,
            bodyweight=bodyweight,
            unit=parse_unit_or_error(unit, ctx.unit),
            now=datetime.now(UTC),
        )
        return present_body_metric(result)

    return await run_tool(handler)


@apps.tool(
    resource_uri=WIDGET_URI,
    name="undo_last_log",
    title="Undo last log",
    description="Remove the most recently logged sets and say what was removed.",
)
async def undo_last_log() -> CallToolResult:
    async def handler(db, ctx):
        return present_undo(await workouts.undo_last_log(db, ctx))

    return await run_tool(handler)
