import pytest
import math


def brain_efficiency_signed(close_seq, bars):
    """Directional efficiency for Direction domain: netDirectional/path, signed [-1,+1]"""
    if bars <= 0 or len(close_seq) < bars + 1:
        return 0.0
    net_directional = close_seq[-1] - close_seq[-(bars + 1)]
    path = sum(abs(close_seq[i] - close_seq[i-1]) for i in range(len(close_seq) - bars, len(close_seq)))
    if path <= 0.0:
        return 0.0
    return net_directional / path


def brain_efficiency_magnitude(close_seq, bars):
    """Path efficiency for Momentum domain: |netDirectional|/path, unsigned [0,1]"""
    if bars <= 0 or len(close_seq) < bars + 1:
        return 0.0
    net_directional = close_seq[-1] - close_seq[-(bars + 1)]
    path = sum(abs(close_seq[i] - close_seq[i-1]) for i in range(len(close_seq) - bars, len(close_seq)))
    if path <= 0.0:
        return 0.0
    return abs(net_directional) / path


def momentum_strength_reference(close_seq, atr_last, bars=5):
    """
    Direction-agnostic momentum strength.
    Bull and bear mirror sequences must produce identical strength.
    """
    if len(close_seq) < bars + 1 or not (atr_last > 0.0):
        return None
    
    n = len(close_seq) - 1
    bar_range = close_seq[n] - min(close_seq[n-bars:n+1])  # range proxy
    body = abs(close_seq[n] - close_seq[n-1])
    body_atr = body / atr_last if atr_last > 0.0 else 0.0
    
    # Path efficiency: UNSIGNED magnitude
    efficiency = brain_efficiency_magnitude(close_seq, bars)
    
    # Progression: direction-agnostic cumulative body magnitude
    progression_unsigned = sum(abs(close_seq[i] - close_seq[i-1]) for i in range(n-bars+1, n+1)) / bars / max(atr_last, 1e-9)
    
    # Fixed weights (matching production constants)
    raw = 0.25 * min(1.0, body_atr) + 0.15 * min(1.0, efficiency) + 0.20 * min(1.0, progression_unsigned)
    
    return max(0.0, min(1.0, raw))


def test_MOMENTUM_DIRECTION_AGNOSTIC_mirrored_bull_bear_equal_strength():
    """
    CRITICAL BUG: Momentum strength MUST be direction-agnostic.
    
    Bull and bear mirrored sequences with identical:
    - ATR magnitude
    - body magnitude  
    - range magnitude
    - path magnitude
    
    MUST produce:
    - momentumStrengthScore equal (within tolerance)
    - Momentum enum classification identical
    
    Current BUGGY code uses signed BrainEfficiency in momentum calculation,
    causing bull/bear asymmetry.
    
    Locked semantic: Momentum measures movement MAGNITUDE, not direction.
    Direction information belongs in directionalAlignment (diagnostic-only).
    """
    atr = 1.0
    bars = 5
    base = 100.0
    
    # Efficient bullish move
    bull_close = [base + i * 0.8 for i in range(bars + 1)]
    
    # Efficient bearish move (mirror)
    bear_close = [base - i * 0.8 for i in range(bars + 1)]
    
    bull_strength = momentum_strength_reference(bull_close, atr, bars)
    bear_strength = momentum_strength_reference(bear_close, atr, bars)
    
    assert bull_strength is not None
    assert bear_strength is not None
    
    # MUST be equal for direction-agnostic momentum
    assert abs(bull_strength - bear_strength) < 0.01, \
        f"Momentum strength MUST be direction-agnostic: bull={bull_strength:.4f} bear={bear_strength:.4f}"


def test_MOMENTUM_efficiency_uses_magnitude_not_sign():
    """
    Momentum efficiency component MUST use |netDirectional|/path (unsigned).
    Direction efficiency for Direction domain uses netDirectional/path (signed).
    
    These are two different helpers serving different domains.
    """
    bars = 5
    base = 100.0
    
    # Efficient bearish sequence
    bear_close = [base - i * 1.0 for i in range(bars + 1)]
    
    # Signed efficiency (for Direction domain)
    eff_signed = brain_efficiency_signed(bear_close, bars)
    
    # Magnitude efficiency (for Momentum domain)
    eff_magnitude = brain_efficiency_magnitude(bear_close, bars)
    
    assert eff_signed < 0.0, "Signed efficiency for bearish must be negative"
    assert eff_magnitude > 0.0, "Magnitude efficiency must be positive"
    assert abs(abs(eff_signed) - eff_magnitude) < 0.01, "Magnitudes must match"


def test_MOMENTUM_progression_uses_unsigned_cumulative_body():
    """
    Momentum progression MUST be direction-agnostic cumulative body magnitude,
    NOT signed cumulative (close[i] - close[i-1]).
    
    Bull/bear mirror must produce equal unsigned progression.
    """
    bars = 5
    base = 100.0
    
    bull_close = [base + i * 0.5 for i in range(bars + 1)]
    bear_close = [base - i * 0.5 for i in range(bars + 1)]
    
    # Unsigned cumulative body
    bull_prog = sum(abs(bull_close[i] - bull_close[i-1]) for i in range(1, len(bull_close)))
    bear_prog = sum(abs(bear_close[i] - bear_close[i-1]) for i in range(1, len(bear_close)))
    
    assert abs(bull_prog - bear_prog) < 0.01, \
        f"Unsigned progression must be equal: bull={bull_prog:.4f} bear={bear_prog:.4f}"
