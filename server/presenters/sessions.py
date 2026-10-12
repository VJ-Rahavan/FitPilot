"""Voice text + UI components for the guided session tools."""

from datetime import timedelta
from typing import Any

from server.presenters.speech import (
    join_limited,
    plural,
    say_volume,
    sets_of_reps,
    short_volume,
    spoken_exercise,
)
from server.presenters.workouts import Presentation
from server.services.sessions import (
    CompleteResult,
    EndResult,
    SessionItem,
    SessionView,
    SkipResult,
    StartResult,
)
from server.services.units import Unit, display_weight, format_weight

REST_SECONDS_BARBELL = 120
REST_SECONDS_OTHER = 90

_CONTROLS = (
    ("Log set", "complete_set", "primary"),
    ("Skip exercise", "skip_exercise", "secondary"),
    ("End workout", "end_session", "ghost"),
)
_WRAP_UP = "Say end workout to wrap up."


def _target(item: SessionItem, unit: Unit) -> str:
    """ "6 reps at 185 pounds", "6 reps", or a prompt to pick a weight."""
    reps = plural(item.reps, "rep")
    if item.bodyweight:
        return reps
    if item.target_weight_kg is None:
        return f"{reps}, choose your weight"
    return f"{reps} at {format_weight(item.target_weight_kg, unit)}"


def _intro_exercise(item: SessionItem, unit: Unit) -> str:
    """ "bench press, 4 sets of 6 at 185 pounds"."""
    base = f"{spoken_exercise(item.exercise.name)}, {sets_of_reps([item.reps] * item.sets)}"
    if item.bodyweight:
        return base
    if item.target_weight_kg is None:
        return f"{base}, choose your weight"
    return f"{base} at {format_weight(item.target_weight_kg, unit)}"


def _controls() -> dict[str, Any]:
    return {
        "type": "layout",
        "direction": "row",
        "children": [
            {"type": "button", "label": label, "action": action, "variant": variant}
            for label, action, variant in _CONTROLS
        ],
    }


def _session_card(view: SessionView) -> dict[str, Any]:
    item = view.current
    card: dict[str, Any] = {
        "type": "session_card",
        "exercise": item.exercise.name,
        "set_number": view.position.sets_done + 1,
        "total_sets": item.sets,
        "target_reps": item.reps,
        "unit": view.unit,
    }
    if not item.bodyweight and item.target_weight_kg is not None:
        weight = display_weight(item.target_weight_kg, view.unit)
        card["target_weight"] = float(weight)
    if view.position.sets_done + 1 < item.sets:
        card["next_up"] = f"Set {view.position.sets_done + 2} of {item.sets}"
    elif view.next_item is not None:
        card["next_up"] = view.next_item.exercise.name
    else:
        card["next_up"] = "Last set of the workout"
    if item.exercise.form_cues:
        card["form_cue"] = item.exercise.form_cues[0]
    return card


def _plan_table(view: SessionView) -> dict[str, Any]:
    status = {"done": "Done", "skipped": "Skipped", "pending": ""}
    rows = []
    for i, item in enumerate(view.items):
        label = status[item.status]
        if i == view.position.exercise and not view.finished:
            label = "Now"
        weight = (
            "Bodyweight"
            if item.bodyweight
            else "Your choice"
            if item.target_weight_kg is None
            else format_weight(item.target_weight_kg, view.unit, spoken=False)
        )
        rows.append(
            {
                "exercise": item.exercise.name,
                "target": f"{item.sets} × {item.reps}",
                "weight": weight,
                "status": label,
            }
        )
    return {
        "type": "table",
        "columns": [
            {"key": "exercise", "label": "Exercise"},
            {"key": "target", "label": "Sets × reps", "align": "center"},
            {"key": "weight", "label": "Weight", "align": "right"},
            {"key": "status", "label": "", "align": "right"},
        ],
        "rows": rows,
    }


def _next_step_text(view: SessionView) -> str:
    """What to do next, from the view after a skip."""
    item = view.current
    if item is None:
        return f"That's the whole workout. {_WRAP_UP}"
    if view.position.sets_done == 0:
        return f"Next up: {_intro_exercise(item, view.unit)}."
    return f"Next, set {view.position.sets_done + 1}: {_target(item, view.unit)}."


def _next_step_components(view: SessionView) -> list[dict[str, Any]]:
    if view.current is None:
        return [{"type": "alert", "variant": "success", "title": "All done", "message": _WRAP_UP}]
    return [_session_card(view), _controls()]


# --- start_session ------------------------------------------------------------------------


