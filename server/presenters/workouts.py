"""Voice text + UI components for each MVP tool.

The text must fully answer the request when spoken on a screenless device; the
components are an optional visual of the same information.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from server.catalog.validation import Display
from server.presenters.speech import (
    join_words,
    percent_change,
    plural,
    say_date,
    say_volume,
    sets_of_reps,
    short_date,
    short_volume,
    spoken_exercise,
)
from server.services.context import UserFacingError
from server.services.progression import Suggestion
from server.services.units import Unit, display_weight, format_weight
from server.services.workouts import (
    BodyMetricResult,
    ExerciseProgress,
    LogWorkoutResult,
    TodaysWorkout,
    UndoResult,
    WeeklySummary,
)


@dataclass(frozen=True)
class Presentation:
    text: str
    components: list[dict[str, Any]] = field(default_factory=list)
    display: Display = "fragment"


def _num(value: Decimal) -> float | int:
    """Decimal → JSON number, integral when possible."""
    return int(value) if value == value.to_integral_value() else float(value)


# --- errors ------------------------------------------------------------------------------


def present_error(err: UserFacingError) -> Presentation:
    alert: dict[str, Any] = {"type": "alert", "variant": "warning", "message": err.message}
    components = [alert]
    if err.suggestions:
        components.append(
            {
                "type": "list",
                "title": "Did you mean",
                "items": [{"title": s} for s in err.suggestions],
            }
        )
    return Presentation(err.message, components)


# --- log_workout -------------------------------------------------------------------------


def present_log_workout(r: LogWorkoutResult) -> Presentation:
    name = spoken_exercise(r.exercise.name)
    bodyweight = r.exercise.equipment == "bodyweight"
    what = sets_of_reps([r.reps] * r.sets)
    at = "" if bodyweight else f" at {format_weight(r.weight_kg, r.unit)}"
    short_at = "Bodyweight" if bodyweight else format_weight(r.weight_kg, r.unit, spoken=False)

    if r.duplicate:
        text = f"You already logged {name}, {what}{at}, a moment ago, so I didn't log it twice."
        return Presentation(text, [{"type": "alert", "variant": "info", "message": text}])

    text = f"Logged {name}: {what}{at}."
    if r.pr == "weight" and r.previous_best_kg is not None:
        text += (
            f" That's a new personal record, up from {format_weight(r.previous_best_kg, r.unit)}!"
        )
    elif r.pr == "reps":
        text += " That's a rep record at this weight!"

    card_children: list[dict[str, Any]] = [
        {
            "type": "metric",
            "label": "Logged",
            "value": f"{r.sets} × {r.reps}",
            "caption": short_at,
            "icon": "dumbbell",
        }
    ]
    if r.pr:
        card_children.append(
            {
                "type": "alert",
                "variant": "success",
                "title": "New personal record",
                "message": "Heaviest ever." if r.pr == "weight" else "Most reps at this weight.",
            }
        )
    return Presentation(
        text, [{"type": "card", "title": r.exercise.name, "children": card_children}]
    )


# --- undo_last_log -----------------------------------------------------------------------


def present_undo(r: UndoResult | None) -> Presentation:
    if r is None:
        text = "There's nothing to undo yet."
        return Presentation(text, [{"type": "alert", "variant": "info", "message": text}])
    at = "" if r.bodyweight else f" at {format_weight(r.weight_kg, r.unit)}"
    text = f"Removed your last log: {spoken_exercise(r.exercise)}, {sets_of_reps(r.reps)}{at}."
    if r.rewound_session:
        text += " I've moved your workout back to that set."
    return Presentation(
        text, [{"type": "alert", "variant": "info", "title": "Log removed", "message": text}]
    )


# --- log_body_metric ---------------------------------------------------------------------


def present_body_metric(r: BodyMetricResult) -> Presentation:
    weight = format_weight(r.weight_kg, r.unit, precise=True)
    text = f"Logged your bodyweight at {weight}."
    change_pct = None
    if r.change_kg is not None and r.compared_days:
        when = "yesterday" if r.compared_days == 1 else f"{r.compared_days} days ago"
        delta = format_weight(abs(r.change_kg), r.unit, precise=True)
        if delta.startswith("0 "):  # less than 0.05 of a unit
            text += f" That's the same as {when}."
        else:
            direction = "up" if r.change_kg > 0 else "down"
            text += f" That's {direction} {delta} from {when}."
            previous = r.weight_kg - r.change_kg
            change_pct = float(r.change_kg / previous * 100) if previous else None

    good_direction = "down" if r.goal in ("fat_loss", "cut", "lose_weight") else "up"
    metric: dict[str, Any] = {
        "type": "metric",
        "label": "Bodyweight",
        "value": format_weight(r.weight_kg, r.unit, spoken=False, precise=True).split()[0],
        "unit": r.unit,
        "good_direction": good_direction,
        "icon": "scale",
    }
    if change_pct is not None:
        metric["change_pct"] = round(change_pct, 1)
    return Presentation(text, [metric])


# --- get_todays_workout ------------------------------------------------------------------


READINESS_NOTE = {
    "reduce": "After your readiness check, I've taken 10 percent off today's weights.",
    "light": (
        "After your readiness check, I've taken 20 percent off today's weights and dropped a set."
    ),
    "rest": (
        "Your readiness check suggested a rest day. If you train anyway, I've taken "
        "20 percent off and dropped a set."
    ),
}


def _suggestion_text(s: Suggestion, unit: Unit) -> str:
    if s.action == "bodyweight":
        return ""
    if s.weight_kg is None:
        return ", pick a weight you can do with good form"
    return f" at {format_weight(s.weight_kg, unit)}"


def _suggestion_cells(s: Suggestion, unit: Unit) -> tuple[str, str]:
    if s.action == "bodyweight":
        return "Bodyweight", ""
    if s.weight_kg is None:
        return "Your choice", "New"
    change = {"increase": "Up", "decrease": "Deload", "hold": "Same", "lighter": "Lighter"}.get(
        s.action, ""
    )
    return format_weight(s.weight_kg, unit, spoken=False), change


def present_todays_workout(w: TodaysWorkout) -> Presentation:
    if not w.has_plan:
        text = "You don't have a training plan yet, so there's nothing scheduled for today."
        return Presentation(text, [{"type": "alert", "variant": "info", "message": text}], "full")

    if w.day_name is None:
        text = f"Today is a rest day. Your next session is {w.next_day_name} on {w.next_weekday}."
        return Presentation(
            text,
            [{"type": "alert", "variant": "info", "title": "Rest day", "message": text}],
            "full",
        )

    parts = [
        f"{spoken_exercise(i.exercise.name).capitalize()}, "
        f"{sets_of_reps([i.reps] * i.sets)}{_suggestion_text(i.suggestion, w.unit)}."
        for i in w.items
    ]
    intro = f"Today is {w.day_name}, {plural(len(w.items), 'exercise')}."
    if w.already_trained_today:
        intro = f"You've already logged some training today. Today's plan is {w.day_name}."
    text = " ".join([intro, *parts])
    increased = [
        spoken_exercise(i.exercise.name) for i in w.items if i.suggestion.action == "increase"
    ]
    deloaded = [
        spoken_exercise(i.exercise.name) for i in w.items if i.suggestion.action == "decrease"
    ]
    if w.readiness != "full":
        # Readiness overrides the usual progression notes for today.
        text += " " + READINESS_NOTE[w.readiness]
    else:
        if increased:
            text += f" You've earned more weight on {join_words(increased)}."
        if deloaded:
            text += f" I've lightened {join_words(deloaded)} after two tough sessions."

    rows = []
    for i in w.items:
        weight, change = _suggestion_cells(i.suggestion, w.unit)
        rows.append(
            {
                "exercise": i.exercise.name,
                "target": f"{i.sets} × {i.reps}",
                "weight": weight,
                "change": change,
            }
        )
    table = {
        "type": "table",
        "columns": [
            {"key": "exercise", "label": "Exercise"},
            {"key": "target", "label": "Sets × reps", "align": "center"},
            {"key": "weight", "label": "Weight", "align": "right"},
            {"key": "change", "label": "", "align": "right"},
        ],
        "rows": rows,
    }
    start = {"type": "button", "label": "Start workout", "action": "start_session"}
    return Presentation(
        text,
        [{"type": "card", "title": f"Today · {w.day_name}", "children": [table]}, start],
        "full",
    )


# --- get_weekly_summary ------------------------------------------------------------------


def _week_label(s: WeeklySummary) -> str:
    if s.weeks_ago == 0:
        return "This week"
    if s.weeks_ago == 1:
        return "Last week"
    return f"The week of {say_date(s.week_start)}"


def present_weekly_summary(s: WeeklySummary) -> Presentation:
    label = _week_label(s)
    # The current week isn't over, so comparing it with a full week would mislead.
    change = percent_change(s.volume_kg, s.prev_volume_kg) if s.weeks_ago > 0 else None

    if s.sessions == 0:
        lead = f"{label} you haven't logged any training."
        if s.weeks_ago == 0:
            lead = "You haven't logged any training this week yet."
        text = f"{lead} {s.insight}"
    else:
        days = (
            f"{s.sessions} of {s.planned} planned days" if s.planned else plural(s.sessions, "day")
        )
        lead = "So far this week" if s.weeks_ago == 0 else label
        text = f"{lead} you trained {days} and lifted {say_volume(s.volume_kg, s.unit)}"
        if change is not None and change != 0:
            text += f", {'up' if change > 0 else 'down'} {abs(change)} percent from the week before"
        text += "."
        if s.prs:
            names = join_words([spoken_exercise(n) for n, _ in s.prs])
            text += f" New records on {names}."
        text += f" Coach's note: {s.insight}"

    sessions_value = f"{s.sessions} / {s.planned}" if s.planned else str(s.sessions)
    volume_metric: dict[str, Any] = {
        "type": "metric",
        "label": "Volume",
        "value": short_volume(s.volume_kg, s.unit),
        "icon": "activity",
    }
    if change is not None:
        volume_metric["change_pct"] = change
    metrics = {
        "type": "layout",
        "direction": "grid",
        "columns": 3,
        "children": [
            {"type": "metric", "label": "Sessions", "value": sessions_value, "icon": "calendar"},
            volume_metric,
            {"type": "metric", "label": "Records", "value": len(s.prs), "icon": "trophy"},
        ],
    }
    chart = {
        "type": "chart",
        "chart_type": "bar",
        "title": "Volume by day",
        "data": [
            {"day": d.strftime("%a"), "volume": _num(display_weight(v, s.unit))}
            for d, v in s.daily_volume_kg
        ],
        "x_key": "day",
        "series": [{"key": "volume", "label": "Volume"}],
        "unit": s.unit,
    }
    components: list[dict[str, Any]] = [
        {
            "type": "text",
            "content": f"{label} · from {short_date(s.week_start)}",
            "variant": "heading",
        },
        metrics,
        chart,
    ]
    if s.prs:
        components.append(
            {
                "type": "list",
                "title": "New records",
                "items": [
                    {"title": n, "badge": format_weight(w, s.unit, spoken=False)} for n, w in s.prs
                ],
            }
        )
    components.append(
        {
            "type": "card",
            "title": "Coach's note",
            "children": [{"type": "text", "content": s.insight}],
        }
    )
    return Presentation(text, components, "full")


# --- get_exercise_progress ---------------------------------------------------------------


def _range_label(weeks: int) -> str:
    return "the last week" if weeks == 1 else f"the last {weeks} weeks"


def present_exercise_progress(p: ExerciseProgress) -> Presentation:
    name = spoken_exercise(p.exercise.name)
    span = _range_label(p.weeks)
    if not p.points:
        text = f"You haven't logged {name} in {span}."
        return Presentation(text, [{"type": "alert", "variant": "info", "message": text}], "full")

    first, last = p.points[0], p.points[-1]
    if p.bodyweight:
        start, end = first.reps_at_top, last.reps_at_top
        if end > start:
            trend = f"your best {name} set went from {start} to {end} reps"
        elif end < start:
            trend = f"your best {name} set dropped from {start} to {end} reps"
        else:
            trend = f"your {name} has held at {plural(end, 'rep')} per set"
        best = f" Your best set was {plural(p.best_reps, 'rep')} on {say_date(p.best_on)}."
    else:
        a, b = format_weight(first.top_weight_kg, p.unit), format_weight(last.top_weight_kg, p.unit)
        start_v = display_weight(first.top_weight_kg, p.unit)
        end_v = display_weight(last.top_weight_kg, p.unit)
        if end_v > start_v:
            trend = f"your {name} went from {a.split()[0]} to {b}"
        elif end_v < start_v:
            trend = f"your {name} dropped from {a.split()[0]} to {b}"
        else:
            trend = f"your {name} has held at {b}"
        best = (
            f" Your best set was {format_weight(p.best_weight_kg, p.unit)} for "
            f"{plural(p.best_reps, 'rep')} on {say_date(p.best_on)}."
        )
    sessions = plural(len(p.points), "session")
    text = f"Over {span}, across {sessions}, {trend}.{best}"

    if p.bodyweight:
        data = [{"date": short_date(pt.on), "reps": pt.reps_at_top} for pt in p.points]
        series, unit = [{"key": "reps", "label": "Best set (reps)"}], None
        start_metric = {
            "type": "metric",
            "label": "Start",
            "value": first.reps_at_top,
            "unit": "reps",
        }
        now_metric = {"type": "metric", "label": "Now", "value": last.reps_at_top, "unit": "reps"}
    else:
        data = [
            {"date": short_date(pt.on), "weight": _num(display_weight(pt.top_weight_kg, p.unit))}
            for pt in p.points
        ]
        series, unit = [{"key": "weight", "label": "Top set"}], p.unit
        start_metric = {
            "type": "metric",
            "label": "Start",
            "value": _num(display_weight(first.top_weight_kg, p.unit)),
            "unit": p.unit,
        }
        now_metric = {
            "type": "metric",
            "label": "Now",
            "value": _num(display_weight(last.top_weight_kg, p.unit)),
            "unit": p.unit,
            "icon": "trophy",
        }
    chart: dict[str, Any] = {
        "type": "chart",
        "chart_type": "line",
        "title": f"{p.exercise.name} · {span}",
        "data": data,
        "x_key": "date",
        "series": series,
    }
    if unit:
        chart["unit"] = unit
    components = [
        {
            "type": "layout",
            "direction": "grid",
            "columns": 2,
            "children": [start_metric, now_metric],
        },
        chart,
    ]
    return Presentation(text, components, "full")
