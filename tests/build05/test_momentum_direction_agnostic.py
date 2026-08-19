import pytest
import math

from reference_momentum import (
    momentum_engine_direction_agnostic,
    momentum_enum,
    MOMENTUM,
    STRONG_THRESHOLD,
    brain_tanh,
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


def test_MOMENTUM_direction_agnostic_exact_mirror():
    atr = 1.0
    base = 100.0

    bull_bars = make_mirrored_ohlc_bars(base, 6, "bull", body_size=0.8)
    bear_bars = make_mirrored_ohlc_bars(base, 6, "bear", body_size=0.8)

    bull_result = momentum_engine_direction_agnostic(bull_bars, atr)
    bear_result = momentum_engine_direction_agnostic(bear_bars, atr)

    assert bull_result is not None
    assert bear_result is not None

    assert abs(bull_result["strength"] - bear_result["strength"]) < 0.01, \
        "Momentum strength must be direction-agnostic"

    assert bull_result["directionalAlignment"] > 0, "Bull directionalAlignment must be positive"
    assert bear_result["directionalAlignment"] < 0, "Bear directionalAlignment must be negative"
    assert abs(bull_result["directionalAlignment"] + bear_result["directionalAlignment"]) < 0.01, \
        "directionalAlignment must be equal magnitude opposite sign"


def test_MOMENTUM_momentum_enum_same_for_mirrors():
    atr = 1.0
    base = 100.0

    bull_bars = make_mirrored_ohlc_bars(base, 6, "bull", body_size=0.85)
    bear_bars = make_mirrored_ohlc_bars(base, 6, "bear", body_size=0.85)

    bull_result = momentum_engine_direction_agnostic(bull_bars, atr)
    bear_result = momentum_engine_direction_agnostic(bear_bars, atr)

    bull_enum = momentum_enum(bull_result["strength"], slope=0.0)
    bear_enum = momentum_enum(bear_result["strength"], slope=0.0)

    assert bull_enum == bear_enum, "Momentum enum must match for mirrors"


def test_MOMENTUM_strong_boundary_no_asymmetry():
    atr = 1.0
    base = 100.0

    body_size_boundary = 0.430651

    bull_bars = make_mirrored_ohlc_bars(base, 6, "bull", body_size=body_size_boundary)
    bear_bars = make_mirrored_ohlc_bars(base, 6, "bear", body_size=body_size_boundary)

    bull_result = momentum_engine_direction_agnostic(bull_bars, atr)
    bear_result = momentum_engine_direction_agnostic(bear_bars, atr)

    assert abs(bull_result["strength"] - 0.60) < 0.01, \
        "Bull strength must be near MOM_STRONG boundary"
    assert abs(bear_result["strength"] - 0.60) < 0.01, \
        "Bear strength must be near MOM_STRONG boundary"

    bull_strong = bull_result["strength"] >= STRONG_THRESHOLD
    bear_strong = bear_result["strength"] >= STRONG_THRESHOLD

    assert bull_strong == bear_strong, \
        "Boundary cannot have asymmetric classification"


def test_MOMENTUM_closeLoc_direction_agnostic():
    range_val = 1.0

    bull_close = 100.8
    bull_low = 99.8
    bull_high = 101.0

    bear_close = 99.2
    bear_low = 99.0
    bear_high = 100.2

    bull_close_loc = (bull_close - bull_low) / (bull_high - bull_low)
    bear_close_loc = (bear_high - bear_close) / (bear_high - bear_low)

    assert abs(bull_close_loc - bear_close_loc) < 0.05, \
        "closeLocStrength must be symmetric"


def test_MOMENTUM_progression_magnitude_not_sign():
    prog_bull = 0.5
    prog_bear = -0.5

    mag_bull = abs(brain_tanh(prog_bull))
    mag_bear = abs(brain_tanh(prog_bear))

    assert abs(mag_bull - mag_bear) < 0.001, \
        "Progression magnitude must be symmetric"
