"""BUILD 04 TDD — bootstrap significance + active BOS semantics.

Covers B04-FR1..FR6 from the Master Repair Order.
"""

from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import pytest
from reference_swing import (
    process_swing_structure, SwingStructureResult,
    SWING_KIND, SWING_SIGNIFICANCE, SWING_LABEL, STRUCTURE_STATE,
    swing_is_pivot, swing_label,
)

ATR = 0.0050
T = 3600  # H1 bars


class _Bar:
    """Dot-access bar mirroring MqlRates struct (open/high/low/close/time)."""
    __slots__ = ("time", "open", "high", "low", "close")
    def __init__(self, t, o, h, l, c):
        self.time, self.open = t, o
        self.high, self.low, self.close = h, l, c


def mk_bar(t, o, h, l, c):
    return _Bar(t, o, h, l, c)


def valid_bars(bars):
    """Assert every synthetic OHLC bar is physically valid."""
    for b in bars:
        assert b.low <= b.open <= b.high, f"invalid OHLC at t={b.time}: low={b.low} <= open={b.open} <= high={b.high}"
        assert b.low <= b.close <= b.high, f"invalid OHLC at t={b.time}: low={b.low} <= close={b.close} <= high={b.high}"
        assert b.low <= b.high, f"invalid OHLC at t={b.time}: low={b.low} <= high={b.high}"


def run_structure(bars, width=2, equal_tolerance=0.10, history=512, atr_val=ATR):
    valid_bars(bars)
    atr = [atr_val] * len(bars)
    return process_swing_structure(bars, atr, len(bars), width, equal_tolerance, history)


# ---------------------------------------------------------------------------
# B04-FR1 — first high with no confirmed opposite low → NOT MAJOR
# ---------------------------------------------------------------------------

def test_B04_FR1_first_high_no_opposite_low_not_major():
    """
    A high pivot as the very first meaningful swing has no opposite low yet.
    It must NOT be promoted to MAJOR via the default 1.25 ATR fallback.
    """
    # Bar index 2 is a high pivot (2-left/2-right). No low swing before it.
    bars = [
        mk_bar(T*1,  1.0550, 1.0556, 1.0544, 1.0550),
        mk_bar(T*2,  1.0560, 1.0564, 1.0554, 1.0560),
        mk_bar(T*3,  1.0570, 1.0580, 1.0565, 1.0575),  # high pivot at index 2 (1.0580)
        mk_bar(T*4,  1.0570, 1.0574, 1.0564, 1.0570),
        mk_bar(T*5,  1.0560, 1.0564, 1.0554, 1.0560),
        mk_bar(T*6,  1.0540, 1.0544, 1.0530, 1.0535),  # low pivot at index 5? needs 2 right bars < 1.0530
        mk_bar(T*7,  1.0550, 1.0554, 1.0536, 1.0550),
        mk_bar(T*8,  1.0560, 1.0564, 1.0554, 1.0560),
    ]
    res = run_structure(bars)

    # The high pivot at T*3 must exist but NOT be MAJOR.
    highs = [s for s in res.swings if s.kind == SWING_KIND.HIGH]
    assert len(highs) >= 1, "the first high pivot should still be tracked"
    assert highs[0].significance == SWING_SIGNIFICANCE.MINOR, (
        f"first high with no opposite low must be MINOR, got significance={highs[0].significance}"
    )
    assert highs[0].significance != SWING_SIGNIFICANCE.MAJOR


# ---------------------------------------------------------------------------
# B04-FR2 — first low with no confirmed opposite high → NOT MAJOR
# ---------------------------------------------------------------------------

