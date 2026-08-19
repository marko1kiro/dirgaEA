from enum import Enum


class VOL_LEVEL(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    EXTREME = 3


class VOL_QUALITY(Enum):
    HEALTHY = 0
    COMPRESSED = 1
    EXPANDING = 2
    CHAOTIC = 3
    SHOCK = 4


HIGH_RATIO = 1.5
EXTREME_RATIO = 2.0
LOW_RATIO = 0.7
LEVEL_DWELL = 2

QUALITY_GAP = 0.10
QUALITY_DWELL = 2

BRAIN_DISPLACEMENT_BARS = 20
VOLQUALITY_MIN_BARS = 2 * BRAIN_DISPLACEMENT_BARS + 1  # 41


def volatility_level_enum(ratio, prev=VOL_LEVEL.NORMAL, dwell=0,
                          challenger=None, challenger_dwell=0):
    if ratio >= EXTREME_RATIO:
        cand = VOL_LEVEL.EXTREME
    elif ratio >= HIGH_RATIO:
        cand = VOL_LEVEL.HIGH
    elif ratio <= LOW_RATIO:
        cand = VOL_LEVEL.LOW
    else:
        cand = VOL_LEVEL.NORMAL

    if cand == prev:
        return (cand, min(dwell + 1, LEVEL_DWELL), cand, 0)

    if abs(cand.value - 1) > abs(prev.value - 1):
        if cand == challenger:
            challenger_dwell += 1
        else:
            challenger = cand
            challenger_dwell = 1
        if challenger_dwell >= LEVEL_DWELL:
            return (cand, 0, cand, 0)
        return (prev, dwell, challenger, challenger_dwell)

    return (cand, 0, cand, 0)


def quality_enum(evidence, incumbent_state=VOL_QUALITY.HEALTHY,
                 primed=False,
                 challenger=None, challenger_dwell=0):
    """Evidence-max with challenger-dwell persistence and explicit primed state.

    Uses current-bar evidence for gap (not stale confidence).
    Returns: (state, confidence, primed, challenger, challenger_dwell).
    """
    candidates = {
        VOL_QUALITY.HEALTHY: evidence.get("healthy", 0.0),
        VOL_QUALITY.COMPRESSED: evidence.get("compression", 0.0),
        VOL_QUALITY.EXPANDING: evidence.get("expansion", 0.0),
        VOL_QUALITY.CHAOTIC: evidence.get("chaos", 0.0),
        VOL_QUALITY.SHOCK: evidence.get("shock", 0.0),
    }
    best = max(candidates, key=candidates.get)

    # Not yet primed → pure evidence-max, commit immediately
    if not primed:
        return (best, candidates[best], True, best, 0)

    # best == incumbent
    if best == incumbent_state:
        return (best, candidates[best], True, best, 0)

    # best != incumbent — gap uses CURRENT BAR evidence for both states
    current_inc_evidence = candidates[incumbent_state]
    current_best_evidence = candidates[best]
    gap = current_best_evidence - current_inc_evidence
    if gap < QUALITY_GAP:
        # Insufficient advantage — retain incumbent
        return (incumbent_state, current_inc_evidence, True, incumbent_state, 0)

    # Sufficient gap — challenger dwell logic
    if best == challenger:
        new_dwell = challenger_dwell + 1
    else:
        new_dwell = 1
        challenger = best

    if new_dwell >= QUALITY_DWELL:
        # Commit challenger
        return (best, current_best_evidence, True, best, 0)

    # Hold incumbent, challenger pending
    return (incumbent_state, current_inc_evidence, True, challenger, new_dwell)


# ---------------------------------------------------------------------------
# Evidence computation helpers
# ---------------------------------------------------------------------------

def _clamp01(v):
    return max(0.0, min(1.0, v))


def _mean(vals):
    return sum(vals) / len(vals) if vals else 0.0


def _shrink_evidence(recent_avg, prior_avg):
    if prior_avg <= 0.0:
        return 0.0
    return _clamp01(1.0 - recent_avg / prior_avg)


def _expand_evidence(recent_avg, prior_avg):
    if prior_avg <= 0.0:
        return 0.0
    return _clamp01(recent_avg / prior_avg - 1.0)


def compute_compression_score(atr_recent, atr_prior,
                              range_recent, range_prior,
                              body_recent, body_prior):
    """Compression = mean(atrDecline, rangeShrink, bodyShrink).

    atrDecline = clamp01((priorAvg - recentAvg) / priorAvg) — relative change of means.
    Each component [0,1]. Returns [0,1].
    """
    prior_avg = _mean(atr_prior)
    recent_avg = _mean(atr_recent)
    atr_decline = _clamp01((prior_avg - recent_avg) / prior_avg) if prior_avg > 0.0 else 0.0
    range_shrink = _shrink_evidence(_mean(range_recent), _mean(range_prior))
    body_shrink = _shrink_evidence(_mean(body_recent), _mean(body_prior))
    return _clamp01(_mean([atr_decline, range_shrink, body_shrink]))


def compute_expansion_score(atr_recent, atr_prior,
                            range_recent, range_prior,
                            body_recent, body_prior,
                            eff_rise_scalar, disp_rise_scalar):
    """Expansion = mean(atrRise, rangeExpand, bodyExpand, effRise, dispRise).

    atrRise = clamp01((recentAvg - priorAvg) / priorAvg) — relative change of means.
    eff_rise_scalar and disp_rise_scalar are pre-computed [0,1] values.
    Each component [0,1]. Returns [0,1].
    """
    prior_avg = _mean(atr_prior)
    recent_avg = _mean(atr_recent)
    atr_rise = _clamp01((recent_avg - prior_avg) / prior_avg) if prior_avg > 0.0 else 0.0
    range_expand = _expand_evidence(_mean(range_recent), _mean(range_prior))
    body_expand = _expand_evidence(_mean(body_recent), _mean(body_prior))
    return _clamp01(_mean([atr_rise, range_expand, body_expand, eff_rise_scalar, disp_rise_scalar]))


def _efficiency_magnitude(bars):
    """Efficiency = |netMove| / totalPath over BRAIN_DISPLACEMENT_BARS."""
    n = len(bars) - 1
    if n < BRAIN_DISPLACEMENT_BARS:
        return 0.0
    closes = [b["close"] for b in bars]
    net = closes[-1] - closes[-(BRAIN_DISPLACEMENT_BARS + 1)]
    path = sum(abs(closes[i] - closes[i - 1])
               for i in range(len(closes) - BRAIN_DISPLACEMENT_BARS, len(closes)))
    return abs(net) / path if path > 0.0 else 0.0


def _efficiency_window(bars, start_idx, end_idx):
    """Efficiency magnitude for a window of bars."""
    if end_idx < BRAIN_DISPLACEMENT_BARS:
        return 0.0
    closes = [b["close"] for b in bars[start_idx:end_idx + 1]]
    if len(closes) < BRAIN_DISPLACEMENT_BARS + 1:
        return 0.0
    net = closes[-1] - closes[-(BRAIN_DISPLACEMENT_BARS + 1)]
    path = sum(abs(closes[i] - closes[i - 1])
               for i in range(len(closes) - BRAIN_DISPLACEMENT_BARS, len(closes)))
    return abs(net) / path if path > 0.0 else 0.0


def _displacement_magnitude(bars, atr_avg, end_idx):
    """Displacement = |netMove| / ATR over BRAIN_DISPLACEMENT_BARS."""
    if end_idx < BRAIN_DISPLACEMENT_BARS:
        return 0.0
    closes = [b["close"] for b in bars]
    net = closes[end_idx] - closes[end_idx - BRAIN_DISPLACEMENT_BARS]
    return abs(net) / atr_avg if atr_avg > 0.0 else 0.0


def compute_quality_evidence(bars, atr):
    """Full MQL5-matching quality evidence computation.

    Returns dict: healthy, compression, expansion, chaos, shock.
    Each value [0,1], no NaN/INF.
    """
    if len(bars) < VOLQUALITY_MIN_BARS:
        return dict(healthy=0.0, compression=0.0, expansion=0.0, chaos=0.0, shock=0.0)

    n = len(bars) - 1
    bar = bars[n]
    rng = bar["high"] - bar["low"]
    if rng <= 0.0 or atr[n] <= 0.0:
        return dict(healthy=0.0, compression=0.0, expansion=0.0, chaos=0.0, shock=0.0)

    body = abs(bar["close"] - bar["open"])
    wick = (rng - body) / rng if rng > 0.0 else 0.0
    efficiency = _efficiency_magnitude(bars)

    # --- Compression: mean(atrDecline, rangeShrink, bodyShrink) ---
    # Uses W-bar windows (BRAIN_DISPLACEMENT_BARS = 20) for all components.
    half = BRAIN_DISPLACEMENT_BARS

    recent_slice = slice(-half, None)
    prior_slice = slice(-2 * half, -half) if len(atr) >= 2 * half else slice(0, half)

    recent_atr = list(atr[recent_slice])
    prior_atr = list(atr[prior_slice])
    recent_range = [bars[i]["high"] - bars[i]["low"] for i in range(len(bars) - half, len(bars))]
    prior_range = [bars[i]["high"] - bars[i]["low"]
                   for i in range(max(0, len(bars) - 2 * half), len(bars) - half)]
    recent_body = [abs(bars[i]["close"] - bars[i]["open"])
                   for i in range(len(bars) - half, len(bars))]
    prior_body = [abs(bars[i]["close"] - bars[i]["open"])
                  for i in range(max(0, len(bars) - 2 * half), len(bars) - half)]

    recent_atr_avg = _mean(recent_atr)
    prior_atr_avg = _mean(prior_atr)
    recent_range_avg = _mean(recent_range)
    prior_range_avg = _mean(prior_range)
    recent_body_avg = _mean(recent_body)
    prior_body_avg = _mean(prior_body)

    atr_decline = _clamp01((prior_atr_avg - recent_atr_avg) / prior_atr_avg) if prior_atr_avg > 0.0 else 0.0
    range_shrink = _shrink_evidence(recent_range_avg, prior_range_avg)
    body_shrink = _shrink_evidence(recent_body_avg, prior_body_avg)
    compression = _clamp01(_mean([atr_decline, range_shrink, body_shrink]))

    # --- Expansion: mean(atrRise, rangeExpand, bodyExpand, effRise, dispRise) ---
    atr_rise = _clamp01((recent_atr_avg - prior_atr_avg) / prior_atr_avg) if prior_atr_avg > 0.0 else 0.0
    range_expand = _expand_evidence(recent_range_avg, prior_range_avg)
    body_expand = _expand_evidence(recent_body_avg, prior_body_avg)

    # Efficiency magnitude — recent vs prior windows (W=20 bars each)
    W = BRAIN_DISPLACEMENT_BARS
    if len(bars) >= 2 * W + 1:
        # Recent window: bars[n-W .. n] → W+1 closes → W path diffs
        eff_recent = _efficiency_window(bars, n - W, n)
        # Prior window: bars[n-2W .. n-W] → W+1 closes → W path diffs
        eff_prior = _efficiency_window(bars, n - 2 * W, n - W)
    else:
        eff_recent = 0.0
        eff_prior = 0.0
    eff_rise = _expand_evidence(eff_recent, eff_prior)

    # Displacement magnitude — recent vs prior: |netMove| / endpoint ATR
    if len(bars) >= BRAIN_DISPLACEMENT_BARS + 1:
        net_recent = bars[n]["close"] - bars[n - BRAIN_DISPLACEMENT_BARS]["close"]
        disp_recent = abs(net_recent) / atr[n] if atr[n] > 0.0 else 0.0
        p_end = len(bars) - BRAIN_DISPLACEMENT_BARS - 1
        if p_end >= BRAIN_DISPLACEMENT_BARS:
            net_prior = bars[p_end]["close"] - bars[p_end - BRAIN_DISPLACEMENT_BARS]["close"]
            disp_prior = abs(net_prior) / atr[p_end] if atr[p_end] > 0.0 else 0.0
        else:
            disp_prior = 0.0
    else:
        disp_recent = 0.0
        disp_prior = 0.0
    disp_rise = _expand_evidence(disp_recent, disp_prior)

    expansion = _clamp01(_mean([atr_rise, range_expand, body_expand, eff_rise, disp_rise]))

    # --- Five evidence scores ---
    healthy = _clamp01(efficiency)
    chaos = _clamp01(wick) * (1.0 - efficiency)
    shock = _clamp01(atr_rise) * _clamp01(abs(atr_rise))

    return dict(healthy=healthy, compression=compression, expansion=expansion,
                chaos=chaos, shock=shock)
