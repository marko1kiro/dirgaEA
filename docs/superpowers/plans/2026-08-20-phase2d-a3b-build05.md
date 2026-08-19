# Phase 2D-A3B — B05 Live/Replay Parity Closure

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close B05 live/replay parity — replay initializes via ResetH1BrainInvalid, gates on .valid, removes obsolete mPersist reset, updates direction parity to challenger dwell policy, and adds deterministic parity + invalid-freeze + source invariant tests with full evidence.

**Architecture:** The replay function `RebuildRegimeFusionState()` must mirror the live UpdateH1Brain path exactly: reset each prefix result to invalid defaults, run engines, classify only if .valid, and let MomentumClassify own its own persistence transitions. Direction parity is updated so escalation (same-sign stronger, opposite-sign reversal) goes through DIR_DWELL challenger, while same-sign weaker and step-to-neutral are immediate. All changes are scoped to B05 persistence — no RegimeFusion/BUILD06/VolatilityQuality changes.

**Tech Stack:** MQL5 (MetaEditor), Python 3.12 + pytest, git, SHA256 hashing

**Base commit:** `c3235659befaff5966b3af95d7173d834737a2a1`

---

## File Map

| File | Role |
|------|------|
| `MarketBrain.mqh` | DirectionClassify updated for opposite-sign challenger dwell |
| `AdaptiveSurvivalEA.mq5` | Replay: ResetH1BrainInvalid + .valid gates + remove obsolete mPersist reset |
| `tests/build05/reference_direction.py` | Python reference updated to match new MQL5 direction policy |
| `tests/build05/test_direction.py` | Updated direction mirrors for new parity |
| `tests/build05/test_direction_challenger.py` | Updated challenger dwell tests |
| `tests/build05/test_volatility.py` | Fix step-down test |
| `tests/build05/test_vollevel_challenger.py` | Fix step-down test |
| `tests/build05/test_invalid_persistence_freeze.py` | Rewrite: caller-skip invalid event tests |
| `tests/build05/test_live_replay_parity.py` | NEW: deterministic live/replay state harness |
| `tests/build05/test_source_invariants.py` | NEW: replay .valid guards + no obsolete mPersist reset |
| `audits/2026-08-20/phase2d-a3b-build05/` | Evidence directory |

---

## Task 1: Update DirectionClassify in MQL5 for parity

**Files:**
- Modify: `MarketBrain.mqh:124-165`

Current MQL5 DirectionClassify handles same-sign escalation as challenger, but does NOT handle opposite-sign reversal as challenger. The spec says:

- NEUTRAL → directional = immediate ✓
- same-sign weaker = immediate ✓
- same-sign stronger = DIR_DWELL challenger ✓
- **opposite-sign reversal = DIR_DWELL challenger** ← MISSING
- to NEUTRAL = immediate + challenger reset ✓

Replace the `candMag * prevMag > 0` condition with a check that handles both same-sign stronger AND opposite-sign reversal.

- [ ] **Step 1: Edit DirectionClassify in MarketBrain.mqh**

