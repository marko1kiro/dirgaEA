import pytest
from reference_volatility import volatility_level_enum, VOL_LEVEL


def test_VOLLEVEL_long_incumbent_no_credit():
    """NORMAL for 10 bars then first HIGH: must NOT instantly commit."""
    ratios = [1.0] * 10 + [1.6]
    out = []
    ch = None
    ch_dwell = 0
    for r in ratios:
        prev = out[-1][0] if out else VOL_LEVEL.NORMAL
        d = out[-1][1] if out else 0
        state, dwell, ch, ch_dwell = volatility_level_enum(
            r, prev=prev, dwell=d, challenger=ch, challenger_dwell=ch_dwell)
        out.append((state, dwell))

    assert out[9][0] == VOL_LEVEL.NORMAL, "After 10 NORMAL bars, still NORMAL"
    assert out[10][0] == VOL_LEVEL.NORMAL, "First HIGH: must NOT commit yet"

    state, dwell, ch, ch_dwell = volatility_level_enum(
        1.6, prev=out[-1][0], dwell=out[-1][1],
        challenger=ch, challenger_dwell=ch_dwell)
    assert state == VOL_LEVEL.HIGH, "Second HIGH: must commit"


def test_VOLLEVEL_challenger_interruption():
    """NORMAL → HIGH → NORMAL → HIGH: dwell resets on interruption."""
    out = []
    ch = None
    ch_dwell = 0

    state, dwell, ch, ch_dwell = volatility_level_enum(
        1.6, prev=VOL_LEVEL.NORMAL, dwell=0, challenger=ch, challenger_dwell=ch_dwell)
    out.append((state, dwell))
    assert state == VOL_LEVEL.NORMAL, "First HIGH: dwell=1"
    assert ch_dwell == 1

    state, dwell, ch, ch_dwell = volatility_level_enum(
        1.0, prev=VOL_LEVEL.NORMAL, dwell=0, challenger=ch, challenger_dwell=ch_dwell)
    out.append((state, dwell))
    assert state == VOL_LEVEL.NORMAL
    assert ch == VOL_LEVEL.NORMAL, "Challenger resets"
    assert ch_dwell == 0

    state, dwell, ch, ch_dwell = volatility_level_enum(
        1.6, prev=VOL_LEVEL.NORMAL, dwell=0, challenger=ch, challenger_dwell=ch_dwell)
    out.append((state, dwell))
    assert state == VOL_LEVEL.NORMAL, "Second HIGH after interruption: dwell=1 again"
    assert ch_dwell == 1


def test_VOLLEVEL_step_down_immediate():
    """Committed HIGH → ratio=1.0 (NORMAL): step down is immediate."""
    # Commit HIGH via challenger dwell
    s, d, ch, cd = volatility_level_enum(1.6, prev=VOL_LEVEL.NORMAL, dwell=0)
    assert s == VOL_LEVEL.NORMAL and cd == 1
    s, d, ch, cd = volatility_level_enum(1.6, prev=s, dwell=d, challenger=ch, challenger_dwell=cd)
    assert s == VOL_LEVEL.HIGH, "Committed HIGH after 2 challenger bars"

    # Step down to NORMAL is immediate
    s, d, ch, cd = volatility_level_enum(1.0, prev=s, dwell=d, challenger=ch, challenger_dwell=cd)
    assert s == VOL_LEVEL.NORMAL, "Step down: immediate"
    assert d == 0
