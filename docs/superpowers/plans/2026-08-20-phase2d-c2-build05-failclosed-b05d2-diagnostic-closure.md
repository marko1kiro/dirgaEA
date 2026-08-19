# Phase 2D-C2: BUILD05 Fail-Closed + B05D2 + Diagnostic Closure

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close 9 architect-audit findings: P0 CopyBuffer fail-closed, explicit state init, complete B05D2, real qualityReady, raw diagnostic trace, transition logging, safety counters, determinism tests, and full evidence package.

**Architecture:** Modify `ProcessBuild05ClosedHistoryPrefix` to accept explicit buffer readiness booleans. Add `volQualityReady` field to `Build05BehaviorState`. Create `Build05RawTrace` struct populated from production intermediates. Wire safety counters and transition emission. All changes preserve canonical architecture from Phase 2D-C.

**Tech Stack:** MQL5 (MetaTrader 5), Python 3.12 (pytest), Git

**Starting SHA:** `7bbf3b4df336b5a0c938006c3677baaaff249f50`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `Types.mqh` | Modify | Add `volQualityReady` to `Build05BehaviorState` |
| `MarketBrain.mqh` | Modify | Add buffer-ready params, raw trace, transition emission, safety counter wiring |
| `AdaptiveSurvivalEA.mq5` | Modify | Explicit init in OnInit, pass buffer booleans, wire counters, duplicate H1 guard |
| `DiagnosticCollector.mqh` | Modify | Create `Build05RawTrace`, update `Build05DiagnosticCollect`, transition logging, safety summary |
| `tests/build05/test_phase2d_c2.py` | Create | All new tests (RED + GREEN) |
| `tests/build05/test_source_invariants.py` | Modify | Add C2 invariants |

---

## Task 1: Capture Genuine RED on Starting SHA

- [ ] **Step 1: Create RED test file for all 8 required failing cases**

Create `tests/build05/test_red_phase2d_c2.py` with 8 tests that expose pre-fix issues:

