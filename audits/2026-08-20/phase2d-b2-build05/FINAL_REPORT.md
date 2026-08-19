# Phase 2D-B2: BUILD05 Volatility Quality Semantic Closure

**Date:** 2026-08-20
**Status:** COMPLETE
**Commits:** `2359003` (A: source+tests) → `5a5be2a` (B: evidence)

---

## Summary

Volatility Quality persistence state-machine fully repaired. Compression aggregation uses `BrainMean3` for equal 1/3 weighting across ATR, range, and body components. Efficiency/displacement channels properly separated into independent metrics. Stale confidence gap eliminated via primed-state initialization. Bull/bear mirror symmetry verified across all quality evidence components.

---

## MQL5 Changes

### `MarketBrain.mqh` — AE7724DF4CCA510269889D722B676805A839531A14CAFBD8A299BEA057212D63

| Change | Detail |
|--------|--------|
| `BrainMean3()` helper | `double BrainMean3(double a, double b, double c)` — computes `(a+b+c)/3.0` |
| Compression aggregation | `compression = BrainMean3(atrDecline, rangeShrink, bodyShrink)` — equal 1/3 weighting |
| Efficiency channel | `effRecent = netMoveRecent / totalPathRecent` — `|netMove|/totalPath` |
| Displacement channel | `dispRecent = netMoveRecent / ATRrecent` — `|netMove|/ATR` |
| `effRise` source | `BrainExpandEvidence(effRecent, effPrior)` — uses efficiency channel only |
| `dispRise` source | `BrainExpandEvidence(dispRecent, dispPrior)` — uses displacement channel only |
| `VolatilityQualitySelect` | Primed bool replaces `incConf <= 0` check; gap uses `evidence[(int)incState]` not stale `incConf` |
| Live global | `b05_vol_quality_primed` — initialized false, set true after first compute |

### `AdaptiveSurvivalEA.mq5` — 49940639DE70ACBFE36E4D28D584A58625B77A36B18E052ED5E0C71DE8F94703

| Change | Detail |
|--------|--------|
| Live caller | Passes `primed=b05_vol_quality_primed`; qualityConfidence = `b05_vol_quality_conf` |
| Replay caller | `vQualityPrimed` local; quality inside `.valid` gate; `vQualityResult.primed = vQualityPrimed` |
| Replay primed | Initialized false, set true after first compute in replay path |

### `Types.mqh` — 24A75EABA827212CAEF09CDA837F6819079DBF883DE092A2FC9A45E25DAEA0DF

No changes. `VolatilityResult` struct unchanged.

---

## Python Reference Changes

### `reference_volatility.py`

| Change | Detail |
|--------|--------|
| `quality_enum` return | 5-tuple: `(state, conf, primed, challenger, challenger_dwell)` |
| `compute_compression_score` | `mean3(atrShrink, rangeShrink, bodyShrink)` — equal 1/3 weighting |
| `compute_expansion_score` | Separated `eff_*` and `disp_*` parameters — independent channels |
| `quality_enum` primed | Replaces `incConf <= 0` check; gap uses `evidence[state]` not stale `incConf` |

---

## Test Results

| Suite | Result |
|-------|--------|
| BUILD05 | **125/125 PASSED** |
| BUILD04 | **13/13 PASSED** |
| Compile | **0 errors, 0 warnings** |

### Test Files

| File | Tests | Focus |
|------|-------|-------|
| `test_volatility_quality.py` | 35 | Compression, eff/disp independence, stale gap, persistence, bull/bear mirror, bounding, replay gate |
| `test_red_phase2d_b2.py` | 16 | RED→GREEN semantic closure (compression, eff/disp, stale gap, mirror, full algorithm) |
| `test_volatility.py` | 4 | Level bands, quality evidence max, candidate gap/dwell, all 5 candidates |
| `test_source_invariants.py` | 15 | MQL5 source string invariants (compression BrainMean3, eff/disp separation, primed, replay gate) |
| `test_live_replay_parity.py` | 2 | Live/replay momentum persistence, challenger parity |

---

## EX5 Compilation

```
AdaptiveSurvivalEA.ex5: BF54BDEF2C0462797C13BC22B72C9E97F9A769DFD1227E6A96BDC15471D21A00
Size: 96416 bytes
MetaEditor: 0 errors, 0 warnings, 1404 ms elapsed
```

### Source SHA256 (workspace = deployed)

| File | SHA256 |
|------|--------|
| `MarketBrain.mqh` | `AE7724DF4CCA510269889D722B676805A839531A14CAFBD8A299BEA057212D63` |
| `AdaptiveSurvivalEA.mq5` | `49940639DE70ACBFE36E4D28D584A58625B77A36B18E052ED5E0C71DE8F94703` |
| `Types.mqh` | `24A75EABA827212CAEF09CDA837F6819079DBF883DE092A2FC9A45E25DAEA0DF` |

---

## Evidence Files

```
audits/2026-08-20/phase2d-b2-build05/
├── pre_fix_red.txt           # RAW pytest: 16 failures captured BEFORE repair
├── post_fix_green.txt        # RAW pytest: 125/125 BUILD05 AFTER repair
├── build04_regression.txt    # RAW pytest: 13/13 BUILD04
├── compile.log               # MetaEditor output: 0 errors, 0 warnings
├── invariants.txt            # Source SHA256, EX5 SHA256, test counts
├── reference_volatility.py   # Python reference (snapshot)
├── test_volatility.py        # Test file (snapshot)
├── test_volatility_quality.py # Test file (snapshot)
├── test_red_phase2d_b2.py    # RED tests (snapshot)
├── test_source_invariants.py # Invariant tests (snapshot)
└── test_live_replay_parity.py # Parity tests (snapshot)
```

---

## Git History

```
5a5be2a Phase 2D-B2: BUILD05 Volatility Quality Semantic Closure (Commit B: evidence)
2359003 Phase 2D-B2: BUILD05 Volatility Quality Semantic Closure (Commit A: source+tests)
514fe0a Phase 2D-B evidence: pre/post test output, EX5 SHA256, replay quality gate
db3c7cc Phase 2D-B: BUILD05 Volatility Quality initial repair (Commit A: source+tests)
bc00ce0 Phase 2D-A3B: Live/replay parity closure (Commit B: evidence)
62a4849 Phase 2D-A3B: Live/replay parity closure (Commit A: source+tests)
c323565 Phase 2D-A3: persistence state-machine repair (Commit B: evidence)
65da006 Phase 2D-A3: persistence state-machine repair (Commit A: source+tests)
e8a60e6 Phase 2D-A2: caller fail-closed, persistence validity guards
06c63ab Phase 2D-A: ResetH1BrainInvalid, explicit defaults
009c37a Phase 2C: Momentum direction-agnostic fix
```

---

## Remaining

**BUILD06/07 FROZEN** — architect must explicitly release before proceeding.

All BUILD05 persistence state-machine repairs complete:
- Direction ✅
- Momentum ✅
- Volatility Level ✅
- Volatility Quality ✅
- Live/replay parity ✅
