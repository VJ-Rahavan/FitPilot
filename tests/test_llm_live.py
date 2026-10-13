"""Opt-in live check against the real LLM provider (spends quota).

Run with: FITGEN_LIVE_LLM=1 uv run pytest tests/test_llm_live.py -s
"""

import os
from datetime import date
from decimal import Decimal

import pytest

from server.config import Settings
from server.jobs.insights import (
    SYSTEM_PROMPT,
    InsightRejected,
    LiftTrend,
    WeeklyMetrics,
    render_prompt,
    validate_insight,
)
from server.jobs.llm import build_llm_client
from server.services.units import to_kg

pytestmark = pytest.mark.skipif(
    os.environ.get("FITGEN_LIVE_LLM") != "1", reason="set FITGEN_LIVE_LLM=1 to call the real LLM"
)


async def test_live_insight_passes_validation():
    metrics = WeeklyMetrics(
        week_start=date(2026, 10, 5),
        unit="lb",
        goal="strength",
        sessions=3,
        planned=4,
        volume_kg=to_kg(24460, "lb"),
        volume_change_pct=8,
        week_complete=True,
        records=[("Bench Press", Decimal("190"))],
        lifts=[
            LiftTrend("Bench Press", Decimal("190"), 6, Decimal("175"), 1),
            LiftTrend("Barbell Row", Decimal("145"), 8, Decimal("145"), 4),
        ],
    )
    llm = build_llm_client(Settings())
    prompt = render_prompt(metrics)
    feedback = ""
    for attempt in range(2):
        text = await llm.complete(system=SYSTEM_PROMPT, user=prompt + feedback)
        try:
            insight = validate_insight(text, metrics.exercise_names, metrics.numbers)
            break
        except InsightRejected as exc:
            if attempt == 1:
                raise
            feedback = f"\n\nYour previous answer was rejected because {exc}."
    print(f"\n{llm.model_id}: {insight}")