def test_B04_FR2_first_low_no_opposite_high_not_major():
    """
    A low pivot as the very first meaningful swing has no opposite high yet.
    It must NOT be promoted to MAJOR via the default 1.25 ATR fallback.
    """
    bars = [
        mk_bar(T*1,  1.0450, 1.0456, 1.0444, 1.0450),
        mk_bar(T*2,  1.0440, 1.0444, 1.0434, 1.0440),
        mk_bar(T*3,  1.0430, 1.0440, 1.0420, 1.0425),  # low pivot at index 2 (1.0420)
        mk_bar(T*4,  1.0430, 1.0434, 1.0424, 1.0430),
        mk_bar(T*5,  1.0440, 1.0444, 1.0434, 1.0440),
        mk_bar(T*6,  1.0460, 1.0464, 1.0448, 1.0460),
        mk_bar(T*7,  1.0450, 1.0454, 1.0444, 1.0450),
        mk_bar(T*8,  1.0440, 1.0444, 1.0434, 1.0440),
    ]
    res = run_structure(bars)

    lows = [s for s in res.swings if s.kind == SWING_KIND.LOW]
    assert len(lows) >= 1, "the first low pivot should still be tracked"
    assert lows[0].significance == SWING_SIGNIFICANCE.MINOR, (
        f"first low with no opposite high must be MINOR, got significance={lows[0].significance}"
    )
    assert lows[0].significance != SWING_SIGNIFICANCE.MAJOR


# ---------------------------------------------------------------------------
# B04-FR3 — after genuine opposite swing exists, normal boundaries:
# < 0.50 → MINOR/not-MAJOR, == 0.50 → MINOR, < 1.25 → MINOR, == 1.25 → MAJOR
# ---------------------------------------------------------------------------

def _opposite_probe(bars, kind, index_of_pivot_swing):
    """Run structure and return the significance of the swing at bars[index].time with given kind."""
    res = run_structure(bars)
    target_time = bars[index_of_pivot_swing]["time"]
    for s in res.swings:
        if s.time == target_time and s.kind == kind:
            return s.significance
    return None


def _opposite_bars():
    """Low pivot at idx2 (low=9.98). ATR=1.0 → distance = price delta. 10.0-scale = clean float."""
    return [
        mk_bar(T*1, 10.04, 10.06, 10.01, 10.04),
        mk_bar(T*2, 10.03, 10.05, 10.00, 10.03),
        mk_bar(T*3, 10.02, 10.04, 9.98, 10.00),   # low pivot idx2 (low=9.98)
        mk_bar(T*4, 10.03, 10.05, 10.01, 10.03),
        mk_bar(T*5, 10.05, 10.07, 10.02, 10.05),
    ]


def _high_pivot_bars(high_price):
    """idx5 high pivot at high_price. Distance from low (9.98) == high_price-9.98 ATR."""
    bars = _opposite_bars()
    bars.append(mk_bar(T*6, high_price - 0.001, high_price, high_price - 0.010, high_price - 0.004))  # idx5 high pivot
    bars.append(mk_bar(T*7, high_price - 0.005, high_price - 0.003, high_price - 0.012, high_price - 0.006))
    bars.append(mk_bar(T*8, high_price - 0.008, high_price - 0.006, high_price - 0.015, high_price - 0.009))
    return bars


def test_B04_FR3_boundary_below_half():
    """Opposite swing exists; new pivot at < 0.50 ATR → REJECTED."""
    low = 9.98
    high_price = low + 0.38
    bars = _high_pivot_bars(high_price)
    res = run_structure(bars, atr_val=1.0)
    high = [s for s in res.swings if s.kind == SWING_KIND.HIGH and s.time == bars[5].time]
    assert len(high) == 0, f"high at 0.38 ATR must be REJECTED (dropped), got={high}"


def test_B04_FR3_boundary_equal_half():
    """Opposite swing exists; new pivot at exactly 0.50 ATR → MINOR (not MAJOR, not rejected)."""
    low = 9.98
    high_price = 10.48
    bars = _high_pivot_bars(high_price)
    res = run_structure(bars, atr_val=1.0)
    high = [s for s in res.swings if s.kind == SWING_KIND.HIGH and s.time == bars[5].time]
    assert len(high) == 1, f"expected exactly one high at boundary=0.50, got={high}"
    assert high[0].significance == SWING_SIGNIFICANCE.MINOR, \
        f"exact 0.50 ATR must be MINOR, got={high[0].significance}"


def test_B04_FR3_boundary_below_125():
    """Opposite swing exists; new pivot at < 1.25 ATR → MINOR."""
    low = 9.98
    high_price = low + 1.24
    bars = _high_pivot_bars(high_price)
    res = run_structure(bars, atr_val=1.0)
    high = [s for s in res.swings if s.kind == SWING_KIND.HIGH and s.time == bars[5].time]
    assert len(high) == 1
    assert high[0].significance == SWING_SIGNIFICANCE.MINOR, \
        f"1.24 ATR must be MINOR, got={high[0].significance}"


