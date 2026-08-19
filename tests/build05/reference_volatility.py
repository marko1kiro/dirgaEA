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


def volatility_level_enum(ratio, prev=VOL_LEVEL.NORMAL, dwell=0,
                          challenger=None, challenger_dwell=0):
    """Return (state, dwell_count, challenger, challenger_dwell) for one ATR-ratio observation.

    Challenger dwell tracks consecutive escalation bars for the same challenger.
    """
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


def quality_enum(evidence, incumbent=(VOL_QUALITY.HEALTHY, 0.0, 0),
                 incumbent_state=None, incumbent_conf=None, incumbent_dwell=None,
                 challenger=None, challenger_dwell=0):
    """Non-ordinal evidence-max selection with challenger-dwell persistence.

    evidence: dict with keys healthy, compression, expansion, chaos, shock.
    incumbent: (state, confidence, dwell_count) — legacy tuple form.
    Or use explicit kwargs: incumbent_state, incumbent_conf, incumbent_dwell.
    challenger / challenger_dwell track the pending escalation candidate.
    Returns: (state, confidence, challenger, challenger_dwell).
    """
    candidates = {
        VOL_QUALITY.HEALTHY: evidence.get("healthy", 0.0),
        VOL_QUALITY.COMPRESSED: evidence.get("compression", 0.0),
        VOL_QUALITY.EXPANDING: evidence.get("expansion", 0.0),
        VOL_QUALITY.CHAOTIC: evidence.get("chaos", 0.0),
        VOL_QUALITY.SHOCK: evidence.get("shock", 0.0),
    }
    best = max(candidates, key=candidates.get)

    # Unpack incumbent from either form
    if incumbent_state is not None:
        inc_state = incumbent_state
        inc_conf = incumbent_conf if incumbent_conf is not None else 0.0
        inc_dwell = incumbent_dwell if incumbent_dwell is not None else 0
    else:
        inc_state, inc_conf, inc_dwell = incumbent

    # No established incumbent → pure evidence-max
    if inc_conf <= 0.0 and inc_dwell == 0 and challenger is None:
        return (best, candidates[best], best, 0)

    if best == inc_state:
        # Incumbent holds — clear challenger
        return (best, candidates[best], best, 0)

    # best != incumbent
    gap = candidates[best] - inc_conf
    if gap < QUALITY_GAP:
        # Insufficient advantage — retain incumbent, clear challenger
        return (inc_state, inc_conf, inc_state, 0)

    # Sufficient gap — challenger dwell logic
    if best == challenger:
        new_dwell = challenger_dwell + 1
    else:
        new_dwell = 1
        challenger = best

    if new_dwell >= QUALITY_DWELL:
        # Commit challenger
        return (best, candidates[best], best, 0)

    # Hold incumbent, challenger pending
    return (inc_state, inc_conf, challenger, new_dwell)


# ---------------------------------------------------------------------------
# Evidence computation
# ---------------------------------------------------------------------------

def _mean(vals):
    return sum(vals) / len(vals) if vals else 0.0


def _clamp01(v):
    return max(0.0, min(1.0, v))


def _shrink_evidence(recent_avg, prior_avg):
    """[0,1] where 1 = fully shrunk. prior_avg must be > 0."""
    if prior_avg <= 0.0:
        return 0.0
    return _clamp01(1.0 - recent_avg / prior_avg)


def _expand_evidence(recent_avg, prior_avg):
    """[0,1] where 1 = fully expanded. prior_avg must be > 0."""
    if prior_avg <= 0.0:
        return 0.0
    return _clamp01(recent_avg / prior_avg - 1.0)


def compute_compression_score(atr_recent, atr_prior,
                              range_recent, range_prior,
                              body_recent, body_prior):
    """Compression = mean(atrDecline, rangeShrink, bodyShrink).

    Each component [0,1]. Returns [0,1].
    """
    atr_decline = _clamp01(_mean([(p - r) / p if p > 0 else 0.0
                                   for r, p in zip(atr_recent, atr_prior)]))
    range_shrink = _shrink_evidence(_mean(range_recent), _mean(range_prior))
    body_shrink = _shrink_evidence(_mean(body_recent), _mean(body_prior))
    return _clamp01(_mean([atr_decline, range_shrink, body_shrink]))


def compute_expansion_score(atr_recent, atr_prior,
                            range_recent, range_prior,
                            body_recent, body_prior,
                            eff_recent, eff_prior,
                            disp_recent, disp_prior):
    """Expansion = mean(atrRise, rangeExpand, bodyExpand, effRise, dispRise).

    Each component [0,1]. Returns [0,1].
    """
    atr_rise = _clamp01(_mean([(r - p) / p if p > 0 else 0.0
                                for r, p in zip(atr_recent, atr_prior)]))
    range_expand = _expand_evidence(_mean(range_recent), _mean(range_prior))
    body_expand = _expand_evidence(_mean(body_recent), _mean(body_prior))
    eff_rise = _expand_evidence(_mean(eff_recent), _mean(eff_prior))
    disp_rise = _expand_evidence(_mean(disp_recent), _mean(disp_prior))
    return _clamp01(_mean([atr_rise, range_expand, body_expand, eff_rise, disp_rise]))


def compute_quality_evidence(bars, atr):
    """Compute all five quality evidence scores from OHLC + ATR arrays.

    Returns dict: healthy, compression, expansion, chaos, shock.
    Each value [0,1], no NaN/INF.
    """
    if len(bars) < 3:
        return dict(healthy=0.0, compression=0.0, expansion=0.0, chaos=0.0, shock=0.0)

    n = len(bars) - 1
    bar = bars[n]
    rng = bar["high"] - bar["low"]
    if rng <= 0.0 or atr[n] <= 0.0:
        return dict(healthy=0.0, compression=0.0, expansion=0.0, chaos=0.0, shock=0.0)

    body = abs(bar["close"] - bar["open"])
    body_atr = body / atr[n] if atr[n] > 0.0 else 0.0
    body_range = body / rng if rng > 0.0 else 0.0
    wick = (rng - body) / rng if rng > 0.0 else 0.0

    # Efficiency magnitude
    if len(bars) >= BRAIN_DISPLACEMENT_BARS + 1:
        closes = [b["close"] for b in bars]
        net_dir = closes[-1] - closes[-(BRAIN_DISPLACEMENT_BARS + 1)]
        path = sum(abs(closes[i] - closes[i - 1])
                    for i in range(len(closes) - BRAIN_DISPLACEMENT_BARS, len(closes)))
        efficiency = abs(net_dir) / path if path > 0.0 else 0.0
    else:
        efficiency = 0.0

    # ATR trend
    half = min(5, len(atr) // 2)
    if half < 1:
        half = 1
    recent_atr = atr[-half:]
    prior_atr = atr[-2 * half:-half] if len(atr) >= 2 * half else atr[:half]
    recent_avg = _mean(recent_atr)
    prior_avg = _mean(prior_atr)
    atr_trend = (recent_avg - prior_avg) / prior_avg if prior_avg > 0.0 else 0.0

    # Five evidence scores
    healthy = _clamp01(efficiency)
    compression = _clamp01(-atr_trend)
    expansion = _clamp01(atr_trend)
    chaos = _clamp01(wick) * (1.0 - efficiency)
    shock = _clamp01(atr_trend) * _clamp01(abs(atr_trend))

    return dict(healthy=healthy, compression=compression, expansion=expansion,
                chaos=chaos, shock=shock)


BRAIN_DISPLACEMENT_BARS = 20