```cpp
void DirectionClassify(const double score, const ENUM_DIRECTION_STATE prevState, const int dwell,
                       ENUM_DIRECTION_STATE &state, int &outDwell,
                       ENUM_DIRECTION_STATE &challenger, int &challengerDwell)
{
   const double s = BrainClampSigned(score);
   ENUM_DIRECTION_STATE cand;
   if(s >= DIR_STRONG_COMMIT) cand = DIRECTION_STRONG_BULL;
   else if(s >= DIR_COMMIT)   cand = DIRECTION_BULL;
   else if(s <= -DIR_STRONG_COMMIT) cand = DIRECTION_STRONG_BEAR;
   else if(s <= -DIR_COMMIT)  cand = DIRECTION_BEAR;
   else                       cand = DIRECTION_NEUTRAL;

   if(cand == DIRECTION_NEUTRAL) { state = cand; outDwell = 0; challenger = DIRECTION_NEUTRAL; challengerDwell = 0; return; }
   if(prevState == DIRECTION_NEUTRAL) { state = cand; outDwell = 0; challenger = DIRECTION_NEUTRAL; challengerDwell = 0; return; }
   if(cand == prevState) { state = cand; outDwell = MathMin(dwell + 1, DIR_DWELL); challenger = DIRECTION_NEUTRAL; challengerDwell = 0; return; }

   const int candMag = (cand == DIRECTION_STRONG_BULL) ? 2 :
                       (cand == DIRECTION_BULL) ? 1 :
                       (cand == DIRECTION_BEAR) ? -1 : -2;
   const int prevMag = (prevState == DIRECTION_STRONG_BULL) ? 2 :
                       (prevState == DIRECTION_BULL) ? 1 :
                       (prevState == DIRECTION_BEAR) ? -1 : -2;

   const bool challengerTrigger =
       (candMag * prevMag > 0 && MathAbs(candMag) > MathAbs(prevMag))   // same-sign stronger
       || (candMag * prevMag < 0);                                       // opposite-sign reversal

   if(challengerTrigger)
   {
      if(cand == challenger)
         challengerDwell++;
      else
      {
         challenger = cand;
         challengerDwell = 1;
      }
      if(challengerDwell >= DIR_DWELL) { state = cand; outDwell = 0; challenger = DIRECTION_NEUTRAL; challengerDwell = 0; return; }
      state = prevState; outDwell = dwell; return;
   }

   // same-sign weaker or stepping toward NEUTRAL: immediate
   challenger = DIRECTION_NEUTRAL;
   challengerDwell = 0;
   state = cand; outDwell = 0;
}
```

- [ ] **Step 2: Verify no compile errors**

Deploy to `C:\Users\dirga\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Experts\AdaptiveSurvivalEA\` and compile. Target: 0 errors / 0 warnings.

---

## Task 2: Update Python reference_direction.py to match

**Files:**
- Modify: `tests/build05/reference_direction.py`

- [ ] **Step 1: Replace direction_enum function**

```python
def direction_enum(score, prev=DIRECTION.NEUTRAL, dwell=0, challenger=None, challenger_dwell=0):
    """Return (state, dwell_count, challenger, challenger_dwell) for a single observation.

    challenger tracks the escalation/reversal candidate identity.
    challenger_dwell counts consecutive challenger bars for the same candidate.
    """
    s = max(-1.0, min(1.0, score))

    if s >= STRONG_BULL_COMMIT:
        cand = DIRECTION.STRONG_BULL
    elif s >= BULL_COMMIT:
        cand = DIRECTION.BULL
    elif s <= -STRONG_BULL_COMMIT:
        cand = DIRECTION.STRONG_BEAR
    elif s <= -BULL_COMMIT:
        cand = DIRECTION.BEAR
    else:
        cand = DIRECTION.NEUTRAL

    if cand == DIRECTION.NEUTRAL:
        return (cand, 0, DIRECTION.NEUTRAL, 0)
    if prev == DIRECTION.NEUTRAL:
        return (cand, 0, DIRECTION.NEUTRAL, 0)
    if cand == prev:
        return (cand, min(dwell + 1, DWELL), DIRECTION.NEUTRAL, 0)

    cand_mag = cand.value
    prev_mag = prev.value

    challenger_trigger = (
        (cand_mag * prev_mag > 0 and abs(cand_mag) > abs(prev_mag))
        or (cand_mag * prev_mag < 0)
    )

    if challenger_trigger:
        if cand == challenger:
            challenger_dwell += 1
        else:
            challenger = cand
            challenger_dwell = 1
        if challenger_dwell >= DWELL:
            return (cand, 0, DIRECTION.NEUTRAL, 0)
        return (prev, dwell, challenger, challenger_dwell)

    return (cand, 0, DIRECTION.NEUTRAL, 0)