def test_B04_FR3_boundary_equal_125():
    """Opposite swing exists; new pivot at exactly 1.25 ATR → MAJOR."""
    low = 9.98
    high_price = 11.23
    bars = _high_pivot_bars(high_price)
    res = run_structure(bars, atr_val=1.0)
    high = [s for s in res.swings if s.kind == SWING_KIND.HIGH and s.time == bars[5].time]
    assert len(high) == 1
    assert high[0].significance == SWING_SIGNIFICANCE.MAJOR, \
        f"exact 1.25 ATR must be MAJOR, got={high[0].significance}"


# ---------------------------------------------------------------------------
# B04-FR4 — two bullish candidate MAJOR highs; only the latest active structural
# high is eligible / consumed by bullish BOS.
# ---------------------------------------------------------------------------

def mk_bars_two_highs_bos():
    """
    Sequence (ATR=0.005):
      - leading bar tops; low pivot idx2 = 1.0470 (bootstrap MINOR)
      - high1 = 1.0600  established as MAJOR (opposite low present)
      - high2 = 1.0615  established as MAJOR (higher ⇒ ACTIVE level)
      - dedicated breakout bar closes >= 1.0615 + 0.10*ATR = 1.0620
        → BOS generated ONLY against high2 (the latest active).
      - high1 = 1.0600 stays unconsumed the whole time (no bar closes >= 1.0605 before the breakout).
    """
    # high1 formation: confirm bars must close < 1.0605 so high1 is NOT broken during its own confirmation.
    bars = [
        mk_bar(T*1,  1.0500, 1.0506, 1.0494, 1.0500),
        mk_bar(T*2,  1.0490, 1.0494, 1.0484, 1.0490),
        mk_bar(T*3,  1.0480, 1.0484, 1.0470, 1.0475),  # low pivot idx2 (1.0470)
        mk_bar(T*4,  1.0480, 1.0484, 1.0474, 1.0480),
        mk_bar(T*5,  1.0490, 1.0494, 1.0484, 1.0490),
        mk_bar(T*6,  1.0540, 1.0600, 1.0520, 1.0595),  # high1 idx5 (1.0600), close < 1.0605
        mk_bar(T*7,  1.0590, 1.0592, 1.0572, 1.0586),  # right bar for high1
        mk_bar(T*8,  1.0580, 1.0584, 1.0570, 1.0580),  # right bar for high1
        # pullback (no new high)
        mk_bar(T*9,  1.0575, 1.0579, 1.0555, 1.0565),
        mk_bar(T*10, 1.0560, 1.0564, 1.0545, 1.0550),
        mk_bar(T*11, 1.0570, 1.0615, 1.0558, 1.0600),  # high2 idx10 (1.0615), close < 1.0605
        mk_bar(T*12, 1.0605, 1.0608, 1.0588, 1.0598),  # right bar high2
        mk_bar(T*13, 1.0590, 1.0594, 1.0580, 1.0590),  # right bar high2
        mk_bar(T*14, 1.0600, 1.0630, 1.0595, 1.0622),  # breakout close 1.0622 > 1.0620 → breaks high2 only
    ]
    return bars


def test_B04_FR4_latest_active_level_exclusively_eligible():
    bars = mk_bars_two_highs_bos()
    res = run_structure(bars)
    highs = [s for s in res.swings if s.kind == SWING_KIND.HIGH and s.significance == SWING_SIGNIFICANCE.MAJOR]
    assert len(highs) >= 2, f"need at least 2 MAJOR highs for the test, got={highs}"

    # Exactly ONE bullish BOS must be generated.
    bull_breaks = [b for b in res.breaks if b.bullish]
    assert len(bull_breaks) == 1, f"expected exactly 1 bullish BOS, got={len(bull_breaks)}"

    # The single BOS must be against the LATEST ACTIVE level (high2 = 1.0615).
    latest = max(highs, key=lambda s: s.time)
    assert latest.price == 1.0615
    assert bull_breaks[0].level == 1.0615, \
        f"BOS must reference latest active level 1.0615, got level={bull_breaks[0].level}"


