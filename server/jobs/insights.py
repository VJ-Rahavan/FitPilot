"""`regenerate_weekly_insight`: turn a week's computed metrics into a short coaching note,
spoken by `get_weekly_summary` ("Coach's note: ...") in place of the fallback line.

Privacy: the model sees only numbers, exercise names, the goal and the unit. Never the
user's name, id or any other personal data.
"""

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.db import repository as repo
from server.db.models import Job
from server.jobs.llm import LLMClient
from server.presenters.speech import percent_change, say_volume
from server.services.context import load_user_context
from server.services.exercise_resolver import normalize
from server.services.units import Unit, display_weight
from server.services.workouts import get_weekly_summary

MAX_CHARS = 240
TREND_WEEKS = 4

SYSTEM_PROMPT = (
    "You are FitGen, a concise strength coach. Your words are spoken aloud by a voice "
    "assistant right after the week's sessions, volume and records have been read out, so "
    "don't repeat those. Using only the training data provided, write one or two short "
    "sentences, each under 20 words, with one idea per sentence: what to focus on next and "
    "why. Base it on the data: a stalled lift, missed sessions, a drop in volume, or what "
    "is working. Name at least one exercise from the data. Don't prescribe new weights or "
    "rep targets, because the plan sets those. Always put the unit in full words after any "
    "weight, for example '145 pounds'. Use short everyday words. Plain text only: no "
    "greeting, no lists, no markdown, no emoji, no symbols. Say 'percent' and 'personal "
    "record', not % or PR. Never mention pain, injury, soreness, medication, diet or "
    f"supplements. Stay under {MAX_CHARS} characters."
)


class InsightRejected(ValueError):
    """The model's text failed validation; the message says why (fed back on retry)."""


# --- Metrics (computed in Python, the only thing the model sees) -----------------------


@dataclass
class LiftTrend:
    name: str
    this_week_top: Decimal  # in the user's unit
    reps_at_top: int
    start_top: Decimal | None  # earliest top weight in the trend window
    stalled_sessions: int  # consecutive recent sessions at the same top weight


@dataclass
class WeeklyMetrics:
    week_start: date
    unit: Unit
    goal: str | None
    sessions: int
    planned: int | None
    volume_kg: Decimal
    volume_change_pct: int | None  # None while the week is in progress
    week_complete: bool
    records: list[tuple[str, Decimal]] = field(default_factory=list)
    lifts: list[LiftTrend] = field(default_factory=list)

    @property
    def exercise_names(self) -> list[str]:
        return [lift.name for lift in self.lifts] + [name for name, _ in self.records]

    @property
    def numbers(self) -> set[str]:
        """Every number the model was given, as it would be written."""
        values = [self.sessions, self.volume_change_pct, self.planned]
        values += [w for _, w in self.records]
        for lift in self.lifts:
            values += [lift.this_week_top, lift.reps_at_top, lift.start_top]
        return {_num(Decimal(v)) for v in values if v is not None}


def _week_end(week_start: date, tz) -> datetime:
    return datetime.combine(week_start + timedelta(days=7), time.min, tzinfo=tz)


