"""Task 5 — degradation + invalid + determinism (spec sections 11, 14)."""

import pytest

from reference_fusion import (
    DomainInput,
    STRUCTURE, DIRECTION, MOMENTUM, VOL_LEVEL, VOL_QUALITY,
    REGIME, REGIME_QUALITY, TRANSITION,
    Params, PersistentState, CompressionMemory, update_fusion,
    evidence_completeness,
    DEGRADED_NONE, DEGRADED_STRUCTURE, DEGRADED_DIRECTION,
    DEGRADED_MOMENTUM, DEGRADED_VOLATILITY,
    b06_signature,
)


def _dom(**kw):
    return DomainInput(
        structure_state=kw.get("structure_state", STRUCTURE.BULLISH_STRONG),
        direction_score=kw.get("direction_score", 0.8),
        momentum_state=kw.get("momentum_state", MOMENTUM.STRONG),
        vol_level=kw.get("vol_level", VOL_LEVEL.NORMAL),
        vol_quality=kw.get("vol_quality", VOL_QUALITY.HEALTHY),
        direction_state=kw.get("direction_state", DIRECTION.STRONG_BULL),
        structure_valid=kw.get("structure_valid", True),
        direction_valid=kw.get("direction_valid", True),
        momentum_valid=kw.get("momentum_valid", True),
        volatility_valid=kw.get("volatility_valid", True),
        critical_core_valid=kw.get("critical_core_valid", True),
    )


def test_P_invalid_core_forces_uncertain_zero_completeness():
    st = PersistentState()
    r = update_fusion(_dom(), st, Params(), valid=False)
    assert r["valid"] is False
    assert r["regime"] == REGIME.UNCERTAIN
    assert r["confidence"] == 0.0
    assert r["quality"] == REGIME_QUALITY.WEAK
    assert r["quality_evidence"] == 0.0


def test_P2_V6_one_degraded_domain_completeness_075():
    # one non-critical domain degraded -> valid=true, completeness=0.75
    assert abs(evidence_completeness(DEGRADED_STRUCTURE) - 0.75) < 1e-12
    assert abs(evidence_completeness(DEGRADED_DIRECTION) - 0.75) < 1e-12
    assert abs(evidence_completeness(DEGRADED_MOMENTUM) - 0.75) < 1e-12
    assert abs(evidence_completeness(DEGRADED_VOLATILITY) - 0.75) < 1e-12


def test_V5_adx_helper_degraded_does_not_reduce_completeness():
    # ADX helper degradation is NOT a domain bit; completeness stays 1.0.
    assert evidence_completeness(DEGRADED_NONE) == 1.0


def test_O_adx_helper_degraded_fusion_valid():
    # ADX helper degraded is not modeled as a domain invalidation; fusion proceeds.
    st = PersistentState()
    r = update_fusion(_dom(), st, Params())
    assert r["valid"] is True
    assert r["regime"] == REGIME.TREND_BULL


def test_completeness_all_degraded_is_zero():
    assert evidence_completeness(
        DEGRADED_STRUCTURE | DEGRADED_DIRECTION | DEGRADED_MOMENTUM | DEGRADED_VOLATILITY
    ) == 0.0


def test_R_identical_sequence_identical_signature():
    seq = [_dom(structure_state=STRUCTURE.BULLISH_STRONG, direction_score=0.8),
           _dom(structure_state=STRUCTURE.BULLISH_STRONG, direction_score=0.8)]
    def run():
        st = PersistentState()
        cm = CompressionMemory()
        sigs = []
        for d in seq:
            r = update_fusion(d, st, Params())
            sigs.append(b06_signature(r, st, cm, d.directional_alignment))
            cm.append(d.compression_score)
        return sigs
    assert run() == run()


def test_V1_signature_differs_on_pending_candidate():
    # Two states with identical VISIBLE result but different pendingCandidateRegime.
    st_a = PersistentState()
    st_a.regime = REGIME.TREND_BULL
    st_a.regime_age_bars = 5
    st_a.pending_candidate = REGIME.TREND_BEAR
    st_a.candidate_age_bars = 1

    st_b = PersistentState()
    st_b.regime = REGIME.TREND_BULL
    st_b.regime_age_bars = 5
    st_b.pending_candidate = None
    st_b.candidate_age_bars = 0

    d = _dom()
    from reference_fusion import compute_candidate_scores, compute_uncertain_mass
    scores = compute_candidate_scores(d)
    su = compute_uncertain_mass(scores, d.structure_state, d.vol_quality, d.direction_score)
    result_a = {
        "regime": REGIME.TREND_BULL, "quality": REGIME_QUALITY.STRONG,
        "quality_evidence": 1.0, "confidence": 0.9, "valid": True,
        "previous_regime": REGIME.TREND_BULL, "regime_age_bars": 5,
        "transition_reason": TRANSITION.NONE, "pending_candidate": st_a.pending_candidate,
        "candidate_age_bars": st_a.candidate_age_bars, "score_uncertain": su,
        "scores": scores,
    }
    result_b = dict(result_a)
    result_b["pending_candidate"] = st_b.pending_candidate
    result_b["candidate_age_bars"] = st_b.candidate_age_bars

    cm = CompressionMemory()
    sig_a = b06_signature(result_a, st_a, cm, d.directional_alignment)
    sig_b = b06_signature(result_b, st_b, cm, d.directional_alignment)
    assert sig_a != sig_b


def test_V2_signature_differs_on_compression_fifo():
    # Identical visible result + same max, but different FIFO contents => different signature.
    d = _dom()
    from reference_fusion import compute_candidate_scores, compute_uncertain_mass
    scores = compute_candidate_scores(d)
    su = compute_uncertain_mass(scores, d.structure_state, d.vol_quality, d.direction_score)
    st = PersistentState()
    st.regime = REGIME.BREAKOUT_BULL
    st.regime_age_bars = 1
    result = {
        "regime": REGIME.BREAKOUT_BULL, "quality": REGIME_QUALITY.NORMAL,
        "quality_evidence": 0.5, "confidence": 0.7, "valid": True,
        "previous_regime": REGIME.BREAKOUT_BULL, "regime_age_bars": 1,
        "transition_reason": TRANSITION.NONE, "pending_candidate": None,
        "candidate_age_bars": 0, "score_uncertain": su, "scores": scores,
    }
    cm_a = CompressionMemory(lookback=4)
    cm_a.append(0.5); cm_a.append(0.5)   # max 0.5
    cm_b = CompressionMemory(lookback=4)
    cm_b.append(0.1); cm_b.append(0.5)   # max 0.5, different contents
    assert abs(cm_a.max() - cm_b.max()) < 1e-12  # same max
    sig_a = b06_signature(result, st, cm_a, d.directional_alignment)
    sig_b = b06_signature(result, st, cm_b, d.directional_alignment)
    assert sig_a != sig_b
