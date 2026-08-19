import pytest

from reference_direction import direction_enum, DIRECTION


def _score_sequence(scores):
    out = []
    ch = DIRECTION.NEUTRAL
    ch_dwell = 0
    for s in scores:
        prev_state = out[-1][0] if out else DIRECTION.NEUTRAL
        prev_dwell = out[-1][1] if out else 0
        state, dwell, ch, ch_dwell = direction_enum(s, prev=prev_state, dwell=prev_dwell,
                                                     challenger=ch, challenger_dwell=ch_dwell)
        out.append((state, dwell))
    return out


def test_bull_then_strong_bull_requires_commit_and_dwell():
    seq = _score_sequence([0.0, 0.0, 0.6, 0.6, 0.85, 0.85])
    states = [s for s, _ in seq]
    assert states == [DIRECTION.NEUTRAL, DIRECTION.NEUTRAL, DIRECTION.BULL,
                      DIRECTION.BULL, DIRECTION.BULL, DIRECTION.STRONG_BULL]


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
                      DIRECTION.BEAR, DIRECTION.STRONG_BEAR]


def test_score_clamped():
    state, *_ = direction_enum(3.0)
    assert state == DIRECTION.STRONG_BULL
    state, *_ = direction_enum(-3.0)
    assert state == DIRECTION.STRONG_BEAR


def test_bull_to_strong_bear_reversal():
    """BULL → STRONG_BEAR #1 → remain BULL, #2 → STRONG_BEAR."""
    s1, d1, ch1, cd1 = direction_enum(0.6, prev=DIRECTION.NEUTRAL, dwell=0)
    assert s1 == DIRECTION.BULL
    s2, d2, ch2, cd2 = direction_enum(-0.85, prev=s1, dwell=d1, challenger=ch1, challenger_dwell=cd1)
    assert s2 == DIRECTION.BULL, "First STRONG_BEAR reversal: hold BULL"
    assert ch2 == DIRECTION.STRONG_BEAR
    assert cd2 == 1
    s3, d3, ch3, cd3 = direction_enum(-0.85, prev=s2, dwell=d2, challenger=ch2, challenger_dwell=cd2)
    assert s3 == DIRECTION.STRONG_BEAR, "Second STRONG_BEAR: commit"


def test_strong_bull_to_bear_reversal():
    """STRONG_BULL → BEAR #1 → remain STRONG_BULL, #2 → BEAR."""
    s1, d1, ch1, cd1 = direction_enum(0.85, prev=DIRECTION.NEUTRAL, dwell=0)
    assert s1 == DIRECTION.STRONG_BULL
    s2, d2, ch2, cd2 = direction_enum(-0.6, prev=s1, dwell=d1, challenger=ch1, challenger_dwell=cd1)
    assert s2 == DIRECTION.STRONG_BULL, "First BEAR reversal: hold STRONG_BULL"
    assert ch2 == DIRECTION.BEAR
    assert cd2 == 1
    s3, d3, ch3, cd3 = direction_enum(-0.6, prev=s2, dwell=d2, challenger=ch2, challenger_dwell=cd2)
    assert s3 == DIRECTION.BEAR, "Second BEAR: commit"


def test_same_sign_weaker_immediate():
    """STRONG_BULL → BULL = immediate (same-sign weaker)."""
    s1, d1, _, _ = direction_enum(0.85, prev=DIRECTION.NEUTRAL, dwell=0)
    assert s1 == DIRECTION.STRONG_BULL
    s2, d2, _, _ = direction_enum(0.6, prev=s1, dwell=d1)
    assert s2 == DIRECTION.BULL, "Same-sign weaker: immediate"
    assert d2 == 0


def test_neutral_entry_immediate():
    """NEUTRAL → BULL = immediate."""
    s, d, _, _ = direction_enum(0.6, prev=DIRECTION.NEUTRAL, dwell=0)
    assert s == DIRECTION.BULL
    assert d == 0


def test_bearish_mirrors():
    """Bearish mirrors: BEAR → STRONG_BULL = challenger, STRONG_BEAR → BULL = challenger."""
    s1, d1, ch1, cd1 = direction_enum(-0.6, prev=DIRECTION.NEUTRAL, dwell=0)
    assert s1 == DIRECTION.BEAR
    s2, d2, ch2, cd2 = direction_enum(0.85, prev=s1, dwell=d1, challenger=ch1, challenger_dwell=cd1)
    assert s2 == DIRECTION.BEAR, "First STRONG_BULL reversal: hold BEAR"
    assert ch2 == DIRECTION.STRONG_BULL
    s3, d3, ch3, cd3 = direction_enum(0.85, prev=s2, dwell=d2, challenger=ch2, challenger_dwell=cd2)
    assert s3 == DIRECTION.STRONG_BULL

    s4, d4, ch4, cd4 = direction_enum(-0.85, prev=DIRECTION.NEUTRAL, dwell=0)
    assert s4 == DIRECTION.STRONG_BEAR
    s5, d5, ch5, cd5 = direction_enum(0.6, prev=s4, dwell=d4, challenger=ch4, challenger_dwell=cd4)
    assert s5 == DIRECTION.STRONG_BEAR, "First BULL reversal: hold STRONG_BEAR"
    assert ch5 == DIRECTION.BULL
    s6, d6, ch6, cd6 = direction_enum(0.6, prev=s5, dwell=d5, challenger=ch5, challenger_dwell=cd5)
    assert s6 == DIRECTION.BULL


def test_challenger_interruption_resets():
    """Different challenger resets dwell."""
    s1, d1, ch1, cd1 = direction_enum(0.6, prev=DIRECTION.NEUTRAL, dwell=0)
    assert s1 == DIRECTION.BULL
    s2, d2, ch2, cd2 = direction_enum(0.85, prev=s1, dwell=d1, challenger=ch1, challenger_dwell=cd1)
    assert s2 == DIRECTION.BULL
    assert ch2 == DIRECTION.STRONG_BULL and cd2 == 1
    s3, d3, ch3, cd3 = direction_enum(-0.6, prev=s2, dwell=d2, challenger=ch2, challenger_dwell=cd2)
    assert s3 == DIRECTION.BULL, "Different challenger (BEAR): hold BULL"
    assert ch3 == DIRECTION.BEAR and cd3 == 1, "Challenger changed, dwell reset to 1"