```

- [ ] **Step 2: Run existing direction tests to see which break**

```bash
cd tests/build05 && python -m pytest test_direction.py test_direction_challenger.py -v
```

---

## Task 3: Fix direction tests for new parity

**Files:**
- Modify: `tests/build05/test_direction.py`
- Modify: `tests/build05/test_direction_challenger.py`

The new policy means:
- BULL → STRONG_BEAR = challenger (opposite-sign reversal), dwell increments on 2nd bar
- STRONG_BULL → BEAR = challenger, same pattern
- Same-sign weaker (STRONG_BULL → BULL) = immediate

- [ ] **Step 1: Update test_direction.py mirrors**

Add/update these specific mirrors from the spec:

```python
def test_DIRECTION_bull_to_strong_bear_reversal():
    """BULL → STRONG_BEAR #1 → remain BULL, #2 → STRONG_BEAR."""
    s1, d1, ch1, cd1 = direction_enum(0.6, prev=DIRECTION.NEUTRAL, dwell=0)
    assert s1 == DIRECTION.BULL
    s2, d2, ch2, cd2 = direction_enum(-0.85, prev=s1, dwell=d1, challenger=ch1, challenger_dwell=cd1)
    assert s2 == DIRECTION.BULL, "First STRONG_BEAR reversal: hold BULL"
    assert ch2 == DIRECTION.STRONG_BEAR
    assert cd2 == 1
    s3, d3, ch3, cd3 = direction_enum(-0.85, prev=s2, dwell=d2, challenger=ch2, challenger_dwell=cd2)
    assert s3 == DIRECTION.STRONG_BEAR, "Second STRONG_BEAR: commit"


def test_DIRECTION_strong_bull_to_bear_reversal():
    """STRONG_BULL → BEAR #1 → remain STRONG_BULL, #2 → BEAR."""
    s1, d1, ch1, cd1 = direction_enum(0.85, prev=DIRECTION.NEUTRAL, dwell=0)
    assert s1 == DIRECTION.STRONG_BULL
    s2, d2, ch2, cd2 = direction_enum(-0.6, prev=s1, dwell=d1, challenger=ch1, challenger_dwell=cd1)
    assert s2 == DIRECTION.STRONG_BULL, "First BEAR reversal: hold STRONG_BULL"
    assert ch2 == DIRECTION.BEAR
    assert cd2 == 1
    s3, d3, ch3, cd3 = direction_enum(-0.6, prev=s2, dwell=d2, challenger=ch2, challenger_dwell=cd2)
    assert s3 == DIRECTION.BEAR, "Second BEAR: commit"


def test_DIRECTION_same_sign_weaker_immediate():
    """STRONG_BULL → BULL = immediate (same-sign weaker)."""
    s1, d1, _, _ = direction_enum(0.85, prev=DIRECTION.NEUTRAL, dwell=0)
    assert s1 == DIRECTION.STRONG_BULL
    s2, d2, _, _ = direction_enum(0.6, prev=s1, dwell=d1)
    assert s2 == DIRECTION.BULL, "Same-sign weaker: immediate"
    assert d2 == 0


def test_DIRECTION_neutral_entry_immediate():
    """NEUTRAL → BULL = immediate."""
    s, d, _, _ = direction_enum(0.6, prev=DIRECTION.NEUTRAL, dwell=0)
    assert s == DIRECTION.BULL
    assert d == 0


def test_DIRECTION_bearish_mirrors():
    """Bearish mirrors: BEAR → STRONG_BULL = challenger, STRONG_BEAR → BULL = challenger."""
    s1, d1, ch1, cd1 = direction_enum(-0.6, prev=DIRECTION.NEUTRAL, dwell=0)
    assert s1 == DIRECTION.BEAR
    s2, d2, ch2, cd2 = direction_enum(0.85, prev=s1, dwell=d1, challenger=ch1, challenger_dwell=cd1)
    assert s2 == DIRECTION.BEAR, "First STRONG_BULL reversal: hold BEAR"
    assert ch2 == DIRECTION.STRONG_BULL
    s3, d3, ch3, cd3 = direction_enum(0.85, prev=s2, dwell=d2, challenger=ch2, challenger_dwell=cd2)
    assert s3 == DIRECTION.STRONG_BULL

    s4, d4, ch4, cd4 = direction_enum(-0.85, prev=DIRECTION.NEUTRAL, dwell=0)
    assert s4 == DIRECTION.STRONG_BEAR
    s5, d5, ch5, cd5 = direction_enum(0.6, prev=s4, dwell=d4, challenger=ch4, challenger_dwell=cd4)
    assert s5 == DIRECTION.STRONG_BEAR, "First BULL reversal: hold STRONG_BEAR"
    assert ch5 == DIRECTION.BULL
    s6, d6, ch6, cd6 = direction_enum(0.6, prev=s5, dwell=d5, challenger=ch5, challenger_dwell=cd5)
    assert s6 == DIRECTION.BULL