def test_B04_FR5_stale_level_no_duplicate_bos():
    bars = mk_bars_two_highs_bos()
    res = run_structure(bars)
    # The older unconsumed 1.0600 high must NOT produce a BOS.
    bull_breaks = [b for b in res.breaks if b.bullish]
    for b in bull_breaks:
        assert b.level != 1.0600, f"stale level 1.0600 must not generate BOS, got level={b.level}"


def test_B04_FR6_deterministic_next_active_after_consumption():
    """
    After the latest active level (high2) is consumed by a break,
    the next structurally relevant high (if any) becomes the active level.

    Sequence (ATR=0.005):
      low pivot 1.0470 (bootstrap MINOR)
      high1 1.0600 MAJOR, close bars < 1.0605 (never broken)
      high2 1.0615 MAJOR
      break high2: close 1.0622 >= 1.0620 → high2 consumed, exact 1 BOS vs 1.0615
      pullback deep (lows ~1.0520)
      high3 1.0635 MAJOR (distance to low ~2.3 ATR)
      break high3: close 1.0645 >= 1.0640 → high3 consumed, 2nd BOS vs 1.0635
      high1 remains unconsumed throughout.
    """
    bars = [
        mk_bar(T*1,  1.0500, 1.0506, 1.0494, 1.0500),
        mk_bar(T*2,  1.0490, 1.0494, 1.0484, 1.0490),
        mk_bar(T*3,  1.0480, 1.0484, 1.0470, 1.0475),  # low pivot idx2 (1.0470)
        mk_bar(T*4,  1.0480, 1.0484, 1.0474, 1.0480),
        mk_bar(T*5,  1.0490, 1.0494, 1.0484, 1.0490),
        mk_bar(T*6,  1.0540, 1.0600, 1.0520, 1.0595),  # high1 idx5 (1.0600), close < 1.0605
        mk_bar(T*7,  1.0590, 1.0592, 1.0572, 1.0586),
        mk_bar(T*8,  1.0580, 1.0584, 1.0570, 1.0580),
        mk_bar(T*9,  1.0575, 1.0579, 1.0555, 1.0565),
        mk_bar(T*10, 1.0560, 1.0564, 1.0545, 1.0550),
        mk_bar(T*11, 1.0570, 1.0615, 1.0558, 1.0600),  # high2 idx10 (1.0615), close < 1.0605
        mk_bar(T*12, 1.0605, 1.0608, 1.0588, 1.0598),
        mk_bar(T*13, 1.0590, 1.0594, 1.0580, 1.0590),
        mk_bar(T*14, 1.0600, 1.0630, 1.0595, 1.0622),  # break high2: close 1.0622 >= 1.0620
        # deep pullback → high3 far enough from opposite low to be MAJOR
        mk_bar(T*15, 1.0610, 1.0612, 1.0580, 1.0590),
        mk_bar(T*16, 1.0585, 1.0587, 1.0520, 1.0530),  # low ~1.0520
        mk_bar(T*17, 1.0540, 1.0635, 1.0535, 1.0628),  # high3 idx16 (1.0635), close < 1.0620? must be < 1.0620 to not break high1... but 1.0628 >= 1.0620 breaks high2 again? high2 already consumed. But must NOT break... high2 consumed, OK.
        mk_bar(T*18, 1.0620, 1.0624, 1.0610, 1.0615),
        mk_bar(T*19, 1.0610, 1.0614, 1.0600, 1.0610),
        mk_bar(T*20, 1.0620, 1.0640, 1.0610, 1.0638),  # break high3: close 1.0638 >= 1.0635+0.0005=1.0640? NO, 1.0638 < 1.0640
    ]
    # fix T*20 close to exceed 1.0640
    bars[19] = mk_bar(T*20, 1.0625, 1.0650, 1.0615, 1.0648)
    res = run_structure(bars)

    # high2 consumed by its break. high1 = 1.0600 must stay unconsumed (never broken).
    h1 = [s for s in res.swings if s.kind == SWING_KIND.HIGH and abs(s.price - 1.0600) < 1e-9]
    h2 = [s for s in res.swings if s.kind == SWING_KIND.HIGH and abs(s.price - 1.0615) < 1e-9]
    h3 = [s for s in res.swings if s.kind == SWING_KIND.HIGH and abs(s.price - 1.0635) < 1e-9]
    assert h1 and not h1[0].consumed, "high1 (1.0600) should remain unconsumed"
    assert h2 and h2[0].consumed, "high2 (1.0615) should be consumed by its break"
    assert h3 and h3[0].consumed, "high3 (1.0635) should be consumed by its break"

    # Exactly 2 bullish BOS total: one vs 1.0615, one vs 1.0635.
    bull_breaks = [b for b in res.breaks if b.bullish]
    assert len(bull_breaks) == 2, f"expected exactly 2 bullish BOS, got={len(bull_breaks)}"
    levels = sorted(b.level for b in bull_breaks)
    assert levels == sorted([1.0615, 1.0635]), f"unexpected BOS levels: {levels}"


