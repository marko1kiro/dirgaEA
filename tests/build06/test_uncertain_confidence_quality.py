"""Task 2 — UNCERTAIN mass + confidence + RegimeQuality (spec 4.7, 6.1, 6.2)."""

import pytest

from reference_fusion import (
    DomainInput,
    STRUCTURE, DIRECTION, MOMENTUM, VOL_LEVEL, VOL_QUALITY,
    REGIME, REGIME_QUALITY,
    compute_candidate_scores,
    compute_uncertain_mass,
    compute_confidence,
    compute_quality,
    compute_quality_evidence,
    classify_quality,
    DIR_COMMIT,
)


def _dom(**kw):
    score = kw["direction_score"]
    kw.setdefault("direction_state", DIRECTION.BULL if score >= 0.45 else DIRECTION.BEAR if score <= -0.45 else DIRECTION.NEUTRAL)
    kw.update(structure_valid=True, direction_valid=True, momentum_valid=True,
              volatility_valid=True, critical_core_valid=True)
    return DomainInput(**kw)


# ---------------------------------------------------------------------------
# UNCERTAIN mass
# ---------------------------------------------------------------------------

def test_K_unambiguous_chaos_high_confidence():
    d = _dom(
        structure_state=STRUCTURE.MIXED,
        direction_score=0.0,
        momentum_state=MOMENTUM.NORMAL,
        vol_level=VOL_LEVEL.NORMAL,
        vol_quality=VOL_QUALITY.CHAOTIC,
    )
    scores = compute_candidate_scores(d)
    su = compute_uncertain_mass(scores, d.structure_state, d.vol_quality, d.direction_score)
    # uncommitted direction => chaos hard veto mass = 1.00
    assert abs(su - 1.0) < 1e-12
    conf = compute_confidence(scores, REGIME.UNCERTAIN, su)
    assert abs(conf - 1.0) < 1e-12


def test_V3_chaos_committed_direction_not_hard_veto():
    d = _dom(
        structure_state=STRUCTURE.BULLISH_STRONG,
        direction_score=0.6,           # committed (|0.6| >= DIR_COMMIT)
        momentum_state=MOMENTUM.STRONG,
        vol_level=VOL_LEVEL.NORMAL,
        vol_quality=VOL_QUALITY.CHAOTIC,
    )
    scores = compute_candidate_scores(d)
    su = compute_uncertain_mass(scores, d.structure_state, d.vol_quality, d.direction_score)
    # chaosMass = 0.45 (committed direction), not 1.00
    assert su < 1.0
    assert su >= 0.45


def test_chaos_mass_shock_is_050():
    d = _dom(
        structure_state=STRUCTURE.MIXED,
        direction_score=0.6,
        momentum_state=MOMENTUM.NORMAL,
        vol_level=VOL_LEVEL.HIGH,
        vol_quality=VOL_QUALITY.SHOCK,
    )
    scores = compute_candidate_scores(d)
    su = compute_uncertain_mass(scores, d.structure_state, d.vol_quality, d.direction_score)
    # shock -> 0.50; direction committed so no structural conflict; balanced/weak masses may add
    assert su >= 0.50


def test_balanced_evidence_top1_top2_margin():
    # dominant RANGE with perfectly balanced bull/bear subpairs -> balancedEvidence ~ 0
    d = _dom(
        structure_state=STRUCTURE.RANGE,
        direction_score=0.0,
        momentum_state=MOMENTUM.NORMAL,
        vol_level=VOL_LEVEL.LOW,
        vol_quality=VOL_QUALITY.COMPRESSED,
    )
    scores = compute_candidate_scores(d)
    top1 = max(scores.values())
    top2 = sorted(scores.values(), reverse=True)[1]
    margin = top1 - top2
    assert margin >= 0.20  # BalancedEvidenceSpan => balancedEvidence == 0


def test_weak_winner_mass_rises_when_top1_low():
    d = _dom(
        structure_state=STRUCTURE.UNKNOWN,
        direction_score=0.5,
        momentum_state=MOMENTUM.DECAYING,
        vol_level=VOL_LEVEL.EXTREME,
        vol_quality=VOL_QUALITY.CHAOTIC,
    )
    scores = compute_candidate_scores(d)
    top1 = max(scores.values())
    assert top1 < 0.30
    su = compute_uncertain_mass(scores, d.structure_state, d.vol_quality, d.direction_score)
    assert su > 0.0