def test_DIRECTION_challenger_interruption_resets():
    """Different challenger resets dwell."""
    s1, d1, ch1, cd1 = direction_enum(0.6, prev=DIRECTION.NEUTRAL, dwell=0)
    assert s1 == DIRECTION.BULL
    s2, d2, ch2, cd2 = direction_enum(0.85, prev=s1, dwell=d1, challenger=ch1, challenger_dwell=cd1)
    assert s2 == DIRECTION.BULL
    assert ch2 == DIRECTION.STRONG_BULL and cd2 == 1
    s3, d3, ch3, cd3 = direction_enum(-0.6, prev=s2, dwell=d2, challenger=ch2, challenger_dwell=cd2)
    assert s3 == DIRECTION.BULL, "Different challenger (BEAR): hold BULL"
    assert ch3 == DIRECTION.BEAR and cd3 == 1, "Challenger changed, dwell reset to 1"
```

- [ ] **Step 2: Update test_direction_challenger.py for new mirrors**

```python
def test_DIRECTION_bull_to_strong_bear_hold():
    """BULL → STRONG_BEAR: dwell increments, then commit."""
    s, d, ch, cd = direction_enum(0.6, prev=DIRECTION.NEUTRAL, dwell=0)
    assert s == DIRECTION.BULL
    s, d, ch, cd = direction_enum(-0.85, prev=s, dwell=d, challenger=ch, challenger_dwell=cd)
    assert s == DIRECTION.BULL and cd == 1
    s, d, ch, cd = direction_enum(-0.85, prev=s, dwell=d, challenger=ch, challenger_dwell=cd)
    assert s == DIRECTION.STRONG_BEAR


def test_DIRECTION_strong_bull_to_bear_hold():
    """STRONG_BULL → BEAR: hold, then commit."""
    s, d, ch, cd = direction_enum(0.85, prev=DIRECTION.NEUTRAL, dwell=0)
    assert s == DIRECTION.STRONG_BULL
    s, d, ch, cd = direction_enum(-0.6, prev=s, dwell=d, challenger=ch, challenger_dwell=cd)
    assert s == DIRECTION.STRONG_BULL and ch == DIRECTION.BEAR and cd == 1
    s, d, ch, cd = direction_enum(-0.6, prev=s, dwell=d, challenger=ch, challenger_dwell=cd)
    assert s == DIRECTION.BEAR
```

- [ ] **Step 3: Run direction tests**

```bash
cd tests/build05 && python -m pytest test_direction.py test_direction_challenger.py -v
```

---

## Task 4: Replay parity — ResetH1BrainInvalid + .valid gates + remove obsolete mPersist reset

**Files:**
- Modify: `AdaptiveSurvivalEA.mq5:444-468`

Three changes in the replay loop:

1. Call `ResetH1BrainInvalid(replayBrain)` at the top of each iteration (after `ZeroMemory` — replace it).
2. Gate `DirectionClassify` on `replayBrain.direction.valid`.
3. Gate `MomentumClassify` + `MomentumEngine` on `replayBrain.momentum.valid`.
4. Gate `VolatilityLevelClassify` on `replayBrain.volatility.valid`.
5. **Remove** the lines:
```cpp
if(mState == MOMENTUM_EXPANDING || mState == MOMENTUM_STRONG)
    mPersist = 0;