def present_start(r: StartResult) -> Presentation:
    view = r.view
    parts = []
    if r.closed_stale_on is not None:
        parts.append(f"I closed your unfinished workout from {r.closed_stale_on.strftime('%A')}.")
    item = view.current
    if r.resumed:
        if item is None:
            parts.append(f"You've finished every exercise in {view.day_name}. {_WRAP_UP}")
        else:
            parts.append(
                f"Welcome back to {view.day_name}. You're on "
                f"{spoken_exercise(item.exercise.name)}, set {view.position.sets_done + 1} "
                f"of {item.sets}: {_target(item, view.unit)}."
            )
    else:
        lead = f"Starting {view.day_name}"
        if r.rest_day:
            lead = f"Today's a rest day, so let's do {view.day_name}"
        parts.append(
            f"{lead}, {plural(len(view.items), 'exercise')}. "
            f"First up: {_intro_exercise(item, view.unit)}. "
            "Say done after each set."
        )
    components: list[dict[str, Any]] = [
        {"type": "text", "content": view.day_name, "variant": "heading"},
        *_next_step_components(view),
        _plan_table(view),
    ]
    return Presentation(" ".join(parts), components, "full")


# --- complete_set -------------------------------------------------------------------------


def _resume_text(view: SessionView) -> str:
    item = view.current
    if item is None:
        return f"That's the whole workout. {_WRAP_UP}"
    return (
        f"You're on {spoken_exercise(item.exercise.name)}, "
        f"set {view.position.sets_done + 1} of {item.sets}."
    )


def present_complete(r: CompleteResult) -> Presentation:
    """Heard after every set, so it stays short: details only when they differ from target."""
    if r.duplicate:
        text = f"I already logged that set. {_resume_text(r.view)}"
        return Presentation(text, _next_step_components(r.view))

    name = spoken_exercise(r.exercise.name)
    unit = r.view.unit
    reps_differ = r.reps != r.target_reps
    weight_differs = r.weight_kg != (r.target_weight_kg or 0)
    text = f"Set {r.set_number} of {r.total_sets} done"
    if reps_differ:
        text += f": {plural(r.reps, 'rep')}"
    if weight_differs:
        text += f" at {format_weight(r.weight_kg, unit)}"
    text += "."
    if r.pr == "weight":
        text += f" New personal record on {name}!"
    elif r.pr == "reps":
        text += f" That's a rep record on {name}!"
    if r.view.current is None:
        text += f" That's the whole workout. {_WRAP_UP}"
    elif r.exercise_finished:
        text += f" That's {name} done. Next up: {_intro_exercise(r.view.current, unit)}."

    components = _next_step_components(r.view)
    if r.view.current is not None:
        seconds = REST_SECONDS_BARBELL if r.exercise.equipment == "barbell" else REST_SECONDS_OTHER
        components.insert(1, {"type": "timer", "label": "Rest", "seconds": seconds})
    return Presentation(text, components)


# --- skip_exercise ------------------------------------------------------------------------


def present_skip(r: SkipResult) -> Presentation:
    name = spoken_exercise(r.skipped.name)
    text = f"Moving on from {name}." if r.partial else f"Skipped {name}."
    if r.view.current is None:
        text += f" That was the last exercise. {_WRAP_UP}"
    else:
        text += " " + _next_step_text(r.view)
    return Presentation(text, _next_step_components(r.view))


# --- end_session --------------------------------------------------------------------------


def _say_duration(d: timedelta) -> str:
    minutes = round(d.total_seconds() / 60)
    if minutes < 1:
        return "under a minute"
    hours, mins = divmod(minutes, 60)
    if hours == 0:
        return plural(mins, "minute")
    if mins == 0:
        return plural(hours, "hour")
    return f"{plural(hours, 'hour')} {plural(mins, 'minute')}"


def present_end(r: EndResult) -> Presentation:
    if r.cancelled:
        text = "You hadn't logged any sets, so I cancelled the workout."
        return Presentation(text, [{"type": "alert", "variant": "info", "message": text}], "full")

    text = (
        f"Nice work. You finished {r.day_name} in {_say_duration(r.duration)}: "
        f"{plural(r.sets, 'set')}, {say_volume(r.volume_kg, r.unit)} lifted."
    )
    if r.prs:
        text += f" New records on {join_limited([spoken_exercise(n) for n, _ in r.prs])}!"
    if r.skipped:
        text += f" You skipped {join_limited([spoken_exercise(n) for n in r.skipped])}."

    minutes = max(1, round(r.duration.total_seconds() / 60))
    components: list[dict[str, Any]] = [
        {"type": "text", "content": f"{r.day_name} complete", "variant": "heading"},
        {
            "type": "layout",
            "direction": "grid",
            "columns": 3,
            "children": [
                {
                    "type": "metric",
                    "label": "Duration",
                    "value": minutes,
                    "unit": "min",
                    "icon": "timer",
                },
                {"type": "metric", "label": "Sets", "value": r.sets, "icon": "dumbbell"},
                {
                    "type": "metric",
                    "label": "Volume",
                    "value": short_volume(r.volume_kg, r.unit),
                    "icon": "activity",
                },
            ],
        },
    ]
    if r.prs:
        components.append(
            {
                "type": "list",
                "title": "New records",
                "items": [
                    {"title": n, "badge": format_weight(w, r.unit, spoken=False)} for n, w in r.prs
                ],
            }
        )
    if r.skipped:
        components.append(
            {"type": "list", "title": "Skipped", "items": [{"title": n} for n in r.skipped]}
        )
    return Presentation(text, components, "full")
