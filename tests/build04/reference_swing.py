"""BUILD 04 reference swing structure — mirrors SwingStructure.mqh logic for testing."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
from enum import IntEnum

SWING_STRUCTURE_MAX_HISTORY = 512

class SWING_KIND(IntEnum):
    HIGH = 0
    LOW = 1

class SWING_SIGNIFICANCE(IntEnum):
    REJECTED = 0
    MINOR = 1
    MAJOR = 2

class SWING_LABEL(IntEnum):
    NONE = 0
    HH = 1
    LH = 2
    EH = 3
    HL = 4
    LL = 5
    EL = 6

class FOLLOW_THROUGH(IntEnum):
    NONE = 0
    VALID = 1
    STRONG = 2
    FAILED = 3

class STRUCTURE_STATE(IntEnum):
    UNKNOWN = 0
    BULLISH_STRONG = 1
    BEARISH_STRONG = 2
    RANGE = 3
    MIXED = 4
    BULLISH_WEAK = 5
    BEARISH_WEAK = 6

@dataclass
class SwingPoint:
    time: int = 0
    price: float = 0.0
    atr: float = 0.0
    kind: int = 0
    significance: int = 0
    label: int = 0
    consumed: bool = False

@dataclass
class StructureBreak:
    time: int = 0
    bullish: bool = False
    level: float = 0.0
    penetrationAtr: float = 0.0
    strong: bool = False
    followThrough: int = 0
    followThroughFinalized: bool = False

@dataclass
class SwingStructureResult:
    swings: List[SwingPoint] = field(default_factory=list)
    breaks: List[StructureBreak] = field(default_factory=list)
    state: int = STRUCTURE_STATE.UNKNOWN
    sweep: bool = False
    valid: bool = False
    latestTime: int = 0
    swingCount: int = 0
    breakCount: int = 0


def swing_is_pivot(rates, index: int, count: int, width: int, high: bool) -> bool:
    value = rates[index].high if high else rates[index].low
    for offset in range(1, width + 1):
        left = rates[index - offset].high if high else rates[index - offset].low
        right = rates[index + offset].high if high else rates[index + offset].low
        if (high and (value <= left or value <= right)) or (not high and (value >= left or value >= right)):
            return False
    return True


def swing_label(result: SwingStructureResult, kind: int, price: float, atr: float, tolerance: float) -> int:
    for i in range(len(result.swings) - 1, -1, -1):
        prior = result.swings[i]
        if prior.kind != kind or prior.significance != SWING_SIGNIFICANCE.MAJOR:
            continue
        if abs(price - prior.price) <= tolerance * atr:
            return SWING_LABEL.EH if kind == SWING_KIND.HIGH else SWING_LABEL.EL
        if kind == SWING_KIND.HIGH:
            return SWING_LABEL.HH if price > prior.price else SWING_LABEL.LH
        return SWING_LABEL.HL if price > prior.price else SWING_LABEL.LL
    return SWING_LABEL.NONE


def swing_add(result: SwingStructureResult, bar, atr: float, kind: int, significance: int, tolerance: float, history: int):
    if result.swingCount >= history:
        result.swings = result.swings[1:]
        result.swingCount = history - 1
    price = bar.high if kind == SWING_KIND.HIGH else bar.low
    label = swing_label(result, kind, price, atr, tolerance) if significance == SWING_SIGNIFICANCE.MAJOR else SWING_LABEL.NONE
    sp = SwingPoint(time=bar.time, price=price, atr=atr, kind=kind, significance=significance, label=label, consumed=False)
    result.swings.append(sp)
    result.swingCount += 1


def swing_add_break(result: SwingStructureResult, bar, bullish: bool, level: float, atr: float, history: int):
    if result.breakCount >= history:
        result.breaks = result.breaks[1:]
        result.breakCount = history - 1
    range_ = bar.high - bar.low
    penetration = abs(bar.close - level) / atr
    body = abs(bar.close - bar.open) / range_ if range_ > 0 else 0
    directional_close = (bar.close - bar.low) / range_ if bullish and range_ > 0 else (bar.high - bar.close) / range_
    if not bullish and range_ > 0:
        directional_close = (bar.high - bar.close) / range_
    strong = penetration >= 0.35 and body >= 0.60 and directional_close >= 0.75
    brk = StructureBreak(time=bar.time, bullish=bullish, level=level, penetrationAtr=penetration, strong=strong)
    result.breaks.append(brk)
    result.breakCount += 1


def swing_classify_state(result: SwingStructureResult):
    high, low = SWING_LABEL.NONE, SWING_LABEL.NONE
    for i in range(len(result.swings) - 1, -1, -1):
        sw = result.swings[i]
        if sw.significance != SWING_SIGNIFICANCE.MAJOR:
            continue
        if sw.kind == SWING_KIND.HIGH and high == SWING_LABEL.NONE:
            high = sw.label
        if sw.kind == SWING_KIND.LOW and low == SWING_LABEL.NONE:
            low = sw.label
    if high == SWING_LABEL.EH and low == SWING_LABEL.EL:
        result.state = STRUCTURE_STATE.RANGE
    elif high == SWING_LABEL.HH and low == SWING_LABEL.HL:
        result.state = STRUCTURE_STATE.BULLISH_STRONG
    elif high == SWING_LABEL.LH and low == SWING_LABEL.LL:
        result.state = STRUCTURE_STATE.BEARISH_STRONG
    elif (high == SWING_LABEL.HH and (low == SWING_LABEL.NONE or low == SWING_LABEL.HL)) or \
         (low == SWING_LABEL.HL and (high == SWING_LABEL.NONE or high == SWING_LABEL.HH)):
        result.state = STRUCTURE_STATE.BULLISH_WEAK
    elif (high == SWING_LABEL.LH and (low == SWING_LABEL.NONE or low == SWING_LABEL.LL)) or \
         (low == SWING_LABEL.LL and (high == SWING_LABEL.NONE or high == SWING_LABEL.LH)):
        result.state = STRUCTURE_STATE.BEARISH_WEAK
    elif high != SWING_LABEL.NONE or low != SWING_LABEL.NONE:
        result.state = STRUCTURE_STATE.MIXED
    else:
        result.state = STRUCTURE_STATE.UNKNOWN


def process_swing_structure(rates, atr, count: int, width: int, equal_tolerance: float, history: int) -> SwingStructureResult:
    result = SwingStructureResult()
    if count < width * 2 + 3 or width < 1 or history < 1 or history > SWING_STRUCTURE_MAX_HISTORY or equal_tolerance < 0.0:
        return result
    for i in range(count):
        r = rates[i]
        if r.time <= 0 or atr[i] <= 0 or r.open <= 0 or r.high <= 0 or r.low <= 0 or r.close <= 0 or \
           r.high < r.low or r.open < r.low or r.open > r.high or r.close < r.low or r.close > r.high or \
           (i > 0 and r.time <= rates[i - 1].time):
            return result
    # Pass 1: pivot detection across the pivot window [width, count-width).
    for i in range(width, count):
        def _classify(value: float, kind: int, i: int) -> int:
            opp_kind = SWING_KIND.LOW if kind == SWING_KIND.HIGH else SWING_KIND.HIGH
            opposite = 0.0
            for sw in reversed(result.swings):
                if sw.kind == opp_kind:
                    opposite = sw.price
                    break
            if opposite <= 0.0:
                # B04-R1: no opposite swing exists → never MAJOR, MINOR bootstrap
                return SWING_SIGNIFICANCE.MINOR
            distance = abs(value - opposite) / atr[i]
            if distance < 0.5:
                return SWING_SIGNIFICANCE.REJECTED
            return SWING_SIGNIFICANCE.MAJOR if distance >= 1.25 else SWING_SIGNIFICANCE.MINOR

        if i < count - width and swing_is_pivot(rates, i, count, width, True):
            sig = _classify(rates[i].high, SWING_KIND.HIGH, i)
            if sig != SWING_SIGNIFICANCE.REJECTED:
                swing_add(result, rates[i], atr[i], SWING_KIND.HIGH, sig, equal_tolerance, history)
        if i < count - width and swing_is_pivot(rates, i, count, width, False):
            sig = _classify(rates[i].low, SWING_KIND.LOW, i)
            if sig != SWING_SIGNIFICANCE.REJECTED:
                swing_add(result, rates[i], atr[i], SWING_KIND.LOW, sig, equal_tolerance, history)
        range_ = rates[i].high - rates[i].low
        if range_ <= 0.0:
            continue
        # B04-R2v2: find NEWEST MAJOR of kind (regardless of consumed).
        # If newest is consumed → no active level for that direction.
        for kind in (SWING_KIND.HIGH, SWING_KIND.LOW):
            active = None
            for j in range(len(result.swings) - 1, -1, -1):
                sw = result.swings[j]
                if sw.kind == kind and sw.significance == SWING_SIGNIFICANCE.MAJOR and sw.time < rates[i].time:
                    active = j
                    break
            if active is None:
                continue
            if result.swings[active].consumed:
                continue
            sw = result.swings[active]
            bullish = sw.kind == SWING_KIND.HIGH
            broken = (rates[i].close >= sw.price + 0.10 * atr[i]) if bullish else (rates[i].close <= sw.price - 0.10 * atr[i])
            if broken:
                swing_add_break(result, rates[i], bullish, sw.price, atr[i], history)
                result.swings[active].consumed = True
                continue
            swept_wick = rates[i].high > sw.price if bullish else rates[i].low < sw.price
            inside = rates[i].close <= sw.price if bullish else rates[i].close >= sw.price
            sweep = swept_wick and inside and abs(rates[i].close - sw.price) <= equal_tolerance * atr[i]
            result.sweep = result.sweep or sweep
    swing_classify_state(result)
    result.valid = True
    result.latestTime = rates[count - 1].time
    return result