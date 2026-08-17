# BUILD 06 — H1 Regime Fusion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement H1 Regime Fusion (native MQL5) as a classification-only layer that consumes final BUILD 04 + BUILD 05 outputs and emits `RegimeResult` (official regime enum + quality + confidence + supporting candidate scores), with a Python reference harness proving the fusion/hysteresis/maturation math.

**Architecture:** Pure MQL5 engine functions in a new `RegimeFusion.mqh` consume the already-computed `SwingStructureResult` + `H1BrainResult` (final outputs, never raw evidence) and emit `RegimeResult`. A separate Python harness independently re-implements the locked fusion math. No trade logic, no M15.

**Tech Stack:** MQL5 (pure functions over final structs), Python 3.12 (pytest harness, reference-only).

**Locked reference:** `docs/specs/2026-08-15-build-06-regime-fusion-design.md`.

---

## File structure

- Modify `Types.mqh`: append `ENUM_REGIME_STATE`, `ENUM_REGIME_QUALITY`, `ENUM_REGIME_TRANSITION_REASON`, `RegimeResult`, degradation bit defines.
- Create `RegimeFusion.mqh`: candidate scoring, compression memory, conflict/veto, hysteresis classify, maturation, `RegimeResult` builder.
- Modify `Config.mqh`: `Build06DiagnosticMode` + small B06 params.
- Modify `AdaptiveSurvivalEA.mq5`: B06 persistence state, `UpdateRegimeFusion()` after B04+B05, timestamp alignment check, store `RegimeResult`.
- Modify `DiagnosticCollector.mqh`: `[REGIME_FUSION]` + `[REGIME_TRANSITION]` + `B06D1` signature (B04/B05 helpers untouched).
- Create `tests/build06/` Python harness (pytest, reference-only).

---

## Task 1: Python reference harness — types + candidate scoring

**Files:**
- Create: `tests/build06/reference_fusion.py` (types + scoring + confidence + quality)
- Create: `tests/build06/test_scoring.py`

- [x] **Step 1: Write failing tests** for candidate scoring over synthetic domain tuples.
  - A: aligned bull → `scoreTrendBull` is the max candidate.
  - B: mirror bear → `scoreTrendBear` max.
  - C: strong bull structure with **no BOS** → `scoreTrendBull` high (BOS not in trend scoring).
  - D: range tuple → `scoreRange` max.
  - E: neutral + chaotic → not RANGE (RANGE suppressed by chaos).
  - F: compression context + fresh bull break + EXPANDING → `scoreBreakoutBull` max.
  - G: mirror.
  - J: bull structure + bear direction → conflict mass high (cross terms verified exactly).
  - K2: universally weak candidates → `scoreUncertain` high (weak-winner insufficiency; max real score < threshold).
  - Q: effective tie (within `TieEpsilon`) → tie resolution path exercised.
  - U1: dominant RANGE with balanced bull/bear subpairs → NOT UNCERTAIN (top-1/top-2 margin drives `balancedEvidence`).
  - MA: `momentumDirectionalAlignment` does NOT gate `M_supportiveBull`/`M_supportiveBear` (direction-agnostic strength).
- [x] **Step 2: Implement** `compute_candidate_scores(structure, direction, momentum, vol)` returning the five real scores per section 4 of the spec (fixed weights).
- [x] **Step 3: Green.** (12 passed)

## Task 2: Python reference harness — UNCERTAIN mass + confidence + quality

**Files:** `tests/build06/test_uncertain_confidence_quality.py`, extend `reference_fusion.py`.

- [x] **Step 1: Failing tests**
  - K: unambiguous chaos → UNCERTAIN with **high** confidence (`confidence == scoreUncertain`).
  - Confidence = final reported regime's own score vs best alternative (spec 6.1), NOT raw top-1.
  - V4: incumbent reported while behind → `confidence` has NO positive margin bonus (marginFactor=0 when scoreR < bestAlt).
  - V3: CHAOTIC + committed direction → chaosMass 0.45 (NOT hard veto); CHAOTIC + uncommitted → 1.00 (veto).
  - UNCERTAIN confidence is `scoreUncertain`, not `1 - scoreUncertain`.
  - Deterministic `balancedEvidence`, `weakWinnerMass`, `scoreUncertain` component mappings (exact equations, clamp behavior).
  - RegimeQuality regime-specific formulas (spec 6.2): Q1–Q10 (TREND/RANGE/BREAKOUT/UNCERTAIN, threshold boundaries 0.75/0.45, critical-invalid → WEAK, momentumDirectionalAlignment no-op).
- [x] **Step 2: Implement** `compute_confidence(...)`, `compute_quality(...)` (four regime-specific formulas, spec 6.2), and the deterministic UNCERTAIN sub-masses (`balancedEvidence`, `weakWinnerMass`, `chaosMass`, `structuralDirectionConflict`, `degradationMass`).
- [x] **Step 3: Green.**