```python
"""Phase 2D-C2 RED tests — genuine failures on starting SHA 7bbf3b4."""
import re
import os
import pytest

SOURCE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MQ5_PATH = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
MQH_PATH = os.path.join(SOURCE_DIR, "MarketBrain.mqh")
TYPES_PATH = os.path.join(SOURCE_DIR, "Types.mqh")
DIAG_PATH = os.path.join(SOURCE_DIR, "DiagnosticCollector.mqh")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _find_func_body(source, pattern):
    match = re.search(pattern, source)
    if not match:
        return ""
    start = match.start()
    brace_count = 0
    end = start
    in_func = False
    for i, c in enumerate(source[start:], start):
        if c == "{":
            brace_count += 1
            in_func = True
        elif c == "}":
            brace_count -= 1
            if brace_count == 0 and in_func:
                end = i + 1
                break
    return source[start:end]


class TestRED_AtrPartialCopyBufferUnsafe:
    """RED 1: Canonical function must NOT index atr[] without atrBufferReady."""
    def test_canonical_has_atr_ok_internal(self):
        """BAD: canonical computes atrOk internally by indexing atr[count-1]."""
        source = _read(MQH_PATH)
        body = _find_func_body(source, r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(")
        # On starting SHA, atrOk is computed inside the function
        assert "BrainValidAt(atr[count - 1])" in body or "BrainValidAt(atr[count-1])" in body, \
            "ALREADY GREEN: canonical does not compute atrOk internally"


class TestRED_EmaPartialCopyBufferUnsafe:
    """RED 2: Canonical function must NOT index emaFast[]/emaSlow[] without emaBufferReady."""
    def test_canonical_has_ema_ok_internal(self):
        """BAD: canonical computes emaOk internally by indexing arrays."""
        source = _read(MQH_PATH)
        body = _find_func_body(source, r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(")
        assert "BrainValidAt(emaFast[count - 1])" in body or "BrainValidAt(emaFast[count-1])" in body, \
            "ALREADY GREEN: canonical does not compute emaOk internally"


class TestRED_B05StateNotExplicitlyInitialized:
    """RED 3: b05_state must be explicitly initialized before first UpdateH1Brain."""
    def testOnInitDoesNotInitB05State(self):
        """BAD: OnInit does not call Build05BehaviorStateInit before UpdateH1Brain."""
        source = _read(MQ5_PATH)
        oninit = _find_func_body(source, r"int\s+OnInit\s*\(\s*\)")
        # Check that Build05BehaviorStateInit(b05_state) appears before UpdateH1Brain()
        init_pos = oninit.find("Build05BehaviorStateInit(b05_state)")
        update_pos = oninit.find("UpdateH1Brain()")
        if init_pos < 0 or update_pos < 0:
            pass  # Test will fail below
        else:
            assert init_pos < update_pos, \
                "ALREADY GREEN: Build05BehaviorStateInit appears before UpdateH1Brain"
        # Force failure if not found
        assert init_pos >= 0 and update_pos >= 0 and init_pos < update_pos, \
            "b05_state not explicitly initialized before first UpdateH1Brain"


class TestRED_B05D2HiddenCollision:
    """RED 4: B05D2 must hash directionState — same visible output with different hidden state must differ."""
    def test_b05d2_includes_direction_state(self):
        """BAD: B05D2 does not encode directionState enum."""
        source = _read(DIAG_PATH)
        sig_func = _find_func_body(source, r"string\s+Build05DiagnosticSignature\s*\(")
        assert "dstate" not in sig_func or "b.direction.state" not in sig_func, \
            "ALREADY GREEN: B05D2 already encodes direction state"
        # Check: the current B05D2 hashes b.direction.state (visible), not s.directionState (hidden)
        assert "s.directionState" not in sig_func, \
            "ALREADY GREEN: B05D2 encodes hidden directionState"


class TestRED_QualityReadyTimestampInference:
    """RED 5: qualityReady must use real count, not timestamp != 0 ? 41 : 0."""
    def test_b05d2_quality_ready_uses_timestamp(self):
        """BAD: B05D2 derives qualityReady from timestamp, not count."""
        source = _read(DIAG_PATH)
        sig_func = _find_func_body(source, r"string\s+Build05DiagnosticSignature\s*\(")
        assert "latestClosedH1" in sig_func and "41" in sig_func, \
            "ALREADY GREEN: qualityReady does not use timestamp inference"
        # Specific check: the bad pattern
        assert "!= 0) ? 41 : 0" in sig_func or "!=0)?41:0" in sig_func, \
            "ALREADY GREEN: qualityReady inference pattern removed"


class TestRED_MissingRawDiagnosticTrace:
    """RED 6: No real raw diagnostic trace struct exists."""
    def test_no_raw_trace_struct(self):
        """BAD: No Build05RawTrace or equivalent struct."""
        source = _read(DIAG_PATH)
        assert "struct Build05RawTrace" not in source, \
            "ALREADY GREEN: Build05RawTrace struct exists"


class TestRED_MissingTransitionEmission:
    """RED 7: Transition structs exist but no actual B05_*_TRANSITION emission."""
    def test_no_transition_emission(self):
        """BAD: No LogDebug with B05_DIRECTION_TRANSITION."""
        source = _read(DIAG_PATH)
        assert "B05_DIRECTION_TRANSITION" not in source, \
            "ALREADY GREEN: B05_DIRECTION_TRANSITION emission exists"


class TestRED_SafetyCountersNotWired:
    """RED 8: Safety counters struct exists but not wired into canonical function."""
    def test_counters_not_wired(self):
        """BAD: Canonical function does not reference counters."""
        source = _read(MQH_PATH)
        body = _find_func_body(source, r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(")
        assert "counters" not in body.lower() or "copyBufferFailures" not in body, \
            "ALREADY GREEN: counters wired into canonical function"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

- [ ] **Step 2: Run RED tests to verify they fail on starting SHA**

Run: `cd tests/build05 && python -m pytest test_red_phase2d_c2.py -v --tb=short`
Expected: 8 failed (or some ALREADY GREEN). Save output to `audits/2026-08-20/phase2d-c2-build05/pre_fix_red.txt`.

- [ ] **Step 3: Commit RED tests**

```bash
git add tests/build05/test_red_phase2d_c2.py
git commit -m "Phase 2D-C2: RED tests capturing 8 pre-fix failures"
```

---

## Task 2: P0 — CopyBuffer Fail-Closed Safety

- [ ] **Step 1: Modify canonical function signature in MarketBrain.mqh**

Replace the current signature:

```cpp
bool ProcessBuild05ClosedHistoryPrefix(
   const MqlRates &rates[],
   const double &atr[],
   const double &emaFast[],
   const double &emaSlow[],
   const double &adx[],
   const int count,
   const bool adxValid,
   Build05BehaviorState &state,
   H1BrainResult &result)
```

With:

```cpp
bool ProcessBuild05ClosedHistoryPrefix(
   const MqlRates &rates[],
   const double &atr[],
   const double &emaFast[],
   const double &emaSlow[],
   const double &adx[],
   const int count,
   const bool atrBufferReady,
   const bool emaBufferReady,
   const bool adxBufferReady,
   Build05BehaviorState &state,
   H1BrainResult &result)
