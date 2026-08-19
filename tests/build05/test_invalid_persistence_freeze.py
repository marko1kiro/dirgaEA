import pytest
from reference_momentum import momentum_enum, MOMENTUM, PERSISTENCE


def test_INVALID_persistence_freeze_momentum():
    """Invalid domain must not advance momentum persistent state."""
    state = MOMENTUM.STRONG
    persist = [0]

    state = momentum_enum(0.65, 0.0, prev=state, persist=persist)
    assert state == MOMENTUM.STRONG
    assert persist[0] == 0

    state = momentum_enum(0.50, 0.0, prev=state, persist=persist)
    assert state == MOMENTUM.STRONG
    assert persist[0] == 1

    state = momentum_enum(0.65, 0.0, prev=state, persist=persist)
    assert state == MOMENTUM.STRONG
    assert persist[0] == 0

    state = momentum_enum(0.50, 0.0, prev=state, persist=persist)
    assert state == MOMENTUM.STRONG, "After interruption, first low bar retains"
    assert persist[0] == 1


def test_INVALID_persistence_freeze_direction():
    """Invalid domain must not advance direction challenger dwell."""
    from reference_direction import direction_enum, DIRECTION

    state, dwell, ch, ch_dwell = direction_enum(
        0.6, prev=DIRECTION.NEUTRAL, dwell=0)
    assert state == DIRECTION.BULL
    assert ch == DIRECTION.NEUTRAL
    assert ch_dwell == 0

    state, dwell, ch, ch_dwell = direction_enum(
        0.85, prev=DIRECTION.BULL, dwell=0,
        challenger=DIRECTION.STRONG_BULL, challenger_dwell=0)
    assert state == DIRECTION.BULL
    assert ch_dwell == 1

    state, dwell, ch, ch_dwell = direction_enum(
        0.85, prev=DIRECTION.BULL, dwell=dwell,
        challenger=ch, challenger_dwell=ch_dwell)
    assert state == DIRECTION.STRONG_BULL, "Second challenger: commit"
    assert ch == DIRECTION.NEUTRAL
    assert ch_dwell == 0


def test_INVALID_persistence_freeze_vollevel():
    """Invalid domain must not advance vol level challenger dwell."""
    from reference_volatility import volatility_level_enum, VOL_LEVEL

    state, dwell, ch, ch_dwell = volatility_level_enum(
        1.6, prev=VOL_LEVEL.NORMAL, dwell=0)
    assert state == VOL_LEVEL.NORMAL
    assert ch_dwell == 1

    state, dwell, ch, ch_dwell = volatility_level_enum(
        1.6, prev=VOL_LEVEL.NORMAL, dwell=dwell,
        challenger=ch, challenger_dwell=ch_dwell)
    assert state == VOL_LEVEL.HIGH, "Second challenger: commit"
