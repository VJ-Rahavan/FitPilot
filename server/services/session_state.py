"""Position within a guided session, as pure functions (no DB).

A position is (exercise index, sets done of that exercise). The session is finished when
the index runs past the last exercise.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Position:
    exercise: int
    sets_done: int

    def finished(self, set_counts: list[int]) -> bool:
        return self.exercise >= len(set_counts)


def after_set(pos: Position, set_counts: list[int]) -> Position:
    """One more set done; move to the next exercise when this one is complete."""
    done = pos.sets_done + 1
    if done >= set_counts[pos.exercise]:
        return Position(pos.exercise + 1, 0)
    return Position(pos.exercise, done)


def after_skip(pos: Position) -> Position:
    return Position(pos.exercise + 1, 0)
