import pytest
import math


def brain_tanh(v):
    e = math.exp(-2.0 * v)
    if not math.isfinite(e):
        return 1.0 if v >= 0.0 else -1.0
    return (1.0 - e) / (1.0 + e)


def brain_clamp_signed(v):
    return max(-1.0, min(1.0, v))


def brain_clamp_unit(v):
    return max(0.0, min(1.0, v))


def brain_displacement(close_seq, atr_last, bars):
    if bars <= 0 or len(close_seq) < bars + 1:
        return 0.0
    if not (atr_last > 0.0):
        return 0.0
    return (close_seq[-1] - close_seq[-(bars + 1)]) / atr_last


def brain_efficiency(close_seq, bars):
    if bars <= 0 or len(close_seq) < bars + 1:
        return 0.0
    net_directional = close_seq[-1] - close_seq[-(bars + 1)]
    path = 0.0
    for i in range(len(close_seq) - bars, len(close_seq)):
        path += abs(close_seq[i] - close_seq[i - 1])
    if path <= 0.0:
        return 0.0
    return net_directional / path


def direction_score(close_seq, ema_fast_seq, ema_slow_seq, atr_last, bars=20):
    if len(close_seq) < 3 or len(ema_fast_seq) < 3 or len(ema_slow_seq) < 3:
        return None
    if not (atr_last > 0.0):
        return None

    slope_fast = (ema_fast_seq[-1] - ema_fast_seq[-3]) / atr_last
    slope_slow = (ema_slow_seq[-1] - ema_slow_seq[-3]) / atr_last
    displacement = brain_displacement(close_seq, atr_last, bars)
    efficiency = brain_efficiency(close_seq, bars)
    
    positioning = (1.0 if close_seq[-1] > ema_fast_seq[-1] else -1.0) * 0.5 \
                + (1.0 if close_seq[-1] > ema_slow_seq[-1] else -1.0) * 0.5

    raw = (0.30 * brain_tanh(slope_fast)
         + 0.25 * brain_tanh(slope_slow)
         + 0.15 * brain_clamp_signed(positioning)
         + 0.15 * brain_tanh(displacement)
         + 0.15 * brain_clamp_signed(efficiency))

    return brain_clamp_signed(raw)


def test_B05_FR1_mirrored_bullish_bearish_equal_magnitude_opposite_sign():
    base = 100.0
    atr = 1.0
    bars = 20

    bull_close = [base + i * 0.5 for i in range(bars + 1)]
    bear_close = [base - i * 0.5 for i in range(bars + 1)]

    ema_fast_bull = [base + i * 0.4 for i in range(3)]
    ema_slow_bull = [base + i * 0.3 for i in range(3)]
    ema_fast_bear = [base - i * 0.4 for i in range(3)]
    ema_slow_bear = [base - i * 0.3 for i in range(3)]

    score_bull = direction_score(bull_close, ema_fast_bull, ema_slow_bull, atr, bars)
    score_bear = direction_score(bear_close, ema_fast_bear, ema_slow_bear, atr, bars)

    assert score_bull is not None
    assert score_bear is not None
    assert score_bull > 0.0, "Bull mirrored sequence must produce positive score"
    assert score_bear < 0.0, "Bear mirrored sequence must produce negative score"
    assert abs(score_bull + score_bear) < 0.01, f"Mirrored sequences must have equal magnitude opposite sign: bull={score_bull:.4f} bear={score_bear:.4f}"


def test_B05_FR2_efficient_bearish_move_negative_efficiency_contribution():
    base = 100.0
    atr = 1.0
    bars = 10

    bear_close = [base - i * 1.0 for i in range(bars + 1)]

    efficiency = brain_efficiency(bear_close, bars)

    assert efficiency < 0.0, f"SIGNED efficiency for bearish efficient move must be negative, got {efficiency:.4f}"
    assert abs(efficiency - (-1.0)) < 0.01, "Perfect bearish efficiency should be close to -1.0"


def test_B05_FR3_oscillating_high_path_low_net_efficiency_near_zero():
    base = 100.0
    bars = 20

    oscillating_close = [base + (1.0 if i % 2 == 0 else -1.0) for i in range(bars + 1)]

    efficiency = brain_efficiency(oscillating_close, bars)

    assert abs(efficiency) < 0.2, f"Oscillating sequence should have near-zero efficiency, got {efficiency:.4f}"