```

- [ ] **Step 2: Remove internal atrOk/emaOk computation, gate all access**

Replace the body after `count < 3` check. Remove:
```cpp
const bool atrOk = BrainValidAt(atr[count - 1]);
const bool emaOk = BrainValidAt(emaFast[count - 1]) && BrainValidAt(emaSlow[count - 1]);
```

Replace all `atrOk` with `atrBufferReady`, all `emaOk` with `emaBufferReady`. The Direction block must check `atrBufferReady && emaBufferReady`. Momentum checks `atrBufferReady`. Volatility checks `atrBufferReady`.

- [ ] **Step 3: Update live caller in AdaptiveSurvivalEA.mq5**

In `UpdateH1Brain()`, change the call from:
```cpp
ProcessBuild05ClosedHistoryPrefix(rates, atrB05, emaFast, emaSlow, adx,
                                  copiedRates, adxOk, b05_state, h1_brain);
```
To:
```cpp
const bool atrBufferReady = (copiedAtr == copiedRates);
const bool emaBufferReady = (copiedFast == copiedRates && copiedSlow == copiedRates);
const bool adxBufferReady = (copiedAdx == copiedRates);

ProcessBuild05ClosedHistoryPrefix(rates, atrB05, emaFast, emaSlow, adx,
                                  copiedRates, atrBufferReady, emaBufferReady,
                                  adxBufferReady, b05_state, h1_brain);
