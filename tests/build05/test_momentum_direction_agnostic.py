import pytest
import math

from reference_momentum import (
    momentum_engine_current_buggy,
    momentum_engine_direction_agnostic,
    MOMENTUM,
    STRONG_THRESHOLD,
    brain_tanh,
)


def make_mirrored_ohlc_bars(base_price, bar_count, direction, body_size=0.8, range_size=1.2, wick_size=0.2):
    """
    Create mirrored bullish/bearish OHLC bars with identical:
    - ATR magnitude
    - body magnitude
    - range magnitude
    - wick geometry (mirrored)
    - path magnitude
    """
    bars = []
    for i in range(bar_count):
        if direction == "bull":
            open_price = base_price + i * body_size
            close_price = base_price + (i + 1) * body_size
            low = open_price - wick_size
            high = close_price + wick_size
        else:  # bear
            open_price = base_price - i * body_size
            close_price = base_price - (i + 1) * body_size
            low = close_price - wick_size
            high = open_price + wick_size
        
        bars.append({
            "open": open_price,
            "high": high,
            "low": low,
            "close": close_price,
        })
    
    return bars


def test_MOMENTUM_current_buggy_direction_bias_proven():
    """
    PROVE THE BUG: Current momentum engine has direction bias.
    
    Bull/bear mirrored sequences with identical magnitudes must produce
    equal momentum strength, but current buggy code does NOT.
    """
    atr = 1.0
    base = 100.0
    
    bull_bars = make_mirrored_ohlc_bars(base, 6, "bull")
    bear_bars = make_mirrored_ohlc_bars(base, 6, "bear")
    
    bull_result = momentum_engine_current_buggy(bull_bars, atr)
    bear_result = momentum_engine_current_buggy(bear_bars, atr)
    
    assert bull_result is not None
    assert bear_result is not None
    
    # THIS WILL FAIL because current code is buggy
    assert abs(bull_result["strength"] - bear_result["strength"]) < 0.01, \
        f"CURRENT BUG: bull strength={bull_result['strength']:.4f}, bear strength={bear_result['strength']:.4f}"


def test_MOMENTUM_direction_agnostic_exact_mirror():
    """
    Direction-agnostic momentum: exact bull/bear mirror produces equal strength.
    """
    atr = 1.0
    base = 100.0
    
    bull_bars = make_mirrored_ohlc_bars(base, 6, "bull")
    bear_bars = make_mirrored_ohlc_bars(base, 6, "bear")
    
    bull_result = momentum_engine_direction_agnostic(bull_bars, atr)
    bear_result = momentum_engine_direction_agnostic(bear_bars, atr)
    
    assert bull_result is not None
    assert bear_result is not None
    
    # Strength MUST be equal
    assert abs(bull_result["strength"] - bear_result["strength"]) < 0.01, \
        f"Momentum strength must be direction-agnostic: bull={bull_result['strength']:.4f} bear={bear_result['strength']:.4f}"
    
    # directionalAlignment MUST be opposite sign
    assert bull_result["directionalAlignment"] > 0, "Bull directionalAlignment must be positive"
    assert bear_result["directionalAlignment"] < 0, "Bear directionalAlignment must be negative"
    assert abs(bull_result["directionalAlignment"] + bear_result["directionalAlignment"]) < 0.01, \
        f"directionalAlignment must be equal magnitude opposite sign"


def test_MOMENTUM_momentum_enum_same_for_mirrors():
    """
    Bull and bear mirrored sequences must produce identical Momentum enum.
    """
    atr = 1.0
    base = 100.0
    
    # Create bars that produce STRONG momentum
    bull_bars = make_mirrored_ohlc_bars(base, 6, "bull", body_size=0.9, range_size=1.0)
    bear_bars = make_mirrored_ohlc_bars(base, 6, "bear", body_size=0.9, range_size=1.0)
    
    bull_result = momentum_engine_direction_agnostic(bull_bars, atr)
    bear_result = momentum_engine_direction_agnostic(bear_bars, atr)
    
    # Both must have same classification
    bull_enum = MOMENTUM.STRONG if bull_result["strength"] >= 0.6 else MOMENTUM.NORMAL
    bear_enum = MOMENTUM.STRONG if bear_result["strength"] >= 0.6 else MOMENTUM.NORMAL
    
    assert bull_enum == bear_enum, f"Momentum enum must match: bull={bull_enum} bear={bear_enum}"


def test_MOMENTUM_strong_boundary_no_asymmetry():
    """
    Boundary fixture: at MOM_STRONG=0.60 threshold, one mirror cannot land STRONG
    while the other lands NORMAL.
    """
    atr = 1.0
    base = 100.0
    
    # Create bars that land near the 0.60 boundary
    bull_bars = make_mirrored_ohlc_bars(base, 6, "bull", body_size=0.75, range_size=0.9)
    bear_bars = make_mirrored_ohlc_bars(base, 6, "bear", body_size=0.75, range_size=0.9)
    
    bull_result = momentum_engine_direction_agnostic(bull_bars, atr)
    bear_result = momentum_engine_direction_agnostic(bear_bars, atr)
    
    bull_strong = bull_result["strength"] >= 0.60
    bear_strong = bear_result["strength"] >= 0.60
    
    # Both or neither must be STRONG - cannot have asymmetric classification
    assert bull_strong == bear_strong, \
        f"Boundary asymmetry: bull={'STRONG' if bull_strong else 'NORMAL'}, bear={'STRONG' if bear_strong else 'NORMAL'}"


def test_MOMENTUM_closeLoc_direction_agnostic():
    """
    Test directional-close-strength is direction-agnostic.
    
    Bullish close near high → (close - low) / range
    Bearish close near low → (high - close) / range
    
    Both should give similar magnitude for mirrored candles.
    """
    range_val = 1.0
    wick = 0.2
    
    # Bullish: open=100, close=100.8, low=99.8, high=101.0
    bull_close = 100.8
    bull_low = 99.8
    bull_high = 101.0
    
    # Bearish: open=100, close=99.2, low=99.0, high=100.2
    bear_close = 99.2
    bear_low = 99.0
    bear_high = 100.2
    
    # Direction-agnostic closeLocStrength
    bull_close_loc = (bull_close - bull_low) / (bull_high - bull_low)
    bear_close_loc = (bear_high - bear_close) / (bear_high - bear_low)
    
    assert abs(bull_close_loc - bear_close_loc) < 0.05, \
        f"closeLocStrength must be symmetric: bull={bull_close_loc:.4f} bear={bear_close_loc:.4f}"


def test_MOMENTUM_progression_magnitude_not_sign():
    """
    Momentum strength must use |tanh(signedProgression)|, not tanh(progression).
    """
    # Progression magnitude must be same for opposite signs
    prog_bull = 0.5
    prog_bear = -0.5
    
    mag_bull = abs(brain_tanh(prog_bull))
    mag_bear = abs(brain_tanh(prog_bear))
    
    assert abs(mag_bull - mag_bear) < 0.001, \
        f"Progression magnitude must be symmetric: bull={mag_bull:.4f} bear={mag_bear:.4f}"
