"""Task 4 — breakout maturation / aging / handoff (spec sections 9-10)."""

import pytest

from reference_fusion import (
    DomainInput,
    STRUCTURE, DIRECTION, MOMENTUM, VOL_LEVEL, VOL_QUALITY,
    REGIME, TRANSITION,
    Params, PersistentState, update_fusion,
)


def _dom(structure, dscore, momentum, vol_level=VOL_LEVEL.NORMAL,
         vol_quality=VOL_QUALITY.HEALTHY, **kw):
    return DomainInput(
        structure_state=structure, direction_score=dscore, momentum_state=momentum,
        vol_level=vol_level, vol_quality=vol_quality,
        direction_state=DIRECTION.BULL if dscore >= 0.45 else DIRECTION.BEAR if dscore <= -0.45 else DIRECTION.NEUTRAL,
        structure_valid=True, direction_valid=True, momentum_valid=True,
        volatility_valid=True, critical_core_valid=True, **kw,
    )


def _breakout_bull_bar(compression=1.0, expansion=1.0):
    # A bar that strongly favors BREAKOUT_BULL (fresh bull break + expansion).
    return _dom(STRUCTURE.MIXED, 0.7, MOMENTUM.EXPANDING,
                vol_quality=VOL_QUALITY.EXPANDING,
                compression_score=compression, expansion_score=expansion,
                break_bull_score=1.0)


def _run(seq, params=None):
    params = params or Params()
    st = PersistentState()
    return [update_fusion(d, st, params) for d in seq]


def test_H_breakout_matures_to_trend():
    p = Params()
    # First bar: breakout bull wins (fresh break + expansion).
    # Then sustained bullish structure + bull direction + non-decaying momentum.
    seq = [_breakout_bull_bar(),
           _dom(STRUCTURE.BULLISH_STRONG, 0.7, MOMENTUM.STRONG)]
    out = _run(seq, p)
    assert out[0]["regime"] == REGIME.BREAKOUT_BULL
    # maturation eligible at age >= 2 (BreakoutMaturationMinBars=2): entry=age1, bar2=age2
    assert out[1]["regime"] == REGIME.TREND_BULL
    assert out[1]["transition_reason"] == TRANSITION.MATURATION


def test_H2_T2_maturation_blocked_before_min_bars():
    # min=3: at age 2 (bar 2) maturation is NOT eligible even with sustained evidence;
    # it matures only at age 3 (bar 3).
    p = Params(breakout_maturation_min_bars=3, breakout_max_age_bars=99)
    seq = [_breakout_bull_bar(),
           _dom(STRUCTURE.BULLISH_STRONG, 0.7, MOMENTUM.STRONG),  # age 2, blocked
           _dom(STRUCTURE.BULLISH_STRONG, 0.7, MOMENTUM.STRONG)]  # age 3, mature
    out = _run(seq, p)
    assert out[0]["regime"] == REGIME.BREAKOUT_BULL
    assert out[1]["regime"] == REGIME.BREAKOUT_BULL           # blocked at age 2 (< min 3)
    assert out[1]["transition_reason"] == TRANSITION.NONE
    assert out[2]["regime"] == REGIME.TREND_BULL              # matures at age 3
    assert out[2]["transition_reason"] == TRANSITION.MATURATION


def test_N_T3_max_age_triggers_at_age_cap():
    p = Params(breakout_maturation_min_bars=99,  # maturation effectively disabled
               breakout_max_age_bars=3)
    # breakout persists without acceptance (structure stays MIXED, no sustained bull)
    seq = [_breakout_bull_bar(),
           _dom(STRUCTURE.MIXED, 0.3, MOMENTUM.NORMAL),
           _dom(STRUCTURE.MIXED, 0.3, MOMENTUM.NORMAL)]
    out = _run(seq, p)
    # entry=age1, bar2=age2 (stay), bar3=age3 == max => failed breakout => UNCERTAIN
    assert out[1]["regime"] == REGIME.BREAKOUT_BULL   # age 2, still below max 3
    assert out[2]["regime"] == REGIME.UNCERTAIN       # age 3 == max => fail
    assert out[2]["transition_reason"] == TRANSITION.FAILED_BREAKOUT


def test_I_failed_breakout_then_range_handoff():
    p = Params(breakout_maturation_min_bars=99, breakout_max_age_bars=2)
    seq = [_breakout_bull_bar(),
           _dom(STRUCTURE.MIXED, 0.3, MOMENTUM.NORMAL),   # no acceptance -> age 2 => fail
           # then RANGE structure re-confirmed (non-chaotic, low conviction)
           _dom(STRUCTURE.RANGE, 0.0, MOMENTUM.NORMAL, vol_quality=VOL_QUALITY.COMPRESSED)]
    out = _run(seq, p)
    assert out[1]["regime"] == REGIME.UNCERTAIN
    assert out[1]["transition_reason"] == TRANSITION.FAILED_BREAKOUT
    # range re-confirmed -> exits UNCERTAIN into RANGE (gap+dwell)
    assert out[2]["regime"] == REGIME.RANGE


def test_F1_immediate_failure_on_opposing_structure():
    p = Params(breakout_maturation_min_bars=99, breakout_max_age_bars=99)
    seq = [_breakout_bull_bar(),
           _dom(STRUCTURE.BEARISH_STRONG, -0.7, MOMENTUM.NORMAL)]  # opposing structure
    out = _run(seq, p)
    # opposing structure => immediate failed breakout (regardless of age)
    assert out[1]["regime"] == REGIME.UNCERTAIN
    assert out[1]["transition_reason"] == TRANSITION.FAILED_BREAKOUT


def test_breakout_never_sticky_beyond_max_age():
    p = Params(breakout_maturation_min_bars=99, breakout_max_age_bars=4)
    seq = [_breakout_bull_bar()] + [_dom(STRUCTURE.MIXED, 0.3, MOMENTUM.NORMAL)] * 10
    out = _run(seq, p)
    # by max age 4 it fails; never remains BREAKOUT indefinitely
    regimes = [r["regime"] for r in out]
    assert REGIME.BREAKOUT_BULL not in regimes[4:]