async def build_metrics(
    db: AsyncSession, user_id: int, now: datetime, week_start: date | None = None
) -> WeeklyMetrics:
    """Metrics for the week starting `week_start` (default: the current week at `now`)."""
    ctx = await load_user_context(db, user_id)
    as_of = now
    if week_start is not None:
        as_of = min(now, _week_end(week_start, ctx.tz) - timedelta(minutes=1))
    summary = await get_weekly_summary(db, ctx, weeks_ago=0, now=as_of)
    unit = ctx.unit
    week_end = _week_end(summary.week_start, ctx.tz)
    complete = now >= week_end

    start_dt = week_end - timedelta(days=7)
    sets = await repo.get_sets_between(
        db, user_id, start_dt - timedelta(weeks=TREND_WEEKS), week_end
    )

    # Per exercise: top weight per training day, oldest first.
    days: dict[str, dict[date, list]] = defaultdict(lambda: defaultdict(list))
    for s in sets:
        if s.weight_kg > 0:
            days[s.exercise.name][s.logged_at.astimezone(ctx.tz).date()].append(s)

    lifts = []
    for name, by_day in days.items():
        ordered_days = sorted(by_day)
        this_week = [d for d in ordered_days if d >= summary.week_start]
        if not this_week:
            continue
        tops = [max(x.weight_kg for x in by_day[d]) for d in ordered_days]
        last_rows = by_day[this_week[-1]]
        top_now = max(x.weight_kg for x in last_rows)
        stalled = 1
        for prev in reversed(tops[:-1]):
            if prev != tops[-1]:
                break
            stalled += 1
        lifts.append(
            LiftTrend(
                name=name,
                this_week_top=display_weight(top_now, unit),
                reps_at_top=max(x.reps for x in last_rows if x.weight_kg == top_now),
                start_top=display_weight(tops[0], unit) if len(tops) > 1 else None,
                stalled_sessions=stalled,
            )
        )
    return WeeklyMetrics(
        week_start=summary.week_start,
        unit=unit,
        goal=ctx.goal,
        sessions=summary.sessions,
        planned=summary.planned,
        volume_kg=summary.volume_kg,
        # A partial week compared with a full one is misleading, so only compare complete weeks.
        volume_change_pct=(
            percent_change(summary.volume_kg, summary.prev_volume_kg) if complete else None
        ),
        week_complete=complete,
        records=[(n, display_weight(w, unit)) for n, w in summary.prs],
        lifts=lifts,
    )


def _num(value: Decimal) -> str:
    text = f"{value:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def render_prompt(m: WeeklyMetrics) -> str:
    word = "pounds" if m.unit == "lb" else "kilograms"
    sessions = (
        f"{m.sessions} of {m.planned} planned sessions" if m.planned else f"{m.sessions} sessions"
    )
    week = "This week" if m.week_complete else "This week so far (the week is not over)"
    line = f"{week}: {sessions}, total volume {say_volume(m.volume_kg, m.unit)}"
    if m.volume_change_pct is not None:
        direction = "up" if m.volume_change_pct >= 0 else "down"
        line += f", {direction} {abs(m.volume_change_pct)} percent vs last week"
    lines = [f"Goal: {m.goal or 'general strength'}.", line + "."]
    if m.records:
        records = "; ".join(f"{n} {_num(w)} {word}" for n, w in m.records)
        lines.append(f"New personal records (already announced): {records}.")
    for lift in m.lifts:
        text = f"{lift.name}: top set {_num(lift.this_week_top)} {word} for {lift.reps_at_top} reps"
        if lift.start_top is not None:
            text += f", was {_num(lift.start_top)} {word} {TREND_WEEKS} weeks ago"
        if lift.stalled_sessions >= 3:
            text += f", same top weight for {lift.stalled_sessions} sessions"
        lines.append(text + ".")
    return "\n".join(lines)


# --- Validation -------------------------------------------------------------------------

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_MARKDOWN = re.compile(r"[*#`_]|^\s*[-•]\s", re.MULTILINE)
_UNSAFE = re.compile(
    r"\b(pain\w*|hurt\w*|injur\w*|sore\w*|ache\w*|strain\w*|sprain\w*|ice|medic\w*|doctor\w*|"
    r"physio\w*|diagnos\w*|supplement\w*|protein|calorie\w*|diet\w*)\b",
    re.IGNORECASE,
)
_UNIT = re.compile(r"(\d+(?:\.\d+)?)\s*(lbs?|kgs?)\b\.?(?=(\s+([A-Za-z]+))?)", re.IGNORECASE)
# After "175 lb", these words keep "pounds"; any other word makes it an adjective ("175-pound").
_NOT_A_NOUN = {
    "and",
    "at",
    "by",
    "each",
    "for",
    "from",
    "in",
    "is",
    "last",
    "next",
    "of",
    "on",
    "or",
    "per",
    "the",
    "this",
    "to",
    "was",
    "were",
    "with",
    "x",
    "you",
    "your",
}


