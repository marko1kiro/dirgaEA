# BUILD 07 — M15 Trend Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the M15 Trend Strategy layer (BUILD 07) that consumes H1 Regime (BUILD 06) and generates at most one deterministic `TradeCandidate` per completed M15 bar across three setup families (Pullback, Break-Retest, Momentum).

**Architecture:** Pure MQL5 strategy component `TrendStrategy.mqh` driven strictly by completed M15 bars, gated by H1 Regime epoch transitions, with zero execution or lot-sizing logic. Fully verified against Python reference implementation via parity test vectors.

**Tech Stack:** MQL5, MetaTrader 5 (Build 6180+), Python 3.12 (pytest test harness, reference implementation).

---

### Task 1: Update Types.mqh with BUILD 07 Enums and Structs

**Files:**
- Modify: `Types.mqh`
- Test: `tests/build07/test_scenarios.py`

- [ ] **Step 1: Inspect Types.mqh and declare BUILD 07 structures**
Add `ENUM_SETUP_FAMILY`, `TradeCandidate`, `TrendEpochState`, `TrendBreakState` matching spec §20 and `tests/build07/reference_trend.py`.

- [ ] **Step 2: Run pytest to ensure Python contracts match Types.mqh**
Run: `python -m pytest tests/build07/test_scenarios.py`
Expected: 42 passed.

- [ ] **Step 3: Verify MQL5 syntax and compatibility**
Check field names, types, default initializers in `Types.mqh`.

- [ ] **Step 4: Commit Types.mqh updates**
```bash
git add Types.mqh
git commit -m "BUILD07: add types and structs for M15 trend strategy"
```

---

### Task 2: Implement M15 Swing Tracker and Epoch Barrier in TrendStrategy.mqh

**Files:**
- Create: `TrendStrategy.mqh`
- Test: `tests/build07/test_scenarios.py`

- [ ] **Step 1: Implement TrendStrategy class boilerplate and epoch state machine**
Support tracking H1 regime transitions (`TREND_BULL`, `TREND_BEAR`), starting new `trendEpochId`, and resetting active setups on epoch change or invalid regime.

- [ ] **Step 2: Implement M15 Swing Structure and Break history buffer**
Add continuous M15 swing ingestion and structure break detection with epoch-tagged validity.

- [ ] **Step 3: Verify epoch reset rules via test scenarios**
Ensure no setups cross epoch boundaries when regime leaves trend.

- [ ] **Step 4: Commit TrendStrategy epoch barrier**
```bash
git add TrendStrategy.mqh
git commit -m "BUILD07: implement trend strategy epoch barrier and swing tracking"
```

---

### Task 3: Implement Setup Family 1: Pullback

**Files:**
- Modify: `TrendStrategy.mqh`
- Test: `tests/build07/test_scenarios.py`

- [ ] **Step 1: Implement Pullback geometry and confirmation rules**
Detect valid pullback pivot C confirmed within epoch, retracement depth `0.30 - 1.5 ATR`, stop placement behind pivot C with 0.10 ATR buffer.

- [ ] **Step 2: Implement Pullback trigger bar validation**
Require trigger bar close in trend direction, displacement >= 0.33, extension <= 2.5 ATR.

- [ ] **Step 3: Commit Pullback implementation**
```bash
git add TrendStrategy.mqh
git commit -m "BUILD07: implement pullback setup family"
```

---

### Task 4: Implement Setup Family 2: Break-Retest

**Files:**
- Modify: `TrendStrategy.mqh`
- Test: `tests/build07/test_scenarios.py`

- [ ] **Step 1: Implement Break-Retest detection and tracking**
Track structure break in epoch (penetration >= 0.10 ATR), retest touch of broken level (tolerance 0.20 ATR), max 8 bars.

- [ ] **Step 2: Implement Break-Retest confirmation and stop placement**
Stop loss behind swing base with 0.10 ATR buffer, clamped `[0.5, 3.0] ATR`.

- [ ] **Step 3: Commit Break-Retest implementation**
```bash
git add TrendStrategy.mqh
git commit -m "BUILD07: implement break-retest setup family"
```

---

### Task 5: Implement Setup Family 3: Momentum Continuation

**Files:**
- Modify: `TrendStrategy.mqh`
- Test: `tests/build07/test_scenarios.py`

- [ ] **Step 1: Implement Momentum trigger validation**
Check 3-bar displacement >= 0.8 ATR in trend direction within epoch.

- [ ] **Step 2: Implement Momentum stop and target calculation**
Target lookback 8 bars for swing target, compute risk distance and reward/risk ratio.

- [ ] **Step 3: Commit Momentum implementation**
```bash
git add TrendStrategy.mqh
git commit -m "BUILD07: implement momentum continuation setup family"
```

---

### Task 6: Implement Candidate Selection Priority & Deduplication

**Files:**
- Modify: `TrendStrategy.mqh`
- Test: `tests/build07/test_scenarios.py`

- [ ] **Step 1: Implement candidate priority resolver**
If multiple setups qualify on the same bar: PULLBACK > BREAK_RETEST > MOMENTUM.

- [ ] **Step 2: Implement completed bar deduplication**
Ensure at most 1 candidate emitted per M15 bar timestamp; duplicate ticks ignore candidate generation.

- [ ] **Step 3: Commit Candidate resolver**
```bash
git add TrendStrategy.mqh
git commit -m "BUILD07: implement candidate selection and deduplication"
```

---

### Task 7: Build Native MQL5 Parity Probe and Replay Test Suite

**Files:**
- Create: `tests/build07/native/Build07ParityProbe.mq5`
- Create: `tests/build07/test_native_parity.py`
- Modify: `AdaptiveSurvivalEA.mq5`

- [ ] **Step 1: Create Build07ParityProbe.mq5**
Probe script that runs synthetic and historical data vectors through MQL5 `TrendStrategy` and outputs diagnostic hashes / candidate streams.

- [ ] **Step 2: Run Parity Probe in MT5 and verify exact hash match with reference_trend.py**
Run python parity test checking bitwise/tolerance match across all candidates.

- [ ] **Step 3: Wire TrendStrategy into AdaptiveSurvivalEA.mq5**
Integrate M15 completed bar event loop calling `TrendStrategy.OnM15Bar(...)`.

- [ ] **Step 4: Commit Native Probe and Parity verification**
```bash
git add tests/build07/ AdaptiveSurvivalEA.mq5
git commit -m "BUILD07: native parity probe, test harness, and EA integration"
```
