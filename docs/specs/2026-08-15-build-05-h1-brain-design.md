# BUILD 05 — H1 Direction / Momentum / Volatility Design Spec

**Status:** LOCKED design (awaiting implementation).
**Scope:** H1 Direction, Momentum, Volatility Level, Volatility Quality, Compression/Expansion evidence.
**Out of scope:** Regime Fusion (BUILD 06), trade signals, M15 strategy, risk, execution.

---

## 1. Boundaries and invariants

1. BUILD 04 `SwingStructureResult` is an **independent evidence domain**. BUILD 05 reads it for
   diagnostic-only agreement logging and must **not** use it to alter Direction score or state.
   Structure is a BUILD 06 Regime Fusion input, not a BUILD 05 input.
2. BUILD 04 semantics are immutable. No BUILD 04 logic, thresholds, or struct fields are changed.
3. BUILD 05 produces **no direct trade signals**. Outputs are evidence consumed by BUILD 06.
4. Production indicators are native MQL5 (`iMA`, `iADX`, `iATR` + `CopyBuffer`) on **completed H1
   bars only** (shift 1). MCP `get_ema`/`get_adx`/`get_atr` are reference-validation only.
5. Every domain emits an **official enum** (downstream contract) plus **continuous supporting
   scores** (diagnostics/audit/parity). Scores are evidence, never signals.

---

## 2. Enums and paired scores

| Domain | Official enum | Supporting score(s) |
|---|---|---|
| Direction | `STRONG_BULL, BULL, NEUTRAL, BEAR, STRONG_BEAR` | `directionScore` signed `[-1.0, +1.0]` |
| Momentum | `EXPANDING, STRONG, NORMAL, WEAK, DECAYING` | `momentumStrengthScore` `[0.0, 1.0]`; diagnostic-only `momentumDirectionalAlignment` `[-1.0, +1.0]` |
| Volatility Level | `LOW, NORMAL, HIGH, EXTREME` (ordinal) | `volatilityLevelScore` magnitude `[0.0, 1.0]` |
| Volatility Quality | `HEALTHY, COMPRESSED, EXPANDING, CHAOTIC, SHOCK` (non-ordinal) | `qualityConfidence` `[0.0, 1.0]` + per-category evidence scores (`compressionScore`, `expansionScore`, `chaosScore`, `shockScore`, `healthyScore`, each `[0.0, 1.0]`) |

Each domain result struct:

```text
{ enum, valid, latestClosedH1, inputs snapshot, supporting score(s) }
```

---

## 3. Domain definitions

### 3.1 Direction

**Required inputs (all ATR-normalized):**
- fast EMA slope / ATR (default EMA 20)
- slow EMA slope / ATR (default EMA 50)
- relative positioning (price vs fast EMA vs slow EMA)
- price displacement = net move over N bars / ATR
- directional efficiency = net move / total path move

`directionScore` = weighted evidence mean, clamped to `[-1.0, +1.0]`.

Hysteresis (ordinal): enum transition requires the score to cross a commit band plus a minimum
dwell (N closed H1 bars) before flipping. Score always reflects current truth.

### 3.2 Momentum

**Required inputs:**
- recent candle body / ATR
- body / total range
- close location within range
- multi-bar directional progression
- directional efficiency

**Helper (supporting only):**
- ADX level, ADX slope

`momentumStrengthScore` = weighted mean of required inputs, clamped `[0.0, 1.0]`.
`momentumStrengthDelta` = change in `momentumStrengthScore` versus prior closed H1 bar.
`momentumStrengthSlope` = slope of `momentumStrengthScore` over a short lookback.
`momentumDirectionalAlignment` = diagnostic-only signed alignment of the multi-bar progression
and directional efficiency, clamped `[-1.0, +1.0]`.

Temporal classification: `EXPANDING` vs `STRONG` and `DECAYING` vs `WEAK` are determined by the
temporal change in price-based momentum strength (`momentumStrengthDelta` / `momentumStrengthSlope`).
ADX slope remains helper-only.

**ADX failure alone must not invalidate** otherwise-valid price-based Momentum. If ADX is
unavailable/invalid, Momentum remains valid and reports `helperDegraded=adx` (or similar) rather
than `valid=false`.

Persistence: Momentum uses **state-specific persistence** (EXPANDING/STRONG/etc. each have an
explicit exit condition), not a single ordinal band.

### 3.3 Volatility Level

**Required inputs:**
- current ATR
- ATR baseline (rolling mean over lookback)
- ATR ratio = current ATR / baseline

`volatilityLevelScore` = clamped monotonic mapping of ATR ratio to `[0.0, 1.0]` used only for
audit; enum banding uses ATR-ratio thresholds.

Hysteresis (ordinal): commit band + dwell, same discipline as Direction.

### 3.4 Volatility Quality (non-ordinal)

**Required inputs:**
- directional efficiency (shared)
- wick noise (wick/range)
- compression evidence (ATR declining, range shrinking, body shrinking)
- expansion evidence (ATR rising, range/body expanding, efficiency rising, displacement rising)

**Output:** enum `HEALTHY / COMPRESSED / EXPANDING / CHAOTIC / SHOCK` + `qualityConfidence`
`[0.0, 1.0]` + per-category evidence scores:

```text
compressionScore, expansionScore, chaosScore, shockScore, healthyScore  (each [0.0, 1.0])
```

All five non-ordinal enum candidates participate consistently in evidence-max selection.