## Task 3: Python reference harness — hysteresis / persistence

**Files:** `tests/build06/test_hysteresis.py`.

- [x] **Step 1: Failing tests**
  - L: challenger leads but gap < `ChallengerGap` → incumbent kept.
  - L2: challenger identity changes → `candidateAgeBars` resets to age 1 → no premature flip.
  - M: one-bar spike candidate → no flip-flop.
  - M2: incumbent score recomputed every bar (change incumbent evidence; challenger compared against recomputed value, not frozen).
  - Q: effective tie → retain incumbent when valid; UNCERTAIN when no incumbent.
  - R: identical input sequence → identical output sequence.
  - T1: `RegimeDwell=2` flips only on the 2nd consecutive challenger bar (age 1 → age 2), not the 1st.
- [x] **Step 2: Implement** `classify_regime(...)` with explicit `pendingCandidateRegime`, `candidateAgeBars` (1-based entry per section 8.0), per-bar incumbent recomputation, tie handling.
- [x] **Step 3: Green.**

## Task 4: Python reference harness — breakout maturation / aging / handoff

**Files:** `tests/build06/test_breakout.py`.

- [x] **Step 1: Failing tests**
  - H: BREAKOUT_BULL persists + structure accepts + dir bull → matures to TREND_BULL after `BreakoutMaturationMinBars`.
  - H2/T2: maturation blocked at age 1 (`BreakoutMaturationMinBars=2` → first eligible at age 2).
  - N: breakout exceeds `BreakoutMaxAgeBars` without acceptance → failed → UNCERTAIN.
  - T3: `BreakoutMaxAgeBars` triggers at age == max (not max+1).
  - I: failed breakout → UNCERTAIN → RANGE only after Structure==RANGE + non-chaotic + low conviction.
  - F1: immediate failure on explicit opposing structure/conflict (trigger 1), regardless of age.
  - Breakout never sticky beyond `BreakoutMaxAgeBars`.
- [x] **Step 2: Implement** maturation + aging + failed-breakout handoff (two exact triggers per section 10).
- [x] **Step 3: Green.**

## Task 4b: Python reference harness — compression rolling memory

**Files:** `tests/build06/test_compression_memory.py`, extend `reference_fusion.py`.

- [x] **Step 1: Failing tests** (bounded rolling buffer per spec section 7)
  - S1: old max evicted → `compressionMax` recomputed from retained observations (not stale max).
  - S2: current bar's compression excluded from its own breakout scoring (prior-only append-after-finalize).
  - S3: window overflow → FIFO eviction keeps exactly `BreakoutLookbackBars` observations.
  - S4: empty window → `Q_compressionContext == 0.0`.
- [x] **Step 2: Implement** `CompressionMemory` rolling buffer + `compression_max()` recompute.
- [x] **Step 3: Green.**

## Task 5: Python reference harness — degradation + invalid + determinism

**Files:** `tests/build06/test_degraded_invalid.py`.

- [x] **Step 1: Failing tests**
  - O: ADX helper degraded (`helperDegraded`) → fusion valid, no invalidation.
  - P: invalid core (no ATR/rates) → `valid=false`, `regime=UNCERTAIN`, `evidenceCompleteness=0.0`.
  - P2/V6: one non-critical domain degraded → `valid=true`, `evidenceCompleteness=0.75`, confidence reduced, bit set.
  - V5: ADX helper degraded → `evidenceCompleteness` UNCHANGED (still 1.0 when 4 domains valid).
  - R: identical sequence → identical `B06D1` signature (reference signature function).
  - V1: identical visible result, different `pendingCandidateRegime` → different `B06D1`.
  - V2: identical visible result + same max, different compression FIFO contents → different `B06D1`.
- [x] **Step 2: Implement** completeness (4×0.25)/degradation bits + reference `b06_signature()` (hashes `pendingCandidateRegime`, `momentumDirectionalAlignment` mirror, compression FIFO contents+count).
- [x] **Step 3: Green.**

## Task 5b: Python reference harness — cold-start / reload reconstruction

**Files:** `tests/build06/test_replay.py`, extend `reference_fusion.py`.

- [x] **Step 1: Failing tests** (spec section 15b)
  - W1: same chronological sequence of `(B04Final, B05Final)` tuples → continuous-run final state == cold-start replay final state (regime, quality, confidence, `B06D1`, `pendingCandidateRegime`, `candidateAgeBars`, `regimeAgeBars`, compression FIFO all equal).
  - W2: replay MUST be oldest→newest; feeding out-of-order detects a mismatch (guard).
- [x] **Step 2: Implement** a replay driver that reconstructs B06 state by feeding finalized `(B04Final, B05Final)` outputs through the same `classify_regime`/`update` entry point used live.
- [x] **Step 3: Green.**

