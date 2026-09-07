"""BUILD 12 reference breakout strategy implementation."""

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
MIN_PENETRATION_ATR = 0.15
MAX_CHASE_ATR = 1.5


class BreakoutEngine:
    def __init__(self, symbol: str = "EURUSDm"):
        self.symbol = symbol
        self.swings: List[Sw] = []

    def set_swings(self, swings: List[Sw]):
        self.swings = swings

    def feed(self, bar: Bar, atr: float, h1_regime: int, h1_valid: bool) -> Optional[Candidate]:
        if not h1_valid or atr <= 0:
            return None

        # 3 = REGIME_BREAKOUT_BULL, 4 = REGIME_BREAKOUT_BEAR
        if h1_regime == 3:
            # Bull Breakout: Find highest swing high
            res_sw = [s for s in self.swings if s.k == 1 and s.ct <= bar.avail]
            if not res_sw:
                return None
            level = max(s.p for s in res_sw)

            penetration = bar.c - level
            if penetration < MIN_PENETRATION_ATR * atr:
                return None
            if penetration > MAX_CHASE_ATR * atr:  # Anti-chase
                return None

            sl = bar.l - STOP_BUF * atr
            sd = abs(bar.c - sl)
            tp = bar.c + 1.5 * sd
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

        elif h1_regime == 4:
            # Bear Breakout: Find lowest swing low
            sup_sw = [s for s in self.swings if s.k == -1 and s.ct <= bar.avail]
            if not sup_sw:
                return None
            level = min(s.p for s in sup_sw)

            penetration = level - bar.c
            if penetration < MIN_PENETRATION_ATR * atr:
                return None
            if penetration > MAX_CHASE_ATR * atr:  # Anti-chase
                return None

            sl = bar.h + STOP_BUF * atr
            sd = abs(sl - bar.c)
            tp = bar.c - 1.5 * sd
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
