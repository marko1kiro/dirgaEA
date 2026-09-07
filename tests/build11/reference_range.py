"""BUILD 11 reference range / mean-reversion strategy implementation."""

from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum
from typing import List, Optional


class DIR(IntEnum):
    NONE = 0
    BUY = 1
    SELL = 2


@dataclass
class Bar:
    t: int
    o: float
    h: float
    l: float
    c: float
    avail: int


@dataclass
class Sw:
    bt: int
    ct: int
    p: float
    k: int  # 1 = High, -1 = Low


@dataclass
class Candidate:
    valid: bool
    symbol: str
    direction: DIR
    entry_price: float
    stop_loss: float
    take_profit: float
    stop_distance: float
    reward_risk_ratio: float


STOP_BUF = 0.10
MIN_RANGE_HEIGHT_ATR = 2.0


class RangeEngine:
    def __init__(self, symbol: str = "EURUSDm"):
        self.symbol = symbol
        self.swings: List[Sw] = []

    def set_swings(self, swings: List[Sw]):
        self.swings = swings

    def feed(self, bar: Bar, atr: float, h1_regime: int, h1_valid: bool) -> Optional[Candidate]:
        if not h1_valid or h1_regime != 2 or atr <= 0:  # 2 = REGIME_RANGE
            return None

        # Determine Range High & Range Low
        res_sw = [s for s in self.swings if s.k == 1 and s.ct <= bar.avail]
        sup_sw = [s for s in self.swings if s.k == -1 and s.ct <= bar.avail]

        if not res_sw or not sup_sw:
            return None

        range_high = max(s.p for s in res_sw)
        range_low = min(s.p for s in sup_sw)

        range_height = range_high - range_low
        if range_height < MIN_RANGE_HEIGHT_ATR * atr:
            return None

        # Check Support Sweep (Buy)
        if bar.l < range_low and bar.c > range_low:
            sl = bar.l - STOP_BUF * atr
            tp = range_high
            sd = abs(bar.c - sl)
            rd = abs(tp - bar.c)
            rr = rd / sd if sd > 0 else 0.0
            return Candidate(
                valid=True,
                symbol=self.symbol,
                direction=DIR.BUY,
                entry_price=bar.c,
                stop_loss=sl,
                take_profit=tp,
                stop_distance=sd,
                reward_risk_ratio=rr
            )

        # Check Resistance Sweep (Sell)
        if bar.h > range_high and bar.c < range_high:
            sl = bar.h + STOP_BUF * atr
            tp = range_low
            sd = abs(sl - bar.c)
            rd = abs(bar.c - tp)
            rr = rd / sd if sd > 0 else 0.0
            return Candidate(
                valid=True,
                symbol=self.symbol,
                direction=DIR.SELL,
                entry_price=bar.c,
                stop_loss=sl,
                take_profit=tp,
                stop_distance=sd,
                reward_risk_ratio=rr
            )

        return None
