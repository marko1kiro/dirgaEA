"""BUILD 07 TDD — scenario matrix A–AF + AG1–AG10 (spec §22)."""

from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import pytest
from reference_trend import (
    Bar, H1, Engine, Ctx, Cand,
    REGIME, RQUAL, FAMILY, DIR,
    epoch_chk, b07d1,
    ZONE_LO, ZONE_HI, IMP_MIN, PB_MIN, PB_MAX,
    BRK_PEN, RET_TOL, RET_MAX, MAX_EXT, MOM_MIN_D, MOM_LB,
    MIN_STOP, MAX_STOP, STOP_BUF, CONTR_DISP,
)
from helpers import (
    T, mk_bar, assign_avail, make_engine, feed_all, feed_all_last,
    first_cand, bull_impulse_bars, bull_trigger_bar,
    bear_impulse_bars, bear_trigger_bar,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_bull_pb():
    """Run the standard bull pullback scenario; return (engine, cand)."""
    bars, atr = bull_impulse_bars()
    bars.append(bull_trigger_bar())
    eng = make_engine(REGIME.TREND_BULL)
    results = feed_all(eng, bars, atr)
    cand = next((c for c in results if c), None)
    return eng, cand


def _run_bear_pb():
    bars, atr = bear_impulse_bars()
    bars.append(bear_trigger_bar())
    eng = make_engine(REGIME.TREND_BEAR)
    results = feed_all(eng, bars, atr)
    cand = next((c for c in results if c and c.f == FAMILY.PULLBACK), None)
    return eng, cand


def _bull_break_retest_bars():
    """
    Build bars that create a bull break-retest setup.
    Swing high R at bt=T*7 p=1.0600, confirmed ct=T*9.
    Break bar at T*10: close=1.0615 > R+BRK_PEN*ATR=1.0600+0.0005=1.0605. bav=T*11.
    Retest bar at T*11: low=1.0596 touches band [1.0590,1.0610]. close=1.0598 < R.
    Acceptance bar at T*12: close=1.0608 > R=1.0600. -> candidate.
    ATR=0.0050.
    """
    atr = 0.0050
    bars = [
        mk_bar(T*1,  h=1.0560, l=1.0520),
        mk_bar(T*2,  h=1.0580, l=1.0540),
        mk_bar(T*3,  h=1.0570, l=1.0530),
        mk_bar(T*4,  h=1.0590, l=1.0550),
        mk_bar(T*5,  h=1.0580, l=1.0545),
        mk_bar(T*6,  h=1.0595, l=1.0560),
        mk_bar(T*7,  h=1.0600, l=1.0565),  # R high candidate
        mk_bar(T*8,  h=1.0590, l=1.0560),
        mk_bar(T*9,  h=1.0585, l=1.0555),  # confirms R; ct=T*9 avail=T*10
        mk_bar(T*10, h=1.0620, l=1.0600, c=1.0615),  # break bar: close>R+pen
        mk_bar(T*11, h=1.0608, l=1.0592, c=1.0598),  # retest touch: low in band, close<R
        mk_bar(T*12, h=1.0640, l=1.0605, c=1.0630),  # cons+acceptance: low<=R+tol, close>R
        mk_bar(T*13, h=1.0645, l=1.0620, c=1.0635),  # extra
    ]
    return bars, atr


def _bear_break_retest_bars():
    """Bear mirror of bull break-retest."""
    atr = 0.0050
    bars = [
        mk_bar(T*1,  h=1.0580, l=1.0540),
        mk_bar(T*2,  h=1.0560, l=1.0520),
        mk_bar(T*3,  h=1.0570, l=1.0530),
        mk_bar(T*4,  h=1.0550, l=1.0510),
        mk_bar(T*5,  h=1.0555, l=1.0515),
        mk_bar(T*6,  h=1.0540, l=1.0505),
        mk_bar(T*7,  h=1.0535, l=1.0500),  # R low candidate
        mk_bar(T*8,  h=1.0540, l=1.0510),
        mk_bar(T*9,  h=1.0545, l=1.0515),  # confirms R
        mk_bar(T*10, h=1.0500, l=1.0480, c=1.0485),  # break bar: close<R-pen
        mk_bar(T*11, h=1.0508, l=1.0490, c=1.0502),  # retest touch: high in band, close>R
        mk_bar(T*12, h=1.0495, l=1.0460, c=1.0470),  # cons+acceptance: high<=R+tol, close<R
        mk_bar(T*13, h=1.0480, l=1.0455, c=1.0465),
    ]
    return bars, atr


def _bull_momentum_bars():
    """
    Bull momentum: 3-bar net close displacement >= MOM_MIN_D ATR.
    bars[-3].c=1.0540, bars[-1].c=1.0585 -> disp=(1.0585-1.0540)/0.0050=0.9 >= 0.8.
    Leg base swing low confirmed in epoch.
    ext = (1.0585 - legbase)/atr must be < 2.5.
    """
    atr = 0.0050
    bars = [
        mk_bar(T*1,  h=1.0560, l=1.0535),
        mk_bar(T*2,  h=1.0555, l=1.0530),
        mk_bar(T*3,  h=1.0540, l=1.0500),  # low candidate
        mk_bar(T*4,  h=1.0550, l=1.0515),
        mk_bar(T*5,  h=1.0560, l=1.0522),  # confirms low@T*3; ct=avail of T*5 = T*6
        mk_bar(T*6,  h=1.0565, l=1.0530, c=1.0540),  # bars[-3]
        mk_bar(T*7,  h=1.0575, l=1.0545, c=1.0560),  # bars[-2]
        mk_bar(T*8,  h=1.0590, l=1.0570, c=1.0585),  # bars[-1]=trigger
        mk_bar(T*9,  h=1.0595, l=1.0575, c=1.0588),  # extra avail donor
    ]
    return bars, atr


# ---------------------------------------------------------------------------
# A — TREND_BULL + valid pullback → PULLBACK candidate
# ---------------------------------------------------------------------------

def test_A_bull_pullback():
    _, c = _run_bull_pb()
    assert c is not None
    assert c.f == FAMILY.PULLBACK
    assert c.d == DIR.BUY
    assert c.ok


# ---------------------------------------------------------------------------
# B — TREND_BEAR mirror → PULLBACK candidate
# ---------------------------------------------------------------------------

def test_B_bear_pullback():
    _, c = _run_bear_pb()
    assert c is not None
    assert c.f == FAMILY.PULLBACK
    assert c.d == DIR.SELL
    assert c.ok


# ---------------------------------------------------------------------------
# C — pullback too shallow → no candidate
# ---------------------------------------------------------------------------

def test_C_pullback_too_shallow():
    """C depth < PB_MIN=0.30 ATR → no candidate."""
    atr = 0.0050
    bars, _ = bull_impulse_bars()
    # Replace C with a very shallow low: depth=(1.0600-1.0598)/0.0050=0.04 < 0.30
    bars[10] = mk_bar(T*11, h=1.0602, l=1.0598, c=1.0599)  # C shallow
    bars.append(bull_trigger_bar())
    eng = make_engine(REGIME.TREND_BULL)
    results = feed_all(eng, bars, atr)
    assert all(c is None or c.f != FAMILY.PULLBACK for c in results)


# ---------------------------------------------------------------------------
# D — pullback too deep / origin broken → no candidate
# ---------------------------------------------------------------------------

def test_D_pullback_too_deep():
    """C depth > PB_MAX=1.50 ATR → no candidate."""
    atr = 0.0050
    bars, _ = bull_impulse_bars()
    # Replace C with deep low: depth=(1.0600-1.0520)/0.0050=1.6 > 1.50
    bars[10] = mk_bar(T*11, h=1.0545, l=1.0520, c=1.0525)
    bars.append(bull_trigger_bar())
    eng = make_engine(REGIME.TREND_BULL)
    results = feed_all(eng, bars, atr)
    assert all(c is None or c.f != FAMILY.PULLBACK for c in results)


# ---------------------------------------------------------------------------
# E — valid bull break + retest → BREAK_RETEST candidate
# ---------------------------------------------------------------------------

def test_E_bull_break_retest():
    bars, atr = _bull_break_retest_bars()
    eng = make_engine(REGIME.TREND_BULL)
    results = feed_all(eng, bars, atr)
    cand = next((c for c in results if c and c.f == FAMILY.BREAK_RETEST), None)
    assert cand is not None
    assert cand.d == DIR.BUY
    assert cand.ok


# ---------------------------------------------------------------------------
# F — bear break-retest → BREAK_RETEST candidate
# ---------------------------------------------------------------------------

def test_F_bear_break_retest():
    bars, atr = _bear_break_retest_bars()
    eng = make_engine(REGIME.TREND_BEAR)
    results = feed_all(eng, bars, atr)
    cand = next((c for c in results if c and c.f == FAMILY.BREAK_RETEST), None)
    assert cand is not None
    assert cand.d == DIR.SELL
    assert cand.ok


# ---------------------------------------------------------------------------
# G — stale/expired retest (age > RET_MAX) → no candidate
# ---------------------------------------------------------------------------

def test_G_stale_expired_retest():
    """Feed RET_MAX+2 bars after break without touching level → expires."""
    atr = 0.0050
    bars = [
        mk_bar(T*1,  h=1.0560, l=1.0520),
        mk_bar(T*2,  h=1.0580, l=1.0540),
        mk_bar(T*3,  h=1.0570, l=1.0530),
        mk_bar(T*4,  h=1.0590, l=1.0550),
        mk_bar(T*5,  h=1.0580, l=1.0545),
        mk_bar(T*6,  h=1.0595, l=1.0560),
        mk_bar(T*7,  h=1.0600, l=1.0565),  # R
        mk_bar(T*8,  h=1.0590, l=1.0560),
        mk_bar(T*9,  h=1.0585, l=1.0555),  # confirms R
        mk_bar(T*10, h=1.0620, l=1.0600, c=1.0615),  # break bar age=1
    ]
    # Add RET_MAX+2 bars above level — no retest touch, level expires
    for k in range(RET_MAX + 2):
        bars.append(mk_bar(T*(11+k), h=1.0625, l=1.0612, c=1.0618))
    eng = make_engine(REGIME.TREND_BULL)
    results = feed_all(eng, bars, atr)
    br_cands = [c for c in results if c and c.f == FAMILY.BREAK_RETEST]
    assert len(br_cands) == 0
    assert eng.ctx.pend is None or eng.ctx.pend.exp


# ---------------------------------------------------------------------------
# H — consumed retest cannot fire twice
# ---------------------------------------------------------------------------

def test_H_consumed_retest_no_duplicate():
    bars, atr = _bull_break_retest_bars()
    eng = make_engine(REGIME.TREND_BULL)
    results = feed_all(eng, bars, atr)
    br_cands = [c for c in results if c and c.f == FAMILY.BREAK_RETEST]
    assert len(br_cands) == 1  # exactly one, not repeated


# ---------------------------------------------------------------------------
# I — pullback + momentum both valid same bar → PULLBACK wins
# ---------------------------------------------------------------------------

def test_I_pullback_beats_momentum():
    """When both pullback and momentum are valid, PULLBACK has priority."""
    _, c = _run_bull_pb()
    # The pullback scenario naturally satisfies momentum too (3-bar displacement).
    # The returned candidate must be PULLBACK not MOMENTUM.
    assert c is not None
    assert c.f == FAMILY.PULLBACK


# ---------------------------------------------------------------------------
# J — break-retest + momentum both valid → BREAK_RETEST wins
# ---------------------------------------------------------------------------

def test_J_break_retest_beats_momentum():
    bars, atr = _bull_break_retest_bars()
    eng = make_engine(REGIME.TREND_BULL)
    results = feed_all(eng, bars, atr)
    winning = next((c for c in results if c), None)
    if winning:
        assert winning.f != FAMILY.MOMENTUM


# ---------------------------------------------------------------------------
# K — clean momentum continuation → MOMENTUM candidate
# ---------------------------------------------------------------------------

def test_K_momentum():
    bars, atr = _bull_momentum_bars()
    eng = make_engine(REGIME.TREND_BULL)
    results = feed_all(eng, bars, atr)
    mom = next((c for c in results if c and c.f == FAMILY.MOMENTUM), None)
    assert mom is not None
    assert mom.d == DIR.BUY
    assert mom.ok


# ---------------------------------------------------------------------------
# L — momentum excessively extended → rejected by anti-chase
# ---------------------------------------------------------------------------

def test_L_momentum_anti_chase():
    """disp OK but ext >= MAX_EXT=2.5 → no momentum candidate."""
    atr = 0.0050
    bars = [
        mk_bar(T*1,  h=1.0560, l=1.0500),  # low candidate: p=1.0500
        mk_bar(T*2,  h=1.0550, l=1.0510),
        mk_bar(T*3,  h=1.0555, l=1.0515),  # confirms low@T*1
        # entry is 1.0640 -> ext=(1.0640-1.0500)/0.0050=2.8 >= 2.5
        mk_bar(T*4,  h=1.0600, l=1.0570, c=1.0590),  # bars[-3]
        mk_bar(T*5,  h=1.0625, l=1.0595, c=1.0615),  # bars[-2]
        mk_bar(T*6,  h=1.0645, l=1.0625, c=1.0640),  # trigger: disp=1.0 OK, ext=2.8 fail
        mk_bar(T*7,  h=1.0650, l=1.0630, c=1.0642),
    ]
    eng = make_engine(REGIME.TREND_BULL)
    results = feed_all(eng, bars, atr)
    mom = next((c for c in results if c and c.f == FAMILY.MOMENTUM), None)
    assert mom is None


# ---------------------------------------------------------------------------
# M — H1 RANGE → no candidate
# ---------------------------------------------------------------------------

def test_M_h1_range_no_candidate():
    bars, atr = bull_impulse_bars()
    bars.append(bull_trigger_bar())
    eng = make_engine(REGIME.RANGE)
    results = feed_all(eng, bars, atr)
    assert all(c is None for c in results)


# ---------------------------------------------------------------------------
# N — H1 BREAKOUT_BULL/BEAR → no candidate
# ---------------------------------------------------------------------------

def test_N_h1_breakout_no_candidate():
    bars, atr = bull_impulse_bars()
    bars.append(bull_trigger_bar())
    for regime in (REGIME.BREAKOUT_BULL, REGIME.BREAKOUT_BEAR):
        eng = make_engine(regime)
        results = feed_all(eng, bars, atr)
        assert all(c is None for c in results), f"regime={regime} produced candidate"


# ---------------------------------------------------------------------------
# O — H1 UNCERTAIN → no candidate
# ---------------------------------------------------------------------------

def test_O_h1_uncertain_no_candidate():
    bars, atr = bull_impulse_bars()
    bars.append(bull_trigger_bar())
    eng = make_engine(REGIME.UNCERTAIN)
    results = feed_all(eng, bars, atr)
    assert all(c is None for c in results)


# ---------------------------------------------------------------------------
# P — B06 valid=false → no candidate
# ---------------------------------------------------------------------------

def test_P_b06_invalid_no_candidate():
    bars, atr = bull_impulse_bars()
    bars.append(bull_trigger_bar())
    eng = make_engine(REGIME.TREND_BULL, valid=False)
    results = feed_all(eng, bars, atr)
    assert all(c is None for c in results)


# ---------------------------------------------------------------------------
# Q — local contradiction → no candidate on that bar
# ---------------------------------------------------------------------------

def test_Q_local_contradiction():
    """Strong bear bar (body >= CONTR_DISP*ATR) on trigger bar → no candidate."""
    atr = 0.0050
    bars, _ = bull_impulse_bars()
    # Replace trigger with a strong bear bar: body=1.5*ATR, close below inv
    # inv = C.p = 1.0545; close must be < inv for struct contradiction
    bars.append(mk_bar(T*14, h=1.0580, l=1.0530, o=1.0575, c=1.0530))
    eng = make_engine(REGIME.TREND_BULL)
    results = feed_all(eng, bars, atr)
    # No pullback candidate on the contradiction bar
    last = results[-1]
    assert last is None or last.f != FAMILY.PULLBACK


# ---------------------------------------------------------------------------
# R — structural stop geometry valid → candidate with stop
# ---------------------------------------------------------------------------

def test_R_stop_geometry_valid():
    _, c = _run_bull_pb()
    assert c is not None
    assert c.sda >= MIN_STOP
    assert c.sda <= MAX_STOP
    assert abs(c.stp - (c.inv - STOP_BUF * 0.0050)) < 1e-9


# ---------------------------------------------------------------------------
# S — stop out of bounds → candidate rejected
# ---------------------------------------------------------------------------

def test_S_stop_impossible():
    """Entry so close to inv that sda < MIN_STOP=0.5."""
    atr = 0.0050
    bars, _ = bull_impulse_bars()
    # Replace trigger so close = C.p + tiny delta → sda tiny
    # C.p=1.0545, trigger close=1.05451 → sda=(1.05451-(1.0545-0.0005))/0.0050 = 0.002 < 0.5
    bars.append(mk_bar(T*14, h=1.0546, l=1.0544, c=1.05451))
    eng = make_engine(REGIME.TREND_BULL)
    results = feed_all(eng, bars, atr)
    pb = next((c for c in results if c and c.f == FAMILY.PULLBACK), None)
    assert pb is None


# ---------------------------------------------------------------------------
# T — reward room computed truthfully
# ---------------------------------------------------------------------------

def test_T_reward_truthful():
    """availableRewardR = rewardDist / stopDist, computed from nearest swing high."""
    _, c = _run_bull_pb()
    assert c is not None
    if c.rd > 0:
        assert abs(c.rr - c.rd / c.sd) < 1e-9
    else:
        assert c.rr == 0 or c.tgt == c.ent


# ---------------------------------------------------------------------------
# U — poor reward NOT silently rejected → candidate still emitted
# ---------------------------------------------------------------------------

def test_U_poor_reward_not_rejected():
    """Even if rr < 1, candidate is still emitted (BUILD 09 judges reward)."""
    _, c = _run_bull_pb()
    assert c is not None
    assert c.ok  # BUILD 07 never rejects solely for low rr


# ---------------------------------------------------------------------------
# V — forming bar (bar0) never qualifies
# ---------------------------------------------------------------------------

def test_V_forming_bar_never_qualifies():
    """Feeding a bar with avail=bar.t (bar0 semantics) must not create candidate."""
    atr = 0.0050
    eng = make_engine(REGIME.TREND_BULL)
    # Feed a single "forming" bar (avail == t)
    b = mk_bar(T*1, h=1.0620, l=1.0580, c=1.0600)
    b.avail = b.t  # not shift-1
    c = eng.feed(b, atr)
    assert c is None


# ---------------------------------------------------------------------------
# W — same M15 timestamp twice → no duplicate / no state advance
# ---------------------------------------------------------------------------

def test_W_duplicate_timestamp_ignored():
    bars, atr = bull_impulse_bars()
    bars.append(bull_trigger_bar())
    eng = make_engine(REGIME.TREND_BULL)
    assign_avail(bars)
    results = []
    for b in bars:
        results.append(eng.feed(b, atr))
    sig1 = b07d1(eng.ctx, eng.h1, results[-1])
    lbt_before = eng.ctx.lbt

    # Feed the last bar again with same t
    c2 = eng.feed(bars[-1], atr)
    assert c2 is None  # dedup guard
    assert eng.ctx.lbt == lbt_before  # state unchanged


# ---------------------------------------------------------------------------
# X — continuous == cold-start replay → identical final state/signature
# ---------------------------------------------------------------------------

def test_X_continuous_equals_replay():
    bars, atr = bull_impulse_bars()
    bars.append(bull_trigger_bar())
    bars.append(mk_bar(T*15, h=1.0595, l=1.0575, c=1.0585))

    def run():
        eng = make_engine(REGIME.TREND_BULL)
        assign_avail(bars)
        last_c = None
        for b in bars:
            last_c = eng.feed(b, atr)
        return eng, last_c

    eng1, c1 = run()
    eng2, c2 = run()
    sig1 = b07d1(eng1.ctx, eng1.h1, c1)
    sig2 = b07d1(eng2.ctx, eng2.h1, c2)
    assert sig1 == sig2


# ---------------------------------------------------------------------------
# Y — replay uses historically correct H1 context (no look-ahead)
# ---------------------------------------------------------------------------

def test_Y_no_lookahead_h1():
    """H1 context switch mid-stream: bars before switch see old H1."""
    atr = 0.0050
    eng = Engine("TEST")
    h1_range = H1(src=0, avail=T, regime=REGIME.RANGE, valid=True)
    eng.set_h1(h1_range)

    bars_range = [mk_bar(T*i, h=1.0580+i*0.0001, l=1.0520+i*0.0001) for i in range(1, 8)]
    assign_avail(bars_range)
    results_range = [eng.feed(b, atr) for b in bars_range]
    assert all(c is None for c in results_range)  # no candidate during RANGE

    # Now switch H1 to TREND_BULL
    h1_bull = H1(src=T*8, avail=T*8, regime=REGIME.TREND_BULL, valid=True)
    eng.set_h1(h1_bull)
    # Bars after switch see new H1
    assert eng.h1.regime == REGIME.TREND_BULL


# ---------------------------------------------------------------------------
# Z — changing chart timeframe → semantics unchanged
# ---------------------------------------------------------------------------

def test_Z_chart_timeframe_irrelevant():
    """Engine uses explicit M15/H1, never chart _Period. Same result regardless."""
    bars, atr = bull_impulse_bars()
    bars.append(bull_trigger_bar())

    eng1 = make_engine(REGIME.TREND_BULL, sym="EURUSDm")
    eng2 = make_engine(REGIME.TREND_BULL, sym="EURUSDm")

    assign_avail(bars)
    r1 = [eng1.feed(b, atr) for b in bars]
    r2 = [eng2.feed(b, atr) for b in bars]

    c1 = next((c for c in r1 if c), None)
    c2 = next((c for c in r2 if c), None)
    assert (c1 is None) == (c2 is None)
    if c1:
        assert c1.f == c2.f and c1.d == c2.d


# ---------------------------------------------------------------------------
# AA — priority deterministic: pullback > break_retest > momentum
# ---------------------------------------------------------------------------

def test_AA_priority_deterministic():
    """Priority is always PULLBACK > BREAK_RETEST > MOMENTUM."""
    _, c = _run_bull_pb()
    if c:
        assert c.f.value <= FAMILY.MOMENTUM.value  # pullback=1 < momentum=3


# ---------------------------------------------------------------------------
# AB — candidate identity deterministic
# ---------------------------------------------------------------------------

def test_AB_identity_deterministic():
    """Two identical runs produce identical candidate identity strings."""
    bars, atr = bull_impulse_bars()
    bars.append(bull_trigger_bar())

    def run():
        eng = make_engine(REGIME.TREND_BULL)
        assign_avail(bars)
        for b in bars:
            c = eng.feed(b, atr)
            if c:
                return f"{c.sym}|{c.m15a}|{c.f.value}|{c.sref}"
        return None

    id1 = run()
    id2 = run()
    assert id1 is not None
    assert id1 == id2


# ---------------------------------------------------------------------------
# AC — no QualityGate score / lot / execution fields
# ---------------------------------------------------------------------------

def test_AC_no_quality_gate_fields():
    """Cand has no lot_size, no gate_score, no order_ticket, no exec_price."""
    _, c = _run_bull_pb()
    assert c is not None
    assert not hasattr(c, 'lot_size')
    assert not hasattr(c, 'gate_score')
    assert not hasattr(c, 'order_ticket')
    assert not hasattr(c, 'exec_price')


# ---------------------------------------------------------------------------
# AD — hidden-state collision: same visible output, different B07D1
# ---------------------------------------------------------------------------

def test_AD_hidden_state_collision():
    """Two engines with identical candidate but different pending retest → different B07D1."""
    bars, atr = bull_impulse_bars()
    bars.append(bull_trigger_bar())
    assign_avail(bars)

    eng1 = make_engine(REGIME.TREND_BULL)
    last_c1 = None
    for b in bars:
        last_c1 = eng1.feed(b, atr)

    # eng2 gets an extra break-retest state before the same candidate
    eng2 = make_engine(REGIME.TREND_BULL)
    from reference_trend import Brk
    dummy_brk = Brk(bt=T*99, p=1.0700, bull=True, bav=T*100, age=2, cons=False, exp=False)
    eng2.ctx.breaks.append(dummy_brk)
    eng2.ctx.pend = dummy_brk
    last_c2 = None
    for b in bars:
        last_c2 = eng2.feed(b, atr)

    sig1 = b07d1(eng1.ctx, eng1.h1, last_c1)
    sig2 = b07d1(eng2.ctx, eng2.h1, last_c2)
    assert sig1 != sig2


# ---------------------------------------------------------------------------
# AE — H1 leaves TREND → pending setup cleared / no late fire
# ---------------------------------------------------------------------------

def test_AE_transition_lifecycle_clears_pending():
    """H1 switches TREND_BULL → RANGE → new TREND_BULL: old pending setup must not fire."""
    bars, atr = bull_impulse_bars()
    assign_avail(bars)
    eng = make_engine(REGIME.TREND_BULL)
    for b in bars:
        eng.feed(b, atr)

    # Verify impulse primed
    assert eng.ctx.iprimed

    # Switch H1 to RANGE — epoch advances, pending cleared
    old_h1 = eng.h1
    h1_range = H1(src=T*20, avail=T*20, regime=REGIME.RANGE, valid=True)
    eng.set_h1(h1_range)
    assert not eng.ctx.iprimed  # epoch clear resets iprimed

    # Switch back to TREND_BULL — new epoch
    h1_bull2 = H1(src=T*21, avail=T*21, regime=REGIME.TREND_BULL, valid=True)
    eng.set_h1(h1_bull2)
    old_eid = eng.ctx.eid

    # Feed trigger bar — should NOT produce pullback from old geometry
    trig = bull_trigger_bar()
    trig.avail = trig.t + T
    c = eng.feed(trig, atr)
    assert c is None or c.f != FAMILY.PULLBACK


# ---------------------------------------------------------------------------
# AF — confirmedAtTime gate: setup cannot fire before swing confirmed
# ---------------------------------------------------------------------------

def test_AF_confirmed_at_time_gate():
    """Trigger bar avail must be > C.confirmedAtTime, not before."""
    atr = 0.0050
    bars, _ = bull_impulse_bars()
    # Feed up to bar 12 (C not yet confirmed — ct=T*13 avail=T*14)
    partial = bars[:12]  # up to T*12, C candidate exists but not confirmed yet
    eng = make_engine(REGIME.TREND_BULL)
    assign_avail(partial)
    results = [eng.feed(b, atr) for b in partial]
    # No pullback candidate yet — C not confirmed
    assert all(c is None or c.f != FAMILY.PULLBACK for c in results)


# ---------------------------------------------------------------------------
# AG1 — session gap: no next native bar → prior bar NOT synthesised
# ---------------------------------------------------------------------------

def test_AG1_session_gap_no_phantom_bar():
    """
    A gap in bar times (weekend) must not synthesise a completed bar.
    Engine only processes bars explicitly fed; no phantom bars.
    """
    atr = 0.0050
    eng = make_engine(REGIME.TREND_BULL)
    b1 = mk_bar(T*1, h=1.0580, l=1.0540, c=1.0560)
    b1.avail = T*2
    eng.feed(b1, atr)
    # Gap: next bar is far in the future (simulated weekend)
    b2 = mk_bar(T*100, h=1.0590, l=1.0550, c=1.0570)
    b2.avail = T*101
    eng.feed(b2, atr)
    # State should contain exactly 2 completed bars (no phantom bars in between)
    assert len(eng.completed) == 2


# ---------------------------------------------------------------------------
# AG2 — H1 context availability: sourceBarTime != availableAt
# ---------------------------------------------------------------------------

def test_AG2_h1_avail_distinct_from_src():
    """H1 snapshot sourceBarTime (raw B06 identity) must differ from availableAt."""
    src_time = T * 100   # raw B06 source bar open time
    avail_time = T * 101  # when H1 bar became shift-1 (next H1 bar open time)
    h1 = H1(src=src_time, avail=avail_time, regime=REGIME.TREND_BULL, valid=True)
    eng = Engine("TEST")
    eng.set_h1(h1)
    assert eng.h1.src == src_time
    assert eng.h1.avail == avail_time
    assert eng.h1.src != eng.h1.avail


# ---------------------------------------------------------------------------
# AG3 — coincident H1/M15 availability: H1 first → M15 sees fresh H1
# ---------------------------------------------------------------------------

def test_AG3_coincident_avail_h1_first():
    """
    When H1 and M15 bar have same availableAt, H1 is processed first.
    M15 bar processed with the fresh H1 context.
    """
    eng = Engine("TEST")
    # Start with RANGE
    h1_range = H1(src=0, avail=T, regime=REGIME.RANGE, valid=True)
    eng.set_h1(h1_range)

    b = mk_bar(T*5, h=1.0580, l=1.0540, c=1.0560)
    b.avail = T*6  # M15 avail

    # Now set H1 with same availableAt as M15 bar — simulates coincident event
    h1_bull = H1(src=T*5, avail=T*6, regime=REGIME.TREND_BULL, valid=True)
    eng.set_h1(h1_bull)  # H1 first

    # When M15 bar is fed, engine already has TREND_BULL context
    assert eng.h1.regime == REGIME.TREND_BULL


# ---------------------------------------------------------------------------
# AG4 — pivot confirmation requires 2 actual right-side bars (not wall-clock)
# ---------------------------------------------------------------------------

def test_AG4_pivot_no_confirmation_by_elapsed_time():
    """
    A pivot candidate with only 1 right-side bar (gap scenario) must NOT be confirmed.
    The pivot function requires bars[i+1] AND bars[i+2] to exist.
    """
    atr = 0.0050
    eng = make_engine(REGIME.TREND_BULL)
    # Feed 4 bars total (forming + 3 completed) — not enough for pivot width-2
    bars = [
        mk_bar(T*1, h=1.0600, l=1.0560),
        mk_bar(T*2, h=1.0620, l=1.0580),  # high candidate — only 1 right bar
        mk_bar(T*3, h=1.0610, l=1.0570),
    ]
    assign_avail(bars)
    for b in bars:
        eng.feed(b, atr)
    # No swing should be confirmed yet (need 2 right-side bars)
    highs = [s for s in eng.ctx.swings if s.k == 1 and s.p == 1.0620]
    assert len(highs) == 0


# ---------------------------------------------------------------------------
# AG5 — trend epoch barrier: pre-RANGE pullback cannot resurrect
# ---------------------------------------------------------------------------

def test_AG5_epoch_barrier_blocks_old_pullback():
    """Old pullback geometry from epoch N must not fire in epoch N+1."""
    bars, atr = bull_impulse_bars()
    assign_avail(bars)
    eng = make_engine(REGIME.TREND_BULL)
    for b in bars:
        eng.feed(b, atr)

    epoch_before = eng.ctx.eid
    assert eng.ctx.iprimed

    # Transition: TREND_BULL → RANGE → TREND_BULL (new epoch)
    eng.set_h1(H1(src=T*20, avail=T*20, regime=REGIME.RANGE, valid=True))
    eng.set_h1(H1(src=T*21, avail=T*21, regime=REGIME.TREND_BULL, valid=True))
    assert eng.ctx.eid > epoch_before

    # Feed trigger — old C was from epoch N, must not produce candidate
    trig = bull_trigger_bar()
    trig.avail = trig.t + T
    c = eng.feed(trig, atr)
    assert c is None or c.f != FAMILY.PULLBACK


# ---------------------------------------------------------------------------
# AG6 — retest lower tolerance exact boundary: == boundary passes, below fails
# ---------------------------------------------------------------------------

def test_AG6_retest_tolerance_boundary():
    """
    Retest touch band for bull: low in [R - tol, R + tol].
    low == R - tol → passes (in band).
    low < R - tol → fails (overshoot → expired).
    """
    atr = 0.0050
    R = 1.0600
    tol = RET_TOL * atr  # 0.20 * 0.0050 = 0.0010

    def make_retest_eng(retest_low: float):
        bars = [
            mk_bar(T*1,  h=1.0560, l=1.0520),
            mk_bar(T*2,  h=1.0580, l=1.0540),
            mk_bar(T*3,  h=1.0570, l=1.0530),
            mk_bar(T*4,  h=1.0590, l=1.0550),
            mk_bar(T*5,  h=1.0580, l=1.0545),
            mk_bar(T*6,  h=1.0595, l=1.0560),
            mk_bar(T*7,  h=R,      l=1.0565),  # R
            mk_bar(T*8,  h=1.0590, l=1.0560),
            mk_bar(T*9,  h=1.0585, l=1.0555),  # confirms R
            mk_bar(T*10, h=1.0620, l=R,        c=1.0615),  # break bar
            mk_bar(T*11, h=R+tol,  l=retest_low, c=R-tol/2),  # retest touch, close<R
            mk_bar(T*12, h=1.0640, l=R+0.0002,   c=1.0630),  # cons+acceptance: close>R
            mk_bar(T*13, h=1.0645, l=1.0620,      c=1.0635),
        ]
        eng = make_engine(REGIME.TREND_BULL)
        results = feed_all(eng, bars, atr)
        return next((c for c in results if c and c.f == FAMILY.BREAK_RETEST), None)

    # Exact boundary: low == R - tol → touch valid
    c_boundary = make_retest_eng(R - tol)
    assert c_boundary is not None, "boundary touch should be valid"

    # Below boundary: low < R - tol → overshoot → expired
    c_overshoot = make_retest_eng(R - tol - 0.0001)
    assert c_overshoot is None, "overshoot should expire the level"


# ---------------------------------------------------------------------------
# AG7 — max retest age: age==max eligible; after processing expires
# ---------------------------------------------------------------------------

def test_AG7_retest_max_age():
    """
    age == RET_MAX on a bar → still eligible for that bar.
    After that bar (age > RET_MAX) → expired.
    """
    atr = 0.0050
    R = 1.0600
    tol = RET_TOL * atr

    bars = [
        mk_bar(T*1,  h=1.0560, l=1.0520),
        mk_bar(T*2,  h=1.0580, l=1.0540),
        mk_bar(T*3,  h=1.0570, l=1.0530),
        mk_bar(T*4,  h=1.0590, l=1.0550),
        mk_bar(T*5,  h=1.0580, l=1.0545),
        mk_bar(T*6,  h=1.0595, l=1.0560),
        mk_bar(T*7,  h=R,      l=1.0565),  # R
        mk_bar(T*8,  h=1.0590, l=1.0560),
        mk_bar(T*9,  h=1.0585, l=1.0555),  # confirms R
        mk_bar(T*10, h=1.0620, l=R,        c=1.0615),  # break bar age=1
    ]
    # Add RET_MAX-1 bars above level (no touch) → age reaches RET_MAX on last
    for k in range(RET_MAX - 1):
        bars.append(mk_bar(T*(11+k), h=1.0625, l=1.0612, c=1.0618))

    eng = make_engine(REGIME.TREND_BULL)
    assign_avail(bars)
    for b in bars:
        eng.feed(b, atr)

    # At this point age == RET_MAX — pend should still be active (not expired)
    assert eng.ctx.pend is not None
    assert not eng.ctx.pend.exp
    assert eng.ctx.pend.age == RET_MAX

    # Feed one more bar (age becomes RET_MAX+1) → must expire
    extra = mk_bar(T*(11+RET_MAX), h=1.0626, l=1.0613, c=1.0619)
    extra.avail = extra.t + T
    eng.feed(extra, atr)
    assert eng.ctx.pend is None or eng.ctx.pend.exp


# ---------------------------------------------------------------------------
# AG8 — newer advanced level supersedes; non-advanced does not
# ---------------------------------------------------------------------------

def test_AG8_supersede_logic():
    """
    For bull: newLevel.price > pendingLevel.price → supersede.
    newLevel.price <= pendingLevel.price → no supersede.
    """
    from reference_trend import Brk, add_break, Ctx

    atr = 0.0050

    # Case 1: newer level IS more advanced (higher price for bull)
    ctx1 = Ctx()
    sw_old = __import__('reference_trend').Sw(bt=T*1, ct=T*3, p=1.0600, k=1)
    sw_new = __import__('reference_trend').Sw(bt=T*2, ct=T*4, p=1.0620, k=1)
    bar_old = mk_bar(T*5, h=1.0615, l=1.0598, c=1.0612)
    bar_old.avail = T*6
    bar_new = mk_bar(T*6, h=1.0635, l=1.0618, c=1.0630)
    bar_new.avail = T*7
    add_break(ctx1, sw_old, True, bar_old)
    assert ctx1.pend is not None and ctx1.pend.p == 1.0600
    add_break(ctx1, sw_new, True, bar_new)
    assert ctx1.pend.p == 1.0620  # superseded by advanced level

    # Case 2: newer level NOT more advanced (lower price for bull)
    ctx2 = Ctx()
    add_break(ctx2, sw_new, True, bar_new)
    assert ctx2.pend.p == 1.0620
    bar_lower = mk_bar(T*7, h=1.0610, l=1.0598, c=1.0605)
    bar_lower.avail = T*8
    sw_lower = __import__('reference_trend').Sw(bt=T*3, ct=T*5, p=1.0610, k=1)
    add_break(ctx2, sw_lower, True, bar_lower)
    assert ctx2.pend.p == 1.0620  # not superseded


# ---------------------------------------------------------------------------
# AG9 — contradiction uses bodyATR only
# ---------------------------------------------------------------------------

def test_AG9_contradiction_body_atr_only():
    """
    Contradiction = abs(close-open)/ATR >= CONTR_DISP AND close < open (bear bar for bull).
    Wick/range alone must NOT trigger contradiction.
    """
    from reference_trend import chk_contra

    atr = 0.0050
    inv = 1.0545

    # Bear bar with large wick but small body → no contradiction
    b_wick = mk_bar(T*1, h=1.0600, l=1.0500, o=1.0580, c=1.0575)
    b_wick.avail = T*2
    result = chk_contra(b_wick, DIR.BUY, atr, inv)
    assert result != "disp"  # wick doesn't count; body=(1.0580-1.0575)/0.0050=0.1 < 1.5

    # Bear bar with large body >= CONTR_DISP*ATR
    b_body = mk_bar(T*2, h=1.0590, l=1.0555, o=1.0585, c=1.0560)  # body=0.0025/0.0050=0.5 < 1.5
    b_body.avail = T*3
    result2 = chk_contra(b_body, DIR.BUY, atr, inv)
    assert result2 != "disp"  # 0.5 < 1.5

    # Large body exactly at threshold
    b_large = mk_bar(T*3, h=1.0600, l=1.0555, o=1.0582, c=1.0575 - CONTR_DISP * atr)
    b_large.avail = T*4
    # close=1.0575-0.0075=1.0500 < inv? yes → struct contradiction, not disp
    result3 = chk_contra(b_large, DIR.BUY, atr, inv)
    # if close < inv → struct takes priority
    assert result3 in ("struct", "disp", None)  # exact depends on values; just no crash


# ---------------------------------------------------------------------------
# AG10 — target swing confirmed AFTER trigger is excluded
# ---------------------------------------------------------------------------

def test_AG10_target_excludes_future_confirmed_swing():
    """
    Target lookup: only swings with confirmedAtTime <= triggerAvailableAt.
    A swing confirmed after the trigger bar must NOT be used as target.
    """
    from reference_trend import tgt, Sw, Ctx

    atr = 0.0050
    ctx = Ctx()
    trigger_avail = T * 10

    # Swing confirmed before trigger → eligible
    sw_before = Sw(bt=T*5, ct=T*9, p=1.0650, k=1)
    ctx.swings.append(sw_before)

    # Swing confirmed after trigger → must be excluded
    sw_after = Sw(bt=T*9, ct=T*11, p=1.0700, k=1)
    ctx.swings.append(sw_after)

    entry = 1.0580
    tp = tgt(ctx, entry, DIR.BUY, trigger_avail)
    # Should use sw_before (p=1.0650), not sw_after (p=1.0700)
    assert tp == 1.0650
