"""BUILD 17 funnel fixes — source invariants for candidate-flow defects.

Proven baseline (Fase 2b, EURUSDm M15): 10,760 trend-regime bars yielded
0 candidates; quality mean 33.6 with target==entry degenerates; UNCERTAIN 64%.

(a) latch: swing/break tables must evict (bounded/self-expiring) + throttled
    block diagnostic; (b) B06: recalibrated UncertainVeto (+exit companions)
    with veto logic retained; (c) degenerate: rewardDistance>0 guard on each
    Evaluate path that sets valid=true (Breakout structurally exempt).
"""

import os
import re

SOURCE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read_source(name):
    path = os.path.join(SOURCE_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def function_region(src, signature):
    start = src.find(signature)
    assert start != -1, "%s not found" % signature
    depth = 0
    i = src.find("{", start)
    assert i != -1, "body of %s not found" % signature
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
    raise AssertionError("unbalanced braces in %s" % signature)


# --- Item 1a: tables bounded (FIFO eviction, mirrors m_bars ring) ---

def test_trend_swing_table_evicts_oldest():
    src = read_source("TrendStrategy.mqh")
    assert re.search(r"m_swings\[\s*\w+\s*\]\s*=\s*m_swings\[\s*\w+\s*\+\s*1\s*\]", src), \
        "swing table must FIFO-shift when full or it saturates and freezes DetectPivots"
    assert re.search(r"m_swingsCount\s*=\s*B07_MAX_SWINGS\s*-\s*1|m_swingsCount--", src), \
        "swing eviction must free a slot"


def test_trend_break_table_evicts_oldest():
    src = read_source("TrendStrategy.mqh")
    assert re.search(r"m_breaks\[\s*\w+\s*\]\s*=\s*m_breaks\[\s*\w+\s*\+\s*1\s*\]", src), \
        "break table must FIFO-shift when full or new breaks are silently dropped"
    assert re.search(r"m_breaksCount\s*=\s*B07_MAX_BREAKS\s*-\s*1|m_breaksCount--", src), \
        "break eviction must free a slot"


def test_trend_contradiction_block_diagnostic_throttled():
    src = read_source("TrendStrategy.mqh")
    assert re.search(r"LogDebug\(\s*\"TREND_EVAL_BLOCKED\"", src), \
        "contradiction skip needs a debug-level one-line diagnostic"
    assert "3600" in src, "block diagnostic must be throttled (max 1/hour)"


# --- Item 2: B06 recalibration (calibration, not removal) ---

def test_uncertain_veto_recalibrated():
    src = read_source("Config.mqh")
    m = re.search(r"input\s+double\s+UncertainVeto\s*=\s*([0-9.]+)", src)
    assert m, "UncertainVeto input missing"
    assert float(m.group(1)) == 0.70, \
        "UncertainVeto must be recalibrated 0.55 -> 0.70 (got %s)" % m.group(1)


def test_uncertain_veto_logic_retained():
    src = read_source("RegimeFusion.mqh")
    assert len(re.findall(r"p\.uncertainVeto", src)) >= 2, \
        "soft-veto uses (bootstrap + incumbent) must remain — calibration, not removal"
    assert "RegimeHardUncertainVeto(o)" in src, "hard veto must remain"


def test_uncertain_exit_companions():
    src = read_source("Config.mqh")
    m = re.search(r"input\s+double\s+UncertainExitThreshold\s*=\s*([0-9.]+)", src)
    assert m and float(m.group(1)) == 0.35, "UncertainExitThreshold must be 0.35"


# --- Item 3: degenerate reward killed at source ---

def test_trend_evaluate_rejects_degenerate_reward():
    src = read_source("TrendStrategy.mqh")
    for fn in ("EvaluatePullback", "EvaluateBreakRetest", "EvaluateMomentum"):
        region = function_region(src, "bool CTrendStrategy::%s" % fn)
        assert "GetTargetPrice" in region, "%s must derive target from swings" % fn
        assert re.search(r"if\s*\(\s*rd\s*<=\s*0", region), \
            "%s must reject rd<=0 before valid=true" % fn
        valid_idx = region.find("cand.valid = true")
        guard = re.search(r"if\s*\(\s*rd\s*<=\s*0", region)
        assert valid_idx != -1 and guard and guard.start() < valid_idx, \
            "%s guard must sit before valid=true" % fn


def test_range_evaluate_rejects_degenerate_reward():
    src = read_source("RangeStrategy.mqh")
    region = function_region(src, "bool CRangeStrategy::Evaluate")
    assert len(re.findall(r"if\s*\(\s*rd\s*<=\s*0", region)) >= 2, \
        "both Range sweep paths must reject rd<=0 before valid=true"


def test_breakout_target_structurally_nondegenerate():
    src = read_source("BreakoutStrategy.mqh")
    assert "1.5 * sd" in src, \
        "Breakout tp=c+-1.5*sd with sd>0 strictly — degenerate shape impossible, guard skipped"
