"""Resolve spoken exercise names ("bench", "squats", "squatz") to exercises.

Works on an in-memory index (exercises are small shared reference data), so a lookup
costs no database round trip. Order: exact name/alias → fuzzy match → suggestions.
"""

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

# A fuzzy match is accepted only above this score and clearly ahead of the runner-up.
MATCH_THRESHOLD = 88.0
MATCH_MARGIN = 5.0
# Below this, a "did you mean" would be noise (e.g. "zumba" vs "dumbbell bench press" = 60).
SUGGESTION_THRESHOLD = 70.0
MAX_SUGGESTIONS = 3


def _singular(word: str) -> str:
    if len(word) <= 2:
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith(("sses", "shes", "ches", "xes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def normalize(name: str) -> str:
    """Lowercase, drop punctuation, collapse spaces, singularize each word.

    Applied to both stored names/aliases and queries, so rules only need to be consistent.
    """
    words = re.sub(r"[^a-z0-9 ]+", " ", name.lower().replace("-", " ")).split()
    return " ".join(_singular(w) for w in words)


@dataclass(frozen=True)
class ExerciseEntry:
    id: int
    name: str
    aliases: tuple[str, ...] = ()
    equipment: str = "barbell"
    form_cues: tuple[str, ...] = ()


@dataclass(frozen=True)
class Resolution:
    exercise_id: int | None
    name: str | None
    matched_by: str  # "exact" | "fuzzy" | "none" | "ambiguous"
    suggestions: tuple[str, ...] = field(default=())

    @property
    def found(self) -> bool:
        return self.exercise_id is not None


class ExerciseResolver:
    def __init__(self, entries: list[ExerciseEntry]):
        self._by_id = {e.id: e for e in entries}
        # normalized key → exercise id; names and aliases share one namespace.
        self._keys: dict[str, int] = {}
        for e in entries:
            for key in (e.name, *e.aliases):
                self._keys.setdefault(normalize(key), e.id)
        self._key_list = list(self._keys)
        # Same keys without spaces, so "benchpress" finds "bench press".
        self._compact = {k.replace(" ", ""): i for k, i in self._keys.items()}

    def get(self, exercise_id: int) -> ExerciseEntry:
        return self._by_id[exercise_id]

    def resolve(self, query: str) -> Resolution:
        q = normalize(query)
        if not q:
            return Resolution(None, None, "none")

        exact = self._keys.get(q) or self._compact.get(q.replace(" ", ""))
        if exact is not None:
            return Resolution(exact, self._by_id[exact].name, "exact")

        # Candidates by WRatio (good at partial overlap, for suggestions); the match
        # itself is decided by plain ratio (good at typos, not fooled by substrings).
        typo: dict[int, float] = {}
        overlap: dict[int, float] = {}
        for key, w_score, _ in process.extract(
            q, self._key_list, scorer=fuzz.WRatio, limit=20, score_cutoff=SUGGESTION_THRESHOLD
        ):
            ex_id = self._keys[key]
            overlap[ex_id] = max(overlap.get(ex_id, 0.0), w_score)
            typo[ex_id] = max(typo.get(ex_id, 0.0), fuzz.ratio(q, key))

        by_typo = sorted(typo.items(), key=lambda kv: kv[1], reverse=True)
        if by_typo and by_typo[0][1] >= MATCH_THRESHOLD:
            runner_up = by_typo[1][1] if len(by_typo) > 1 else 0.0
            if by_typo[0][1] - runner_up >= MATCH_MARGIN:
                ex_id = by_typo[0][0]
                return Resolution(ex_id, self._by_id[ex_id].name, "fuzzy")

        by_overlap = sorted(overlap.items(), key=lambda kv: kv[1], reverse=True)
        suggestions = tuple(self._by_id[i].name for i, _ in by_overlap[:MAX_SUGGESTIONS])
        strong = sum(1 for _, score in by_overlap if score >= MATCH_THRESHOLD)
        return Resolution(None, None, "ambiguous" if strong >= 2 else "none", suggestions)
