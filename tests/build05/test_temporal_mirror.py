import pytest
import math

from reference_momentum import (
    momentum_engine_direction_agnostic,
    momentum_enum,
    MOMENTUM,
    brain_clamp_signed,
)


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


def test_MOMENTUM_temporal_mirror_two_consecutive_h1():
    atr = 1.0
    base = 100.0
    body_size = 0.75

    bull_seq_n = make_mirrored_ohlc_bars(base, 6, "bull", body_size=body_size)
    bear_seq_n = make_mirrored_ohlc_bars(base, 6, "bear", body_size=body_size)

    bull_seq_n1 = make_mirrored_ohlc_bars(base + 5 * body_size, 6, "bull", body_size=body_size)
    bear_seq_n1 = make_mirrored_ohlc_bars(base - 5 * body_size, 6, "bear", body_size=body_size)

    bull_n = momentum_engine_direction_agnostic(bull_seq_n, atr)
    bear_n = momentum_engine_direction_agnostic(bear_seq_n, atr)

    bull_n1 = momentum_engine_direction_agnostic(bull_seq_n1, atr)
    bear_n1 = momentum_engine_direction_agnostic(bear_seq_n1, atr)

    assert abs(bull_n["strength"] - bear_n["strength"]) < 0.01, \
        "Strength N must be equal for mirrors"

    assert abs(bull_n1["strength"] - bear_n1["strength"]) < 0.01, \
        "Strength N+1 must be equal for mirrors"

    bull_delta = bull_n1["strength"] - bull_n["strength"]
    bear_delta = bear_n1["strength"] - bear_n["strength"]
    assert abs(bull_delta - bear_delta) < 0.01, \
        "Delta must be equal for temporal mirrors"

    bull_slope = brain_clamp_signed(bull_delta)
    bear_slope = brain_clamp_signed(bear_delta)
    assert abs(bull_slope - bear_slope) < 0.01, \
        "Slope must be equal for temporal mirrors"

    bull_enum_n1 = momentum_enum(bull_n1["strength"], bull_slope)
    bear_enum_n1 = momentum_enum(bear_n1["strength"], bear_slope)
    assert bull_enum_n1 == bear_enum_n1, \
        "Momentum enum must be identical for temporal mirrors"

    assert bull_n["directionalAlignment"] > 0, "Bull N alignment must be positive"
    assert bear_n["directionalAlignment"] < 0, "Bear N alignment must be negative"
    assert abs(bull_n["directionalAlignment"] + bear_n["directionalAlignment"]) < 0.01, \
        "Alignment N must be opposite sign"

    assert bull_n1["directionalAlignment"] > 0, "Bull N+1 alignment must be positive"
    assert bear_n1["directionalAlignment"] < 0, "Bear N+1 alignment must be negative"
    assert abs(bull_n1["directionalAlignment"] + bear_n1["directionalAlignment"]) < 0.01, \
        "Alignment N+1 must be opposite sign"


def test_MOMENTUM_temporal_mirror_slope_computed_not_injected():
    atr = 1.0
    base = 100.0
    body_n = 0.70
    body_n1 = 0.85

    bull_seq_n = make_mirrored_ohlc_bars(base, 6, "bull", body_size=body_n)
    bear_seq_n = make_mirrored_ohlc_bars(base, 6, "bear", body_size=body_n)

    bull_seq_n1 = make_mirrored_ohlc_bars(base + 5 * body_n, 6, "bull", body_size=body_n1)
    bear_seq_n1 = make_mirrored_ohlc_bars(base - 5 * body_n, 6, "bear", body_size=body_n1)

    bull_n = momentum_engine_direction_agnostic(bull_seq_n, atr)
    bear_n = momentum_engine_direction_agnostic(bear_seq_n, atr)
    bull_n1 = momentum_engine_direction_agnostic(bull_seq_n1, atr)
    bear_n1 = momentum_engine_direction_agnostic(bear_seq_n1, atr)

    bull_delta = bull_n1["strength"] - bull_n["strength"]
    bear_delta = bear_n1["strength"] - bear_n["strength"]

    assert abs(bull_delta - bear_delta) < 0.01, \
        "Delta computed from actual engine outputs must match"

    assert bull_delta != 0, "Delta must be non-zero for real temporal change"

    bull_slope_actual = brain_clamp_signed(bull_delta)
    bear_slope_actual = brain_clamp_signed(bear_delta)

    bull_enum_actual = momentum_enum(bull_n1["strength"], bull_slope_actual)
    bear_enum_actual = momentum_enum(bear_n1["strength"], bear_slope_actual)

    assert bull_enum_actual == bear_enum_actual, \
        "Enum from computed slope must match"
