"""Voice text + UI components for the utility tools."""

from collections import Counter
from decimal import Decimal
from typing import Any

from server.presenters.speech import join_words, plural, spoken_exercise
from server.presenters.workouts import Presentation
from server.services.exercise_resolver import ExerciseEntry
from server.services.preferences import PreferencesResult, spoken_timezone
from server.services.readiness import Assessment
from server.services.units import display_weight, format_weight
from server.services.utilities import MacroResult, PlateResult

_NUMBER_WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}
GOAL_SPOKEN = {
    "strength": "strength",
    "muscle": "building muscle",
    "fat_loss": "fat loss",
    "general": "general fitness",
}
PAIN_ADVICE = (
    "If something hurts, stop that exercise and see a doctor or physical therapist "
    "before doing it again."
)
_ORDINALS = ("First", "Second", "Third", "Fourth", "Fifth")
# After the pain advice: what changes for the rest of today.
_PAIN_CHANGE = {
    "full": "Train as planned on anything that doesn't hurt.",
    "reduce": "For everything else today, I've taken 10 percent off your weights.",
    "light": "For everything else today, I've taken 20 percent off your weights and dropped a set.",
    "rest": "Today is a good day to rest. If you train anyway, I've taken 20 percent off.",
}
# After the readiness lead-in, so the rest level doesn't repeat "rest day".
_READINESS_CHANGE = {
    "full": "Train as planned on anything that doesn't hurt.",
    "reduce": "I've taken 10 percent off today's weights.",
    "light": "I've taken 20 percent off today's weights and dropped a set.",
    "rest": "If you train anyway, I've taken 20 percent off and dropped a set.",
}


def _num(value: Decimal) -> str:
    text = f"{value:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _weight_words(value: Decimal, unit: str) -> str:
    word = "pound" if unit == "lb" else "kilogram"
    return f"{_num(value)} {word}{'' if value == 1 else 's'}"


def _bar_words(value: Decimal, unit: str) -> str:
    """Adjective form: "45-pound", "20-kilogram"."""
    return f"{_num(value)}-{'pound' if unit == 'lb' else 'kilogram'}"


# --- plate_calculator --------------------------------------------------------------------


def _plates_spoken(per_side: tuple[Decimal, ...]) -> str:
    """(45, 45, 10) → "two 45s and a 10"."""
    parts = []
    for plate, count in Counter(per_side).items():
        if count == 1:
            parts.append(f"a {_num(plate)}")
        else:
            parts.append(f"{_NUMBER_WORDS.get(count, str(count))} {_num(plate)}s")
    return join_words(parts)


def present_plates(r: PlateResult) -> Presentation:
    bar = _bar_words(r.bar, r.unit)
    if r.below_bar:
        text = f"{_weight_words(r.requested, r.unit)} is lighter than the {bar} bar."
        return Presentation(text, [{"type": "alert", "variant": "info", "message": text}])
    if not r.per_side:
        text = f"That's just the empty {bar} bar."
        if not r.exact:
            text = (
                f"I can't make {_weight_words(r.requested, r.unit)} with standard plates. "
                f"The closest is the empty {bar} bar."
            )
        return Presentation(text, [{"type": "alert", "variant": "info", "message": text}])

    lead = f"For {_weight_words(r.loadable, r.unit)}"
    if not r.exact:
        lead = (
            f"I can't make exactly {_weight_words(r.requested, r.unit)} with standard plates. "
            f"For {_weight_words(r.loadable, r.unit)}"
        )
    text = f"{lead}, put {_plates_spoken(r.per_side)} on each side of the {bar} bar."
    diagram = {
        "type": "plate_diagram",
        "total_weight": float(r.loadable),
        "bar_weight": float(r.bar),
        "unit": r.unit,
        "plates_per_side": [float(p) for p in r.per_side],
    }
    if not r.exact:
        diagram["remainder"] = float(r.requested - r.loadable)
    return Presentation(text, [diagram])


# --- get_form_cues ------------------------------------------------------------------------


def present_form_cues(entry: ExerciseEntry) -> Presentation:
    cues = [c.rstrip(".") for c in entry.form_cues]
    name = spoken_exercise(entry.name)
    if len(cues) == 1:
        text = f"One cue for {name}: {cues[0][0].lower()}{cues[0][1:]}."
    else:
        # One sentence per cue: cues often contain "and", which blurs a joined list.
        count = _NUMBER_WORDS.get(len(cues), str(len(cues))).capitalize()
        steps = " ".join(
            f"{_ORDINALS[i] if i < len(_ORDINALS) else 'Next'}, {c[0].lower()}{c[1:]}."
            for i, c in enumerate(cues)
        )
        text = f"{count} cues for {name}. {steps}"
    card = {
        "type": "card",
        "title": entry.name,
        "children": [
            {
                "type": "list",
                "title": "Form cues",
                "ordered": True,
                "items": [{"title": c} for c in cues],
            }
        ],
    }
    return Presentation(text, [card])