```

- [ ] **Step 1: Edit the replay section**

Replace the current B05 replay block (lines ~444-468) with:

```cpp
      // B05 final output at prefix t (replay-local hysteresis)
      H1BrainResult replayBrain;
      ResetH1BrainInvalid(replayBrain);
      if(atrB05Ok && emaOk)
      {
         DirectionEngine(rates, emaFast, emaSlow, atrB05, count, replayBrain.direction);
         if(replayBrain.direction.valid)
         {
            DirectionClassify(replayBrain.direction.score, dState, dDwell, dState, dDwell,
                              dChallenger, dChallengerDwell);
            replayBrain.direction.state = dState;
         }
      }
      if(atrB05Ok)
      {
         MomentumEngine(rates, atrB05, adx, count, adxOk, replayBrain.momentum);
         if(replayBrain.momentum.valid)
         {
            if(momentumPrimed)
               replayBrain.momentum.strengthDelta = replayBrain.momentum.strengthScore - prevMomentumStrength;
            else
               replayBrain.momentum.strengthDelta = 0.0;
            replayBrain.momentum.strengthSlope = BrainClampSigned(replayBrain.momentum.strengthDelta);
            MomentumClassify(replayBrain.momentum.strengthScore, replayBrain.momentum.strengthSlope,
                             mState, mPersist, mState);
            replayBrain.momentum.state = mState;
            prevMomentumStrength = replayBrain.momentum.strengthScore;
            momentumPrimed = true;
         }
      }
      if(atrB05Ok)
      {
         VolatilityEngine(rates, atrB05, count, VolatilityBaselineBars, replayBrain.volatility);
         if(replayBrain.volatility.valid)
         {
            VolatilityLevelClassify(replayBrain.volatility.levelScore, vLevel, vDwell, vLevel, vDwell,
                                    vLevelChallenger, vLevelChallengerDwell);
            replayBrain.volatility.level = vLevel;
         }
         VolatilityQualityEngine(rates, atrB05, count, replayBrain.volatility);
         double evidence[5];
         evidence[0] = replayBrain.volatility.healthyScore;
         evidence[1] = replayBrain.volatility.compressionScore;
         evidence[2] = replayBrain.volatility.expansionScore;
         evidence[3] = replayBrain.volatility.chaosScore;
         evidence[4] = replayBrain.volatility.shockScore;
         const ENUM_VOLATILITY_QUALITY priorQ = vQuality;
         VolatilityQualitySelect(evidence, vQuality, vConf, vQDwell, vQuality);
         replayBrain.volatility.quality = vQuality;
         if(vQuality == priorQ)
            vQDwell = MathMin(vQDwell + 1, VOLQ_DWELL);
         else
            vQDwell = 0;
         replayBrain.volatility.qualityConfidence = evidence[(int)vQuality];
         vConf = replayBrain.volatility.qualityConfidence;
      }
```

Note: VolatilityQualityEngine and VolatilityQualitySelect remain OUTSIDE the .valid gate (BUILD06 scope, not changed here per spec). Only VolatilityLevelClassify is gated.

- [ ] **Step 2: Deploy + compile, verify 0 errors / 0 warnings**

---

## Task 5: Add live/replay state-harness test

**Files:**
- Create: `tests/build05/test_live_replay_parity.py`

- [ ] **Step 1: Write the test**

```python
import pytest
from reference_momentum import momentum_enum, MOMENTUM


def test_live_replay_momentum_persistence_identical():
    """Live model and replay model must produce identical state sequences.

    Sequence: STRONG → NORMAL candidate → NORMAL candidate
    Expected: bar1 STRONG persist=1, bar2 NORMAL persist=0
    """
    live_persist = [0]
    live_state = MOMENTUM.STRONG
    replay_persist = [0]
    replay_state = MOMENTUM.STRONG
    live_seq = []
    replay_seq = []

    inputs = [
        (0.65, 0.0),   # STRONG bar
        (0.50, 0.0),   # NORMAL candidate #1
        (0.50, 0.0),   # NORMAL candidate #2
    ]

    for strength, slope in inputs:
        live_state = momentum_enum(strength, slope, prev=live_state, persist=live_persist)
        live_seq.append((live_state, live_persist[0]))

        replay_state = momentum_enum(strength, slope, prev=replay_state, persist=replay_persist)
        replay_seq.append((replay_state, replay_persist[0]))

    assert live_seq == replay_seq, f"Live/replay diverged: {live_seq} vs {replay_seq}"
    assert live_seq[0] == (MOMENTUM.STRONG, 1), "Bar1: STRONG, persist=1"
    assert live_seq[1] == (MOMENTUM.STRONG, 1), "Bar2: still STRONG (persistence holds)"
    assert live_seq[2] == (MOMENTUM.NORMAL, 0), "Bar3: exit STRONG → NORMAL"


