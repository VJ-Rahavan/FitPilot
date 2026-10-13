"""Guided session tools: start_session, complete_set, skip_exercise, end_session."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from mcp.types import CallToolResult
from pydantic import Field

from server.presenters.sessions import present_complete, present_end, present_skip, present_start
from server.services import sessions
from server.services.resolver_cache import get_resolver
from server.tools.logging_tools import UNIT_DESCRIPTION, parse_unit_or_error
from server.tools.registry import WIDGET_URI, apps, run_tool


@apps.tool(
    resource_uri=WIDGET_URI,
    name="start_session",
    title="Start workout",
    description=(
        "Start today's guided workout when the user says 'start my workout', "
        "or resume the one in progress."
    ),
)
async def start_session() -> CallToolResult:
    async def handler(db, ctx):
        result = await sessions.start_session(
            db, ctx, await get_resolver(db), now=datetime.now(UTC)
        )
        return present_start(result)

    return await run_tool(handler)


@apps.tool(
    resource_uri=WIDGET_URI,
    name="complete_set",
    title="Complete set",
    description=(
        "Log the current set when the user says 'done' or 'only got 6'. "
        "Omit reps and weight if the target was hit."
    ),
)
async def complete_set(
    reps: Annotated[
        int | None,
        Field(
            ge=1,
            le=100,
            description="Reps done, only if different from the target. 'Only got 6' means 6.",
        ),
    ] = None,
    weight: Annotated[
        float | None,
        Field(
            ge=0,
            le=2000,
            description=(
                "Weight used, only if different from the target or when FitGen asks for it. "
                "'Did 190' means 190."
            ),
        ),
    ] = None,
    unit: Annotated[str | None, Field(description=UNIT_DESCRIPTION)] = None,
    effort: Annotated[
        Literal["easy", "ok", "hard", "failed"] | None,
        Field(
            description="How the set being logged felt, only if the user said. easy: 'easy', "
            "'too light'. ok: 'felt good', 'solid', 'nailed it'. hard: 'tough', 'rough', "
            "'heavy'. failed: 'brutal', 'barely made it', 'couldn't finish'. Never call "
            "complete_set again just to add effort to a set already logged."
        ),
    ] = None,
) -> CallToolResult:
    async def handler(db, ctx):
        result = await sessions.complete_set(
            db,
            ctx,
            await get_resolver(db),
            reps=reps,
            weight=weight,
            unit=parse_unit_or_error(unit, ctx.unit),
            now=datetime.now(UTC),
            effort=effort,
        )
        return present_complete(result)

    return await run_tool(handler)


@apps.tool(
    resource_uri=WIDGET_URI,
    name="skip_exercise",
    title="Skip exercise",
    description="Skip the current exercise when the user says 'skip this', and move to the next.",
)
async def skip_exercise() -> CallToolResult:
    async def handler(db, ctx):
        result = await sessions.skip_exercise(
            db, ctx, await get_resolver(db), now=datetime.now(UTC)
        )
        return present_skip(result)

    return await run_tool(handler)


@apps.tool(
    resource_uri=WIDGET_URI,
    name="end_session",
    title="End workout",
    description=(
        "Finish the workout when the user says they're done, and summarize it. "
        "Cancels a workout with no sets."
    ),
)
async def end_session() -> CallToolResult:
    async def handler(db, ctx):
        result = await sessions.end_session(db, ctx, await get_resolver(db), now=datetime.now(UTC))
        return present_end(result)

    return await run_tool(handler)
