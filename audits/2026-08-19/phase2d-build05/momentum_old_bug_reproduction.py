"""
ARCHIVED: Old bug reproduction test (moved from pytest collection).

This file documents the pre-fix momentum direction bias bug.
It is NOT a pytest test file and will not be collected by pytest.

Historical evidence:
- test_MOMENTUM_current_buggy_direction_bias_proven FAILED
- Bull strength=0.8081, Bear strength=0.5752 (bias 0.23)
- This proved the bug existed before the direction-agnostic fix.

The bug was fixed in commit 009c37a173cca1e16e700ec69664194ede9efb37.
"""

from enum import Enum
import math


class MOMENTUM(Enum):
    EXPANDING = 0
    STRONG = 1
    NORMAL = 2
    WEAK = 3
    DECAYING = 4


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


def make_mirrored_ohlc_bars(base_price, bar_count, direction, body_size=0.8):
    bars = []
    for i in range(bar_count):
        if direction == "bull":
            open_price = base_price + i * body_size
            close_price = base_price + (i + 1) * body_size
            low = open_price - 0.2
            high = close_price + 0.2
        else:
            open_price = base_price - i * body_size
            close_price = base_price - (i + 1) * body_size
            low = close_price - 0.2
            high = open_price + 0.2
        
        bars.append({
            "open": open_price,
            "high": high,
            "low": low,
            "close": close_price,
        })
    
    return bars


def reproduce_bug():
    atr = 1.0
    base = 100.0
    
    bull_bars = make_mirrored_ohlc_bars(base, 6, "bull")
    bear_bars = make_mirrored_ohlc_bars(base, 6, "bear")
    
    bull_result = momentum_engine_current_buggy(bull_bars, atr)
    bear_result = momentum_engine_current_buggy(bear_bars, atr)
    
    print("=" * 60)
    print("MOMENTUM DIRECTION BIAS BUG REPRODUCTION")
    print("=" * 60)
    print()
    print("Using BUGGY momentum engine (pre-fix):")
    print()
    print("  Bull strength: %.4f" % bull_result["strength"])
    print("  Bear strength: %.4f" % bear_result["strength"])
    print("  Bias:          %.4f" % abs(bull_result["strength"] - bear_result["strength"]))
    print()
    print("EXPECTED: Equal strength for mirrored sequences")
    print("ACTUAL:   %.2f%% directional bias" % (abs(bull_result["strength"] - bear_result["strength"]) * 100))
    print()
    print("This bug was fixed in commit 009c37a173cca1e16e700ec69664194ede9efb37")
    print("=" * 60)


if __name__ == "__main__":
    reproduce_bug()
