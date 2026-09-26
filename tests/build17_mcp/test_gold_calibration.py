"""Gold calibration (XAUUSDm executability) — source invariants.

Item 1: symbol-aware spread ceiling (relative bound, EURUSDm maps to ~35).
Item 2: quality scale verdict — UNCHANGED (RR zero shared EURUSD/gold =
  candidate geometry, forbidden; spread tier healthy). Documents numbers.
Item 3: silent dispatch-drop log tags (observation only).
Item 4: 2f selectivity symbol gate (EURUSDm-only, filter retained).
"""

import os
import re

import pytest

SOURCE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read_source(name):
    path = os.path.join(SOURCE_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# --- Item 1: symbol-aware spread ceiling ---

def test_ceiling_uses_runtime_typical_spread():
    src = read_source("ExecutionSafety.mqh")
    assert "SYMBOL_SPREAD" in src, \
        "ceiling must derive per-symbol typical spread via SYMBOL_SPREAD"


def test_ceiling_eurusdm_floor_maps_to_35():
    src = read_source("ExecutionSafety.mqh")
    assert re.search(r"MathMax\s*\(\s*m_maxSpreadCeiling", src), \
        "EURUSDm effective ceiling must floor at configured 35.0 by construction"
    assert re.search(r"EURUSDm.*35|35.*EURUSDm", src), \
        "comment must prove EURUSDm maps to ~35 points"


def test_ceiling_gold_effective_documented():
    src = read_source("ExecutionSafety.mqh")
    assert re.search(r"XAUUSDm|gold", src, re.IGNORECASE), \
        "comment must document gold effective ceiling"
    assert "260" in src, \
        "comment must document gold typical spread (~260 pts) and resulting ceiling"


def test_ceiling_keeps_safety_reason_key():
    src = read_source("ExecutionSafety.mqh")
    assert "spread_exceeds_absolute_ceiling" in src, \
        "EXECUTION_BLOCKED_SAFETY reason key must be kept"


def test_spread_input_default_still_35():
    src = read_source("Config.mqh")
    assert re.search(r"input\s+double\s+AbsoluteMaxSpreadPoints\s*=\s*35\.0", src), \
        "AbsoluteMaxSpreadPoints default must stay 35.0 (floor for EURUSDm)"


# --- Item 2: quality scale UNCHANGED verdict ---

def test_quality_threshold_70_intact():
    qg = read_source("QualityGate.mqh")
    assert re.search(r"#define\s+B09_QUALITY_THRESHOLD\s+70\.0", qg), \
        "B09_QUALITY_THRESHOLD must stay 70.0"
    ea = read_source("AdaptiveSurvivalEA.mq5")
    assert re.search(r"double\s+requiredQualityScore\s*=\s*70\.0", ea), \
        "requiredQualityScore 70.0 must stay unchanged"


def test_quality_scale_untouched_with_verdict():
    src = read_source("QualityGate.mqh")
    assert "_Symbol" not in src and "SymbolInfo" not in src, \
        "QualityGate must stay symbol-agnostic (no per-symbol normalization)"
    assert src.count("rejectReason =") == 4, \
        "CQualityGate::Evaluate body must stay untouched"
    assert re.search(r"3\.4|87%|53 zeros", src), \
        "verdict comment must cite gold RR numbers (3.4/35, 87% zeros)"
    assert re.search(r"3\.1", src), \
        "verdict comment must cite EURUSD RR 3.1 (shared disease => geometry)"
    assert re.search(r"11\.8", src), \
        "verdict comment must cite spread-friction health (11.8/15)"


# --- Item 3: silent dispatch-drop tags ---

@pytest.mark.parametrize("tag", [
    "PREPARE_REJECTED_INVALID_CANDIDATE",
    "PREPARE_REJECTED_RISK",
    "PREPARE_REJECTED_MAX_POSITIONS",
    "PREPARE_REJECTED_UNKNOWN_DIRECTION",
])
def test_prepare_reject_tags(tag):
    src = read_source("ExecutionBridge.mqh")
    assert tag in src, "PrepareMarketOrder silent exit needs LogWarning tag %s" % tag


def test_dispatch_prepare_rejected_logged():
    src = read_source("AdaptiveSurvivalEA.mq5")
    assert "DISPATCH_PREPARE_REJECTED" in src, \
        "PrepareMarketOrder-false branch must LogWarning DISPATCH_PREPARE_REJECTED"


def test_execute_unknown_action_tag():
    src = read_source("ExecutionBridge.mqh")
    assert "EXECUTION_REJECTED_UNKNOWN_ACTION" in src, \
        "ExecuteIntent invalid-action exit needs LogWarning tag"


# --- Item 4: selectivity symbol gate ---

def test_selectivity_symbol_gate():
    src = read_source("AdaptiveSurvivalEA.mq5")
    assert re.search(r'_Symbol\s*==\s*"EURUSDm"', src), \
        "selectivity must be gated by explicit EURUSDm symbol allowlist"
    gate_idx = src.find('_Symbol == "EURUSDm"')
    call_idx = src.find("IsEntrySelectivityPassed(b09_last_quality_result))")
    assert gate_idx != -1 and call_idx != -1 and gate_idx < call_idx, \
        "symbol gate must sit before IsEntrySelectivityPassed call"
    assert re.search(r"calibration phase|own winner/loser", src, re.IGNORECASE), \
        "comment must note gold needs its own calibration phase"


def test_selectivity_filter_retained():
    src = read_source("AdaptiveSurvivalEA.mq5")
    assert re.search(r"SELECTIVITY_MAX_TOTAL_SCORE\s*=\s*100\.0", src)
    assert re.search(r"SELECTIVITY_MIN_REGIME_SCORE\s*=\s*5\.0", src)
    assert re.search(r"totalScore\s*>=\s*SELECTIVITY_MAX_TOTAL_SCORE", src)
    assert re.search(r"scoreRegime\s*<=\s*SELECTIVITY_MIN_REGIME_SCORE", src)
