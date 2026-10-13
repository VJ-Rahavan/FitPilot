"""Plate math and macro estimates. Pure, deterministic functions plus thin DB wrappers."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from server.db import repository as repo
from server.services.context import UserContext, UserFacingError
from server.services.exercise_resolver import ExerciseEntry, ExerciseResolver
from server.services.units import Unit, display_weight, to_kg
from server.services.workouts import resolve_exercise

PLATES: dict[Unit, tuple[Decimal, ...]] = {
    "lb": tuple(Decimal(p) for p in ("45", "35", "25", "10", "5", "2.5")),
    "kg": tuple(Decimal(p) for p in ("25", "20", "15", "10", "5", "2.5", "1.25")),
}
STANDARD_BAR: dict[Unit, Decimal] = {"lb": Decimal("45"), "kg": Decimal("20")}
# Common bars and their counterpart in the other unit (45 lb ↔ 20 kg, 35 lb ↔ 15 kg).
BAR_COUNTERPARTS: dict[tuple[str, Decimal], Decimal] = {
    ("lb", Decimal("45")): Decimal("20"),
    ("lb", Decimal("35")): Decimal("15"),
    ("lb", Decimal("15")): Decimal("7"),  # technique bars
    ("kg", Decimal("20")): Decimal("45"),
    ("kg", Decimal("15")): Decimal("35"),
    ("kg", Decimal("7")): Decimal("15"),
}


# --- plate_calculator --------------------------------------------------------------------


@dataclass(frozen=True)
class PlateResult:
    requested: Decimal
    unit: Unit
    bar: Decimal
    per_side: tuple[Decimal, ...]  # heaviest first
    loadable: Decimal  # closest total at or below the request that plates can make

    @property
    def exact(self) -> bool:
        return self.loadable == self.requested

    @property
    def below_bar(self) -> bool:
        return self.requested < self.bar


def plates_for(weight: Decimal, unit: Unit, bar: Decimal) -> PlateResult:
    """Greedy plate loading per side, heaviest first, the way lifters load a bar.

    Always reaches the closest loadable total at or below the request (every plate is a
    multiple of the smallest one), though in pounds not always with the fewest plates.
    """
    if weight < bar:
        return PlateResult(weight, unit, bar, (), bar)
    remaining = (weight - bar) / 2
    per_side = []
    for plate in PLATES[unit]:
        while remaining >= plate:
            per_side.append(plate)
            remaining -= plate
    loadable = bar + 2 * sum(per_side, Decimal("0"))
    return PlateResult(weight, unit, bar, tuple(per_side), loadable)


def bar_for(ctx: UserContext, unit: Unit) -> Decimal:
    """The user's bar in `unit`. Asking in the other unit uses the bar's counterpart there
    (a 15 kg bar is a 35 lb bar), or the standard bar for that unit."""
    if unit == ctx.unit:
        return display_weight(ctx.bar_weight_kg, unit)
    own = display_weight(ctx.bar_weight_kg, ctx.unit)
    return BAR_COUNTERPARTS.get((ctx.unit, own), STANDARD_BAR[unit])


def plate_calculator(ctx: UserContext, *, weight: float, unit: Unit) -> PlateResult:
    return plates_for(Decimal(str(weight)), unit, bar_for(ctx, unit))


# --- get_form_cues -----------------------------------------------------------------------


def form_cues(resolver: ExerciseResolver, exercise: str) -> ExerciseEntry:
    entry = resolve_exercise(resolver, exercise)
    if not entry.form_cues:
        raise UserFacingError(
            f"I don't have form cues for {entry.name.lower()} yet. "
            "Want cues for a different exercise?"
        )
    return entry


# --- calculate_macros --------------------------------------------------------------------

PROTEIN_G_PER_KG = {
    "strength": Decimal("1.8"),
    "muscle": Decimal("2.0"),
    "fat_loss": Decimal("2.2"),
    "general": Decimal("1.6"),
}
CALORIE_FACTOR = {
    "strength": Decimal("1.05"),
    "muscle": Decimal("1.10"),
    "fat_loss": Decimal("0.80"),
    "general": Decimal("1.00"),
}
MAINTENANCE_KCAL_PER_KG = Decimal("33")  # rough, for an active adult
FAT_G_PER_KG = Decimal("0.9")


@dataclass(frozen=True)
class MacroResult:
    bodyweight_kg: Decimal
    unit: Unit
    goal: str
    calories: int
    protein_g: int
    fat_g: int
    carbs_g: int
    from_latest_weigh_in: bool


def _round_to(value: Decimal, step: int) -> int:
    return int((value / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step)


def macros_for(bodyweight_kg: Decimal, goal: str | None) -> tuple[int, int, int, int]:
    """(calories, protein g, fat g, carbs g), rounded for speech."""
    goal = goal if goal in PROTEIN_G_PER_KG else "general"
    calories = _round_to(bodyweight_kg * MAINTENANCE_KCAL_PER_KG * CALORIE_FACTOR[goal], 50)
    protein = _round_to(bodyweight_kg * PROTEIN_G_PER_KG[goal], 5)
    fat = _round_to(bodyweight_kg * FAT_G_PER_KG, 5)
    carbs = max(0, (calories - 4 * protein - 9 * fat) // 20 * 5)  # 4 kcal/g, in 5 g steps
    return calories, protein, fat, carbs


async def calculate_macros(
    db: AsyncSession, ctx: UserContext, *, bodyweight: float | None, unit: Unit
) -> MacroResult:
    from_weigh_in = bodyweight is None
    if bodyweight is None:
        recent = await repo.get_recent_body_metrics(db, ctx.user_id, limit=1)
        if not recent:
            raise UserFacingError(
                "What's your bodyweight? For example, say calculate my macros at 180 pounds."
            )
        weight_kg = recent[0].bodyweight_kg
    else:
        weight_kg = to_kg(bodyweight, unit)
    goal = ctx.goal if ctx.goal in PROTEIN_G_PER_KG else "general"
    calories, protein, fat, carbs = macros_for(weight_kg, goal)
    return MacroResult(weight_kg, unit, goal, calories, protein, fat, carbs, from_weigh_in)
