import pytest
from tests.build12.reference_breakout import (
    BreakoutEngine, Bar, Sw, Candidate, DIR
)


def test_direct_impulse_breakout_bull():
    engine = BreakoutEngine(symbol="EURUSDm")
    # Resistance swing at 1.1000
    swings = [Sw(bt=1700000000, ct=1700001000, p=1.1000, k=1)]
    engine.set_swings(swings)

    # Candle closes at 1.1025 breaking through 1.1000 (penetration = 0.0025 > 0.15 * 0.0010, dist = 0.0025 <= 1.5 * 0.0010 = 0.0015 -> wait, let's set close = 1.1010 for dist <= 1.5 ATR)
    # Open = 1.0990, High = 1.1012, Low = 1.0988, Close = 1.1010, ATR = 0.0010
    bar = Bar(t=1700002000, o=1.0990, h=1.1012, l=1.0988, c=1.1010, avail=1700002900)
    cand = engine.feed(bar, atr=0.0010, h1_regime=3, h1_valid=True)  # 3 = REGIME_BREAKOUT_BULL

    assert cand is not None
    assert cand.valid is True
    assert cand.direction == DIR.BUY
    assert cand.entry_price == 1.1010
    # Stop Loss = bar.l (1.0988) - 0.10 * ATR (0.0001) = 1.0987
    assert pytest.approx(cand.stop_loss, 1e-5) == 1.0987
    # Target = 1.1010 + 1.5 * (1.1010 - 1.0988) = 1.1010 + 0.0033 = 1.1043
    assert cand.take_profit > cand.entry_price


def test_anti_chase_rejection():
    engine = BreakoutEngine(symbol="EURUSDm")
    swings = [Sw(bt=1700000000, ct=1700001000, p=1.1000, k=1)]
    engine.set_swings(swings)

    # Candle closes at 1.1020 breaking through 1.1000 (distance = 2.0 pips > 1.5 * 0.0010 ATR) -> Rejected by Anti-Chase
    bar = Bar(t=1700002000, o=1.0990, h=1.1022, l=1.0988, c=1.1020, avail=1700002900)
    cand = engine.feed(bar, atr=0.0010, h1_regime=3, h1_valid=True)

    assert cand is None