# --- readiness_check ----------------------------------------------------------------------


def present_readiness(a: Assessment) -> Presentation:
    if a.pain_reported:
        # Safety first; the lighter day follows.
        text = f"Thanks for telling me. {PAIN_ADVICE} {_PAIN_CHANGE[a.level]}"
    elif a.level == "full":
        text = "You sound ready. Train as planned today."
        if a.reasons and a.energy_high:
            text = (
                f"Even with {join_words(list(a.reasons))}, your energy is good, "
                "so train as planned."
            )
    else:
        because = f"With {join_words(list(a.reasons))}, " if a.reasons else ""
        lead = {
            "reduce": f"{because}let's ease off a little today.",
            "light": f"{because}let's keep today light.",
            "rest": f"{because}today is a good day to rest.",
        }[a.level]
        text = f"{lead[0].upper()}{lead[1:]} {_READINESS_CHANGE[a.level]}"
    if a.session_adjusted:
        text += " That applies to the rest of your workout, starting with the next exercise."

    variant = "warning" if a.pain_reported or a.level in ("light", "rest") else "info"
    components: list[dict[str, Any]] = [
        {"type": "alert", "variant": variant, "title": "Readiness", "message": text}
    ]
    return Presentation(text, components)


# --- set_preferences ----------------------------------------------------------------------


def present_preferences(r: PreferencesResult) -> Presentation:
    if r.needs_setup:
        text = (
            "Let's set you up. Tell me your units, your goal and how many days a week you can "
            "train. For example, say pounds, building muscle, four days a week. Goals can be "
            "strength, building muscle, fat loss or general fitness."
        )
        return Presentation(text, [{"type": "alert", "variant": "info", "message": text}])

    unit_word = "pounds" if r.unit == "lb" else "kilograms"
    said = {
        "unit": f"use {unit_word}",
        "bar_weight": f"use a {_bar_words(display_weight(r.bar_weight_kg, r.unit), r.unit)} bar",
        "goal": f"focus on {GOAL_SPOKEN.get(r.goal or '', 'your goal')}",
        "days_per_week": f"plan for {plural(r.days_per_week or 0, 'day')} a week",
        "timezone": f"use the {spoken_timezone(r.timezone)} time zone",
    }
    if not r.changes:
        text = "Those settings were already in place, so nothing changed."
    else:
        text = f"Done. I'll {join_words([said[c] for c in r.changes])}."
        if "days_per_week" in r.changes:
            text += " Your current plan stays the same for now."

    rows = [
        {"setting": "Units", "value": unit_word.capitalize()},
        {"setting": "Bar", "value": format_weight(r.bar_weight_kg, r.unit, spoken=False)},
        {"setting": "Goal", "value": GOAL_SPOKEN.get(r.goal or "", "Not set").capitalize()},
        {"setting": "Days per week", "value": r.days_per_week or "Not set"},
        {"setting": "Time zone", "value": r.timezone},
    ]
    table = {
        "type": "table",
        "title": "Your settings",
        "columns": [{"key": "setting", "label": "Setting"}, {"key": "value", "label": "Value"}],
        "rows": rows,
    }
    return Presentation(text, [table])


# --- calculate_macros ---------------------------------------------------------------------


def present_macros(r: MacroResult) -> Presentation:
    weight = format_weight(r.bodyweight_kg, r.unit, precise=True)
    at = f"your latest weigh-in of {weight}" if r.from_latest_weigh_in else weight
    text = (
        f"For {GOAL_SPOKEN[r.goal]} at {at}, aim for about {r.calories:,} calories a day. "
        f"That's roughly {r.protein_g} grams of protein, {r.fat_g} grams of fat and "
        f"{r.carbs_g} grams of carbs. Treat it as a starting point."
    )
    metrics = {
        "type": "layout",
        "direction": "grid",
        "columns": 4,
        "children": [
            {
                "type": "metric",
                "label": "Calories",
                "value": r.calories,
                "unit": "kcal",
                "icon": "flame",
            },
            {"type": "metric", "label": "Protein", "value": r.protein_g, "unit": "g"},
            {"type": "metric", "label": "Fat", "value": r.fat_g, "unit": "g"},
            {"type": "metric", "label": "Carbs", "value": r.carbs_g, "unit": "g"},
        ],
    }
    note = {
        "type": "text",
        "variant": "muted",
        "content": "An estimate from bodyweight and goal, not medical or dietary advice.",
    }
    return Presentation(text, [metrics, note])