def test_live_replay_challenger_parity():
    """Live and replay challenger tracking must be identical."""
    from reference_direction import direction_enum, DIRECTION

    live = (DIRECTION.NEUTRAL, 0, DIRECTION.NEUTRAL, 0)
    replay = (DIRECTION.NEUTRAL, 0, DIRECTION.NEUTRAL, 0)
    live_seq = []
    replay_seq = []

    inputs = [0.6, 0.85, 0.85, -0.6, -0.85, -0.85]

    for s in inputs:
        live = direction_enum(s, prev=live[0], dwell=live[1],
                              challenger=live[2], challenger_dwell=live[3])
        replay = direction_enum(s, prev=replay[0], dwell=replay[1],
                                challenger=replay[2], challenger_dwell=replay[3])
        live_seq.append(live[:2])
        replay_seq.append(replay[:2])

    assert live_seq == replay_seq, f"Live/replay diverged: {live_seq} vs {replay_seq}"
```

- [ ] **Step 2: Run the test**

```bash
cd tests/build05 && python -m pytest test_live_replay_parity.py -v
```

---

## Task 6: Add invalid middle event + caller-skip tests

**Files:**
- Replace: `tests/build05/test_invalid_persistence_freeze.py`

The current tests don't actually simulate a caller skipping an invalid event. The spec says: challenger bar #1 → invalid domain update (caller skips classification) → challenger bar #2. The invalid update must freeze committed state + challenger identity + challenger dwell/persistence.

- [ ] **Step 1: Rewrite test_invalid_persistence_freeze.py**

```python
import pytest
from reference_momentum import momentum_enum, MOMENTUM
from reference_direction import direction_enum, DIRECTION
from reference_volatility import volatility_level_enum, VOL_LEVEL


def _caller_skipclassify_momentum(state, persist):
    """Simulate caller skipping MomentumClassify (invalid domain)."""
    return state, persist


def test_INVALID_momentum_caller_skip_freezes():
    """STRONG → low [caller skips] → low: persist must be frozen at 0, then resume."""
    state = MOMENTUM.STRONG
    persist = [0]

    state = momentum_enum(0.65, 0.0, prev=state, persist=persist)
    assert state == MOMENTUM.STRONG and persist[0] == 0

    state = momentum_enum(0.50, 0.0, prev=state, persist=persist)
    assert state == MOMENTUM.STRONG and persist[0] == 1

    # Caller skips: do NOT call MomentumClassify this bar
    # persist stays at 1, state stays STRONG (frozen)
    assert persist[0] == 1, "Persist frozen during skip"

    state = momentum_enum(0.50, 0.0, prev=state, persist=persist)
    assert state == MOMENTUM.NORMAL, "Resume: exits STRONG"
    assert persist[0] == 0


def test_INVALID_direction_caller_skip_freezes():
    """BULL challenger bar #1 [caller skips] → challenger bar #2: dwell frozen, then resume."""
    s, d, ch, cd = direction_enum(0.6, prev=DIRECTION.NEUTRAL, dwell=0)
    assert s == DIRECTION.BULL

    s, d, ch, cd = direction_enum(0.85, prev=s, dwell=d, challenger=ch, challenger_dwell=cd)
    assert s == DIRECTION.BULL and ch == DIRECTION.STRONG_BULL and cd == 1

    # Caller skips direction classify: dwell stays 1 (frozen)
    assert cd == 1, "Challenger dwell frozen during skip"

    s, d, ch, cd = direction_enum(0.85, prev=s, dwell=d, challenger=ch, challenger_dwell=cd)
    assert s == DIRECTION.STRONG_BULL, "Resume: commits STRONG_BULL"