# ---------------------------------------------------------------------------
# B04-FR7 — stale reactivation: after high2 consumed, continuation bar
# must NOT reactivate high1.
# ---------------------------------------------------------------------------

def test_B04_FR7_stale_reactivation_blocked():
    """
    High1 MAJOR, High2 newer MAJOR. Break High2 → BOS 1.0615.
    Append one continuation bar that closes above both levels.
    High1 must NOT reactivate → total bullish BOS remains exactly 1.
    """
    bars = mk_bars_two_highs_bos()
    # bars[-1] is T*14 break bar (close 1.0622, breaks high2).
    # Append one continuation bar that closes above high1 (1.0605) but
    # since high2 is already consumed and is the newest MAJOR high,
    # there is NO active bullish BOS level.
    bars.append(mk_bar(T*15, 1.0615, 1.0640, 1.0610, 1.0635))  # close 1.0635 > 1.0605
    valid_bars(bars)
    res = run_structure(bars)

    bull_breaks = [b for b in res.breaks if b.bullish]
    assert len(bull_breaks) == 1, (
        f"stale high1 reactivation: expected exactly 1 bullish BOS, got {len(bull_breaks)}: "
        f"levels={[b.level for b in bull_breaks]}"
    )
    assert bull_breaks[0].level == 1.0615, f"only BOS should be vs high2, got level={bull_breaks[0].level}"

    # high1 must remain unconsumed
    h1 = [s for s in res.swings if s.kind == SWING_KIND.HIGH and abs(s.price - 1.0600) < 1e-9]
    assert h1 and not h1[0].consumed, "high1 must remain unconsumed (never reactivated)"


# ---------------------------------------------------------------------------
# B04-FR8 — after high2 consumed, no active level until genuinely NEWER
# high3 MAJOR forms; high1 never reactivates.
# ---------------------------------------------------------------------------

def test_B04_FR8_new_major_required_after_consumption():
    """
    High1 MAJOR, High2 newer MAJOR consumed by BOS.
    Continuation bars close above high1 but no active level exists.
    Then a genuinely NEWER High3 MAJOR forms and is broken → BOS vs high3.
    High1 never reactivates.
    Total bullish BOS: exactly 2 (high2 + high3).
    """
    bars = mk_bars_two_highs_bos()
    # bars[-1] = T*14 break high2. Add continuation + new high3.
    bars.extend([
        mk_bar(T*15, 1.0615, 1.0640, 1.0610, 1.0635),  # continuation, closes > high1 but no active level
        mk_bar(T*16, 1.0630, 1.0634, 1.0610, 1.0620),
        mk_bar(T*17, 1.0610, 1.0614, 1.0540, 1.0550),  # deep pullback → low ~1.0540
        mk_bar(T*18, 1.0560, 1.0650, 1.0555, 1.0640),  # high3 idx17 (1.0650) MAJOR, close < 1.0655
        mk_bar(T*19, 1.0630, 1.0634, 1.0615, 1.0625),  # right bar high3
        mk_bar(T*20, 1.0620, 1.0624, 1.0610, 1.0620),  # right bar high3
        mk_bar(T*21, 1.0625, 1.0670, 1.0620, 1.0662),  # break high3: close 1.0662 >= 1.0650+0.0005=1.0655
    ])
    valid_bars(bars)
    res = run_structure(bars)

    bull_breaks = [b for b in res.breaks if b.bullish]
    assert len(bull_breaks) == 2, (
        f"expected exactly 2 bullish BOS (high2+high3), got {len(bull_breaks)}: "
        f"levels={[b.level for b in bull_breaks]}"
    )
    levels = sorted(b.level for b in bull_breaks)
    assert 1.0600 not in levels, f"high1 must never generate BOS, got levels={levels}"
    assert levels == sorted([1.0615, 1.0650]), f"unexpected BOS levels: {levels}"

    h1 = [s for s in res.swings if s.kind == SWING_KIND.HIGH and abs(s.price - 1.0600) < 1e-9]
    assert h1 and not h1[0].consumed, "high1 must remain unconsumed forever"


