"""BUILD 10 reference execution bridge implementation."""

from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum


class ORDER_ACTION(IntEnum):
    NONE = 0
    BUY_MARKET = 1
    SELL_MARKET = 2
    MODIFY_SL = 3
    CLOSE_MARKET = 4


@dataclass
class Candidate:
    valid: bool
    symbol: str
    direction: str  # "BUY" or "SELL"
    entry_price: float
    stop_loss: float
    take_profit: float


@dataclass
class RiskResult:
    approved: bool
    volume: float
    reject_reason: str = ""


@dataclass
class OrderIntent:
    action: ORDER_ACTION
    symbol: str = ""
    volume: float = 0.0
    price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    ticket: int = 0
    reason: str = ""


class ExecutionBridge:
    def __init__(self, symbol: str = "EURUSDm", magic: int = 123456, max_positions: int = 1):
        self.symbol = symbol
        self.magic = magic
        self.max_positions = max_positions

    def prepare_market_order(
        self,
        cand: Candidate,
        risk: RiskResult,
        open_positions_count: int
    ) -> OrderIntent:
        if not cand.valid:
            return OrderIntent(ORDER_ACTION.NONE, reason="invalid_candidate")

        if not risk.approved or risk.volume <= 0:
            return OrderIntent(ORDER_ACTION.NONE, reason="risk_rejected")

        if open_positions_count >= self.max_positions:
            return OrderIntent(ORDER_ACTION.NONE, reason="max_positions_reached")

        action = ORDER_ACTION.BUY_MARKET if cand.direction == "BUY" else ORDER_ACTION.SELL_MARKET
        return OrderIntent(
            action=action,
            symbol=cand.symbol,
            volume=risk.volume,
            price=cand.entry_price,
            stop_loss=cand.stop_loss,
            take_profit=cand.take_profit,
            reason="new_trade_entry"
        )
