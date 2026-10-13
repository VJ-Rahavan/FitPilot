"""Deterministic weekly coaching line, used until a background AI insight exists."""

from decimal import Decimal


def fallback_insight(
    *, sessions: int, planned: int | None, volume_kg: Decimal, prev_volume_kg: Decimal
) -> str:
    if sessions == 0:
        return "No training logged this week yet. Even one short session keeps your momentum going."
    change = (volume_kg - prev_volume_kg) / prev_volume_kg if prev_volume_kg else None
    if planned and sessions < planned:
        missing = planned - sessions
        more = "one more session" if missing == 1 else f"{missing} more sessions"
        # The summary already says "N of M planned days", so don't repeat the count.
        return (
            "Every session counts most right now. "
            f"Fitting in {more} will do more for your progress than adding weight."
        )
    if change is not None and change < Decimal("-0.10"):
        return (
            "Your volume dipped compared to last week. If you're run down that's fine, "
            "otherwise aim to hit every prescribed rep next week."
        )
    if change is not None and change > 0:
        return (
            "You hit your planned sessions and lifted more than last week. "
            "Keep the plan and add weight wherever the reps felt easy."
        )
    return "Solid, consistent week. Keep chasing your prescribed reps and the weight will follow."
