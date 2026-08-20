# PHASE 2D-C3 BUILD05 Diagnostics and Determinism Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close BUILD05 trace provenance, live-only diagnostics, cumulative safety counters, committed transitions, and restart determinism without changing locked behavior or B05D2.

**Architecture:** Keep `ProcessBuild05ClosedHistoryPrefix` sole canonical updater and add caller-owned trace output. Engines expose exact local intermediates through output trace fields; live orchestration alone updates counters and emits diagnostics, while replay remains side-effect-free.

**Tech Stack:** MQL5, Python 3.12, pytest, Git

---

### Task 1: Genuine RED coverage

**Files:**
- Create: `tests/build05/test_phase2d_c3.py`
- Create: `tests/build05/reference_build05.py`

- [ ] Add masked-source parser tests for canonical trace ownership, no canonical logging/collector calls, exact live/replay call counts, full scoped trace fields, production-intermediate assignments, counters, transition gates/event payloads, and single diagnostic update.
- [ ] Add deterministic Python fixture using actual BUILD05 formulas and persistence functions. Compare continuous N/N+1 with replay/hydrate/N+1, full state/result/B05D2, repeated replay signatures, and omitted-field negative control.
- [ ] Run `python -m pytest tests/build05/test_phase2d_c3.py -v --tb=short` and save expected feature-missing failures to ignored `phase2d-c3-red.tmp`.

### Task 2: Canonical production trace

**Files:**
- Modify: `DiagnosticCollector.mqh`
- Modify: `MarketBrain.mqh`

- [ ] Expand `Build05RawTrace` with exact direction, momentum, ADX, volatility, readiness, and five quality fields.
- [ ] Add trace reset/init function.
- [ ] Pass trace outputs into engines and assign fields from production locals exactly once.
- [ ] Change canonical signature to caller-owned `Build05RawTrace &trace`; remove all logging and collector access.
- [ ] Keep classification, persistence, validity, and B05D2 semantics unchanged.

### Task 3: Live-only orchestration and diagnostics

**Files:**
- Modify: `AdaptiveSurvivalEA.mq5`
- Modify: `DiagnosticCollector.mqh`

- [ ] Add one global cumulative `Build05DiagnosticCounters` and initialize it in `OnInit`.
- [ ] Increment duplicate/forming/copy/invalid/degraded/not-ready/abnormal counters from real live outcomes only.
- [ ] Reject duplicates before canonical mutation; call canonical once with live trace.
- [ ] Replay with local trace/copy-failure variables; never emit or touch live counters.
- [ ] Emit valid committed transitions with required exact event names and payload fields.
- [ ] Emit one `BRAIN_UPDATE` and one bounded cumulative `B05_SAFETY` per live diagnostic update.

### Task 4: GREEN and regressions

**Files:**
- Modify only files above if failures reveal C3 defects.

- [ ] Run focused C3 tests until green.
- [ ] Run `python -m pytest tests/build05 -v` and require zero failed/skipped/deselected.
- [ ] Run `python -m pytest tests/build04 -v` and require 13 passed.
- [ ] Do not compile, deploy, create evidence, or push.

### Task 5: Review and Commit A

- [ ] Inspect `git status --short`, `git diff --check`, `git diff`, and `git log --oneline -10`.
- [ ] Verify frozen BUILD06/07 files unchanged and temporary RED output untracked/ignored.
- [ ] Stage only intended source, tests, design, and plan.
- [ ] Commit `Phase 2D-C3: close BUILD05 diagnostics and determinism`.
- [ ] Report files, RED/GREEN counts, full regression counts, commit SHA, and compile-sensitive concerns.
