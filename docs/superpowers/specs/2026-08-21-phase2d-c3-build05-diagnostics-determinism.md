# PHASE 2D-C3 BUILD05 Diagnostic and Determinism Closure

**Date:** 2026-08-21

## Goal

Make BUILD05 diagnostics live-only, cumulative, single-emission, and derived from exact production intermediates while preserving scoring, persistence, fail-closed behavior, and B05D2.

## Design

`ProcessBuild05ClosedHistoryPrefix` remains sole canonical state transition. Caller supplies `Build05RawTrace &trace`; canonical zeroes/fills it and never logs or accesses globals/counters. Direction, momentum, volatility-level, and volatility-quality engines accept trace output references and assign values from local production intermediates, avoiding diagnostic recomputation.

Replay owns local trace and invokes canonical with the same calculation inputs as live orchestration. Replay emits no live diagnostics and touches no live diagnostic counters. Live orchestration rejects duplicate/older closed H1 before canonical mutation, snapshots committed enums, invokes canonical once, updates one cumulative `Build05DiagnosticCounters`, then emits at most one transition set, one `BRAIN_UPDATE`, and one bounded cumulative `B05_SAFETY` group under `Build05DiagnosticMode`.

Transitions use exact event names `B05_DIRECTION_TRANSITION`, `B05_MOMENTUM_TRANSITION`, `B05_VOLLEVEL_TRANSITION`, and `B05_VOLQUALITY_TRANSITION`. Emission requires accepted valid domain output and actual committed enum difference. Messages carry `closed_h1`, `from`, `to`, and relevant dwell/persist/challenger fields.

`BRAIN_UPDATE` uses `schema=B05T1 h=<closedH1> d=[...] m=[...] v=[...] p=[...] sig=B05D2:<hash> end=1`. Runtime raw doubles use fixed-point integer encoding with scale 10000: MQL5 encodes with `MathRound(value * 10000)` and consumers decode with `encoded / 10000.0`. Canonical B05D2 keeps its 15-digit serializer unchanged. Field order remains `d`, `m`, `v`, `p`; stable positions are:

- `d`: state, score, valid, fastSlopeAtr, slowSlopeAtr, positioning, signedDisplacement, signedEfficiency, rawScore
- `m`: state, strength, delta, slope, alignment, valid, degraded, bodyAtr, bodyRange, closeLocation, signedProgression, progressionStrength, efficiencyMagnitude, signedEfficiency, rawScore, adxCurrent, adxPrevious, adxSlope
- `v`: level, levelScore, quality, qualityConfidence, valid, qualityReady, atrCurrent, atrBaseline, atrRatio, recentAtr, priorAtr, atrDecline, atrRise, recentRange, priorRange, rangeShrink, rangeExpand, recentBody, priorBody, bodyShrink, bodyExpand, recentEfficiency, priorEfficiency, efficiencyRise, recentDisplacement, priorDisplacement, displacementRise, wickNoise, healthy, compression, expansion, chaos, shock
- `p`: directionState, directionDwell, directionChallenger, directionChallengerDwell, momentumState, momentumPersist, prevMomentumStrength, momentumStrengthPrimed, volLevel, volLevelDwell, volLevelChallenger, volLevelChallengerDwell, volQuality, volQualityConfidence, volQualityPrimed, volQualityChallenger, volQualityChallengerDwell

Trace remains outside `Build05BehaviorState`, `H1BrainResult`, risk, and signature serialization.

## Verification

Python tests parse comment/string-masked MQL5 scopes and calls for structural/dataflow guarantees. Behavioral fixture extends production-equivalent Python reference logic, runs deterministic continuous and cold-replay/hydration scenarios, compares full state/result/B05D2 at N and N+1, repeats cold replay, and proves omission of a non-default hydration field fails equality.