Selection is **evidence-max** (highest category score) with candidate-confidence persistence
(no flip until a challenger exceeds the incumbent's confidence by a gap for a dwell window).
There is **no single scalar** linearly mapped into the enum.

### 3.5 Compression / Expansion evidence

Derived internally and feeds Volatility Quality. Exposed for diagnostics as
`COMPRESSING / EXPANDING / NEUTRAL`. Not a standalone downstream state.

---

## 4. Native indicator setup

- `iMA(_Symbol, PERIOD_H1, 20, 0, MODE_EMA, PRICE_CLOSE)`.
- `iMA(_Symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE)`.
- `iADX(_Symbol, PERIOD_H1, 14)` — read ADX mainline (buffer 0); DI buffers read only if needed
  for diagnostics, never required.

### 4.1 ATR handle ownership (unambiguous)

BUILD 05 does **not** take ownership of, reuse, or read the BUILD 04 ATR handle
(`atr_h1_handle` in `AdaptiveSurvivalEA.mq5`). BUILD 05 owns its own dedicated native ATR handle:

- Create in `OnInit`: `iATR(_Symbol, PERIOD_H1, 14)` into a BUILD 05-scoped handle variable
  (`atr_h1_handle_b05`).
- Read only by BUILD 05 code via `CopyBuffer`.
- Release in `OnDeinit` by BUILD 05 code via `IndicatorRelease`.

BUILD 04's handle creation, read, and release are unchanged; the two handles are independent.
This avoids any coupling to BUILD 04 ownership/semantics while keeping production indicators native.

All buffers read via `CopyBuffer(..., 1, requested, ...)` on completed bars, series → chronological.

Failure handling:
- Invalid ATR or rate copy → Direction/Momentum/Volatility all `valid=false`, enum defaults
  (`NEUTRAL`, `NORMAL`, `NORMAL`), scores 0, `helperDegraded` recorded.
- Invalid ADX copy → Momentum stays valid (price evidence intact), `helperDegraded=adx`.

---

## 5. Hysteresis summary (domain-specific)

| Domain | Mechanism |
|---|---|
| Direction | ordinal commit band + dwell |
| Volatility Level | ordinal commit band + dwell |
| Momentum | state-specific persistence (per-state exit conditions) |
| Volatility Quality | evidence-max + candidate-confidence persistence (gap + dwell) |

---

## 6. Diagnostic observability (BUILD 05)

- New `Build05DiagnosticMode` input, default `false`. When false, detailed emission and
  non-essential computation are skipped (production overhead minimized).
- One bounded record per H1 update: raw inputs (EMA slopes, displacement, efficiency, body/range,
  close loc, ADX level/slope, ATR ratio, wick noise, per-category quality scores), scores, enums,
  dwell/age, `helperDegraded`, structure-vs-direction agreement (diagnostic only).
- Transition-only records for enum changes.
- Versioned canonical ASCII FNV-1a signature `B05D1:<hex>` over finalized domain state
  (enums + scores + latest closed H1), excluding transient timestamps. Same discipline as BUILD 04.
- Safety counters: invalid ATR/CopyBuffer skips, duplicate H1 attempts, forming-bar attempts,
  abnormal skips.
- No trade API usage.

---

## 7. Native-vs-MCP parity plan

- Native (production): EA diagnostic logs `iMA`/`iADX`/`iATR` `CopyBuffer` values per completed H1
  timestamp.
- MCP (reference): `get_atr` (ATR14), `get_ema`, `get_adx` — all three Python reference endpoints
  are available and locked. Use them directly on identical completed H1 timestamps.
- Compare per timestamp with tolerance; report max abs/relative delta and PASS/FAIL.
- **Determinism:** two identical reloads → same `B05D1` signature.

---

## 8. Parameter surface (intentionally small)

Named inputs, no per-evidence-weight knobs:

```text
Direction: fast period (20), slow period (50), displacement bars, thresholds (commit bands), dwell
Momentum: body/range lookback, progression bars, state exit thresholds, dwell
Volatility: ATR baseline lookback, level ratio thresholds, level commit band/dwell
Volatility Quality: efficiency/chaos/shock thresholds, confidence gap, dwell
Build05DiagnosticMode (false)
```

No exposure of individual evidence weights. Thresholds are named config, not per-tick tunables.

---

## 9. Files & non-breaking changes

- `Types.mqh`: add Direction/Momentum/Volatility enums + result structs + `H1BrainResult`
  aggregator. No existing structs modified.
- New `MarketBrain.mqh`: Direction/Momentum/Volatility/Compression engines as pure functions over
  `MqlRates[]` + `double[]` buffers.
- `AdaptiveSurvivalEA.mq5`: native `iMA`×2 / `iADX` / `iATR` handles, H1 update hook (reuse
  `DetectNewBar(PERIOD_H1)`), call engines after structure update, emit diagnostics.
- `Config.mqh`: BUILD 05 inputs.
- `DiagnosticCollector.mqh`: BUILD 05 emit + signature (new helpers; BUILD 04 helpers untouched).

---

## 10. Acceptance (before BUILD 06)

- Compile 0 errors / 0 warnings; forbidden trade/strategy API scan clean; activity identity
  unchanged (0 side effects).
- XAUUSDm + EURUSDm: representative Direction/Momentum/Volatility enum + score logs, hysteresis
  (no wild flip), `helperDegraded` reporting, safety counters 0, deterministic `B05D1` signature
  across two reloads.
- Native-vs-MCP parity: ATR confirmed; EMA/ADX against locked endpoints with tolerance; any
  unavailable endpoint documented as caveat, never silently reimplemented.
- Synthetic/unit tests prove thresholds, hysteresis, dwell, decay, and quality transitions.
  Runtime events not naturally present are reported `NOT OBSERVED IN VALIDATION WINDOW`; thresholds
  are never tuned to manufacture them.
