from server.services.session_state import Position, after_set, after_skip

SETS = [3, 2]  # two exercises: 3 sets, then 2 sets


def test_walk_through_all_sets():
    pos = Position(0, 0)
    seen = []
    while not pos.finished(SETS):
        seen.append((pos.exercise, pos.sets_done))
        pos = after_set(pos, SETS)
    assert seen == [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1)]
    assert pos == Position(2, 0)


def test_skip_moves_to_next_exercise_from_any_set():
    assert after_skip(Position(0, 0)) == Position(1, 0)
    assert after_skip(Position(0, 2)) == Position(1, 0)
    assert after_skip(Position(1, 1)).finished(SETS)
