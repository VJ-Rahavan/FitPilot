"""Helpers for short, natural spoken text."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from server.services.units import Unit, from_kg


def plural(n: int, word: str, plural_word: str | None = None) -> str:
    return f"{n} {word if n == 1 else (plural_word or word + 's')}"


def join_words(items: list[str]) -> str:
    """["a"] → "a"; ["a", "b"] → "a and b"; ["a", "b", "c"] → "a, b and c"."""
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"


def sets_of_reps(reps: tuple[int, ...] | list[int]) -> str:
    """(5, 5, 5) → "3 sets of 5"; (8, 8, 6) → "3 sets of 8, 8 and 6"."""
    reps = list(reps)
    if len(set(reps)) == 1:
        return f"{plural(len(reps), 'set')} of {reps[0]}"
    return f"{plural(len(reps), 'set')} of {join_words([str(r) for r in reps])}"


def spoken_exercise(name: str) -> str:
    return name.lower()


def say_volume(volume_kg: Decimal, unit: Unit) -> str:
    """Total lifted, rounded for speech: "about 24,500 pounds"."""
    value = from_kg(volume_kg, unit)
    step = Decimal("100") if value >= 1000 else Decimal("10")
    rounded = int((value / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step)
    word = "pounds" if unit == "lb" else "kilograms"
    return f"about {rounded:,} {word}"


def short_volume(volume_kg: Decimal, unit: Unit) -> str:
    """Compact display: "24.5k lb"."""
    value = from_kg(volume_kg, unit)
    if value >= 1000:
        return f"{value / 1000:.1f}k {unit}"
    return f"{value:.0f} {unit}"


def percent_change(new: Decimal, old: Decimal) -> int | None:
    if not old:
        return None
    return int(((new - old) / old * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def say_date(d: date) -> str:
    return f"{d.strftime('%B')} {d.day}"


def short_date(d: date) -> str:
    return f"{d.strftime('%b')} {d.day}"
