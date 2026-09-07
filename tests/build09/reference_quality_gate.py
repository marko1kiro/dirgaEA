"""BUILD 09 reference quality gate implementation."""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class CandidateMetrics:
    valid: bool
    rr_ratio: float
    regime_quality: int  # 0=WEAK, 1=NORMAL, 2=STRONG
    regime_confidence: float
    extension_atr: float
    spread: float
    stop_distance: float


@dataclass
class QualityGateResult:
    approved: bool
    total_score: float
    score_rr: float = 0.0
    score_regime: float = 0.0
    score_extension: float = 0.0
    score_spread: float = 0.0
    reject_reason: str = ""


THRESHOLD_SCORE = 70.0


def evaluate_quality_gate(m: CandidateMetrics) -> QualityGateResult:
    if not m.valid or m.stop_distance <= 0:
        return QualityGateResult(False, 0.0, reject_reason="invalid_metrics")

    if m.spread > 0.25 * m.stop_distance:
        return QualityGateResult(False, 0.0, reject_reason="excessive_spread")

    # 1. RR Score (35 max)
    score_rr = 0.0
    if m.rr_ratio >= 2.0:
        score_rr = 35.0
    elif m.rr_ratio >= 1.5:
        score_rr = 25.0
    elif m.rr_ratio >= 1.0:
        score_rr = 15.0

    # 2. Regime Score (30 max)
    score_regime = 5.0
    if m.regime_quality == 2 and m.regime_confidence >= 0.80:
        score_regime = 30.0
    elif m.regime_quality == 1 and m.regime_confidence >= 0.60:
        score_regime = 20.0

    # 3. Extension Score (20 max)
    score_ext = 0.0
    if m.extension_atr <= 1.8:
        score_ext = 20.0
    elif m.extension_atr <= 2.2:
        score_ext = 10.0

    # 4. Spread Score (15 max)
    score_spread = 0.0
    if m.spread <= 0.05 * m.stop_distance:
        score_spread = 15.0
    elif m.spread <= 0.10 * m.stop_distance:
        score_spread = 10.0

    total = score_rr + score_regime + score_ext + score_spread
    approved = (total >= THRESHOLD_SCORE)

    return QualityGateResult(
        approved=approved,
        total_score=total,
        score_rr=score_rr,
        score_regime=score_regime,
        score_extension=score_ext,
        score_spread=score_spread,
        reject_reason="" if approved else "low_quality_score"
    )
