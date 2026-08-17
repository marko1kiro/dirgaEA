"""BUILD 07 reference trend strategy — independently derived from the locked spec.

Mirrors docs/specs/2026-08-17-build-07-m15-trend-strategy-design.md.
Consumes locked B06 H1 regime context + M15 completed bars.
Produces at most ONE TradeCandidate per completed M15 bar.

No MQL5 import. No execution/trading/quality-gate/risk logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class REGIME(IntEnum):
    TREND_BULL = 0; TREND_BEAR = 1; RANGE = 2
    BREAKOUT_BULL = 3; BREAKOUT_BEAR = 4; UNCERTAIN = 5

class RQUAL(IntEnum):
    WEAK = 0; NORMAL = 1; STRONG = 2

class FAMILY(IntEnum):
    NONE = 0; PULLBACK = 1; BREAK_RETEST = 2; MOMENTUM = 3

class DIR(IntEnum):
    NONE = 0; BUY = 1; SELL = 2


# ---------------------------------------------------------------------------
# Constants (spec §21)
# ---------------------------------------------------------------------------

ZONE_LO = 0.33; ZONE_HI = 0.66
CONTR_DISP = 1.5; TGT_LOOKBACK = 8; MOM_LB = 3; M15_SEC = 900
IMP_MIN = 1.0; PB_MIN = 0.30; PB_MAX = 1.5
BRK_PEN = 0.10; RET_TOL = 0.20; RET_MAX = 8
STOP_BUF = 0.10; MIN_STOP = 0.5; MAX_STOP = 3.0
MAX_EXT = 2.5; MOM_MIN_D = 0.8


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass
class Bar:
    t: int; o: float=0; h: float=0; l: float=0; c: float=0; avail: int=0

@dataclass
class H1:
    src: int; avail: int; regime: REGIME=REGIME.RANGE
    qual: RQUAL=RQUAL.NORMAL; valid: bool=False

@dataclass
class Sw:
    bt: int; ct: int; p: float; k: int  # bar_time, confirm_time, price, kind

@dataclass
class Brk:
    bt: int; p: float; bull: bool; bav: int
    age: int=0; cons: bool=False; exp: bool=False

@dataclass
class Cand:
    ok: bool=False; sym: str=""; d: DIR=DIR.NONE; f: FAMILY=FAMILY.NONE
    sr: REGIME=REGIME.RANGE; sq: RQUAL=RQUAL.NORMAL
    h1a: int=0; h1s: int=0; m15t: int=0; m15a: int=0
    ent: float=0; inv: float=0; stp: float=0
    sd: float=0; sda: float=0
    tgt: float=0; rd: float=0; rr: float=0
    pbd: float=0; disp: float=0; rtd: float=0; ext: float=0
    sref: int=0; age: int=0; why: str=""; bad: str=""


# ---------------------------------------------------------------------------
# FNV-1a 64-bit
# ---------------------------------------------------------------------------

def _fnv(data: bytes) -> int:
    h = 0xCBF29CE484222325
    for b in data:
        h ^= b; h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trend(r: REGIME) -> bool:
    return r in (REGIME.TREND_BULL, REGIME.TREND_BEAR)

def _rdir(r: REGIME) -> DIR:
    return DIR.BUY if r == REGIME.TREND_BULL else (DIR.SELL if r == REGIME.TREND_BEAR else DIR.NONE)

def _llen(a: Sw, b: Sw, atr: float) -> float:
    return abs(b.p - a.p) / atr if atr > 0 else 0

def _impulse(a: Sw, b: Sw, d: DIR) -> bool:
    if d == DIR.BUY: return b.k==1 and a.k==-1 and b.p>a.p
    return b.k==-1 and a.k==1 and b.p<a.p

def _cnt(s: int, e: int, bars: List[Bar]) -> int:
    return sum(1 for b in bars if s < b.avail <= e)


# ---------------------------------------------------------------------------
# Pivot detection (spec §4.4 — chronological order, bars[0]=forming)
# ---------------------------------------------------------------------------

def pivots(bars: List[Bar]) -> List[Sw]:
    """bars[0]=forming(excluded), bars[1..]=completed. Chronological."""
    out: List[Sw] = []
    if len(bars) < 5: return out
    for i in range(2, len(bars)-2):
        hi, lo = bars[i].h, bars[i].l
        is_hi = hi>bars[i-1].h and hi>bars[i-2].h and hi>bars[i+1].h and hi>bars[i+2].h
        is_lo = lo<bars[i-1].l and lo<bars[i-2].l and lo<bars[i+1].l and lo<bars[i+2].l
        ct = bars[i+2].avail
        if is_hi: out.append(Sw(bars[i].t, ct, hi, 1))
        if is_lo: out.append(Sw(bars[i].t, ct, lo, -1))
    return out


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

@dataclass
class Ctx:
    eid: int=0; estart: int=0; edir: DIR=DIR.NONE
    swings: List[Sw]=field(default_factory=list)
    iot: int=0; iop: float=0; iet: int=0; iep: float=0; ila: float=0
    pbt: int=0; pbp: float=0; pbd: float=0; iprimed: bool=False
    pend: Optional[Brk]=None; breaks: List[Brk]=field(default_factory=list)
    lbt: int=0; la: int=0; lid: str=""


# ---------------------------------------------------------------------------
# Epoch (spec §3.1)
# ---------------------------------------------------------------------------

def epoch_chk(ctx: Ctx, o: H1, n: H1):
    ot, nt = _trend(o.regime), _trend(n.regime)
    adv = False
    if not ot and nt: adv = True
    elif ot and nt:
        od, nd = _rdir(o.regime), _rdir(n.regime)
        if od!=nd and od!=DIR.NONE and nd!=DIR.NONE: adv = True
    elif ot and not nt: adv = True
    if adv:
        ctx.eid+=1; ctx.estart=n.avail; ctx.edir=_rdir(n.regime)
        ctx.pend=None; ctx.iprimed=False


# ---------------------------------------------------------------------------
# Legs
# ---------------------------------------------------------------------------

def upd_legs(ctx: Ctx, atr: float, d: DIR):
    ctx.iprimed = False
    if len(ctx.swings)<2 or atr<=0: return
    for i in range(len(ctx.swings)-1, 0, -1):
        a, b = ctx.swings[i-1], ctx.swings[i]
        if _impulse(a, b, d) and _llen(a, b, atr)>=IMP_MIN:
            ctx.iot=a.ct; ctx.iop=a.p; ctx.iet=b.ct; ctx.iep=b.p
            ctx.ila=_llen(a, b, atr); ctx.iprimed=True
            ctx.pbt=0; ctx.pbp=0; ctx.pbd=0
            for j in range(len(ctx.swings)-1, -1, -1):
                s = ctx.swings[j]
                if s.ct<=b.ct: break
                if d==DIR.BUY and s.k==-1:
                    dep=abs(b.p-s.p)/atr
                    if PB_MIN<=dep<=PB_MAX: ctx.pbt=s.ct; ctx.pbp=s.p; ctx.pbd=dep; break
                elif d==DIR.SELL and s.k==1:
                    dep=abs(s.p-b.p)/atr
                    if PB_MIN<=dep<=PB_MAX: ctx.pbt=s.ct; ctx.pbp=s.p; ctx.pbd=dep; break
            return
    ctx.iprimed = False


# ---------------------------------------------------------------------------
# Breaks (spec §9)
# ---------------------------------------------------------------------------

def add_break(ctx: Ctx, sw: Sw, bull: bool, bar: Bar):
    for b in ctx.breaks:
        if b.bt==sw.bt: return
    nw = Brk(sw.bt, sw.p, bull, bar.avail, age=1)
    if ctx.pend and not ctx.pend.cons and not ctx.pend.exp:
        o = ctx.pend
        if o.bull==bull:
            sup = (bull and nw.p>o.p) or (not bull and nw.p<o.p)
            if sup: o.exp=True; ctx.pend=nw
            return
    ctx.pend = nw; ctx.breaks.append(nw)

def adv_ages(ctx: Ctx):
    for b in ctx.breaks:
        if not b.cons and not b.exp:
            b.age+=1
            if b.age>RET_MAX: b.exp=True
    if ctx.pend and ctx.pend.exp: ctx.pend=None

def chk_retest(ctx: Ctx, bar: Bar, atr: float):
    pr = ctx.pend
    if pr is None or pr.cons or pr.exp or atr<=0: return
    if bar.avail<=pr.bav: return
    if pr.age>RET_MAX: return
    tol = RET_TOL*atr
    if pr.bull:
        if bar.l<pr.p-tol: pr.exp=True; return
        if bar.l<=pr.p+tol and bar.c>pr.p: pr.cons=True
    else:
        if bar.h>pr.p+tol: pr.exp=True; return
        if bar.h>=pr.p-tol and bar.c<pr.p: pr.cons=True


# ---------------------------------------------------------------------------
# Contradiction (spec §13)
# ---------------------------------------------------------------------------

def chk_contra(bar: Bar, d: DIR, atr: float, inv: float) -> Optional[str]:
    if atr<=0: return None
    if d==DIR.BUY and bar.c<inv: return "struct"
    if d==DIR.SELL and bar.c>inv: return "struct"
    body = abs(bar.c-bar.o)/atr
    if d==DIR.BUY and bar.c<bar.o and body>=CONTR_DISP: return "disp"
    if d==DIR.SELL and bar.c>bar.o and body>=CONTR_DISP: return "disp"
    return None


# ---------------------------------------------------------------------------
# Target (spec §16 — confirmedAtTime <= triggerAvailableAt)
# ---------------------------------------------------------------------------

def tgt(ctx: Ctx, ent: float, d: DIR, after: int) -> float:
    best = None; cnt = 0
    for sw in reversed(ctx.swings):
        if sw.ct>after: continue
        cnt+=1
        if cnt>TGT_LOOKBACK: break
        if d==DIR.BUY and sw.k==1 and sw.p>ent:
            if best is None or sw.p<best.p: best=sw
        elif d==DIR.SELL and sw.k==-1 and sw.p<ent:
            if best is None or sw.p>best.p: best=sw
    return best.p if best else ent


# ---------------------------------------------------------------------------
# Setup evaluation
# ---------------------------------------------------------------------------

def eval_pb(ctx: Ctx, h1: H1, bars: List[Bar], atr: float, sym: str, now: int) -> Optional[Cand]:
    if not ctx.iprimed or atr<=0: return None
    d = _rdir(h1.regime)
    if d==DIR.NONE: return None
    # Find C
    c = None
    for sw in reversed(ctx.swings):
        if sw.ct<=ctx.iet: break
        if sw.ct<ctx.estart: continue
        if d==DIR.BUY and sw.k==-1: c=sw; break
        if d==DIR.SELL and sw.k==1: c=sw; break
    if c is None: return None
    # Value zone (both bounds)
    ap, bp = ctx.iop, ctx.iep
    zlo = ap+ZONE_LO*(bp-ap); zhi = ap+ZONE_HI*(bp-ap)
    if d==DIR.BUY:
        if not (zlo<=c.p<=zhi): return None
        if c.p<ap: return None
    else:
        if not (zhi<=c.p<=zlo): return None
        if c.p>ap: return None
    # Trigger: reclaim midpoint
    mid = (bp+c.p)/2
    tri = None
    for bar in bars:
        if bar.avail<=c.ct: continue
        if bar.avail>now: continue
        if d==DIR.BUY and bar.c>mid: tri=bar; break
        if d==DIR.SELL and bar.c<mid: tri=bar; break
    if tri is None: return None
    ent = tri.c; inv = c.p
    stp = inv-STOP_BUF*atr if d==DIR.BUY else inv+STOP_BUF*atr
    sd = abs(ent-stp); sda = sd/atr if atr>0 else 0
    if sda<MIN_STOP or sda>MAX_STOP: return None
    ext = abs(ent-c.p)/atr if atr>0 else 0
    if ext>=MAX_EXT: return None
    tp = tgt(ctx, ent, d, now); rd = abs(tp-ent); rr = rd/sd if sd>0 else 0
    age = _cnt(c.ct, tri.avail, bars)
    return Cand(ok=True,sym=sym,d=d,f=FAMILY.PULLBACK,sr=h1.regime,sq=h1.qual,
        h1a=h1.avail,h1s=h1.src,m15t=tri.t,m15a=tri.avail,
        ent=ent,inv=inv,stp=stp,sd=sd,sda=sda,tgt=tp,rd=rd,rr=rr,
        pbd=ctx.pbd,ext=ext,sref=c.ct,age=age,why="pullback")

def eval_br(ctx: Ctx, h1: H1, bars: List[Bar], atr: float, sym: str, now: int) -> Optional[Cand]:
    pr = ctx.pend
    if pr is None or not pr.cons or pr.exp or atr<=0: return None
    if pr.age>RET_MAX: return None
    d = _rdir(h1.regime)
    if d==DIR.NONE: return None
    # Acceptance bar
    acc = None
    for bar in bars:
        if bar.avail<=pr.bav: continue
        if bar.avail>now: continue
        if d==DIR.BUY and bar.c>pr.p: acc=bar; break
        if d==DIR.SELL and bar.c<pr.p: acc=bar; break
    if acc is None: return None
    ent = acc.c
    # Touch extreme
    tl = pr.p if d==DIR.BUY else pr.p
    th = pr.p
    for bar in bars:
        if bar.avail<=pr.bav: continue
        if d==DIR.BUY: tl=min(tl,bar.l)
        else: th=max(th,bar.h)
    inv = tl if d==DIR.BUY else th
    stp = inv-STOP_BUF*atr if d==DIR.BUY else inv+STOP_BUF*atr
    sd = abs(ent-stp); sda = sd/atr if atr>0 else 0
    if sda<MIN_STOP or sda>MAX_STOP: return None
    ext = abs(ent-pr.p)/atr if atr>0 else 0
    if ext>=MAX_EXT: return None
    rtd = abs(pr.p-inv)/atr if atr>0 else 0
    tp = tgt(ctx, ent, d, now); rd = abs(tp-ent); rr = rd/sd if sd>0 else 0
    return Cand(ok=True,sym=sym,d=d,f=FAMILY.BREAK_RETEST,sr=h1.regime,sq=h1.qual,
        h1a=h1.avail,h1s=h1.src,m15t=acc.t,m15a=acc.avail,
        ent=ent,inv=inv,stp=stp,sd=sd,sda=sda,tgt=tp,rd=rd,rr=rr,
        rtd=rtd,ext=ext,sref=pr.bt,age=pr.age,why="break_retest")

def eval_mom(ctx: Ctx, h1: H1, bars: List[Bar], atr: float, sym: str, now: int) -> Optional[Cand]:
    if atr<=0 or len(bars)<MOM_LB+1: return None
    d = _rdir(h1.regime)
    if d==DIR.NONE: return None
    # bars[-1]=newest, bars[-1-MOM_LB+1]=older
    cn = bars[-1].c; co = bars[-1-(MOM_LB-1)].c
    disp = (cn-co)/atr if d==DIR.BUY else (co-cn)/atr
    if disp<MOM_MIN_D: return None
    # Leg base
    lb = None
    for sw in reversed(ctx.swings):
        if sw.ct>now: continue
        if sw.ct<ctx.estart: continue
        if d==DIR.BUY and sw.k==-1: lb=sw; break
        if d==DIR.SELL and sw.k==1: lb=sw; break
    if lb is None: return None
    tri = bars[-1]
    ext = abs(tri.c-lb.p)/atr
    if ext>=MAX_EXT: return None
    if tri.avail<ctx.estart: return None
    ent = tri.c; inv = lb.p
    stp = inv-STOP_BUF*atr if d==DIR.BUY else inv+STOP_BUF*atr
    sd = abs(ent-stp); sda = sd/atr if atr>0 else 0
    if sda<MIN_STOP or sda>MAX_STOP: return None
    tp = tgt(ctx, ent, d, now); rd = abs(tp-ent); rr = rd/sd if sd>0 else 0
    return Cand(ok=True,sym=sym,d=d,f=FAMILY.MOMENTUM,sr=h1.regime,sq=h1.qual,
        h1a=h1.avail,h1s=h1.src,m15t=tri.t,m15a=tri.avail,
        ent=ent,inv=inv,stp=stp,sd=sd,sda=sda,tgt=tp,rd=rd,rr=rr,
        disp=disp,ext=ext,sref=lb.ct,age=1,why="momentum")


# ---------------------------------------------------------------------------
# B07D1
# ---------------------------------------------------------------------------

def b07d1(ctx: Ctx, h1: H1, c: Optional[Cand]) -> str:
    parts = []
    parts.append(f"h1src={h1.src};h1avail={h1.avail};h1regime={h1.regime.value};h1valid={int(h1.valid)};h1quality={h1.qual.value}")
    parts.append(f"epoch={ctx.eid};epochStartAvail={ctx.estart};epochDir={ctx.edir.value}")
    parts.append(f"m15barOpen={ctx.lbt};m15avail={ctx.la}")
    if c and c.ok:
        parts.append(f"family={c.f.value};dir={c.d.value};candValid=1")
        parts.append(f"entry={c.ent};inv={c.inv};stop={c.stp};target={c.tgt}")
        parts.append(f"extension={c.ext};displacement={c.disp}")
        parts.append(f"structRef={c.sref};setupAge={c.age}")
    else:
        parts.append("family=0;dir=0;candValid=0;entry=0;inv=0;stop=0;target=0;extension=0;displacement=0;structRef=0;setupAge=0")
    sw = ",".join(f"{s.k}|{s.bt}|{s.p}|{s.ct}" for s in ctx.swings)
    parts.append(f"swings={sw}")
    parts.append(f"impulse={'1' if ctx.iprimed else '0'};{ctx.iot};{ctx.iop};{ctx.iet};{ctx.iep};{ctx.ila}")
    parts.append(f"pullback={ctx.pbt};{ctx.pbp};{ctx.pbd}")
    br = ",".join(f"{b.bt}|{b.p}|{int(b.bull)}|{b.bav}|{b.age}|{int(b.cons)}|{int(b.exp)}" for b in ctx.breaks)
    parts.append(f"breaks={br}")
    if ctx.pend and not ctx.pend.exp:
        p=ctx.pend; parts.append(f"pendRetest=1;{p.bt};{p.p};{p.bav};{p.age}")
    else: parts.append("pendRetest=0")
    con = ",".join(str(b.bt) for b in ctx.breaks if b.cons or b.exp)
    parts.append(f"consumed={con}")
    parts.append(f"lastIdentity={ctx.lid}")
    return f"B07D1:{_fnv(';'.join(parts).encode('ascii')):016X}"

def cand_id(c: Cand) -> str:
    return f"{c.sym}|{c.m15a}|{c.f.value}|{c.sref}"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class Engine:
    def __init__(self, sym="EURUSDm"):
        self.sym=sym; self.ctx=Ctx(); self.h1: Optional[H1]=None; self.ph1: Optional[H1]=None
        self.completed: List[Bar]=[]  # completed bars, chronological

    def set_h1(self, h: H1):
        if self.h1 is not None: self.ph1=self.h1; epoch_chk(self.ctx, self.h1, h)
        self.h1 = h

    def feed(self, bar: Bar, atr: float) -> Optional[Cand]:
        if bar.t==self.ctx.lbt: return None
        self.ctx.lbt=bar.t; self.ctx.la=bar.avail
        self.completed.append(bar)
        adv_ages(self.ctx)

        # Build forming + completed for pivot detection (chronological)
        forming = Bar(t=bar.t-M15_SEC, avail=bar.t)
        full = [forming] + self.completed
        for p in pivots(full):
            if not any(s.bt==p.bt for s in self.ctx.swings):
                self.ctx.swings.append(p)
        self.ctx.swings.sort(key=lambda s: s.ct)

        if self.h1 and _trend(self.h1.regime):
            d = _rdir(self.h1.regime)
            upd_legs(self.ctx, atr, d)
            # Breaks: check latest completed against swings
            if self.completed:
                b = self.completed[-1]
                for sw in self.ctx.swings:
                    if sw.ct>bar.avail: continue
                    if d==DIR.BUY and sw.k==1 and b.c>sw.p+BRK_PEN*atr:
                        add_break(self.ctx, sw, True, b)
                    elif d==DIR.SELL and sw.k==-1 and b.c<sw.p-BRK_PEN*atr:
                        add_break(self.ctx, sw, False, b)
            chk_retest(self.ctx, bar, atr)
            if self.ctx.iprimed:
                inv = self.ctx.pbp if self.ctx.pbp>0 else self.ctx.iop
                if chk_contra(bar, d, atr, inv): return None

        return self._eval(atr)

    def _eval(self, atr: float) -> Optional[Cand]:
        if self.h1 is None or not _trend(self.h1.regime) or not self.h1.valid: return None
        now = self.ctx.la
        for fn in [eval_pb, eval_br, eval_mom]:
            c = fn(self.ctx, self.h1, self.completed, atr, self.sym, now)
            if c:
                ident = cand_id(c)
                if ident==self.ctx.lid: return None
                self.ctx.lid = ident
                return c
        return None
