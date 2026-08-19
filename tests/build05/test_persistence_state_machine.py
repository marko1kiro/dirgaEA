import pytest
from reference_momentum import momentum_enum, MOMENTUM, PERSISTENCE


def test_MOMENTUM_strong_exits_after_persistence_bars():
    """STRONG → low → low must exit STRONG after MOM_PERSISTENCE bars."""
    strength_strong = 0.65
    strength_normal = 0.50
    slope_neutral = 0.0

    state = MOMENTUM.STRONG
    persist = [0]

    state = momentum_enum(strength_strong, slope_neutral, prev=state, persist=persist)
    assert state == MOMENTUM.STRONG
    assert persist[0] == 0, "High band resets persist"

    state = momentum_enum(strength_normal, slope_neutral, prev=state, persist=persist)
    assert state == MOMENTUM.STRONG, "First low bar: retain STRONG"
    assert persist[0] == 1, "Persist increments to 1"

    state = momentum_enum(strength_normal, slope_neutral, prev=state, persist=persist)
    assert state == MOMENTUM.NORMAL, "Second low bar: must exit STRONG"
    assert persist[0] == 0, "Persist resets on exit"


def test_MOMENTUM_interruption_resets_persistence():
    """STRONG → NORMAL → STRONG → NORMAL: two NORMALs are NOT consecutive."""
    strength_high = 0.65
    strength_normal = 0.50
    slope_neutral = 0.0

    state = MOMENTUM.STRONG
    persist = [0]

    state = momentum_enum(strength_high, slope_neutral, prev=state, persist=persist)
    assert state == MOMENTUM.STRONG

    state = momentum_enum(strength_normal, slope_neutral, prev=state, persist=persist)
    assert state == MOMENTUM.STRONG
    assert persist[0] == 1

    state = momentum_enum(strength_high, slope_neutral, prev=state, persist=persist)
    assert state == MOMENTUM.STRONG
    assert persist[0] == 0, "High band resets persist"

    state = momentum_enum(strength_normal, slope_neutral, prev=state, persist=persist)
    assert state == MOMENTUM.STRONG, "Second low after interruption: must NOT exit"
    assert persist[0] == 1


def test_MOMENTUM_three_lows_exits():
    """STRONG → low → low → low: exits on bar 2."""
    state = MOMENTUM.STRONG
    persist = [0]

    state = momentum_enum(0.65, 0.0, prev=state, persist=persist)
    assert state == MOMENTUM.STRONG

    state = momentum_enum(0.50, 0.0, prev=state, persist=persist)
    assert state == MOMENTUM.STRONG
    assert persist[0] == 1

    state = momentum_enum(0.50, 0.0, prev=state, persist=persist)
    assert state == MOMENTUM.NORMAL
    assert persist[0] == 0


def test_MOMENTUM_high_band_resets_persist():
    """When re-entering high band, persist must reset to 0."""
    state = MOMENTUM.STRONG
    persist = [1]
    state = momentum_enum(0.65, 0.0, prev=state, persist=persist)
    assert state == MOMENTUM.STRONG
    assert persist[0] == 0, "Persist must reset to 0 in high band"


def test_MOMENTUM_expanding_to_normal_persistence():
    """EXPANDING → NORMAL → NORMAL: must exit after persistence."""
    state = MOMENTUM.EXPANDING
    persist = [0]

    state = momentum_enum(0.65, 0.06, prev=state, persist=persist)
    assert state == MOMENTUM.EXPANDING

    state = momentum_enum(0.50, 0.0, prev=state, persist=persist)
    assert state == MOMENTUM.EXPANDING
    assert persist[0] == 1

    state = momentum_enum(0.50, 0.0, prev=state, persist=persist)
    assert state == MOMENTUM.NORMAL
    assert persist[0] == 0