def test_INVALID_vollevel_caller_skip_freezes():
    """HIGH challenger bar #1 [caller skips] → challenger bar #2: dwell frozen, then resume."""
    s, d, ch, cd = volatility_level_enum(1.6, prev=VOL_LEVEL.NORMAL, dwell=0)
    assert s == VOL_LEVEL.NORMAL and ch == VOL_LEVEL.HIGH and cd == 1

    # Caller skips: dwell frozen at 1
    assert cd == 1, "Challenger dwell frozen during skip"

    s, d, ch, cd = volatility_level_enum(1.6, prev=s, dwell=d, challenger=ch, challenger_dwell=cd)
    assert s == VOL_LEVEL.HIGH, "Resume: commits HIGH"
```

- [ ] **Step 2: Run the test**

```bash
cd tests/build05 && python -m pytest test_invalid_persistence_freeze.py -v
```

---

## Task 7: Fix test_VOLLEVEL_step_down_immediate

**Files:**
- Modify: `tests/build05/test_vollevel_challenger.py`

The spec says: "Fix test_VOLLEVEL_step_down_immediate so it genuinely tests committed HIGH → NORMAL in one observation according to existing policy."

Current test starts from NORMAL, which is wrong. Must start from a committed HIGH state, then observe ratio=1.0 (below LOW_RATIO) which steps down immediately.

- [ ] **Step 1: Replace the test**

```python
def test_VOLLEVEL_step_down_immediate():
    """Committed HIGH → ratio=1.0 (NORMAL): step down is immediate."""
    # Commit HIGH via challenger dwell
    s, d, ch, cd = volatility_level_enum(1.6, prev=VOL_LEVEL.NORMAL, dwell=0)
    assert s == VOL_LEVEL.NORMAL and cd == 1
    s, d, ch, cd = volatility_level_enum(1.6, prev=s, dwell=d, challenger=ch, challenger_dwell=cd)
    assert s == VOL_LEVEL.HIGH, "Committed HIGH after 2 challenger bars"

    # Step down to NORMAL is immediate
    s, d, ch, cd = volatility_level_enum(1.0, prev=s, dwell=d, challenger=ch, challenger_dwell=cd)
    assert s == VOL_LEVEL.NORMAL, "Step down: immediate"
    assert d == 0
```

- [ ] **Step 2: Run the test**

```bash
cd tests/build05 && python -m pytest test_vollevel_challenger.py -v
```

---

## Task 8: Source invariant tests — replay .valid guards + no obsolete mPersist reset

**Files:**
- Modify: `tests/build05/test_source_invariants.py`

- [ ] **Step 1: Add new invariant tests**

```python
def test_source_replay_calls_reset_h1_brain_invalid():
    """Replay must call ResetH1BrainInvalid(replayBrain) before B05 engines."""
    import re
    src = open("C:/Users/dirga/Documents/EA/AdaptiveSurvivalEA/AdaptiveSurvivalEA.mq5").read()
    pattern = r"H1BrainResult\s+replayBrain;[\s\S]*?ResetH1BrainInvalid\(replayBrain\)"
    assert re.search(pattern, src), "Replay must call ResetH1BrainInvalid(replayBrain)"


def test_source_replay_direction_gated_by_valid():
    """Replay DirectionClassify must be inside if(replayBrain.direction.valid)."""
    import re
    src = open("C:/Users/dirga/Documents/EA/AdaptiveSurvivalEA/AdaptiveSurvivalEA.mq5").read()
    pattern = r"if\s*\(\s*replayBrain\.direction\.valid\s*\)\s*\{[\s\S]*?DirectionClassify"
    assert re.search(pattern, src), "DirectionClassify must be gated by direction.valid"


def test_source_replay_momentum_gated_by_valid():
    """Replay MomentumClassify must be inside if(replayBrain.momentum.valid)."""
    import re
    src = open("C:/Users/dirga/Documents/EA/AdaptiveSurvivalEA/AdaptiveSurvivalEA.mq5").read()
    pattern = r"if\s*\(\s*replayBrain\.momentum\.valid\s*\)\s*\{[\s\S]*?MomentumClassify"
    assert re.search(pattern, src), "MomentumClassify must be gated by momentum.valid"


