"""Shared test helpers for BUILD 07 TDD harness."""

from __future__ import annotations
from typing import List, Optional, Tuple
from reference_trend import (
    Bar, H1, Engine, Cand,
    REGIME, RQUAL, FAMILY, DIR,
)

T = 900  # M15 seconds


def mk_bar(t: int, h: float, l: float, c: float = 0.0, o: float = 0.0) -> Bar:
    if o == 0.0:
        o = (h + l) / 2
    if c == 0.0:
        c = (h + l) / 2
    return Bar(t=t, o=o, h=h, l=l, c=c, avail=0)


def assign_avail(bars: List[Bar]) -> None:
    """Assign avail = next bar's open time (last bar gets +T)."""
    for i, bar in enumerate(bars):
        bar.avail = bars[i + 1].t if i + 1 < len(bars) else bar.t + T


def make_engine(regime: REGIME = REGIME.TREND_BULL,
                valid: bool = True,
                qual: RQUAL = RQUAL.NORMAL,
                sym: str = "TEST") -> Engine:
    eng = Engine(sym)
    h1 = H1(src=0, avail=T, regime=regime, qual=qual, valid=valid)
    eng.set_h1(h1)
    return eng


def feed_all(eng: Engine, bars: List[Bar], atr: float) -> List[Optional[Cand]]:
    assign_avail(bars)
    return [eng.feed(b, atr) for b in bars]


def feed_all_last(eng: Engine, bars: List[Bar], atr: float) -> Optional[Cand]:
    return feed_all(eng, bars, atr)[-1]


def first_cand(eng: Engine, bars: List[Bar], atr: float) -> Optional[Cand]:
    assign_avail(bars)
    for b in bars:
        c = eng.feed(b, atr)
        if c:
            return c
    return None


# ---------------------------------------------------------------------------
# Standard bar sequences
# ---------------------------------------------------------------------------

def bull_impulse_bars() -> Tuple[List[Bar], float]:
    """
    Returns (bars, atr) for a confirmed bull impulse A→B then pullback C in zone.

    Swings (bt=bar open time, ct=confirmedAtTime):
      A: low  bt=T*3  p=1.0515  ct=T*5  avail=T*6
      B: high bt=T*7  p=1.0600  ct=T*9  avail=T*10
      C: low  bt=T*11 p=1.0545  ct=T*13 avail=T*14

    Impulse A→B = (1.0600-1.0515)/0.0050 = 2.85 ATR >= IMP_MIN OK
    Zone [1.05431, 1.05711]; C.p=1.0545 in zone OK
    Depth = (1.0600-1.0545)/0.0050 = 1.1 ATR in [PB_MIN, PB_MAX] OK
    Mid = (1.0600+1.0545)/2 = 1.05725
    Trigger needs close > 1.05725.
    """
    atr = 0.0050
    bars = [
        Bar(t=T*1,  o=1.0620, h=1.0620, l=1.0580, c=1.0600),
        Bar(t=T*2,  o=1.0590, h=1.0610, l=1.0560, c=1.0585),
        Bar(t=T*3,  o=1.0580, h=1.0580, l=1.0520, c=1.0530),  # low candidate
        Bar(t=T*4,  o=1.0550, h=1.0550, l=1.0515, c=1.0538),
        Bar(t=T*5,  o=1.0545, h=1.0545, l=1.0525, c=1.0555),  # confirms A (1.0515)
        Bar(t=T*6,  o=1.0560, h=1.0560, l=1.0535, c=1.0555),
        Bar(t=T*7,  o=1.0580, h=1.0600, l=1.0560, c=1.0590),  # high candidate
        Bar(t=T*8,  o=1.0585, h=1.0585, l=1.0565, c=1.0575),
        Bar(t=T*9,  o=1.0575, h=1.0575, l=1.0558, c=1.0565),  # confirms B
        Bar(t=T*10, o=1.0570, h=1.0570, l=1.0548, c=1.0558),
        Bar(t=T*11, o=1.0565, h=1.0565, l=1.0545, c=1.0550),  # C low (1.0545)
        Bar(t=T*12, o=1.0560, h=1.0560, l=1.0552, c=1.0555),
        Bar(t=T*13, o=1.0565, h=1.0565, l=1.0558, c=1.0572),  # confirms C
    ]
    return bars, atr


def bull_trigger_bar() -> Bar:
    """First bar after C confirmed whose close > mid=1.05725."""
    return Bar(t=T*14, o=1.0575, h=1.0592, l=1.0568, c=1.0582)


def bear_impulse_bars() -> Tuple[List[Bar], float]:
    """
    Bear mirror of bull_impulse_bars.

    A: high bt=T*3  p=1.0595  ct=T*5  avail=T*6
    B: low  bt=T*7  p=1.0515  ct=T*9  avail=T*10
    C: high bt=T*11 p=1.0565  ct=T*13 avail=T*14

    Impulse A→B = (1.0595-1.0515)/0.0050 = 1.6 ATR
    Zone [1.05427, 1.05673]; C.p=1.0565 in zone OK
    Depth = (1.0565-1.0515)/0.0050 = 1.0 ATR in [PB_MIN, PB_MAX] OK
    Mid = (1.0515+1.0565)/2 = 1.0540
    Trigger needs close < 1.0540.
    """
    atr = 0.0050
    bars = [
        Bar(t=T*1,  o=1.0580, h=1.0590, l=1.0555, c=1.0570),
        Bar(t=T*2,  o=1.0575, h=1.0585, l=1.0550, c=1.0565),
        Bar(t=T*3,  o=1.0590, h=1.0600, l=1.0575, c=1.0595),  # A high
        Bar(t=T*4,  o=1.0580, h=1.0588, l=1.0555, c=1.0565),
        Bar(t=T*5,  o=1.0565, h=1.0575, l=1.0545, c=1.0555),  # confirms A
        Bar(t=T*6,  o=1.0555, h=1.0565, l=1.0525, c=1.0535),
        Bar(t=T*7,  o=1.0530, h=1.0542, l=1.0500, c=1.0510),  # B low
        Bar(t=T*8,  o=1.0515, h=1.0530, l=1.0508, c=1.0520),
        Bar(t=T*9,  o=1.0520, h=1.0535, l=1.0512, c=1.0525),  # confirms B
        Bar(t=T*10, o=1.0525, h=1.0538, l=1.0515, c=1.0528),
        Bar(t=T*11,  o=1.0545, h=1.0560, l=1.0532, c=1.0552),  # C high (strictly higher)
        Bar(t=T*12, o=1.0548, h=1.0555, l=1.0530, c=1.0540),
        Bar(t=T*13,  o=1.0542, h=1.0550, l=1.0525, c=1.0535),  # confirms C
    ]
    return bars, atr


def bear_trigger_bar() -> Bar:
    """First bar after C confirmed whose close < mid=1.0540."""
    return Bar(t=T*14, o=1.0535, h=1.0542, l=1.0515, c=1.0520)
