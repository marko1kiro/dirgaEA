# BUILD06-R2 Native Parity Reconstruction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make native BUILD06 consume one normalized, aligned H1 observation and reproduce locked Python R1 behavior for scoring, state, B06D1, and cold replay.

**Architecture:** Add one native observation envelope with explicit `criticalCoreValid`, per-domain validity, and nullable break ages. Normalize it once before all scoring/lifecycle logic. Route live and replay through one ingestion function, then hydrate reconstructed B04/B05/B06 state only after full alignment succeeds.

**Tech Stack:** MQL5, Python 3.12, pytest, Git

---

### Task 1: Lock native RED contracts

**Files:**
- Create: `tests/build06/test_native_input_contracts.py`
- Create: `tests/build06/test_native_scoring_contracts.py`
- Create: `tests/build06/test_native_state_contracts.py`
- Create: `tests/build06/test_native_b06d1_contract.py`
- Create: `tests/build06/test_native_replay_contracts.py`
- Create: `tests/build06/test_native_probe_contract.py`
- Create: `tests/build06/native/Build06ParityProbe.mq5`

- [ ] Add Python parser coverage for `case=<id>|canonical=<raw canonical>|signature=<raw signature>` records and require `B06D1:D80BE01B4A71B434` for `baseline_signature`.
- [ ] Add MQL5 script probe manifest cases `baseline_signature`, `invalid_stale`, `lookback_boundary`, `uncertain_tie`, and `replay_hydration`; print machine-readable raw canonical/signature records.
- [ ] Run `python -m pytest tests/build06/test_native_input_contracts.py tests/build06/test_native_scoring_contracts.py tests/build06/test_native_state_contracts.py tests/build06/test_native_b06d1_contract.py tests/build06/test_native_replay_contracts.py tests/build06/test_native_probe_contract.py -v --tb=short`.
- [ ] Confirm assertion failures name absent native contracts, never syntax or import errors.

### Task 2: Normalize one native observation

**Files:**
- Modify: `Types.mqh`
- Modify: `RegimeFusion.mqh`
- Modify: `AdaptiveSurvivalEA.mq5`

- [ ] Add `RegimeObservation` carrying final B04/B05 snapshots, domain-valid flags, explicit `criticalCoreValid`, exact aligned timestamp, and `Present + ageBars` nullable break ages.
- [ ] Add `RegimeNormalizeObservation`; zero invalid domain data before scores, vetoes, maturation, failure, confidence, and FIFO decisions.
- [ ] Derive break ages from final `breaks[]` with `age < BreakoutLookbackBars`; no literal `4` or hour arithmetic in scoring.
- [ ] Run input/scoring/state contracts; expected PASS.

### Task 3: Apply selection and lifecycle parity

**Files:**
- Modify: `RegimeFusion.mqh`

- [ ] Score normalized observation only, then apply post-score eligibility before `RegimeArgmax` and hysteresis.
- [ ] Gate structural conflict, chaos veto, breakout maturation, failure checks, and compression FIFO writes on relevant domain validity.
- [ ] Clear pending challenger on effective ties with `UNCERTAIN` incumbent.
- [ ] Keep BUILD06 classification-only: native fusion and orchestration contain no `CTrade`, `OrderSend`, `OrderCheck`, `PositionModify`, or `PositionClose` API call.
- [ ] Run scoring/state contracts; expected PASS.

### Task 4: Freeze exact B06D1 canonical bytes

**Files:**
- Modify: `DiagnosticCollector.mqh`
- Modify: `AdaptiveSurvivalEA.mq5`

- [ ] Use `DoubleToString(value, 15)` for every B06D1 decimal and `%016I64X` for hash width. Emit fields exactly in this order: `v`, `regime`, `quality`, `confidence`, `valid`, `initialized`, `latest`, `age`, `prev`, `structure`, `direction`, `dscore`, `momentum`, `mstrength`, `mda`, `vlevel`, `vquality`, `comp`, `exp`, `sTB`, `sTBe`, `sR`, `sBB`, `sBBe`, `sU`, `tx`, `candAge`, `pend`, `complete`, `degraded`, `cm_count`, `cm_obs`.
- [ ] Include exact `NONE` pending identity, initialized state, and FIFO in oldest-to-newest order; executable probe must produce `B06D1:D80BE01B4A71B434` for baseline signature fixture.
- [ ] Pass fusion state to signature generation and diagnostics.
- [ ] Run B06D1 contract; expected PASS.

### Task 5: Reconstruct through shared ingestion

**Files:**
- Modify: `AdaptiveSurvivalEA.mq5`

- [ ] Create `IngestRegimeObservation` used by live update and each replay bar; it aligns all B04/B05 timestamps before mutation.
- [ ] Acquire all available completed H1 history with `WHOLE_ARRAY`; if any required rates or indicator series is unavailable, log `REPLAY_HISTORY_UNAVAILABLE` and retain live state unchanged.
- [ ] Replay into locals; reject every timestamp mismatch before ingestion. Atomically assign B04, B05, B06 state/result, FIFO, and primed flags only after full replay succeeds.
- [ ] Run replay contracts; expected PASS.

### Task 6: Verify regressions

**Files:**
- Modify only files above if verification exposes a contract defect.

- [ ] Run focused native contracts.
- [ ] Run `python -m pytest tests/build06 -v`.
- [ ] Run `git diff --check` and inspect `git status --short`.
- [ ] Do not modify `tests/build06/reference_fusion.py` or existing R1 tests.
