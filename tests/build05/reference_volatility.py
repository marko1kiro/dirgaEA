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


def quality_enum(evidence, incumbent=(VOL_QUALITY.HEALTHY, 0.0, 0)):
    """Non-ordinal evidence-max selection with candidate-confidence persistence.

    evidence: dict with keys healthy, compression, expansion, chaos, shock.
    incumbent: (state, confidence, dwell_count) of the current committed state.
    """
    candidates = {
        VOL_QUALITY.HEALTHY: evidence.get("healthy", 0.0),
        VOL_QUALITY.COMPRESSED: evidence.get("compression", 0.0),
        VOL_QUALITY.EXPANDING: evidence.get("expansion", 0.0),
        VOL_QUALITY.CHAOTIC: evidence.get("chaos", 0.0),
        VOL_QUALITY.SHOCK: evidence.get("shock", 0.0),
    }
    best = max(candidates, key=candidates.get)
    inc_state, inc_conf, inc_dwell = incumbent

    # no established incumbent => pure evidence-max (no persistence)
    if inc_conf <= 0.0 and inc_dwell == 0:
        return best

    if best != inc_state:
        if candidates[best] - inc_conf < QUALITY_GAP:
            return inc_state
        if inc_dwell + 1 < QUALITY_DWELL:
            return inc_state

    return best
