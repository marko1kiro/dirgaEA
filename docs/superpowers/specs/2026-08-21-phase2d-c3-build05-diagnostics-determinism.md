# PHASE 2D-C3 BUILD05 Diagnostic and Determinism Closure

**Date:** 2026-08-21

## Goal

Make BUILD05 diagnostics live-only, cumulative, single-emission, and derived from exact production intermediates while preserving scoring, persistence, fail-closed behavior, and B05D2.

## Design

`ProcessBuild05ClosedHistoryPrefix` remains sole canonical state transition. Caller supplies `Build05RawTrace &trace`; canonical zeroes/fills it and never logs or accesses globals/counters. Direction, momentum, volatility-level, and volatility-quality engines accept trace output references and assign values from local production intermediates, avoiding diagnostic recomputation.

Replay owns local trace and local copy-failure output. It never invokes diagnostic collectors and never mutates live diagnostic counters. Live orchestration rejects duplicate/older closed H1 before canonical mutation, snapshots committed enums, invokes canonical once, updates one cumulative `Build05DiagnosticCounters`, then emits at most one transition set, one `BRAIN_UPDATE`, and one bounded cumulative `B05_SAFETY` group under `Build05DiagnosticMode`.

Transitions use exact event names `B05_DIRECTION_TRANSITION`, `B05_MOMENTUM_TRANSITION`, `B05_VOLLEVEL_TRANSITION`, and `B05_VOLQUALITY_TRANSITION`. Emission requires accepted valid domain output and actual committed enum difference. Messages carry `closed_h1`, `from`, `to`, and relevant dwell/persist/challenger fields.

`BRAIN_UPDATE` carries closed-H1 identity, final enums/scores, full persistence state, unchanged ASCII FNV-1a B05D2, and complete raw trace. Trace remains outside `Build05BehaviorState`, `H1BrainResult`, risk, and signature serialization.

## Verification

Python tests parse comment/string-masked MQL5 scopes and calls for structural/dataflow guarantees. Behavioral fixture extends production-equivalent Python reference logic, runs deterministic continuous and cold-replay/hydration scenarios, compares full state/result/B05D2 at N and N+1, repeats cold replay, and proves omission of a non-default hydration field fails equality.