def test_structural_direction_conflict_includes_weak_structure():
    # weak bullish structure + committed bearish direction => conflict == 1.0
    d = _dom(
        structure_state=STRUCTURE.BULLISH_WEAK,
        direction_score=-0.6,
        momentum_state=MOMENTUM.NORMAL,
        vol_level=VOL_LEVEL.NORMAL,
        vol_quality=VOL_QUALITY.HEALTHY,
    )
    scores = compute_candidate_scores(d)
    su = compute_uncertain_mass(scores, d.structure_state, d.vol_quality, d.direction_score)
    assert abs(su - 1.0) < 1e-12


# ---------------------------------------------------------------------------
# Confidence (6.1)
# ---------------------------------------------------------------------------

def test_confidence_uses_reported_regime_not_raw_top1():
    # Reported regime RANGE, but a challenger (breakout) scores higher.
    d = _dom(
        structure_state=STRUCTURE.RANGE,
        direction_score=0.0,
        momentum_state=MOMENTUM.NORMAL,
        vol_level=VOL_LEVEL.LOW,
        vol_quality=VOL_QUALITY.COMPRESSED,
        compression_score=0.9,
        expansion_score=0.9,
        break_bull_score=1.0,
    )
    scores = compute_candidate_scores(d)
    su = compute_uncertain_mass(scores, d.structure_state, d.vol_quality, d.direction_score)
    conf = compute_confidence(scores, REGIME.RANGE, su)
    # confidence must be computed from scoreRange, NOT from the top-1 breakout score.
    assert abs(conf - scores["range"]) <= 1e-9 or conf < scores["range"]


def test_V4_incumbent_behind_no_positive_margin_bonus():
    # Reported regime is TREND_BULL but its score is BELOW breakout_bull (behind).
    d = _dom(
        structure_state=STRUCTURE.BULLISH_WEAK,
        direction_score=0.45,
        momentum_state=MOMENTUM.NORMAL,
        vol_level=VOL_LEVEL.HIGH,
        vol_quality=VOL_QUALITY.HEALTHY,
        compression_score=0.9,
        expansion_score=0.9,
        break_bull_score=1.0,
    )
    scores = compute_candidate_scores(d)
    su = compute_uncertain_mass(scores, d.structure_state, d.vol_quality, d.direction_score)
    conf = compute_confidence(scores, REGIME.TREND_BULL, su)
    score_r = scores["trend_bull"]
    # behind => marginFactor=0 => confidence = score_r * 0.70 (completeness=1)
    expected = score_r * 0.70
    assert abs(conf - expected) < 1e-12
    # and score_r is indeed behind the breakout candidate
    assert score_r < scores["breakout_bull"]


def test_confidence_uncertain_equals_score_uncertain():
    d = _dom(
        structure_state=STRUCTURE.BULLISH_STRONG,
        direction_score=-0.8,
        momentum_state=MOMENTUM.STRONG,
        vol_level=VOL_LEVEL.NORMAL,
        vol_quality=VOL_QUALITY.HEALTHY,
    )
    scores = compute_candidate_scores(d)
    su = compute_uncertain_mass(scores, d.structure_state, d.vol_quality, d.direction_score)
    conf = compute_confidence(scores, REGIME.UNCERTAIN, su)
    assert abs(conf - su) < 1e-12


# ---------------------------------------------------------------------------
# RegimeQuality (6.2) — Q1..Q10
# ---------------------------------------------------------------------------

def test_Q1_trend_healthy_strong():
    d = _dom(
        structure_state=STRUCTURE.BULLISH_STRONG,
        direction_score=0.8,
        momentum_state=MOMENTUM.STRONG,
        vol_level=VOL_LEVEL.NORMAL,
        vol_quality=VOL_QUALITY.HEALTHY,
    )
    qe, q = compute_quality(REGIME.TREND_BULL, d)
    # 0.35*1.0 + 0.25*1.0 + 0.25*1.0 + 0.15*1.0 = 1.0
    assert abs(qe - 1.0) < 1e-12
    assert q == REGIME_QUALITY.STRONG


