"""Entry-selectivity filter source invariants (in-sample loser shapes).

Kills exactly two proven-loser entry shapes (19 Trend trades: qtot=100 0W/2L,
qreg=5.0 0W/2L): (a) perfect-score chase totalScore>=100, (b) weak-regime
floor scoreRegime<=5. Threshold 70.0 + CQualityGate::Evaluate untouched.
"""

import os
import re

SOURCE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read_source(name):
    path = os.path.join(SOURCE_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_selectivity_constants_defined():
    src = read_source("AdaptiveSurvivalEA.mq5")
    assert re.search(r"SELECTIVITY_MAX_TOTAL_SCORE\s*=\s*100\.0", src), \
        "SELECTIVITY_MAX_TOTAL_SCORE = 100.0 missing"
    assert re.search(r"SELECTIVITY_MIN_REGIME_SCORE\s*=\s*5\.0", src), \
        "SELECTIVITY_MIN_REGIME_SCORE = 5.0 missing"


def test_selectivity_helper_rejects_chase_and_weak_regime():
    src = read_source("AdaptiveSurvivalEA.mq5")
    m = re.search(
        r"bool\s+IsEntrySelectivityPassed\s*\(\s*const\s+QualityGateResult\s*&\s*\w+\s*\)(.*?)",
        src, re.DOTALL)
    assert m, "IsEntrySelectivityPassed(const QualityGateResult &) helper missing"
    body_start = m.end()
    body = src[body_start:body_start + 1200]
    assert "SELECTIVITY_MAX_TOTAL_SCORE" in body, \
        "helper must compare totalScore against SELECTIVITY_MAX_TOTAL_SCORE"
    assert "SELECTIVITY_MIN_REGIME_SCORE" in body, \
        "helper must compare scoreRegime against SELECTIVITY_MIN_REGIME_SCORE"
    assert re.search(r"totalScore\s*>=\s*SELECTIVITY_MAX_TOTAL_SCORE", body), \
        "helper must reject totalScore >= 100"
    assert re.search(r"scoreRegime\s*<=\s*SELECTIVITY_MIN_REGIME_SCORE", body), \
        "helper must reject scoreRegime <= 5"


def test_selectivity_call_site_between_approval_and_lock():
    src = read_source("AdaptiveSurvivalEA.mq5")
    approval = src.find("B09_QUALITY_APPROVED")
    assert approval != -1, "quality approval marker missing"
    call = src.find("IsEntrySelectivityPassed", approval)
    assert call != -1, "selectivity call must sit after quality approval"
    lock = src.find("AcquireOrderLock()", call)
    assert lock != -1, "AcquireOrderLock missing after selectivity call"
    assert approval < call < lock, \
        "call site must sit between quality approval and AcquireOrderLock"
    skip_region = src[call:call + 600]
    assert "return" in skip_region, "selectivity skip must return (skip-guard pattern)"
    assert "LogDebug" in skip_region or "SELECTIVITY" in skip_region, \
        "selectivity skip must log the reason"


def test_quality_threshold_and_evaluate_unchanged():
    ea = read_source("AdaptiveSurvivalEA.mq5")
    assert re.search(r"double\s+requiredQualityScore\s*=\s*70\.0", ea), \
        "quality threshold 70.0 must stay unchanged in EA main"
    qg = read_source("QualityGate.mqh")
    assert "low_quality_score" in qg, "CQualityGate reject reasons changed"
    assert qg.count("rejectReason =") == 4, \
        "CQualityGate::Evaluate body changed (rejectReason assignments != 4)"
    assert "SELECTIVITY" in ea, "filter must live in EA main, not QualityGate.mqh"
    assert "SELECTIVITY" not in qg, "QualityGate.mqh must stay untouched"