## Task 6: MQL5 types — RegimeState/Quality/TransitionReason/RegimeResult

**Files:** Modify `Types.mqh`.

- [x] Append `ENUM_REGIME_STATE`, `ENUM_REGIME_QUALITY`, `ENUM_REGIME_TRANSITION_REASON`, degradation bit defines, `RegimeResult` struct (exact fields from spec section 3).
- [x] Compile check (0 errors/0 warnings).

## Task 7: RegimeFusion.mqh — pure engines

**Files:** Create `RegimeFusion.mqh`.

- [x] `RegimeCandidateScores(...)` — six scores from final `SwingStructureResult` + `H1BrainResult` (Momentum direction-agnostic; NO `directionalAlignment` gate).
- [x] `RegimeUncertainMass(...)` — conflict/insufficiency/chaos/balanced/degradation mass (deterministic equations; chaosMass 1.00/0.45/0.50/0).
- [x] `RegimeConfidence(...)` — final reported regime's own score vs best alternative (spec 6.1). `RegimeQuality(...)` — four regime-specific formulas (spec 6.2.1–6.2.6).
- [x] `RegimeCompressionMemory(...)` — bounded rolling buffer over a **dynamically sized** `obs[]` array (runtime `BreakoutLookbackBars`) + `compressionMax` recompute on eviction.
- [x] `RegimeClassify(...)` — hysteresis with `pendingCandidateRegime`, `candidateAgeBars` (1-based), per-bar incumbent recompute, tie handling.
- [x] `RegimeMaturation(...)` — breakout → trend / fail (two exact triggers).
- [x] `RegimeReplay(...)` — cold-start reconstruction driver (section 15b).
- [x] `RegimeResult` builder + `Build06Signature` helper.
- [x] Compile check.

## Task 8: Config + EA wiring + diagnostics

**Files:** Modify `Config.mqh`, `AdaptiveSurvivalEA.mq5`, `DiagnosticCollector.mqh`.

- [x] `Config.mqh`: `Build06DiagnosticMode=false` + B06 params (section 16 of spec).
- [x] `AdaptiveSurvivalEA.mq5`: B06 persistence state (`regime`, `previousRegime`, `regimeAgeBars`, `pendingCandidateRegime`, `candidateAgeBars`, dynamically sized compression memory); `UpdateRegimeFusion()` called after B04+B05 for the same closed H1; timestamp alignment check (skip + diagnostic on mismatch); store `RegimeResult`.
- [x] `AdaptiveSurvivalEA.mq5`: cold-start reconstruction on attach — replay synchronized completed-H1 B04/B05 final outputs oldest→newest through `RegimeReplay()` to rebuild B06 persistent state before live bars are processed (section 15b).
- [x] `DiagnosticCollector.mqh`: `Build06DiagnosticCollect` + `[REGIME_FUSION]`/`[REGIME_TRANSITION]` + `B06D1` FNV-1a signature (hashes pendingCandidateRegime, momentumDirectionalAlignment mirror, compression FIFO contents+count; B04/B05 helpers untouched).
- [x] Forbidden trade/strategy API scan = 0.
- [x] Compile check (0/0).

## Task 9: Runtime + parity validation

- [ ] Deploy `.ex5` + sources to MT5 data folder.
- [ ] Attach on EURUSDm + XAUUSDm H1 with `Build06DiagnosticMode=true`.
- [ ] Capture `[REGIME_FUSION]`/`[REGIME_TRANSITION]` records; verify representative regime/quality/confidence/scores/hysteresis/age/signature.
- [ ] Verify determinism: two identical reloads → identical `B06D1`.
- [ ] Verify reload reconstruction: detach + re-attach at the same history point → reconstructed persistent state + `B06D1` equal the pre-restart values (section 15b.3 native acceptance).
- [ ] Verify timestamp alignment (`B04.latestTime == B05.latestClosedH1 == B06.latestClosedH1`).
- [ ] Capture activity identity before/after → 0/0/0 unchanged.
- [ ] Report any regime states NOT naturally present as `NOT OBSERVED IN VALIDATION WINDOW`.

---

## Definition of done

- All locked A–R scenarios and variants pass (including K2/L2/M2/H2/P2/Q-tie, plus S1–S4 compression
  memory, T1–T3 age/dwell off-by-one, U1 dominant-range, MA direction-agnostic momentum, F1 immediate
  breakout failure, V1–V6 chaos/completeness/signature-collision, W1–W2 cold-start replay, Q1–Q10
  RegimeQuality, X1–X8 HARD-vs-SOFT uncertainty split).
- MQL5 compiles 0 errors / 0 warnings; forbidden trade/strategy scan 0.
- Runtime determinism (`B06D1`) + reload reconstruction + zero side effects proven on EURUSDm + XAUUSDm.
- Spec + plan committed; BUILD 04/05 untouched; BUILD 07 blocked.