def _spell_unit(match: re.Match) -> str:
    number, unit, next_word = match.group(1), match.group(2).lower(), match.group(4)
    base = "pound" if unit.startswith("lb") else "kilogram"
    keep_period = match.group(0).endswith(".")
    if next_word and next_word.lower() not in _NOT_A_NOUN and not keep_period:
        return f"{number}-{base}"
    word = base if number in ("1", "1.0") else base + "s"
    return f"{number} {word}" + ("." if keep_period else "")


def validate_insight(
    text: str, known_terms: list[str], known_numbers: set[str] | frozenset = frozenset()
) -> str:
    """Normalize the model's text for speech, or raise InsightRejected with the reason."""
    if _MARKDOWN.search(text):  # checked on the raw text, before whitespace is flattened
        raise InsightRejected("it used markdown or list formatting")
    cleaned = unicodedata.normalize("NFKC", text)
    for dash in ("‐", "‑", "‒", "–", "—"):
        cleaned = cleaned.replace(dash, "-")
    # Quotes add nothing when spoken and hide sentence ends like `."`.
    cleaned = cleaned.replace("’", "'")
    for quote in ('"', "“", "”"):
        cleaned = cleaned.replace(quote, "")
    cleaned = re.sub(r"\s*(->|→)\s*", " to ", cleaned)
    cleaned = re.sub(r"\s*%", " percent", cleaned)
    cleaned = re.sub(r"\bPRs\b", "personal records", cleaned)
    cleaned = re.sub(r"\bPR\b", "personal record", cleaned)
    cleaned = _UNIT.sub(_spell_unit, cleaned)
    cleaned = re.sub(
        r"(\d|pounds?|kilograms?)\s*[x×]\s*(\d)", r"\1 for \2", cleaned, flags=re.IGNORECASE
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned.endswith((".", "!", "?")):
        raise InsightRejected("it did not end with a full sentence")
    sentences = [s for s in _SENTENCE_END.split(cleaned) if s]
    if len(sentences) > 2:
        raise InsightRejected(f"it had {len(sentences)} sentences; use one or two")
    if len(cleaned) > MAX_CHARS:
        raise InsightRejected(f"it was {len(cleaned)} characters, over the {MAX_CHARS} limit")
    if unsafe := _UNSAFE.search(cleaned):
        raise InsightRejected(f"it mentioned {unsafe.group(0)!r}; avoid pain, injury and diet")
    normalized = normalize(cleaned)
    names_an_exercise = any(normalize(t) in normalized for t in known_terms)
    numbers = {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", cleaned)}
    if not names_an_exercise and not numbers & set(known_numbers):
        raise InsightRejected("it did not mention any exercise or number from the data")
    return cleaned


# --- Job handler --------------------------------------------------------------------------


async def regenerate_weekly_insight(
    job: Job, *, sessionmaker: async_sessionmaker[AsyncSession], llm: LLMClient, now: datetime
) -> str:
    """Returns a short outcome for the job log. The LLM call runs outside any transaction."""
    week_start = (
        date.fromisoformat(job.payload["week_start"]) if job.payload.get("week_start") else None
    )
    async with sessionmaker() as db:
        metrics = await build_metrics(db, job.user_id, now, week_start)
    if metrics.sessions == 0:
        return f"skipped: no training logged in the week of {metrics.week_start}"

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
            feedback = (
                f"\n\nYour previous answer was rejected because {exc}. "
                "Reply again following every rule."
            )

    async with sessionmaker() as db:
        await repo.upsert_insight(db, job.user_id, metrics.week_start, insight, llm.model_id)
        await db.commit()
    return f"stored insight for week of {metrics.week_start}"
