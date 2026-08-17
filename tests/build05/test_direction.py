import pytest

from reference_direction import direction_enum, DIRECTION


def _score_sequence(scores):
    out = []
    for s in scores:
        prev_state = out[-1][0] if out else DIRECTION.NEUTRAL
        prev_dwell = out[-1][1] if out else 0
        out.append(direction_enum(s, prev=prev_state, dwell=prev_dwell))
    return out


def test_bull_then_strong_bull_requires_commit_and_dwell():
    seq = _score_sequence([0.0, 0.0, 0.6, 0.6, 0.85, 0.85])
    states = [s for s, _ in seq]
    assert states == [DIRECTION.NEUTRAL, DIRECTION.NEUTRAL, DIRECTION.BULL,
                      DIRECTION.BULL, DIRECTION.STRONG_BULL, DIRECTION.STRONG_BULL]


def test_neutral_reentry_requires_drop_below_commit():
    seq = _score_sequence([0.85, 0.85, 0.3, 0.3, 0.3, 0.3])
    states = [s for s, _ in seq]
    assert states[:2] == [DIRECTION.STRONG_BULL, DIRECTION.STRONG_BULL]
    assert states[-1] == DIRECTION.NEUTRAL


def test_dwell_prevents_flip_flop():
    seq = _score_sequence([0.85, 0.1, 0.85, 0.1, 0.85, 0.1, 0.85])
    states = [s for s, _ in seq]
    assert DIRECTION.BEAR not in states and DIRECTION.STRONG_BEAR not in states


def test_bear_and_strong_bear_transitions():
    seq = _score_sequence([-0.6, -0.6, -0.85, -0.85])
    states = [s for s, _ in seq]
    assert states == [DIRECTION.BEAR, DIRECTION.BEAR,
                      DIRECTION.STRONG_BEAR, DIRECTION.STRONG_BEAR]


def test_score_clamped():
    state, _ = direction_enum(3.0)
    assert state == DIRECTION.STRONG_BULL
    state, _ = direction_enum(-3.0)
    assert state == DIRECTION.STRONG_BEAR
