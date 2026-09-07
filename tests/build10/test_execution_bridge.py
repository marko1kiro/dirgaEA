import pytest
from tests.build10.reference_execution import (
    ExecutionBridge, Candidate, RiskResult, OrderIntent, ORDER_ACTION
)


def test_order_intent_creation():
    bridge = ExecutionBridge(symbol="EURUSDm", magic=123456, max_positions=1)
    cand = Candidate(
        valid=True,
        symbol="EURUSDm",
        direction="BUY",
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100
    )
    risk = RiskResult(approved=True, volume=0.10)
    intent = bridge.prepare_market_order(cand, risk, open_positions_count=0)
    assert intent.action == ORDER_ACTION.BUY_MARKET
    assert intent.volume == 0.10
    assert intent.price == 1.1000
    assert intent.stop_loss == 1.0950
    assert intent.take_profit == 1.1100


def test_max_position_limit_rejection():
    bridge = ExecutionBridge(symbol="EURUSDm", magic=123456, max_positions=1)
    cand = Candidate(
        valid=True,
        symbol="EURUSDm",
        direction="BUY",
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100
    )
    risk = RiskResult(approved=True, volume=0.10)
    # 1 open position already exists
    intent = bridge.prepare_market_order(cand, risk, open_positions_count=1)
    assert intent.action == ORDER_ACTION.NONE
    assert intent.reason == "max_positions_reached"


def test_risk_rejection_blocks_order():
    bridge = ExecutionBridge(symbol="EURUSDm", magic=123456, max_positions=1)
    cand = Candidate(
        valid=True,
        symbol="EURUSDm",
        direction="SELL",
        entry_price=1.1000,
        stop_loss=1.1050,
        take_profit=1.0900
    )
    risk = RiskResult(approved=False, volume=0.0, reject_reason="margin_insufficient")
    intent = bridge.prepare_market_order(cand, risk, open_positions_count=0)
    assert intent.action == ORDER_ACTION.NONE
    assert intent.reason == "risk_rejected"

