"""HARD vs SOFT uncertainty split tests (architect patch X1-X8)."""

import pytest

from reference_fusion import (
    DomainInput,
    STRUCTURE, MOMENTUM, VOL_LEVEL, VOL_QUALITY,
    REGIME, TRANSITION,
    Params, PersistentState, update_fusion,
    DIR_COMMIT,
)


def _dom(structure, dscore, momentum=MOMENTUM.STRONG,
         vol_level=VOL_LEVEL.NORMAL, vol_quality=VOL_QUALITY.HEALTHY, **kw):
    return DomainInput(
        structure_state=structure, direction_score=dscore, momentum_state=momentum,
        vol_level=vol_level, vol_quality=vol_quality, **kw,
    )


def _bull():
    return _dom(STRUCTURE.BULLISH_STRONG, 0.8)


def _breakout_bull_bar():
    return _dom(STRUCTURE.MIXED, 0.7, MOMENTUM.EXPANDING,
                vol_quality=VOL_QUALITY.EXPANDING,
                compression_score=1.0, expansion_score=1.0, break_bull_score=1.0)


def _breakout_bear_bar():
    return _dom(STRUCTURE.MIXED, -0.7, MOMENTUM.EXPANDING,
                vol_quality=VOL_QUALITY.EXPANDING,
                compression_score=1.0, expansion_score=1.0, break_bear_score=1.0)


def _weak_soft_bar():
    # Soft uncertainty source (balancedEvidence + weakWinnerMass + chaosMass SHOCK),
    # NO hard veto: UNKNOWN structure (no conflict), committed direction, SHOCK quality.
    return _dom(STRUCTURE.UNKNOWN, 0.5, MOMENTUM.DECAYING,
                vol_level=VOL_LEVEL.EXTREME, vol_quality=VOL_QUALITY.SHOCK)


def _run(seq, params=None):
    params = params or Params()
    st = PersistentState()
    return [update_fusion(d, st, params) for d in seq]


def test_X1_perfect_tie_retains_incumbent_first_bar():
    p = Params()
    seq = [_bull(), _bull(),
           # near-tie: breakout_bull (~0.97) vs trend_bull (~0.88) => balancedEvidence soft
           _dom(STRUCTURE.BULLISH_STRONG, 0.8, MOMENTUM.EXPANDING,
                vol_quality=VOL_QUALITY.COMPRESSED,
                compression_score=1.0, expansion_score=0.8, break_bull_score=1.0)]
    out = _run(seq, p)
    assert out[0]["regime"] == REGIME.TREND_BULL
    assert out[2]["regime"] == REGIME.TREND_BULL       # no immediate override
    assert out[2]["pending_candidate"] == REGIME.UNCERTAIN  # soft uncertainty challenger
    assert out[2]["candidate_age_bars"] == 1


def test_X2_persistent_tie_commits_after_dwell():
    p = Params()  # dwell=2
    seq = [_bull(), _bull(),
           _weak_soft_bar(),   # soft uncertainty, incumbent survives (age 1)
           _weak_soft_bar()]   # age 2 => commit UNCERTAIN
    out = _run(seq, p)
    assert out[2]["regime"] == REGIME.TREND_BULL
    assert out[3]["regime"] == REGIME.UNCERTAIN
    assert out[3]["transition_reason"] == TRANSITION.CHALLENGE_WIN


def test_X3_one_bar_soft_uncertainty_does_not_destroy_incumbent():
    p = Params()
    seq = [_bull(), _bull(), _weak_soft_bar()]
    out = _run(seq, p)
    assert out[2]["regime"] == REGIME.TREND_BULL
    assert out[2]["pending_candidate"] == REGIME.UNCERTAIN
    assert out[2]["candidate_age_bars"] == 1


def test_X4_hard_structural_direction_conflict_immediate():
    p = Params(regime_dwell=99)  # even with huge dwell, hard veto bypasses it
    seq = [_bull(), _bull(),
           _dom(STRUCTURE.BULLISH_STRONG, -0.8)]  # bull structure + bear committed dir
    out = _run(seq, p)
    assert out[2]["regime"] == REGIME.UNCERTAIN
    assert out[2]["transition_reason"] == TRANSITION.OVERRIDE


def test_X5_uncommitted_chaotic_immediate():
    p = Params(regime_dwell=99)
    seq = [_bull(), _bull(),
           _dom(STRUCTURE.MIXED, 0.0, momentum=MOMENTUM.NORMAL,
                vol_quality=VOL_QUALITY.CHAOTIC)]  # chaos + uncommitted direction
    out = _run(seq, p)
    assert out[2]["regime"] == REGIME.UNCERTAIN
    assert out[2]["transition_reason"] == TRANSITION.OVERRIDE


def test_X6_committed_direction_chaotic_not_hard_override():
    p = Params()
    seq = [_bull(), _bull(),
           # CHAOTIC but committed (aligned) direction => chaosMass 0.45 (soft), no hard veto
           _dom(STRUCTURE.BULLISH_STRONG, 0.6, momentum=MOMENTUM.STRONG,
                vol_quality=VOL_QUALITY.CHAOTIC)]
    out = _run(seq, p)
    assert out[2]["regime"] == REGIME.TREND_BULL       # incumbent survives, no override
    assert out[2]["transition_reason"] != TRANSITION.OVERRIDE


def test_X7_breakout_bull_bearish_committed_direction_fails():
    p = Params(breakout_maturation_min_bars=99, breakout_max_age_bars=99)
    seq = [_breakout_bull_bar(),
           _dom(STRUCTURE.MIXED, -0.6, momentum=MOMENTUM.NORMAL)]  # bearish committed dir
    out = _run(seq, p)
    assert out[0]["regime"] == REGIME.BREAKOUT_BULL
    assert out[1]["regime"] == REGIME.UNCERTAIN
    assert out[1]["transition_reason"] == TRANSITION.FAILED_BREAKOUT


def test_X8_breakout_bear_bullish_committed_direction_fails():
    p = Params(breakout_maturation_min_bars=99, breakout_max_age_bars=99)
    seq = [_breakout_bear_bar(),
           _dom(STRUCTURE.MIXED, 0.6, momentum=MOMENTUM.NORMAL)]  # bullish committed dir
    out = _run(seq, p)
    assert out[0]["regime"] == REGIME.BREAKOUT_BEAR
    assert out[1]["regime"] == REGIME.UNCERTAIN
    assert out[1]["transition_reason"] == TRANSITION.FAILED_BREAKOUT
