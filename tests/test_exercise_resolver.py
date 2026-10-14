import pytest

from server.db.seed_data import EXERCISES
from server.services.context import UserFacingError
from server.services.exercise_resolver import ExerciseEntry, ExerciseResolver, normalize
from server.services.workouts import resolve_exercise


@pytest.fixture(scope="module")
def resolver() -> ExerciseResolver:
    entries = [ExerciseEntry(i, e.name, e.aliases) for i, e in enumerate(EXERCISES, start=1)]
    return ExerciseResolver(entries)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Squats", "squat"),
        ("bench presses", "bench press"),
        ("Pull-Ups", "pull up"),
        ("  Romanian   deadlift! ", "romanian deadlift"),
        ("press", "press"),
        ("calves", "calve"),  # crude but consistent: applied to aliases and queries alike
    ],
)
def test_normalize(name, expected):
    assert normalize(name) == expected


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Bench Press", "Bench Press"),
        ("bench", "Bench Press"),
        ("squat", "Back Squat"),
        ("squats", "Back Squat"),
        ("RDL", "Romanian Deadlift"),
        ("ohp", "Overhead Press"),
        ("pullups", "Pull-Up"),
        ("pull-up", "Pull-Up"),
        ("deadlifts", "Deadlift"),
        ("calf raises", "Standing Calf Raise"),
        ("benchpress", "Bench Press"),
    ],
)
def test_exact_and_alias_matches(resolver, query, expected):
    r = resolver.resolve(query)
    assert r.found and r.name == expected and r.matched_by == "exact"


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("squatz", "Back Squat"),
        ("bnech press", "Bench Press"),
        ("overhed press", "Overhead Press"),
        ("romanain deadlift", "Romanian Deadlift"),
        ("lat pull-downs", "Lat Pulldown"),
    ],
)
def test_fuzzy_matches(resolver, query, expected):
    r = resolver.resolve(query)
    assert r.found, r
    assert r.name == expected
    assert r.matched_by in ("fuzzy", "exact")


def test_ambiguous_query_returns_suggestions(resolver):
    r = resolver.resolve("press")
    assert not r.found
    assert r.matched_by == "ambiguous"
    assert len(r.suggestions) >= 2
    assert all("Press" in s for s in r.suggestions)


def test_unknown_exercise(resolver):
    r = resolver.resolve("zumba")
    assert not r.found
    assert r.matched_by == "none"


def test_empty_query(resolver):
    assert resolver.resolve("  ").matched_by == "none"


def test_seed_aliases_are_unique_after_normalizing():
    seen: dict[str, str] = {}
    for e in EXERCISES:
        for key in {normalize(e.name), *(normalize(a) for a in e.aliases)}:
            assert key not in seen, f"{key!r} used by {seen[key]} and {e.name}"
            seen[key] = e.name


def test_voice_errors_for_unresolved_names(resolver):
    assert resolve_exercise(resolver, "squatz").name == "Back Squat"
    with pytest.raises(UserFacingError) as ambiguous:
        resolve_exercise(resolver, "press")
    assert ambiguous.value.message.startswith("Did you mean ")
    assert " or " in ambiguous.value.message
    with pytest.raises(UserFacingError) as unknown:
        resolve_exercise(resolver, "zumba")
    assert unknown.value.message == (
        "I couldn't find an exercise called zumba. Try a name like squat, bench press or deadlift."
    )
    assert ", " in ambiguous.value.message or ambiguous.value.message.count(" or ") == 1
