import pytest
from tests.build08.reference_position_manager import (
    Position, Intent, ACTION, DIR, REGIME, evaluate_position, Sw
)


def test_regime_flip_exit():
    pos = Position(
        ticket=101,
        symbol="EURUSDm",
        direction=DIR.BUY,
        open_price=1.1000,
        current_sl=1.0950,
        current_tp=1.1100,
        initial_sl=1.0950
    )
    intent = evaluate_position(
        pos,
        current_price=1.1020,
        atr_m15=0.0010,
        h1_regime=REGIME.TREND_BEAR,
        h1_valid=True,
        swings_m15=[],
        now=1700000000
    )
    assert intent.action == ACTION.CLOSE_MARKET
    assert intent.reason == "regime_bear_flip"


def test_regime_uncertain_or_invalid_exit():
    pos = Position(
        ticket=102,
        symbol="EURUSDm",
        direction=DIR.SELL,
        open_price=1.1000,
        current_sl=1.1050,
        current_tp=1.0900,
        initial_sl=1.1050
    )
    intent = evaluate_position(
        pos,
        current_price=1.0980,
        atr_m15=0.0010,
        h1_regime=REGIME.UNCERTAIN,
        h1_valid=True,
        swings_m15=[],
        now=1700000000
    )
    assert intent.action == ACTION.CLOSE_MARKET
    assert intent.reason == "regime_uncertain_or_invalid"


def test_breakeven_trigger():
    # Buy: open=1.1000, sl=1.0950 (1R = 0.0050). Target for BE >= 1.1050
    pos = Position(
        ticket=103,
        symbol="EURUSDm",
        direction=DIR.BUY,
        open_price=1.1000,
        current_sl=1.0950,
        current_tp=1.1150,
        initial_sl=1.0950
    )
    # Price reaches 1.1055 (> 1.1050), ATR=0.0010, BE SL = 1.1000 + (0.10 * 0.0010) = 1.1001
    intent = evaluate_position(
        pos,
        current_price=1.1055,
        atr_m15=0.0010,
        h1_regime=REGIME.TREND_BULL,
        h1_valid=True,
        swings_m15=[],
        now=1700000000
    )
    assert intent.action == ACTION.MODIFY_SL
    assert pytest.approx(intent.new_sl, 1e-5) == 1.1001
    assert intent.reason == "trailing_or_be"


def test_swing_trailing_ratchet():
    pos = Position(
        ticket=104,
        symbol="EURUSDm",
        direction=DIR.BUY,
        open_price=1.1000,
        current_sl=1.1001,
        current_tp=1.1200,
        initial_sl=1.0950
    )
    # Confirmed swing low at 1.1040. Trailing SL = 1.1040 - (0.10 * 0.0010) = 1.1039
    sw = [Sw(bt=1700000000, ct=1700001800, p=1.1040, k=-1)]
    intent = evaluate_position(
        pos,
        current_price=1.1080,
        atr_m15=0.0010,
        h1_regime=REGIME.TREND_BULL,
        h1_valid=True,
        swings_m15=sw,
        now=1700002000
    )
    assert intent.action == ACTION.MODIFY_SL
    assert pytest.approx(intent.new_sl, 1e-5) == 1.1039
    assert intent.reason == "trailing_or_be"


def test_trailing_never_widens():
    # Current SL is 1.1050, lower swing low at 1.1020 must NOT move SL backwards
    pos = Position(
        ticket=105,
        symbol="EURUSDm",
        direction=DIR.BUY,
        open_price=1.1000,
        current_sl=1.1050,
        current_tp=1.1200,
        initial_sl=1.0950
    )
    sw = [Sw(bt=1700000000, ct=1700001800, p=1.1020, k=-1)]
    intent = evaluate_position(
        pos,
        current_price=1.1080,
        atr_m15=0.0010,
        h1_regime=REGIME.TREND_BULL,
        h1_valid=True,
        swings_m15=sw,
        now=1700002000
    )
    assert intent.action == ACTION.NONE




