import pytest
from reference_momentum import momentum_enum, MOMENTUM
from reference_direction import direction_enum, DIRECTION
from reference_volatility import volatility_level_enum, VOL_LEVEL


def test_INVALID_momentum_caller_skip_freezes():
    """STRONG → low [caller skips] → low: persist frozen at 1, then resume exits."""
    state = MOMENTUM.STRONG
    persist = [0]

    state = momentum_enum(0.65, 0.0, prev=state, persist=persist)
    assert state == MOMENTUM.STRONG and persist[0] == 0

    state = momentum_enum(0.50, 0.0, prev=state, persist=persist)
    assert state == MOMENTUM.STRONG and persist[0] == 1

    # Caller skips: do NOT call MomentumClassify this bar
    # persist stays at 1, state stays STRONG (frozen)
    assert persist[0] == 1, "Persist frozen during skip"

    state = momentum_enum(0.50, 0.0, prev=state, persist=persist)
    assert state == MOMENTUM.NORMAL, "Resume: exits STRONG"
    assert persist[0] == 0


def test_INVALID_direction_caller_skip_freezes():
    """BULL challenger bar #1 [caller skips] → challenger bar #2: dwell frozen, then resume."""
    s, d, ch, cd = direction_enum(0.6, prev=DIRECTION.NEUTRAL, dwell=0)
    assert s == DIRECTION.BULL

    s, d, ch, cd = direction_enum(0.85, prev=s, dwell=d, challenger=ch, challenger_dwell=cd)
    assert s == DIRECTION.BULL and ch == DIRECTION.STRONG_BULL and cd == 1

    # Caller skips direction classify: dwell stays 1 (frozen)
    assert cd == 1, "Challenger dwell frozen during skip"

    s, d, ch, cd = direction_enum(0.85, prev=s, dwell=d, challenger=ch, challenger_dwell=cd)
    assert s == DIRECTION.STRONG_BULL, "Resume: commits STRONG_BULL"


def test_INVALID_vollevel_caller_skip_freezes():
    """HIGH challenger bar #1 [caller skips] → challenger bar #2: dwell frozen, then resume."""
    s, d, ch, cd = volatility_level_enum(1.6, prev=VOL_LEVEL.NORMAL, dwell=0)
    assert s == VOL_LEVEL.NORMAL and ch == VOL_LEVEL.HIGH and cd == 1

    # Caller skips: dwell frozen at 1
    assert cd == 1, "Challenger dwell frozen during skip"

    s, d, ch, cd = volatility_level_enum(1.6, prev=s, dwell=d, challenger=ch, challenger_dwell=cd)
    assert s == VOL_LEVEL.HIGH, "Resume: commits HIGH"
