# Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all critical audit findings (F-01 through F-08) in DirgaEA MQL5 production code, ensure full clean MetaEditor compilation, and verify runtime and test suites before demo forward-testing.

**Architecture:** MQL5 Expert Advisor with modular event handling (`OnTick`, `OnTimer`, `OnTradeTransaction`), fail-closed safety guards, atomic pre-flight checks, position management, news calendar integration, and daily loss ledger.

**Tech Stack:** MQL5, MetaTrader 5 (x64), Python 3.12 (pytest).

---

### Task 1: Fix F-01 — Connect Position Management to OnTick Runtime
**Files:**
- Modify: `AdaptiveSurvivalEA.mq5`
- Modify: `PositionManager.mqh`
- Modify: `ExecutionBridge.mqh`

- [ ] **Step 1: Inspect PositionManager and ExecutionBridge methods**
- [ ] **Step 2: Add loop over open positions in OnTick to evaluate BE, trailing stop, and regime invalidation**
- [ ] **Step 3: Compile with MetaEditor and verify 0 errors**

---

### Task 2: Fix F-03 & F-06 — Live-Price Sizing, Fresh Tick, Continuous Spread Profiling
**Files:**
- Modify: `AdaptiveSurvivalEA.mq5`
- Modify: `ExecutionSafety.mqh`

- [ ] **Step 1: Refresh tick directly before sizing and gating**
- [ ] **Step 2: Re-calculate risk using Ask for BUY and Bid for SELL**
- [ ] **Step 3: Add spread profiling sample on every tick and enforce absolute spread ceiling**
- [ ] **Step 4: Compile with MetaEditor and verify 0 errors**

---

### Task 3: Fix F-04 — Stale H1 Regime Protection & Atomic Bar Commitment
**Files:**
- Modify: `AdaptiveSurvivalEA.mq5`

- [ ] **Step 1: Update `last_h1_bar_time` only upon successful pipeline completion**
- [ ] **Step 2: Invalidate H1 regime on feed/copy failure**
- [ ] **Step 3: Compile with MetaEditor and verify 0 errors**

---

### Task 4: Fix F-05 — Pending Orders & Multi-Instance Exposure Lock
**Files:**
- Modify: `ExecutionBridge.mqh`
- Modify: `AdaptiveSurvivalEA.mq5`

- [ ] **Step 1: Include active orders in position count**
- [ ] **Step 2: Add GlobalVariable lock with timeout for concurrent execution prevention**
- [ ] **Step 3: Track order pending state through execution**
- [ ] **Step 4: Compile with MetaEditor and verify 0 errors**

---

### Task 5: Fix F-08 — Consistent Symbol Filling Mode & Price Normalization
**Files:**
- Modify: `ExecutionBridge.mqh`
- Modify: `ExecutionSafety.mqh`

- [ ] **Step 1: Query broker filling policy via `SYMBOL_FILLING_MODE`**
- [ ] **Step 2: Align `OrderCheck` filling mode with `CTrade` dynamic policy**
- [ ] **Step 3: Compile with MetaEditor and verify 0 errors**

---

### Task 6: Fix F-07 — Daily Loss Limit & Drawdown Rem Guard
**Files:**
- Modify: `Config.mqh`
- Modify: `AdaptiveSurvivalEA.mq5`

- [ ] **Step 1: Add daily loss parameters to Config.mqh**
- [ ] **Step 2: Implement daily realized/floating loss ledger in AdaptiveSurvivalEA.mq5**
- [ ] **Step 3: Compile with MetaEditor and verify 0 errors**

---

### Task 7: Fix F-02 — News Calendar Fail-Closed Integration
**Files:**
- Modify: `SessionNewsEngine.mqh`
- Modify: `AdaptiveSurvivalEA.mq5`

- [ ] **Step 1: Add MT5 native calendar check or fail-closed calendar reader**
- [ ] **Step 2: Wire news evaluation into gating check**
- [ ] **Step 3: Compile with MetaEditor and verify 0 errors**

---

### Task 8: Fix Python Test Suite Errors & Run Full Suite (F-09)
**Files:**
- Modify: `pytest.ini` or test configuration
- Modify: `tests/` path-dependent tests

- [ ] **Step 1: Fix import collisions and absolute paths in tests**
- [ ] **Step 2: Run `python -m pytest` and ensure 100% pass**

---

### Task 9: Final MetaEditor Compilation & Strategy Tester Verification
**Files:**
- Compile: `AdaptiveSurvivalEA.mq5`

- [ ] **Step 1: Run MetaEditor compile command**
- [ ] **Step 2: Verify compile output log has 0 errors and 0 warnings**