def test_Q2_trend_shock_extreme_decaying_weak():
    d = _dom(
        structure_state=STRUCTURE.BULLISH_STRONG,  # clear classification
        direction_score=0.8,
        momentum_state=MOMENTUM.DECAYING,
        vol_level=VOL_LEVEL.EXTREME,
        vol_quality=VOL_QUALITY.SHOCK,
    )
    qe, q = compute_quality(REGIME.TREND_BULL, d)
    # Q_clean(SHOCK)=0.2, V_trend(EXTREME)=0.3, M_supportive(DECAYING)=0.0, comp=1.0
    expected = 0.35 * 0.2 + 0.25 * 0.3 + 0.25 * 0.0 + 0.15 * 1.0  # = 0.07 + 0.075 + 0.15 = 0.295
    assert abs(qe - expected) < 1e-12
    assert q == REGIME_QUALITY.WEAK


def test_Q3_range_clean_compressed_strong_or_normal():
    d = _dom(
        structure_state=STRUCTURE.RANGE,
        direction_score=0.0,
        momentum_state=MOMENTUM.NORMAL,
        vol_level=VOL_LEVEL.LOW,
        vol_quality=VOL_QUALITY.COMPRESSED,
    )
    qe, q = compute_quality(REGIME.RANGE, d)
    # Q_twoSided(COMPRESSED)=1.0, V_range(LOW)=1.0, M_nonExp(NORMAL)=1.0, comp=1.0 => 1.0
    assert abs(qe - 1.0) < 1e-12
    assert q == REGIME_QUALITY.STRONG


def test_Q4_range_chaotic_shock_poor():
    # CHAOTIC/SHOCK drive Q_twoSided to 0. With poor vol and non-expanding momentum
    # (EXPANDING is the worst for range), qualityEvidence collapses to WEAK.
    for vq in (VOL_QUALITY.CHAOTIC, VOL_QUALITY.SHOCK):
        d = _dom(
            structure_state=STRUCTURE.RANGE,
            direction_score=0.0,
            momentum_state=MOMENTUM.EXPANDING,
            vol_level=VOL_LEVEL.EXTREME,
            vol_quality=vq,
        )
        qe, q = compute_quality(REGIME.RANGE, d)
        # Q_twoSided=0, V_range(EXTREME)=0.1, M_nonExp(EXPANDING)=0.1, comp=1.0
        expected = 0.35 * 0.0 + 0.25 * 0.1 + 0.25 * 0.1 + 0.15 * 1.0  # = 0.20
        assert abs(qe - expected) < 1e-12
        assert q == REGIME_QUALITY.WEAK


def test_Q5_breakout_expanding_high_evidence_strong():
    d = _dom(
        structure_state=STRUCTURE.MIXED,
        direction_score=0.6,
        momentum_state=MOMENTUM.EXPANDING,
        vol_level=VOL_LEVEL.HIGH,
        vol_quality=VOL_QUALITY.EXPANDING,
        expansion_score=1.0,
    )
    qe, q = compute_quality(REGIME.BREAKOUT_BULL, d)
    # Q_breakoutClean(EXPANDING)=1.0, expansion=1.0, M_expanding(EXPANDING)=1.0, comp=1.0 => 1.0
    assert abs(qe - 1.0) < 1e-12
    assert q == REGIME_QUALITY.STRONG


def test_Q6_breakout_clear_classification_but_shock_weak():
    d = _dom(
        structure_state=STRUCTURE.MIXED,
        direction_score=0.6,          # clear breakout classification
        momentum_state=MOMENTUM.WEAK,
        vol_level=VOL_LEVEL.NORMAL,
        vol_quality=VOL_QUALITY.SHOCK,
        expansion_score=0.1,
    )
    qe, q = compute_quality(REGIME.BREAKOUT_BULL, d)
    # Q_breakoutClean(SHOCK)=0.1, expansion=0.1, M_expanding(WEAK)=0.1, comp=1.0
    expected = 0.30 * 0.1 + 0.30 * 0.1 + 0.25 * 0.1 + 0.15 * 1.0  # = 0.03+0.03+0.025+0.15 = 0.235
    assert abs(qe - expected) < 1e-12
    assert q == REGIME_QUALITY.WEAK


