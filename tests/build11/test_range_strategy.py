import pytest
from tests.build11.reference_range import (
    RangeEngine, Bar, Sw, Candidate, DIR
)


def test_range_support_sweep_buy():
    engine = RangeEngine(symbol="EURUSDm")
    # Range: High=1.1050, Low=1.1000 (Height = 50 pips >= 2.0 ATR where ATR=0.0010)
    swings = [
        Sw(bt=1700000000, ct=1700001000, p=1.1050, k=1),   # Resistance
        Sw(bt=1700002000, ct=1700003000, p=1.1000, k=-1)   # Support
    ]
    engine.set_swings(swings)

    # Bar sweeps below 1.1000 to 1.0990, but closes inside at 1.1005
    bar = Bar(t=1700004000, o=1.1002, h=1.1010, l=1.0990, c=1.1005, avail=1700004900)
    cand = engine.feed(bar, atr=0.0010, h1_regime=2, h1_valid=True)  # 2 = REGIME_RANGE

    assert cand is not None
    assert cand.valid is True
    assert cand.direction == DIR.BUY
    assert cand.entry_price == 1.1005
    # SL = sweep low (1.0990) - 0.10 * ATR (0.0001) = 1.0989
    assert pytest.approx(cand.stop_loss, 1e-5) == 1.0989
    # TP = Range High = 1.1050
    assert pytest.approx(cand.take_profit, 1e-5) == 1.1050


def test_range_resistance_sweep_sell():
    engine = RangeEngine(symbol="EURUSDm")
    swings = [
        Sw(bt=1700000000, ct=1700001000, p=1.1050, k=1),   # Resistance
        Sw(bt=1700002000, ct=1700003000, p=1.1000, k=-1)   # Support
    ]
    engine.set_swings(swings)

    # Bar sweeps above 1.1050 to 1.1060, but closes inside at 1.1045
    bar = Bar(t=1700004000, o=1.1048, h=1.1060, l=1.1040, c=1.1045, avail=1700004900)
    cand = engine.feed(bar, atr=0.0010, h1_regime=2, h1_valid=True)

    assert cand is not None
    assert cand.valid is True
    assert cand.direction == DIR.SELL
    assert cand.entry_price == 1.1045
    # SL = sweep high (1.1060) + 0.10 * ATR (0.0001) = 1.1061
    assert pytest.approx(cand.stop_loss, 1e-5) == 1.1061
    # TP = Range Low = 1.1000
    assert pytest.approx(cand.take_profit, 1e-5) == 1.1000

