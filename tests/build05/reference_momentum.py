from enum import Enum


class MOMENTUM(Enum):
    EXPANDING = 0
    STRONG = 1
    NORMAL = 2
    WEAK = 3
    DECAYING = 4


STRONG_THRESHOLD = 0.6
WEAK_THRESHOLD = 0.4
SLOPE_UP = 0.05
SLOPE_DOWN = -0.05
PERSISTENCE = 2


def momentum_enum(strength, slope, prev=MOMENTUM.NORMAL, persist=0):
    """Return the momentum state for one closed-H1 observation.

    strength: price-based momentum strength in [0, 1].
    slope:    momentumStrengthSlope in [-1, 1] (temporal change).

    EXPANDING vs STRONG and DECAYING vs WEAK are decided by the temporal
    slope, not absolute strength alone. ADX slope is helper-only and is not
    part of this function.
    """
    st = max(0.0, min(1.0, strength))
    sl = max(-1.0, min(1.0, slope))

    if st >= STRONG_THRESHOLD:
        cand = MOMENTUM.EXPANDING if sl >= SLOPE_UP else MOMENTUM.STRONG
    elif st >= WEAK_THRESHOLD:
        cand = MOMENTUM.NORMAL
    else:
        cand = MOMENTUM.DECAYING if sl <= SLOPE_DOWN else MOMENTUM.WEAK

    # state-specific persistence: only resist a *magnitude* drop out of the
    # high-momentum band (EXPANDING/STRONG -> NORMAL/WEAK/DECAYING). A slope
    # change within the same band (EXPANDING <-> STRONG) reclassifies immediately.
    high_band = (MOMENTUM.EXPANDING, MOMENTUM.STRONG)
    if prev in high_band and cand not in high_band:
        return prev if persist + 1 < PERSISTENCE else cand
    return cand


def momentum_result(strength, slope, adx_available=True):
    """Full result including validity and helper-degraded reporting.

    ADX is supporting evidence only; its absence must not invalidate an
    otherwise-valid price-based momentum.
    """
    if strength is None or slope is None:
        return {"valid": False, "state": MOMENTUM.NORMAL, "helper_degraded": None}
    degraded = None if adx_available else "adx"
    return {
        "valid": True,
        "state": momentum_enum(strength, slope),
        "helper_degraded": degraded,
    }
