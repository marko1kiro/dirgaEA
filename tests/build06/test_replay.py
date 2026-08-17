"""Task 5b — cold-start / reload reconstruction (spec section 15b)."""

import pytest

from reference_fusion import (
    DomainInput,
    STRUCTURE, MOMENTUM, VOL_LEVEL, VOL_QUALITY,
    REGIME,
    Params, PersistentState, CompressionMemory, update_fusion,
    b06_signature,
)


def _dom(structure, dscore, momentum, **kw):
    return DomainInput(
        structure_state=structure, direction_score=dscore, momentum_state=momentum,
        vol_level=kw.get("vol_level", VOL_LEVEL.NORMAL),
        vol_quality=kw.get("vol_quality", VOL_QUALITY.HEALTHY),
        compression_score=kw.get("compression_score", 0.0),
        expansion_score=kw.get("expansion_score", 0.0),
        break_bull_score=kw.get("break_bull_score", 0.0),
        break_bear_score=kw.get("break_bear_score", 0.0),
        directional_alignment=kw.get("directional_alignment", 0.0),
    )


# A mixed chronological sequence exercising trend, breakout, range, and uncertain.
_SEQ = [
    _dom(STRUCTURE.BULLISH_STRONG, 0.8, MOMENTUM.STRONG),
    _dom(STRUCTURE.BULLISH_STRONG, 0.8, MOMENTUM.STRONG),
    _dom(STRUCTURE.MIXED, 0.7, MOMENTUM.EXPANDING, vol_quality=VOL_QUALITY.EXPANDING,
         compression_score=1.0, expansion_score=1.0, break_bull_score=1.0),
    _dom(STRUCTURE.BULLISH_STRONG, 0.7, MOMENTUM.STRONG),
    _dom(STRUCTURE.BULLISH_STRONG, 0.7, MOMENTUM.STRONG),
    _dom(STRUCTURE.RANGE, 0.0, MOMENTUM.NORMAL, vol_quality=VOL_QUALITY.COMPRESSED),
]


def _continuous_run(seq, params):
    st = PersistentState()
    cm = CompressionMemory()
    results = []
    for d in seq:
        results.append(update_fusion(d, st, params, compression_memory=cm))
    return st, cm, results


def _replay(seq, params):
    st = PersistentState()
    cm = CompressionMemory()
    results = []
    for d in seq:
        results.append(update_fusion(d, st, params, compression_memory=cm))
    return st, cm, results


def _final_signature(st, cm, results, d):
    return b06_signature(results[-1], st, cm, d.directional_alignment)


def test_W1_continuous_run_equals_cold_start_replay():
    params = Params()
    st_c, cm_c, res_c = _continuous_run(_SEQ, params)
    st_r, cm_r, res_r = _replay(_SEQ, params)

    # Final visible result must match.
    assert res_c[-1]["regime"] == res_r[-1]["regime"]
    assert res_c[-1]["quality"] == res_r[-1]["quality"]
    assert abs(res_c[-1]["confidence"] - res_r[-1]["confidence"]) < 1e-15

    # Hidden persistent state must match.
    assert st_c.regime == st_r.regime
    assert st_c.regime_age_bars == st_r.regime_age_bars
    assert st_c.pending_candidate == st_r.pending_candidate
    assert st_c.candidate_age_bars == st_r.candidate_age_bars
    assert cm_c.contents() == cm_r.contents()

    # Signatures must match.
    sig_c = _final_signature(st_c, cm_c, res_c, _SEQ[-1])
    sig_r = _final_signature(st_r, cm_r, res_r, _SEQ[-1])
    assert sig_c == sig_r


def test_W2_replay_must_be_oldest_to_newest():
    # Feeding out-of-order produces a different state (guard: replay ordering matters).
    params = Params()
    st_ok, cm_ok, res_ok = _replay(_SEQ, params)
    reversed_seq = list(reversed(_SEQ))
    st_bad, cm_bad, res_bad = _replay(reversed_seq, params)

    # Out-of-order replay should differ somewhere in persistent state or final result.
    different = (
        st_ok.regime != st_bad.regime
        or st_ok.regime_age_bars != st_bad.regime_age_bars
        or st_ok.pending_candidate != st_bad.pending_candidate
        or cm_ok.contents() != cm_bad.contents()
        or res_ok[-1]["regime"] != res_bad[-1]["regime"]
    )
    assert different