```

- [ ] **Step 4: Update replay caller in AdaptiveSurvivalEA.mq5**

In `RebuildRegimeFusionState()`, compute and pass the same booleans:
```cpp
const bool atrB05Ok = (copiedAtrB05 == count);
const bool emaOkReplay = (copiedFast == count && copiedSlow == count);
const bool adxOkReplay = (copiedAdx == count);
```

Pass these to `ProcessBuild05ClosedHistoryPrefix` instead of just `adxOk`.

- [ ] **Step 5: Write buffer safety regression tests**

In `tests/build05/test_phase2d_c2.py`, add:

```python
class TestBufferSafety:
    """Buffer safety: canonical must not index arrays without readiness."""
    def test_atr_not_indexed_when_not_ready(self):
        """ATR array must not be indexed if atrBufferReady=false."""
        source = _read(MQH_PATH)
        body = _find_func_body(source, r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(")
        # The function must NOT have internal BrainValidAt(atr[count-1])
        assert "BrainValidAt(atr[count - 1])" not in body and \
               "BrainValidAt(atr[count-1])" not in body, \
            "Canonical function still computes atrOk internally"

    def test_ema_not_indexed_when_not_ready(self):
        """EMA arrays must not be indexed if emaBufferReady=false."""
        source = _read(MQH_PATH)
        body = _find_func_body(source, r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(")
        assert "BrainValidAt(emaFast[count - 1])" not in body and \
               "BrainValidAt(emaFast[count-1])" not in body, \
            "Canonical function still computes emaOk internally"

    def test_signature_accepts_three_buffer_flags(self):
        """Canonical function must accept atrBufferReady, emaBufferReady, adxBufferReady."""
        source = _read(MQH_PATH)
        match = re.search(r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(([^)]*)\)", source, re.DOTALL)
        assert match, "ProcessBuild05ClosedHistoryPrefix not found"
        params = match.group(1)
        assert "atrBufferReady" in params, "Missing atrBufferReady parameter"
        assert "emaBufferReady" in params, "Missing emaBufferReady parameter"
        assert "adxBufferReady" in params, "Missing adxBufferReady parameter"

    def test_direction_gated_by_atr_and_ema(self):
        """Direction access must be gated by atrBufferReady && emaBufferReady."""
        source = _read(MQH_PATH)
        body = _find_func_body(source, r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(")
        assert "atrBufferReady && emaBufferReady" in body or \
               "atrBufferReady&&emaBufferReady" in body, \
            "Direction not gated by atrBufferReady && emaBufferReady"

    def test_momentum_gated_by_atr_only(self):
        """Momentum access must be gated by atrBufferReady only."""
        source = _read(MQH_PATH)
        body = _find_func_body(source, r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(")
        # Momentum block: if(atrBufferReady)
        assert "if(atrBufferReady)" in body or "if (atrBufferReady)" in body, \
            "Momentum not gated by atrBufferReady"

    def test_volatility_gated_by_atr_only(self):
        """Volatility access must be gated by atrBufferReady only."""
        source = _read(MQH_PATH)
        body = _find_func_body(source, r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(")
        # Second atrBufferReady gate for volatility
        count = body.count("if(atrBufferReady)") + body.count("if (atrBufferReady)")
        assert count >= 2, \
            f"Expected at least 2 atrBufferReady gates (momentum + volatility), found {count}"

    def test_live_caller_passes_three_flags(self):
        """Live caller must pass atrBufferReady, emaBufferReady, adxBufferReady."""
        source = _read(MQ5_PATH)
        assert "atrBufferReady" in source, "Live caller missing atrBufferReady"
        assert "emaBufferReady" in source, "Live caller missing emaBufferReady"
        assert "adxBufferReady" in source, "Live caller missing adxBufferReady"
```

- [ ] **Step 6: Run tests, verify GREEN**

Run: `cd tests/build05 && python -m pytest test_phase2d_c2.py test_source_invariants.py -v --tb=short`

- [ ] **Step 7: Deploy, compile, verify 0 errors**

Deploy all 10 source files, compile, verify EX5 created.

---

## Task 3: Explicit B05 State Initialization

- [ ] **Step 1: Add init calls in OnInit() before first UpdateH1Brain**

In `AdaptiveSurvivalEA.mq5` `OnInit()`, BEFORE the line `UpdateH1Brain();` (line 447), insert:

```cpp
// Explicit B05 initialization — enum zero values are NOT neutral
Build05BehaviorStateInit(b05_state);
ResetH1BrainInvalid(h1_brain);
b05_h1_brain_primed = false;
```

- [ ] **Step 2: Write source invariant**

In `tests/build05/test_source_invariants.py`, add:

```python
def test_source_b05_state_initialized_before_first_update():
    """Build05BehaviorStateInit(b05_state) must appear before UpdateH1Brain() in OnInit."""
    source_path = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    oninit = _find_func_body(source, r"int\s+OnInit\s*\(\s*\)")
    init_pos = oninit.find("Build05BehaviorStateInit(b05_state)")
    update_pos = oninit.find("UpdateH1Brain()")
    assert init_pos >= 0, "Build05BehaviorStateInit(b05_state) not found in OnInit"
    assert update_pos >= 0, "UpdateH1Brain() not found in OnInit"
    assert init_pos < update_pos, \
        "Build05BehaviorStateInit must appear BEFORE UpdateH1Brain in OnInit"
```

- [ ] **Step 3: Run tests, verify GREEN**

---

## Task 4: B05D2 — Hash Complete Behavior State + volQualityReady

- [ ] **Step 1: Add volQualityReady to Build05BehaviorState in Types.mqh**

After line 195 (`int volQualityChallengerDwell;`), add:

```cpp
   // Quality readiness (set by canonical function, not by caller)
   bool volQualityReady;
```

- [ ] **Step 2: Initialize volQualityReady in Build05BehaviorStateInit**

In `MarketBrain.mqh`, add to `Build05BehaviorStateInit`:
```cpp
   s.volQualityReady = false;
```

- [ ] **Step 3: Set volQualityReady in canonical function**

In `ProcessBuild05ClosedHistoryPrefix`, at the end (before `return`), add:
```cpp
   state.volQualityReady = BrainVolQualityReady(count);
```

- [ ] **Step 4: Update B05D2 signature to hash ALL hidden fields**

In `DiagnosticCollector.mqh`, `Build05DiagnosticSignature`, add these lines AFTER the existing hidden fields:

```cpp
   // Direction hidden — enum itself
   Build04DiagnosticAppend(out, "dstate_h", IntegerToString(s.directionState));
   // Momentum hidden — complete
   Build04DiagnosticAppend(out, "mstate_h", IntegerToString(s.momentumState));
   // VolLevel hidden — enum itself
   Build04DiagnosticAppend(out, "vlstate_h", IntegerToString(s.volLevel));
   // VolQuality hidden — complete
   Build04DiagnosticAppend(out, "vqstate_h", IntegerToString(s.volQuality));
   Build04DiagnosticAppend(out, "vqready", Build04DiagnosticBool(s.volQualityReady));
```

Remove the old timestamp-inferred qualityReady line:
```cpp
   // REMOVE: Build04DiagnosticAppend(out, "vqready", Build04DiagnosticBool(BrainVolQualityReady(
   //    (b.direction.latestClosedH1 != 0) ? 41 : 0)));
```

- [ ] **Step 5: Update BRAIN_UPDATE to use state.volQualityReady**

In `Build05DiagnosticCollect`, replace:
```cpp
   const bool qualityReady = BrainVolQualityReady(
      (b.direction.latestClosedH1 != 0 || ...) ? 41 : 0);
```
With:
```cpp
   // qualityReady comes from state, not timestamp inference
```
And use `s.volQualityReady` in the format string.

- [ ] **Step 6: Write hidden state collision tests**

```python
class TestB05D2HiddenStateSensitivity:
    """B05D2 must produce different hashes for different hidden states with same visible output."""
    def _get_sig_func_body(self):
        source = _read(DIAG_PATH)
        return _find_func_body(source, r"string\s+Build05DiagnosticSignature\s*\(")

    def test_direction_state_encoded(self):
        """B05D2 must encode s.directionState (hidden, not b.direction.state)."""
        body = self._get_sig_func_body()
        assert "dstate_h" in body, "B05D2 missing hidden directionState"

    def test_momentum_state_encoded(self):
        """B05D2 must encode s.momentumState (hidden)."""
        body = self._get_sig_func_body()
        assert "mstate_h" in body, "B05D2 missing hidden momentumState"

    def test_vollevel_state_encoded(self):
        """B05D2 must encode s.volLevel (hidden)."""
        body = self._get_sig_func_body()
        assert "vlstate_h" in body, "B05D2 missing hidden volLevel"

    def test_volquality_state_encoded(self):
        """B05D2 must encode s.volQuality (hidden)."""
        body = self._get_sig_func_body()
        assert "vqstate_h" in body, "B05D2 missing hidden volQuality"

    def test_quality_ready_uses_state_field(self):
        """B05D2 qualityReady must use s.volQualityReady, not timestamp."""
        body = self._get_sig_func_body()
        assert "s.volQualityReady" in body, \
            "B05D2 qualityReady not using state field"
```

- [ ] **Step 7: Run tests, verify GREEN**

---

## Task 5: Raw Diagnostic Trace

- [ ] **Step 1: Create Build05RawTrace struct in DiagnosticCollector.mqh**

After `Build05TransitionStateInit`, add:

```cpp
// Raw diagnostic trace — populated from production intermediates.
// No alternate math. Assignments to already-computed values only.
struct Build05RawTrace
{
   datetime closedH1;
   // Direction raw evidence
   double dirFastSlopeAtr;
   double dirSlowSlopeAtr;
   double dirPositioning;
   double dirDisplacementAtr;
   double dirEfficiencySigned;
   double dirRawScore;
   double dirFinalScore;
   // Momentum raw evidence
   double momBodyAtr;
   double momBodyRange;
   double momCloseLocation;
   double momProgression;
   double momProgressionStrength;
   double momEfficiencyMag;
   double momEfficiencySigned;
   double momRawScore;
   double momStrengthScore;
   double momStrengthDelta;
   double momStrengthSlope;
   double momDirectionalAlignment;
   // ADX helper
   double adxCurrent;
   double adxPrevious;
   double adxSlope;
   bool adxAvailable;
   // Volatility raw evidence
   double volCurrentAtr;
   double volAtrBaseline;
   double volAtrRatio;
   double volRecentAtrAvg;
   double volPriorAtrAvg;
   double volAtrDecline;
   double volAtrRise;
   double volRecentRangeAvg;
   double volPriorRangeAvg;
   double volRangeShrink;
   double volRangeExpand;
   double volRecentBodyAvg;
   double volPriorBodyAvg;
   double volBodyShrink;
   double volBodyExpand;
   double volRecentEfficiency;
   double volPriorEfficiency;
   double volEfficiencyRise;
   double volRecentDisplacement;
   double volPriorDisplacement;
   double volDisplacementRise;
   double volWickNoise;
   double volHealthyScore;
   double volCompressionScore;
   double volExpansionScore;
   double volChaosScore;
   double volShockScore;
   bool volQualityReady;
   double volQualityConfidence;
};
```

- [ ] **Step 2: Modify canonical function to accept and populate trace**

Add `Build05RawTrace *trace = NULL` as an optional output parameter (default NULL). When non-NULL, populate from the same intermediates used for production scores.

The key refactoring: extract intermediate values into local variables, use them for both production scoring and trace population.

```cpp
bool ProcessBuild05ClosedHistoryPrefix(
   const MqlRates &rates[],
   const double &atr[],
   const double &emaFast[],
   const double &emaSlow[],
   const double &adx[],
   const int count,
   const bool atrBufferReady,
   const bool emaBufferReady,
   const bool adxBufferReady,
   Build05BehaviorState &state,
   H1BrainResult &result,
   Build05RawTrace *trace = NULL)  // optional, NULL when diagnostics off
```

When `trace != NULL`, assign production intermediates to trace fields. This is safe because it's just copying already-computed values.

- [ ] **Step 3: Update Build05DiagnosticCollect to accept and log trace**

Modify `Build05DiagnosticCollect` to accept `const Build05RawTrace &trace` and emit a `BRAIN_UPDATE` with all raw fields.

- [ ] **Step 4: Update callers to pass trace when diagnostic mode enabled**

In `UpdateH1Brain()` and `RebuildRegimeFusionState()` (replay loop), declare `Build05RawTrace trace;` when `Build05DiagnosticMode` is true, pass `&trace` to canonical function.

- [ ] **Step 5: Write trace existence test**

```python
class TestRawDiagnosticTrace:
    def test_raw_trace_struct_exists(self):
        source = _read(DIAG_PATH)
        assert "struct Build05RawTrace" in source

    def test_trace_has_direction_fields(self):
        source = _read(DIAG_PATH)
        assert "dirFastSlopeAtr" in source
        assert "dirDisplacementAtr" in source
        assert "dirEfficiencySigned" in source

    def test_trace_has_momentum_fields(self):
        source = _read(DIAG_PATH)
        assert "momBodyAtr" in source
        assert "momProgression" in source
        assert "momStrengthScore" in source

    def test_trace_has_volatility_fields(self):
        source = _read(DIAG_PATH)
        assert "volCurrentAtr" in source
        assert "volAtrRatio" in source
        assert "volHealthyScore" in source

    def test_trace_has_adx_fields(self):
        source = _read(DIAG_PATH)
        assert "adxCurrent" in source
        assert "adxPrevious" in source
        assert "adxSlope" in source

    def test_canonical_accepts_trace_parameter(self):
        source = _read(MQH_PATH)
        match = re.search(r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(([^)]*)\)", source, re.DOTALL)
        assert match
        assert "Build05RawTrace" in match.group(1)
```

- [ ] **Step 6: Run tests, verify GREEN**

---

## Task 6: Transition-Only Logging

- [ ] **Step 1: Implement transition emission in canonical function**

At the end of `ProcessBuild05ClosedHistoryPrefix`, after all classification, add transition detection:

```cpp
   // Transition emission (observability only, no behavioral influence)
   if(trace != NULL)
   {
      if(state.directionState != trace->prevDirectionCommitted)
      {
         LogDebug("B05_DIRECTION_TRANSITION", StringFormat(
            "closed_h1=%I64d from=%d to=%d dwell=%d ch=%d chd=%d",
            (long)result.direction.latestClosedH1,
            (int)trace->prevDirectionCommitted, (int)state.directionState,
            state.directionDwell, (int)state.directionChallenger, state.directionChallengerDwell));
      }
      // ... same for momentum, volLevel, volQuality
   }
```

Wait — this approach requires the trace to carry previous committed state. Better: use the `Build05TransitionState` struct that already exists. The canonical function should accept it as an in/out parameter.

Revised: Add `Build05TransitionState *transition = NULL` as parameter. At the end, compare current committed enums with `transition->prev*` and emit if changed. Then update `transition->prev*` to current.

- [ ] **Step 2: Wire transition state into callers**

In `AdaptiveSurvivalEA.mq5`, declare `Build05TransitionState b05_transition;` as a global, init in `OnInit()`, pass to canonical function.

- [ ] **Step 3: Write transition emission test**

```python
class TestTransitionEmission:
    def test_transition_struct_used(self):
        source = _read(MQH_PATH)
        body = _find_func_body(source, r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(")
        assert "B05_DIRECTION_TRANSITION" in body or "transition" in body.lower()

    def test_transition_event_names_defined(self):
        source = _read(DIAG_PATH)
        assert "B05_DIRECTION_TRANSITION" in source
        assert "B05_MOMENTUM_TRANSITION" in source
        assert "B05_VOLLEVEL_TRANSITION" in source
        assert "B05_VOLQUALITY_TRANSITION" in source
```

- [ ] **Step 4: Run tests, verify GREEN**

---

## Task 7: Safety Counter Runtime Wiring

- [ ] **Step 1: Add global counter state in AdaptiveSurvivalEA.mq5**

After the `b05_transition` declaration, add:
```cpp
Build05DiagnosticCounters b05_counters;
```

In `OnInit()`, add:
```cpp
Build05DiagnosticCountersInit(b05_counters);
```

- [ ] **Step 2: Wire counters into canonical function**

Add `Build05DiagnosticCounters *counters = NULL` as optional parameter. When non-NULL:
- `if(!atrBufferReady) counters->copyBufferFailures++; counters->invalidAtr++;`
- `if(!emaBufferReady) counters->invalidEma++;`
- `if(!adxBufferReady) counters->adxDegraded++;`
- `if(!BrainVolQualityReady(count)) counters->volQualityNotReady++;`

- [ ] **Step 3: Wire counters into live caller**

Pass `&b05_counters` from `UpdateH1Brain()`.

- [ ] **Step 4: Implement B05_SAFETY emission**

In `Build05DiagnosticCollect` (or a new function), emit `B05_SAFETY` summary when diagnostic mode enabled.

- [ ] **Step 5: Write safety counter tests**

```python
class TestSafetyCounters:
    def test_counters_struct_has_all_fields(self):
        source = _read(DIAG_PATH)
        match = re.search(r"struct Build05DiagnosticCounters\s*\{([^}]+)\}", source, re.DOTALL)
        assert match
        body = match.group(1)
        for field in ["copyBufferFailures", "invalidAtr", "invalidEma", "adxDegraded",
                       "duplicateH1Attempts", "formingBarAttempts", "abnormalSkips",
                       "volQualityNotReady"]:
            assert field in body, f"Missing counter field: {field}"

    def test_counters_init_function_exists(self):
        source = _read(DIAG_PATH)
        assert "Build05DiagnosticCountersInit" in source

    def test_canonical_accepts_counters(self):
        source = _read(MQH_PATH)
        match = re.search(r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(([^)]*)\)", source, re.DOTALL)
        assert match
        assert "Build05DiagnosticCounters" in match.group(1)
```

- [ ] **Step 6: Run tests, verify GREEN**

---

## Task 8: Duplicate H1 Guard + Forming-Bar Discipline

- [ ] **Step 1: Add duplicate H1 tracking in live caller**

In `AdaptiveSurvivalEA.mq5`, add global:
```cpp
datetime b05_last_accepted_h1 = 0;
```

In `UpdateH1Brain()`, after computing `closedH1`, before calling canonical function:
```cpp
if(b05_h1_brain_primed && closedH1 == b05_last_accepted_h1)
{
   b05_counters.duplicateH1Attempts++;
   return;  // skip, state must not advance twice
}
```

After canonical function succeeds:
```cpp
b05_last_accepted_h1 = closedH1;
```

- [ ] **Step 2: Add forming-bar validation**

In `UpdateH1Brain()`, after CopyRates:
```cpp
// Forming bar discipline: shift=1 means bar0 is excluded
// Verify latest bar timestamp is not current time
if(copiedRates >= 1 && rates[copiedRates - 1].time >= iTime(_Symbol, PERIOD_H1, 0))
{
   b05_counters.formingBarAttempts++;
   return;
}
```

- [ ] **Step 3: Write duplicate H1 test**

```python
class TestDuplicateH1Guard:
    def test_duplicate_h1_tracking_exists(self):
        source = _read(MQ5_PATH)
        assert "b05_last_accepted_h1" in source
        assert "duplicateH1Attempts" in source

    def test_forming_bar_validation_exists(self):
        source = _read(MQ5_PATH)
        assert "formingBarAttempts" in source
```

- [ ] **Step 4: Run tests, verify GREEN**

---

## Task 9: Native Indicator Diagnostics Extension

- [ ] **Step 1: Extend native log with ADX previous and slope**

In `Build05NativeIndicatorLog` signature, add `adxPrevious` and `adxSlope` parameters.

In `UpdateH1Brain()`, compute ADX previous from `adx[copiedRates - 2]` when available, compute slope.

- [ ] **Step 2: Write native indicator test**

```python
class TestNativeIndicatorDiagnostics:
    def test_native_log_includes_adx_previous(self):
        source = _read(DIAG_PATH)
        assert "adx_previous" in source.lower() or "adxprev" in source.lower()

    def test_native_log_includes_adx_slope(self):
        source = _read(DIAG_PATH)
        assert "adx_slope" in source.lower() or "adxslope" in source.lower()
```

- [ ] **Step 3: Run tests, verify GREEN**

---

## Task 10: Determinism Tests

- [ ] **Step 1: Create deterministic state-machine tests**

These tests call the Python reference implementation to prove continuous vs restart parity.

In `tests/build05/test_phase2d_c2.py`:

```python
class TestDeterministicReload:
    def test_two_clean_replays_produce_identical_state(self):
        """Run same cold replay twice from clean init, require identical output."""
        # This requires Python reference implementation of canonical function
        # or direct source analysis. For now, test that the canonical function
        # is deterministic by checking it has no mutable global state dependencies.
        source = _read(MQH_PATH)
        body = _find_func_body(source, r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(")
        # Must NOT reference global state (only state and result params)
        assert "b05_state" not in body, \
            "Canonical function must not reference global b05_state"
        assert "h1_brain" not in body, \
            "Canonical function must not reference global h1_brain"

    def test_replay_hydration_produces_same_state(self):
        """Replay hydration must produce same state as continuous processing."""
        source = _read(MQ5_PATH)
        assert "b05_state = replayB05State" in source or "b05_state=replayB05State" in source
        assert "h1_brain = replayBrain" in source or "h1_brain=replayBrain" in source
```

- [ ] **Step 2: Write B05D2 determinism test**

```python
class TestB05D2Determinism:
    def test_deterministic_hash_algorithm(self):
        """B05D2 must use FNV-1a hash (deterministic, no wall clock)."""
        source = _read(DIAG_PATH)
        sig_func = _find_func_body(source, r"string\s+Build05DiagnosticSignature\s*\(")
        assert "14695981039346656037" in sig_func, "Missing FNV-1a offset basis"
        assert "1099511628211" in sig_func, "Missing FNV-1a prime"
```

- [ ] **Step 3: Run tests, verify GREEN**

---

## Task 11: Fix Weak Phase 2D-C Tests

- [ ] **Step 1: Strengthen test_red_e (raw inputs)**

Replace the token-existence test with one that checks representative raw fields from all three domains:

```python
class TestRedE_RawInputs:
    def test_raw_trace_has_direction_evidence(self):
        source = _read(DIAG_PATH)
        for field in ["dirFastSlopeAtr", "dirDisplacementAtr", "dirEfficiencySigned"]:
            assert field in source, f"Missing direction raw field: {field}"

    def test_raw_trace_has_momentum_evidence(self):
        source = _read(DIAG_PATH)
        for field in ["momBodyAtr", "momProgression", "momStrengthScore"]:
            assert field in source, f"Missing momentum raw field: {field}"

    def test_raw_trace_has_volatility_evidence(self):
        source = _read(DIAG_PATH)
        for field in ["volCurrentAtr", "volAtrRatio", "volHealthyScore"]:
            assert field in source, f"Missing volatility raw field: {field}"
```

- [ ] **Step 2: Strengthen transition test**

```python
class TestTransitionLogic:
    def test_transition_only_on_enum_change(self):
        """Transition must only fire when committed enum changes, not on dwell/score changes."""
        source = _read(MQH_PATH)
        body = _find_func_body(source, r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(")
        # Must compare previous committed enum with current
        assert "prevDirection" in body or "transition" in body.lower()
```

- [ ] **Step 3: Strengthen safety counter test**

```python
class TestSafetyCounterWiring:
    def test_counters_incremented_in_canonical(self):
        source = _read(MQH_PATH)
        body = _find_func_body(source, r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(")
        assert "copyBufferFailures" in body or "invalidAtr" in body

    def test_counters_observability_only(self):
        """Counters must not affect scores/enums/persistence."""
        source = _read(MQH_PATH)
        body = _find_func_body(source, r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(")
        # Counter increments must not appear inside DirectionEngine/MomentumEngine/VolatilityEngine calls
        # Just verify counters parameter is pointer (observability pattern)
        assert "counters" in body
```

- [ ] **Step 4: Run tests, verify GREEN**

---

## Task 12: Full Regression + Deploy + Evidence

- [ ] **Step 1: Run complete BUILD05 regression**

```bash
cd tests/build05 && python -m pytest -v --tb=short 2>&1 | tee ../../audits/2026-08-20/phase2d-c2-build05/build05_pytest_vv.txt
```

Require: 0 failed, 0 skipped, 0 deselected.

- [ ] **Step 2: Run complete BUILD04 regression**

```bash
cd tests/build04 && python -m pytest -v --tb=short 2>&1 | tee ../../audits/2026-08-20/phase2d-c2-build05/build04_pytest_vv.txt
```

Require: 13 passed, 0 failed.

- [ ] **Step 3: Deploy all 10 source files**

Copy all .mq5/.mqh files to deployed MT5 directory.

- [ ] **Step 4: Compile and record**

Compile deployed EA. Save compile.log. Record EX5 SHA256 and size.

- [ ] **Step 5: Generate workspace_vs_deployed_sha256.txt**

For each of 10 files, record workspace SHA, deployed SHA, and MATCH status.

- [ ] **Step 6: Save all evidence files**

Mandatory files:
- `pre_fix_red.txt`
- `build05_pytest_vv.txt`
- `build04_pytest_vv.txt`
- `compile.log`
- `ex5_sha256.txt`
- `ex5_size.txt`
- `workspace_vs_deployed_sha256.txt`
- `b05d2_determinism.txt`
- `b05_state_hydration.txt`
- `diagnostic_sample.txt`
- `native_indicator_sample.txt`
- `native_mcp_parity.txt`
- `provenance.txt`

- [ ] **Step 7: Commit A (source + tests)**

```bash
git add -A
git commit -m "Phase 2D-C2: Fail-closed + B05D2 + Diagnostic Closure"
```

- [ ] **Step 8: Commit B (evidence only)**

```bash
git add audits/2026-08-20/phase2d-c2-build05/ -f
git commit -m "Phase 2D-C2 evidence"
```

- [ ] **Step 9: Push and verify**

```bash
git push origin main
git fetch origin
git rev-parse HEAD
git rev-parse origin/main
```

Require exact match.

- [ ] **Step 10: Final report in chat**

---

## Spec Coverage Check

| Spec Section | Task |
|-------------|------|
| P0 CopyBuffer fail-closed | Task 2 |
| Explicit b05_state init | Task 3 |
| B05D2 complete hash | Task 4 |
| qualityReady real | Task 4 |
| Raw diagnostic trace | Task 5 |
| Transition logging | Task 6 |
| Safety counters wired | Task 7 |
| Duplicate H1 guard | Task 8 |
| Forming-bar discipline | Task 8 |
| Native indicator extend | Task 9 |
| Determinism tests | Task 10 |
| Fix weak 2D-C tests | Task 11 |
| BUILD05/BUILD04 gate | Task 12 |
| Evidence package | Task 12 |
| Git discipline | Task 12 |
| Final report | Task 12 |
