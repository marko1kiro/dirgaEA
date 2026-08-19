from enum import Enum
import math


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
MOM_PROGRESSION_BARS = 5


def brain_clamp_unit(v):
    return max(0.0, min(1.0, v))


def brain_clamp_signed(v):
    return max(-1.0, min(1.0, v))


def brain_tanh(v):
    e = math.exp(-2.0 * v)
    if not math.isfinite(e):
        return 1.0 if v >= 0.0 else -1.0
    return (1.0 - e) / (1.0 + e)


def brain_efficiency_magnitude(close_seq, bars):
    """Path efficiency magnitude for Momentum domain: |netDirectional|/path (unsigned [0,1])."""
    if bars <= 0 or len(close_seq) < bars + 1:
        return 0.0
    net_directional = close_seq[-1] - close_seq[-(bars + 1)]
    path = sum(abs(close_seq[i] - close_seq[i - 1]) for i in range(len(close_seq) - bars, len(close_seq)))
    if path <= 0.0:
        return 0.0
    return abs(net_directional) / path


def brain_efficiency_signed(close_seq, bars):
    """Signed directional efficiency for Direction domain: netDirectional/path (signed [-1,+1])."""
    if bars <= 0 or len(close_seq) < bars + 1:
        return 0.0
    net_directional = close_seq[-1] - close_seq[-(bars + 1)]
    path = sum(abs(close_seq[i] - close_seq[i - 1]) for i in range(len(close_seq) - bars, len(close_seq)))
    if path <= 0.0:
        return 0.0
    return net_directional / path


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


def momentum_engine_current_buggy(rates, atr_last):
    """
    CURRENT BUGGY momentum strength calculation.
    
    Bugs:
    1. closeLoc = (close - low) / range — biased toward bullish closes
    2. progression = avg((close-open)/ATR) — signed, used through tanh
    3. These create direction bias even with efficiency magnitude fixed
    """
    if len(rates) < MOM_PROGRESSION_BARS + 1 or not (atr_last > 0.0):
        return None
    
    n = -1
    bar = rates[n]
    range_val = bar["high"] - bar["low"]
    body = abs(bar["close"] - bar["open"])
    body_atr = body / atr_last if atr_last > 0.0 else 0.0
    body_range = body / range_val if range_val > 0.0 else 0.0
    
    # BUG: closeLoc biased toward bullish
    close_loc = (bar["close"] - bar["low"]) / range_val if range_val > 0.0 else 0.5
    
    efficiency = brain_efficiency_magnitude([r["close"] for r in rates], MOM_PROGRESSION_BARS)
    
    # BUG: signed progression
    progression = sum((rates[i]["close"] - rates[i]["open"]) / atr_last 
                      for i in range(-MOM_PROGRESSION_BARS, 0)) / MOM_PROGRESSION_BARS
    
    raw = (0.25 * brain_clamp_unit(body_atr)
         + 0.25 * brain_clamp_unit(body_range)
         + 0.20 * brain_clamp_unit(close_loc)
         + 0.15 * brain_clamp_unit(0.5 + 0.5 * brain_tanh(progression))
         + 0.15 * brain_clamp_unit(efficiency))
    
    return {
        "strength": brain_clamp_unit(raw),
        "directionalAlignment": brain_clamp_signed(brain_tanh(progression))
    }


def momentum_engine_direction_agnostic(rates, atr_last):
    """
    DIRECTION-AGNOSTIC momentum strength calculation.
    
    Locked semantic:
    - closeLocStrength: distance from close to opposite extreme (direction-agnostic)
    - progressionStrength: |tanh(signedProgression)| (magnitude only)
    - efficiencyMagnitude: |netDirectional|/path (unsigned)
    """
    if len(rates) < MOM_PROGRESSION_BARS + 1 or not (atr_last > 0.0):
        return None
    
    n = -1
    bar = rates[n]
    range_val = bar["high"] - bar["low"]
    body = abs(bar["close"] - bar["open"])
    body_atr = body / atr_last if atr_last > 0.0 else 0.0
    body_range = body / range_val if range_val > 0.0 else 0.0
    
    # FIXED: directional-close-strength
    # Bullish close near high → (close - low) / range (large)
    # Bearish close near low → (high - close) / range (large)
    if bar["close"] >= bar["open"]:
        close_loc_strength = (bar["close"] - bar["low"]) / range_val if range_val > 0.0 else 0.5
    else:
        close_loc_strength = (bar["high"] - bar["close"]) / range_val if range_val > 0.0 else 0.5
    
    efficiency_magnitude = brain_efficiency_magnitude([r["close"] for r in rates], MOM_PROGRESSION_BARS)
    
    # FIXED: signed progression for diagnostic, magnitude for strength
    signed_progression = sum((rates[i]["close"] - rates[i]["open"]) / atr_last 
                             for i in range(-MOM_PROGRESSION_BARS, 0)) / MOM_PROGRESSION_BARS
    progression_strength = abs(brain_tanh(signed_progression))
    
    raw = (0.25 * brain_clamp_unit(body_atr)
         + 0.25 * brain_clamp_unit(body_range)
         + 0.20 * brain_clamp_unit(close_loc_strength)
         + 0.15 * brain_clamp_unit(progression_strength)
         + 0.15 * brain_clamp_unit(efficiency_magnitude))
    
    return {
        "strength": brain_clamp_unit(raw),
        "directionalAlignment": brain_clamp_signed(brain_tanh(signed_progression))
    }
