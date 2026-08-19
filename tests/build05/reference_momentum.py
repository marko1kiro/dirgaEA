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
    if bars <= 0 or len(close_seq) < bars + 1:
        return 0.0
    net_directional = close_seq[-1] - close_seq[-(bars + 1)]
    path = sum(abs(close_seq[i] - close_seq[i - 1]) for i in range(len(close_seq) - bars, len(close_seq)))
    if path <= 0.0:
        return 0.0
    return abs(net_directional) / path


def brain_efficiency_signed(close_seq, bars):
    if bars <= 0 or len(close_seq) < bars + 1:
        return 0.0
    net_directional = close_seq[-1] - close_seq[-(bars + 1)]
    path = sum(abs(close_seq[i] - close_seq[i - 1]) for i in range(len(close_seq) - bars, len(close_seq)))
    if path <= 0.0:
        return 0.0
    return net_directional / path


def momentum_enum(strength, slope, prev=MOMENTUM.NORMAL, persist=None):
    if persist is None:
        persist = [0]
    elif not isinstance(persist, list):
        persist = [persist]

    st = max(0.0, min(1.0, strength))
    sl = max(-1.0, min(1.0, slope))

    if st >= STRONG_THRESHOLD:
        cand = MOMENTUM.EXPANDING if sl >= SLOPE_UP else MOMENTUM.STRONG
    elif st >= WEAK_THRESHOLD:
        cand = MOMENTUM.NORMAL
    else:
        cand = MOMENTUM.DECAYING if sl <= SLOPE_DOWN else MOMENTUM.WEAK

    high_band = (MOMENTUM.EXPANDING, MOMENTUM.STRONG)
    if prev in high_band and cand not in high_band:
        if persist[0] + 1 < PERSISTENCE:
            persist[0] += 1
            return prev
        else:
            persist[0] = 0
            return cand

    if prev in high_band:
        persist[0] = 0
    return cand


def momentum_result(strength, slope, adx_available=True):
    if strength is None or slope is None:
        return {"valid": False, "state": MOMENTUM.NORMAL, "helper_degraded": None}
    degraded = None if adx_available else "adx"
    return {
        "valid": True,
        "state": momentum_enum(strength, slope),
        "helper_degraded": degraded,
    }


def momentum_engine_direction_agnostic(rates, atr_last):
    if len(rates) < MOM_PROGRESSION_BARS + 1 or not (atr_last > 0.0):
        return None
    
    n = -1
    bar = rates[n]
    range_val = bar["high"] - bar["low"]
    body = abs(bar["close"] - bar["open"])
    body_atr = body / atr_last if atr_last > 0.0 else 0.0
    body_range = body / range_val if range_val > 0.0 else 0.0
    
    if bar["close"] >= bar["open"]:
        close_loc_strength = (bar["close"] - bar["low"]) / range_val if range_val > 0.0 else 0.5
    else:
        close_loc_strength = (bar["high"] - bar["close"]) / range_val if range_val > 0.0 else 0.5
    
    efficiency_magnitude = brain_efficiency_magnitude([r["close"] for r in rates], MOM_PROGRESSION_BARS)
    
    signed_progression = sum((rates[i]["close"] - rates[i]["open"]) / atr_last 
                             for i in range(-MOM_PROGRESSION_BARS, 0)) / MOM_PROGRESSION_BARS
    progression_strength = abs(brain_tanh(signed_progression))
    
    raw = (0.25 * brain_clamp_unit(body_atr)
         + 0.25 * brain_clamp_unit(body_range)
         + 0.20 * brain_clamp_unit(close_loc_strength)
         + 0.15 * brain_clamp_unit(progression_strength)
         + 0.15 * brain_clamp_unit(efficiency_magnitude))
    
    efficiency_signed = brain_efficiency_signed([r["close"] for r in rates], MOM_PROGRESSION_BARS)
    directional_alignment = brain_clamp_signed(0.5 * brain_tanh(signed_progression) + 0.5 * efficiency_signed)
    
    return {
        "strength": brain_clamp_unit(raw),
        "directionalAlignment": directional_alignment
    }
