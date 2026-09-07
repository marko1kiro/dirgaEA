import pytest
from tests.build09.reference_quality_gate import (
    CandidateMetrics, QualityGateResult, evaluate_quality_gate
)


def test_high_quality_candidate_approved():
    metrics = CandidateMetrics(
        valid=True,
        rr_ratio=2.2,
        regime_quality=2,      # STRONG
        regime_confidence=0.85,
        extension_atr=1.5,
        spread=0.00005,
        stop_distance=0.0020
    )
    res = evaluate_quality_gate(metrics)
    assert res.approved is True
    assert res.total_score >= 70.0
    assert res.score_rr == 35.0
    assert res.score_regime == 30.0
    assert res.score_extension == 20.0
    assert res.score_spread == 15.0


def test_low_score_rejected():
    metrics = CandidateMetrics(
        valid=True,
        rr_ratio=1.1,          # 15 pts
        regime_quality=0,      # WEAK -> 5 pts
        regime_confidence=0.5,
        extension_atr=2.4,     # 0 pts
        spread=0.00018,        # > 0.10 * stop (0.0015) -> 0 pts
        stop_distance=0.0015
    )
    res = evaluate_quality_gate(metrics)
    assert res.approved is False
    assert res.total_score == 20.0
    assert res.reject_reason == "low_quality_score"


def test_excessive_spread_hard_veto():
    metrics = CandidateMetrics(
        valid=True,
        rr_ratio=3.0,
        regime_quality=2,
        regime_confidence=0.95,
        extension_atr=1.0,
        spread=0.0010,         # 0.0010 > 0.25 * 0.0020 (0.0005)
        stop_distance=0.0020
    )
    res = evaluate_quality_gate(metrics)
    assert res.approved is False
    assert res.total_score == 0.0
    assert res.reject_reason == "excessive_spread"