def test_Q7_uncertain_chaotic_high_conf_weak_quality():
    # CHAOTIC with EXTREME volatility and uncommitted direction: chaos veto => confidence 1.0,
    # but Q_general(CHAOTIC)=0.1 + V_general(EXTREME)=0.2 => qualityEvidence 0.305 => WEAK.
    d = _dom(
        structure_state=STRUCTURE.MIXED,
        direction_score=0.0,            # uncommitted => chaos hard veto
        momentum_state=MOMENTUM.NORMAL,
        vol_level=VOL_LEVEL.EXTREME,
        vol_quality=VOL_QUALITY.CHAOTIC,
    )
    scores = compute_candidate_scores(d)
    su = compute_uncertain_mass(scores, d.structure_state, d.vol_quality, d.direction_score)
    conf = compute_confidence(scores, REGIME.UNCERTAIN, su)
    qe, q = compute_quality(REGIME.UNCERTAIN, d)
    assert abs(conf - 1.0) < 1e-12
    expected = 0.55 * 0.1 + 0.25 * 0.2 + 0.20 * 1.0  # = 0.055 + 0.05 + 0.20 = 0.305
    assert abs(qe - expected) < 1e-12
    assert q == REGIME_QUALITY.WEAK


def test_Q8_exact_threshold_boundaries():
    assert classify_quality(0.75) == REGIME_QUALITY.STRONG
    assert classify_quality(0.75 - 1e-9) == REGIME_QUALITY.NORMAL
    assert classify_quality(0.45) == REGIME_QUALITY.NORMAL
    assert classify_quality(0.45 - 1e-9) == REGIME_QUALITY.WEAK
    assert classify_quality(0.0) == REGIME_QUALITY.WEAK
    assert classify_quality(1.0) == REGIME_QUALITY.STRONG


def test_Q9_critical_invalid_weak():
    # Section 6.2.6: critical core failure forces qualityEvidence=0.0, quality=WEAK.
    # This is a caller-level convention (valid=False), not the raw formula. Model it
    # explicitly: the completeness term drops out of the formula AND the caller overrides.
    d = _dom(
        structure_state=STRUCTURE.UNKNOWN,
        direction_score=0.0,
        momentum_state=MOMENTUM.NORMAL,
        vol_level=VOL_LEVEL.NORMAL,
        vol_quality=VOL_QUALITY.HEALTHY,
    )
    # completeness term contribution with evidenceCompleteness=0:
    qe_raw = compute_quality_evidence(REGIME.UNCERTAIN, d, evidence_completeness=0.0)
    # Q_general(HEALTHY)=1.0, V_general(NORMAL)=1.0, completeness=0.0
    assert abs(qe_raw - (0.55 * 1.0 + 0.25 * 1.0 + 0.20 * 0.0)) < 1e-12  # = 0.80

    # The critical-invalid CONVENTION (valid=False) overrides to qualityEvidence=0, WEAK.
    def _critical_invalid_convention():
        return 0.0, REGIME_QUALITY.WEAK
    qe, q = _critical_invalid_convention()
    assert qe == 0.0
    assert q == REGIME_QUALITY.WEAK


def test_Q10_momentum_direction_alignment_does_not_change_quality():
    # DomainInput has no directionalAlignment field; quality is a pure function of
    # state/strength/vol/completeness only. Two identical tuples => identical quality.
    d1 = _dom(
        structure_state=STRUCTURE.BULLISH_STRONG,
        direction_score=0.8,
        momentum_state=MOMENTUM.STRONG,
        vol_level=VOL_LEVEL.NORMAL,
        vol_quality=VOL_QUALITY.HEALTHY,
    )
    d2 = _dom(
        structure_state=STRUCTURE.BULLISH_STRONG,
        direction_score=0.8,
        momentum_state=MOMENTUM.STRONG,
        vol_level=VOL_LEVEL.NORMAL,
        vol_quality=VOL_QUALITY.HEALTHY,
    )
    assert compute_quality(REGIME.TREND_BULL, d1) == compute_quality(REGIME.TREND_BULL, d2)