def test_source_replay_volatility_gated_by_valid():
    """Replay VolatilityLevelClassify must be inside if(replayBrain.volatility.valid)."""
    import re
    src = open("C:/Users/dirga/Documents/EA/AdaptiveSurvivalEA/AdaptiveSurvivalEA.mq5").read()
    pattern = r"if\s*\(\s*replayBrain\.volatility\.valid\s*\)\s*\{[\s\S]*?VolatilityLevelClassify"
    assert re.search(pattern, src), "VolatilityLevelClassify must be gated by volatility.valid"


def test_source_replay_no_obsolete_mpersist_reset():
    """Replay must NOT contain the obsolete 'if(mState == MOMENTUM_EXPANDING || mState == MOMENTUM_STRONG) mPersist = 0'."""
    src = open("C:/Users/dirga/Documents/EA/AdaptiveSurvivalEA/AdaptiveSurvivalEA.mq5").read()
    assert "mPersist = 0" not in src.split("RebuildRegimeFusionState")[1], \
        "Replay must not contain obsolete mPersist = 0 reset"
```

- [ ] **Step 2: Run source invariant tests**

```bash
cd tests/build05 && python -m pytest test_source_invariants.py -v
```

---

## Task 9: Full regression — BUILD05 + BUILD04

- [ ] **Step 1: Run full BUILD05 suite**

```bash
cd tests/build05 && python -m pytest -v --tb=short 2>&1
```

Target: 0 failed / 0 skipped / 0 deselected

- [ ] **Step 2: Run full BUILD04 suite**

```bash
cd tests/build04 && python -m pytest -v 2>&1
```

Target: 0 failed

---

## Task 10: Deploy + compile

- [ ] **Step 1: Sync all .mq5/.mqh to deployed tree**

```powershell
$workspace = "C:\Users\dirga\Documents\EA\AdaptiveSurvivalEA"
$deployed = "C:\Users\dirga\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Experts\AdaptiveSurvivalEA"
$files = @("AdaptiveSurvivalEA.mq5", "Config.mqh", "Types.mqh", "Logger.mqh", "BrokerEnvironment.mqh", "RiskEngine.mqh", "SwingStructure.mqh", "DiagnosticCollector.mqh", "MarketBrain.mqh")
foreach ($file in $files) {
    Copy-Item -Path (Join-Path $workspace $file) -Destination (Join-Path $deployed $file) -Force
}
```

- [ ] **Step 2: Compile via MetaEditor**

Target: 0 errors / 0 warnings

- [ ] **Step 3: SHA256 hash comparison (workspace vs deployed)**

Every .mq5/.mqh must match. Record in evidence file.

---

## Task 11: Evidence collection + commits

- [ ] **Step 1: Generate raw evidence files**

```bash
cd tests/build05 && python -m pytest -vv > audits/2026-08-20/phase2d-a3b-build05/build05_pytest_vv.txt 2>&1
cd tests/build04 && python -m pytest -vv > ../audits/2026-08-20/phase2d-a3b-build05/build04_pytest_vv.txt 2>&1
```

- [ ] **Step 2: Write provenance.txt**

```
Phase 2D-A3B BUILD05 — Live/Replay Parity Closure
Date: 2026-08-20
Base commit: c3235659befaff5966b3af95d7173d834737a2a1
Commit A (source+tests): <sha>
Commit B (evidence): <sha>
EX5 SHA256: <sha>
```

- [ ] **Step 3: Record ex5_sha256.txt, ex5_size.txt, compile.log, workspace_vs_deployed_sha256.txt**

- [ ] **Step 4: Git Commit A — source + tests**

```bash
git add <all source + test files>
git commit -m "phase2d-a3b-build05: Live/replay parity closure (direction parity + .valid gates + tests)"
```

- [ ] **Step 5: Record Commit A SHA**

```bash
git rev-parse HEAD
```

- [ ] **Step 6: Git Commit B — evidence only**

```bash
git add audits/2026-08-20/phase2d-a3b-build05/
git commit -m "phase2d-a3b-build05: Evidence (compile + EX5 + test results)"
```

- [ ] **Step 7: Push and verify**

```bash
git push origin main
git log --oneline origin/main -3
```

Copy exact full SHAs. STOP. BUILD06 remains frozen.
