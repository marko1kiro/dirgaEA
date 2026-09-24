"""BUILD 17 B06 regime emission fix — source invariants for argmax starvation.

Diagnosis (RegimeFusion.mqh): on fresh-break bars the same directional
structure that enables the break also feeds TREND (0.35*S + full Q_clean),
while BREAKOUT's 0.30*S plus prior-only compression context (~0 in real data,
memory mean ~0.1) caps realistic BO at ~0.45 and loses argmax to TREND on the
same bar. Veto 0.55->0.70 was digit-identical: starvation is argmax, not veto.

Fix: move 0.10 weight from prior-only Q_compressionContext (0.25->0.15) to the
fresh structural break event S_break (0.30->0.40). Sum stays 1.0; M/D/V, TREND,
RANGE, veto, dwell, guards untouched.
"""

import os
import re

SOURCE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read_source(name):
    path = os.path.join(SOURCE_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def define_value(src, name):
    m = re.search(r"#define\s+%s\s+([0-9.]+)" % name, src)
    assert m, "%s define missing" % name
    return float(m.group(1))


# --- Emission fix: BREAKOUT weight shift S 0.30->0.40, Q 0.25->0.15 ---

def test_breakout_structure_weight_recalibrated():
    src = read_source("RegimeFusion.mqh")
    assert define_value(src, "REGIME_W_BREAK_S") == 0.40, \
        "BREAKOUT S_break must be 0.40 (fresh break is the defining event)"


def test_breakout_context_weight_reduced():
    src = read_source("RegimeFusion.mqh")
    assert define_value(src, "REGIME_W_BREAK_Q") == 0.15, \
        "BREAKOUT Q_context must be 0.15 (prior-only context absent on real bars)"


def test_breakout_weights_still_convex():
    src = read_source("RegimeFusion.mqh")
    total = sum(define_value(src, n) for n in (
        "REGIME_W_BREAK_S", "REGIME_W_BREAK_Q", "REGIME_W_BREAK_M",
        "REGIME_W_BREAK_D", "REGIME_W_BREAK_V"))
    assert abs(total - 1.0) < 1e-12, "BREAKOUT weights must sum to 1.0, got %s" % total


def test_breakout_momentum_direction_expansion_weights_untouched():
    src = read_source("RegimeFusion.mqh")
    assert define_value(src, "REGIME_W_BREAK_M") == 0.20
    assert define_value(src, "REGIME_W_BREAK_D") == 0.15
    assert define_value(src, "REGIME_W_BREAK_V") == 0.10


def test_trend_range_weights_untouched():
    src = read_source("RegimeFusion.mqh")
    for name, want in (("REGIME_W_TREND_S", 0.35), ("REGIME_W_TREND_D", 0.30),
                       ("REGIME_W_TREND_M", 0.15), ("REGIME_W_TREND_V", 0.10),
                       ("REGIME_W_TREND_Q", 0.10), ("REGIME_W_RANGE_S", 0.40),
                       ("REGIME_W_RANGE_D", 0.25), ("REGIME_W_RANGE_M", 0.15),
                       ("REGIME_W_RANGE_V", 0.10), ("REGIME_W_RANGE_Q", 0.10)):
        assert define_value(src, name) == want, "%s must stay %s" % (name, want)


def test_stable_trend_eligibility_stripping_retained():
    src = read_source("RegimeFusion.mqh")
    assert "eligible.breakoutBull = -1.0" in src, "stable-bull BO strip must remain"
    assert "eligible.breakoutBear = -1.0" in src, "stable-bear BO strip must remain"


# --- Lock the forbidden knob: veto/dwell/gap values unchanged ---

def test_veto_values_locked():
    src = read_source("Config.mqh")
    m = re.search(r"input\s+double\s+UncertainVeto\s*=\s*([0-9.]+)", src)
    assert m and float(m.group(1)) == 0.70, "UncertainVeto must stay 0.70"
    m = re.search(r"input\s+double\s+UncertainExitThreshold\s*=\s*([0-9.]+)", src)
    assert m and float(m.group(1)) == 0.35, "UncertainExitThreshold must stay 0.35"


def test_veto_logic_retained():
    src = read_source("RegimeFusion.mqh")
    assert len(re.findall(r"p\.uncertainVeto", src)) >= 2, "soft-veto uses must remain"
    assert "RegimeHardUncertainVeto(o)" in src, "hard veto must remain"


# --- Fresh-break delta: +0.09 vs old weights on recency=1.0, context~0.1 ---

def test_fresh_break_delta_plus_009():
    src = read_source("RegimeFusion.mqh")
    w_s = define_value(src, "REGIME_W_BREAK_S")
    w_q = define_value(src, "REGIME_W_BREAK_Q")
    assert w_s == 0.40 and w_q == 0.15
    assert abs((w_s - 0.30) * 1.0 + (w_q - 0.25) * 0.1 - 0.09) < 1e-12


# --- Lock gap/dwell values against silent drift ---

def test_challenger_gap_dwell_locked():
    src = read_source("Config.mqh")
    m = re.search(r"input\s+double\s+ChallengerGap\s*=\s*([0-9.]+)", src)
    assert m and float(m.group(1)) == 0.10, "ChallengerGap must stay 0.10"
    m = re.search(r"input\s+int\s+RegimeDwell\s*=\s*([0-9]+)", src)
    assert m and int(m.group(1)) == 2, "RegimeDwell must stay 2"
