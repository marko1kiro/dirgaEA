"""Small executable specifications for the forensic remediation invariants.

These models deliberately abstract terminal APIs; source-contract tests bind the
same invariants to production MQL. They are not presented as native MT5 proof.
"""
from dataclasses import dataclass, replace
from enum import Enum, auto
from statistics import median


class Lifecycle(Enum):
    IDLE = auto(); PENDING = auto(); PARTIAL = auto(); TIMEOUT = auto(); BLOCKED = auto(); CONFIRMED = auto(); REJECTED = auto()


class GenerationLock:
    """One signed generation: positive=owned, non-positive=released."""
    def __init__(self): self.value = 0; self.changed = 0
    def cas(self, expected, replacement, now):
        if self.value != expected: return False
        self.value, self.changed = replacement, now
        return True
    def acquire(self, now, lease):
        state = self.value
        if state > 0 and now - self.changed < lease: return None
        generation = abs(state) + 1
        return generation if self.cas(state, generation, now) else None
    def heartbeat(self, generation, now):
        nxt = generation + 1
        return nxt if self.cas(generation, nxt, now) else None
    def release(self, generation, now):
        return self.cas(generation, -(generation + 1), now)


@dataclass
class SubmissionJournal:
    state: str = "clear"
    lifecycle: Lifecycle = Lifecycle.IDLE
    def begin(self): self.state, self.lifecycle = "unresolved", Lifecycle.PENDING
    def timeout(self): self.state, self.lifecycle = "timeout", Lifecycle.TIMEOUT
    def restart(self):
        if self.state == "clear": self.lifecycle = Lifecycle.IDLE
        elif self.state in {"unresolved", "timeout"}: self.lifecycle = Lifecycle.BLOCKED
        else: self.lifecycle = Lifecycle.BLOCKED
    @property
    def entry_blocked(self):
        return self.state != "clear" or self.lifecycle in {Lifecycle.PENDING, Lifecycle.PARTIAL, Lifecycle.TIMEOUT, Lifecycle.BLOCKED}
    def evidence(self, terminal):
        if terminal not in {"fill", "reject"}: return False
        self.state = "clear"
        self.lifecycle = Lifecycle.CONFIRMED if terminal == "fill" else Lifecycle.REJECTED
        return True


def adjusted_daily_loss(baseline_equity, equity, external_cashflow):
    return max(0.0, baseline_equity - (equity - external_cashflow))


def lifecycle_streak(lifecycles):
    """Rows are (closed, [entry/exit economics]); partial rows are ignored."""
    losses = wins = 0
    for closed, economics in lifecycles:
        if not closed: continue
        net = sum(economics)
        if net < 0: losses, wins = losses + 1, 0
        elif net > 0: wins, losses = wins + 1, 0
    return losses, wins


class News(Enum): CLEAR=auto(); LOCK=auto(); SHOCK=auto(); RECOVERY=auto(); UNKNOWN=auto()

def news_state(now, events, coverage, fetch_ok=True):
    if not fetch_ok or coverage is None or coverage[0] > now-2700 or coverage[1] < now+1800: return News.UNKNOWN
    state = News.CLEAR
    for event in events:
        d = event-now
        if 0 <= d <= 1800: state = News.LOCK
        elif -900 <= d < 0 and state != News.LOCK: state = News.SHOCK
        elif -2700 <= d < -900 and state == News.CLEAR: state = News.RECOVERY
    return state


def validate_stop(direction, sl, tp, bid, ask, distance):
    if direction == "buy": return sl <= bid-distance and (tp == 0 or tp >= ask+distance)
    if direction == "sell": return sl >= ask+distance and (tp == 0 or tp <= bid-distance)
    return False


def classify_atr(raw_ratio):
    if raw_ratio < .75: return "low"
    if raw_ratio < 1.25: return "normal"
    if raw_ratio < 1.75: return "high"
    return "extreme"


@dataclass(frozen=True)
class Candidate:
    regime: str; family: str; direction: str; h1_source: int; h1_available: int
    m15_available: int; reference: int; entry: float; stop: float; target: float; extension_reference: float

_ALLOWED = {
    "trend_bull": {("pullback","buy"), ("break_retest","buy"), ("momentum","buy")},
    "trend_bear": {("pullback","sell"), ("break_retest","sell"), ("momentum","sell")},
    "range": {("range_sweep","buy"), ("range_sweep","sell")},
    "breakout_bull": {("breakout_direct","buy")}, "breakout_bear": {("breakout_direct","sell")},
}
_PRIORITY = {"break_retest": 30, "pullback": 20, "momentum": 10}

def arbitrate(candidates, regime, source, available):
    valid = [c for c in candidates if c.regime == regime and c.h1_source == source and c.h1_available == available and (c.family,c.direction) in _ALLOWED.get(regime,set())]
    if not valid: return None
    return sorted(valid, key=lambda c: (-_PRIORITY.get(c.family,100), c.m15_available, c.reference, c.family))[0]


def finalize(c, bid, ask, atr):
    entry = ask if c.direction == "buy" else bid
    if c.direction == "buy":
        if not c.stop < entry < c.target: return None
        extension = (entry-c.extension_reference)/atr
    else:
        if not c.target < entry < c.stop: return None
        extension = (c.extension_reference-entry)/atr
    if not 0 <= extension < 2.5: return None
    return replace(c, entry=entry), abs(c.target-entry)/abs(entry-c.stop), extension


class SpreadWindow:
    def __init__(self, values=()): self.values=list(values)
    def allows(self, current, ratio=2.0):
        return len(self.values)<5 or current/median(self.values) <= ratio
    def epilogue(self, current): self.values=(self.values+[current])[-50:]


class SwingFifo:
    def __init__(self, cap=256): self.cap=cap; self.bars=[]; self.swings=[]
    def feed(self, high, low):
        self.bars.append((high,low))
        if len(self.bars) < 5: return
        p=len(self.bars)-3; window=self.bars[p-2:p+3]
        if all(self.bars[p][0] > x[0] for i,x in enumerate(window) if i != 2): self.swings.append((p,"high",self.bars[p][0]))
        if all(self.bars[p][1] < x[1] for i,x in enumerate(window) if i != 2): self.swings.append((p,"low",self.bars[p][1]))
        self.swings=self.swings[-self.cap:]


class InitialStopStore:
    def __init__(self): self.values={}
    def save(self, account, symbol, magic, identifier, sl): self.values[(account,symbol,magic,identifier)]=sl
    def close(self, key, still_live):
        if not still_live: self.values.pop(key,None)