# ---------------------------------------------------------------------------
# B04-FR9 — bearish mirror: Low1, Low2 newer consumed → Low1 no reactivation.
# ---------------------------------------------------------------------------

def test_B04_FR9_bear_mirror_stale_reactivation_blocked():
    """
    Low1 MAJOR, Low2 newer MAJOR. Break Low2 (bearish BOS).
    Continuation bar closes below both levels.
    Low1 must NOT reactivate → total bearish BOS remains exactly 1.
    """
    atr_val = ATR
    # High pivot at idx2 (1.0625) bootstrap MINOR.
    # Low1 at idx5 (1.0520): opposite=1.0625, dist=2.1 ATR → MAJOR.
    # No intermediate high pivots between low1 and low2.
    # Low2 at idx10 (1.0505): opposite=1.0625 (still the most recent HIGH), dist=2.4 → MAJOR.
    bars = [
        mk_bar(T*1,  1.0610, 1.0616, 1.0604, 1.0610),
        mk_bar(T*2,  1.0615, 1.0620, 1.0610, 1.0615),
        mk_bar(T*3,  1.0620, 1.0625, 1.0615, 1.0620),  # high pivot idx2 (1.0625)
        mk_bar(T*4,  1.0610, 1.0615, 1.0605, 1.0610),
        mk_bar(T*5,  1.0590, 1.0595, 1.0580, 1.0585),
        mk_bar(T*6,  1.0530, 1.0540, 1.0520, 1.0525),  # low1 idx5 (1.0520) MAJOR
        mk_bar(T*7,  1.0525, 1.0530, 1.0522, 1.0527),  # right bar low1 (no new high pivot)
        mk_bar(T*8,  1.0540, 1.0545, 1.0535, 1.0542),  # right bar low1
        mk_bar(T*9,  1.0550, 1.0555, 1.0540, 1.0548),
        mk_bar(T*10, 1.0550, 1.0555, 1.0540, 1.0548),
        mk_bar(T*11, 1.0530, 1.0535, 1.0505, 1.0530),  # low2 idx10 (1.0505) MAJOR, close > low1 break level
        mk_bar(T*12, 1.0515, 1.0520, 1.0512, 1.0518),  # right bar low2
        mk_bar(T*13, 1.0525, 1.0530, 1.0520, 1.0525),  # right bar low2
        mk_bar(T*14, 1.0510, 1.0515, 1.0490, 1.0495),  # break low2: close 1.0495 <= 1.0505-0.0005=1.0500
        mk_bar(T*15, 1.0500, 1.0505, 1.0480, 1.0485),  # continuation, close 1.0485 < low1
    ]
    valid_bars(bars)
    res = run_structure(bars, atr_val=atr_val)

    bear_breaks = [b for b in res.breaks if not b.bullish]
    assert len(bear_breaks) == 1, (
        f"stale low1 reactivation: expected exactly 1 bearish BOS, got {len(bear_breaks)}: "
        f"levels={[b.level for b in bear_breaks]}"
    )
    assert abs(bear_breaks[0].level - 1.0505) < 1e-9, f"only BOS should be vs low2, got level={bear_breaks[0].level}"

    l1 = [s for s in res.swings if s.kind == SWING_KIND.LOW and abs(s.price - 1.0520) < 1e-9]
    assert l1 and not l1[0].consumed, "low1 must remain unconsumed (never reactivated)"


# ---------------------------------------------------------------------------
# OHLC validity helper test (reusable assertion for all synthetic sequences)
# ---------------------------------------------------------------------------

def test_B04_ohlc_physical_validity():
    """Every synthetic OHLC sequence used in BUILD04 tests is physically valid."""
    from reference_swing import swing_is_pivot
    sequences = [
        mk_bars_two_highs_bos(),
    ]
    for bars in sequences:
        valid_bars(bars)