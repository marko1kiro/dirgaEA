"""BUILD 08 reference position manager implementation."""

from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum
from typing import List


class ACTION(IntEnum):
    NONE = 0
    MODIFY_SL = 1
    CLOSE_MARKET = 2


class DIR(IntEnum):
    NONE = 0
    BUY = 1
    SELL = 2


class REGIME(IntEnum):
    TREND_BULL = 0
    TREND_BEAR = 1
    RANGE = 2
    BREAKOUT_BULL = 3
    BREAKOUT_BEAR = 4
    UNCERTAIN = 5


@dataclass
class Position:
    ticket: int
    symbol: str
    direction: DIR
    open_price: float
    current_sl: float
    current_tp: float
    initial_sl: float
    magic: int = 123456


@dataclass
class Sw:
    bt: int
    ct: int
    p: float
    k: int


@dataclass
class Intent:
    ticket: int
    action: ACTION
    new_sl: float = 0.0
    new_tp: float = 0.0
    reason: str = ""


BE_R_MULT = 1.0
BE_ATR_BUFFER = 0.10
TRAILING_ATR_BUFFER = 0.10


def evaluate_position(
    pos: Position,
    current_price: float,
    atr_m15: float,
    h1_regime: REGIME,
    h1_valid: bool,
    swings_m15: List[Sw],
    now: int
) -> Intent:
    if not h1_valid or h1_regime == REGIME.UNCERTAIN:
        return Intent(pos.ticket, ACTION.CLOSE_MARKET, reason="regime_uncertain_or_invalid")
    if pos.direction == DIR.BUY and h1_regime == REGIME.TREND_BEAR:
        return Intent(pos.ticket, ACTION.CLOSE_MARKET, reason="regime_bear_flip")
    if pos.direction == DIR.SELL and h1_regime == REGIME.TREND_BULL:
        return Intent(pos.ticket, ACTION.CLOSE_MARKET, reason="regime_bull_flip")

    risk_dist = abs(pos.open_price - pos.initial_sl)
    if risk_dist <= 0:
        return Intent(pos.ticket, ACTION.NONE)

    be_target = pos.open_price + risk_dist * BE_R_MULT if pos.direction == DIR.BUY else pos.open_price - risk_dist * BE_R_MULT
    be_sl = pos.open_price + BE_ATR_BUFFER * atr_m15 if pos.direction == DIR.BUY else pos.open_price - BE_ATR_BUFFER * atr_m15

    is_be_reached = (current_price >= be_target) if pos.direction == DIR.BUY else (current_price <= be_target)

    if is_be_reached:
        candidate_sl = be_sl

        # Search for confirmed swing trail
        for s in reversed(swings_m15):
            if s.ct > now:
                continue
            if pos.direction == DIR.BUY and s.k == -1:
                potential_sl = s.p - TRAILING_ATR_BUFFER * atr_m15
                if potential_sl > candidate_sl:
                    candidate_sl = potential_sl
                break
            elif pos.direction == DIR.SELL and s.k == 1:
                potential_sl = s.p + TRAILING_ATR_BUFFER * atr_m15
                if potential_sl < candidate_sl:
                    candidate_sl = potential_sl
                break

        if pos.direction == DIR.BUY and candidate_sl > pos.current_sl + 1e-6:
            return Intent(pos.ticket, ACTION.MODIFY_SL, new_sl=candidate_sl, new_tp=pos.current_tp, reason="trailing_or_be")
        elif pos.direction == DIR.SELL and (pos.current_sl <= 0 or candidate_sl < pos.current_sl - 1e-6):
            return Intent(pos.ticket, ACTION.MODIFY_SL, new_sl=candidate_sl, new_tp=pos.current_tp, reason="trailing_or_be")


    return Intent(pos.ticket, ACTION.NONE)


