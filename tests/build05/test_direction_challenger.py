import pytest
from reference_direction import direction_enum, DIRECTION, DWELL


def test_DIRECTION_long_incumbent_no_credit():
    """BULL for 10 bars then first STRONG_BULL: must NOT instantly commit."""
    scores = [0.6] * 10 + [0.85]
    out = []
    ch = DIRECTION.NEUTRAL
    ch_dwell = 0
    for s in scores:
        prev = out[-1][0] if out else DIRECTION.NEUTRAL
        d = out[-1][1] if out else 0
        state, dwell, ch, ch_dwell = direction_enum(s, prev=prev, dwell=d,
                                                     challenger=ch, challenger_dwell=ch_dwell)
        out.append((state, dwell))

    assert out[9] == (DIRECTION.BULL, 2), "After 10 BULL bars, still BULL"
    assert out[10][0] == DIRECTION.BULL, "First STRONG_BULL: must NOT commit yet"

    out.append(direction_enum(0.85, prev=out[-1][0], dwell=out[-1][1],
               challenger=DIRECTION.STRONG_BULL, challenger_dwell=1)[:2])
    assert out[11][0] == DIRECTION.STRONG_BULL, "Second STRONG_BULL: must commit"


def test_DIRECTION_challenger_interruption():
    """BULL → STRONG_BULL → BULL → STRONG_BULL: dwell resets on interruption."""
    out = []
    ch = DIRECTION.NEUTRAL
    ch_dwell = 0

    state, dwell, ch, ch_dwell = direction_enum(0.6, prev=DIRECTION.NEUTRAL, dwell=0,
                                                 challenger=ch, challenger_dwell=ch_dwell)
    out.append((state, dwell))
    assert state == DIRECTION.BULL

    state, dwell, ch, ch_dwell = direction_enum(0.85, prev=DIRECTION.BULL, dwell=0,
                                                 challenger=ch, challenger_dwell=ch_dwell)
    out.append((state, dwell))
    assert state == DIRECTION.BULL, "First STRONG_BULL: dwell=1, not committed"
    assert ch_dwell == 1

    state, dwell, ch, ch_dwell = direction_enum(0.6, prev=DIRECTION.BULL, dwell=0,
                                                 challenger=ch, challenger_dwell=ch_dwell)
    out.append((state, dwell))
    assert state == DIRECTION.BULL
    assert ch == DIRECTION.NEUTRAL, "Challenger resets on reversion"
    assert ch_dwell == 0

    state, dwell, ch, ch_dwell = direction_enum(0.85, prev=DIRECTION.BULL, dwell=0,
                                                 challenger=ch, challenger_dwell=ch_dwell)
    out.append((state, dwell))
    assert state == DIRECTION.BULL, "Second STRONG_BULL after interruption: dwell=1 again"
    assert ch_dwell == 1


def test_DIRECTION_neutral_resets_challenger():
    """STRONG_BULL → NEUTRAL → STRONG_BULL: challenger resets."""
    state, dwell, ch, ch_dwell = direction_enum(0.85, prev=DIRECTION.NEUTRAL, dwell=0)
    assert state == DIRECTION.STRONG_BULL

    state, dwell, ch, ch_dwell = direction_enum(0.1, prev=DIRECTION.STRONG_BULL, dwell=0)
    assert state == DIRECTION.NEUTRAL
    assert ch == DIRECTION.NEUTRAL
    assert ch_dwell == 0
