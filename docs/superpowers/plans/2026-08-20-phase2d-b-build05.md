# Phase 2D-B — BUILD05 Volatility Quality Final Repair

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close all Volatility Quality bugs — replay invalid gate, compression/expansion evidence, direction-agnostic quality, score bounding, quality persistence with challenger dwell, and live/replay parity.

**Architecture:** VolatilityQualityEngine computes five evidence components (HEALTHY, COMPRESSED, EXPANDING, CHAOTIC, SHOCK) from ATR trend, range, body, efficiency magnitude, and displacement magnitude. VolatilityQualitySelect uses challenger-dwell persistence (not incumbent age). Replay must gate all quality computation inside `.valid`. All evidence components are [0,1] clamped, direction-agnostic (magnitude only), and bull/bear mirrors must produce identical results.

**Tech Stack:** MQL5 (MetaEditor), Python 3.12 + pytest, git, SHA256

**Base commit:** `bc00ce0e3c3e63fee99031f4bbf70575d1d9af06`

---

## File Map

| File | Role |
|------|------|
| `MarketBrain.mqh` | VolatilityQualityEngine (compression/expansion evidence), VolatilityQualitySelect (challenger dwell) |
| `AdaptiveSurvivalEA.mq5` | Replay: move quality inside .valid gate; live: add challenger globals |
| `tests/build05/reference_volatility.py` | Python reference: quality_enum with challenger dwell, compression/expansion evidence |
| `tests/build05/test_volatility.py` | Quality persistence, compression/expansion, direction-agnostic, bounded tests |
| `tests/build05/test_source_invariants.py` | Replay .valid gate invariant for VolQuality |

---

## Task 1: TDD RED — Write all failing tests first

Write all tests that will fail against the current implementation. Save raw RED output.

### 1a. Compression evidence tests (isolated components)

```python
# test_volatility.py additions

def test_compression_atr_decline_only():
    """ATR declining → compressionScore > 0, other components unaffected."""
    # 10 bars of ATR: recent 5 bars declining
    # Fixture: rates with high→low ATR trend, constant range/body
    ...

def test_compression_range_shrink_only():
    """Range shrinking → compressionScore > 0."""
    ...

def test_compression_body_shrink_only():
    """Body shrinking → compressionScore > 0."""
    ...

def test_compression_all_three():
    """ATR decline + range shrink + body shrink → compressionScore high."""
    ...

def test_compression_none():
    """No compression signals → compressionScore ≈ 0."""
    ...
```

### 1b. Expansion evidence tests

```python
def test_expansion_atr_rise_only():
    """ATR rising → expansionScore > 0."""
    ...

def test_expansion_range_expand_only():
    """Range expanding → expansionScore > 0."""
    ...

def test_expansion_body_expand_only():
    """Body expanding → expansionScore > 0."""
    ...

def test_expansion_efficiency_rise_only():
    """Efficiency magnitude rising → expansionScore > 0."""
    ...

def test_expansion_displacement_rise_only():
    """Absolute displacement rising → expansionScore > 0."""
    ...

def test_expansion_all_five():
    """All expansion components → expansionScore high."""
    ...
```

### 1c. Direction-agnostic quality tests

```python
def test_quality_bull_bear_mirror_equal():
    """Bull and bear mirrored OHLC must produce identical quality evidence."""
    ...
```

### 1d. Score bounding tests

```python
def test_quality_all_scores_bounded():
    """All quality scores [0,1] for adversarial fixtures."""
    ...

def test_quality_no_nan_inf():
    """No NaN/INF in any quality score for edge cases."""
    ...
```

### 1e. Quality persistence challenger dwell tests

```python
def test_quality_incumbent_held_by_insufficient_gap():
    """best != incumbent but gap < VOLQ_GAP → retain incumbent."""
    ...

def test_quality_challenger_bar1_held():
    """Challenger with sufficient gap → dwell=1, retained."""
    ...

def test_quality_challenger_bar2_commits():
    """Same challenger bar #2 → dwell=2 >= VOLQ_DWELL → commit."""
    ...

def test_quality_challenger_interruption_resets():
    """Different challenger resets dwell."""
    ...

def test_quality_incumbent_recovery_clears():
    """best == incumbent → clear pending challenger."""
    ...

def test_quality_invalid_freezes_challenger():
    """Invalid update freezes all quality persistence."""
    ...
```

### 1f. Replay invalid quality gate test

```python
def test_quality_replay_invalid_freezes_quality():
    """valid challenger bar #1, invalid bar, valid same challenger bar #2 → challenger frozen."""
    ...
```

### 1g. Save RED output

```bash
cd tests/build05 && python -m pytest test_volatility.py -v --tb=short 2>&1 | tee ../audits/2026-08-20/phase2d-b-build05/pre_fix_red.txt
```

---

## Task 2: Compression evidence — locked components

**Files:**
- Modify: `MarketBrain.mqh` (VolatilityQualityEngine)

Current implementation only uses ATR trend for compression. Add range shrink and body shrink as separate normalized components.

Locked aggregation:
```
compressionScore = mean(atrDeclineEvidence, rangeShrinkEvidence, bodyShrinkEvidence)
```

Each component: recent vs prior window, normalized to [0,1].

- [ ] **Step 1: Update VolatilityQualityEngine in MarketBrain.mqh**

Replace the compression/expansion evidence section. Add helper functions for range/body comparison:

```cpp
// Normalized shrink evidence: returns [0,1] where 1 = fully shrunk
double BrainShrinkEvidence(const double recentAvg, const double priorAvg)
{
   if(!(priorAvg > 0.0)) return 0.0;
   const double ratio = recentAvg / priorAvg;
   return BrainClampUnit(1.0 - ratio);  // ratio<1 means shrinking → positive evidence
}

// Normalized expand evidence: returns [0,1] where 1 = fully expanded
double BrainExpandEvidence(const double recentAvg, const double priorAvg)
{
   if(!(priorAvg > 0.0)) return 0.0;
   const double ratio = recentAvg / priorAvg;
   return BrainClampUnit(ratio - 1.0);  // ratio>1 means expanding → positive evidence
}
```

Update VolatilityQualityEngine to compute:
- `atrDeclineEvidence = BrainClampUnit(-atrTrend)` for compression
- `atrRiseEvidence = BrainClampUnit(atrTrend)` for expansion
- `rangeShrinkEvidence = BrainShrinkEvidence(recentRange, priorRange)`
- `rangeExpandEvidence = BrainExpandEvidence(recentRange, priorRange)`
- `bodyShrinkEvidence = BrainShrinkEvidence(recentBody, priorBody)`
- `bodyExpandEvidence = BrainExpandEvidence(recentBody, priorBody)`
- `efficiencyRiseEvidence = BrainExpandEvidence(recentEfficiency, priorEfficiency)`
- `displacementRiseEvidence = BrainExpandEvidence(recentAbsDisp, priorAbsDisp)`

Compression: `mean(atrDecline, rangeShrink, bodyShrink)`
Expansion: `mean(atrRise, rangeExpand, bodyExpand, efficiencyRise, displacementRise)`

- [ ] **Step 2: Run compression tests to verify they pass**

---

## Task 3: Expansion evidence — locked components

**Files:**
- Modify: `MarketBrain.mqh` (VolatilityQualityEngine, already modified in Task 2)

Locked aggregation:
```
expansionScore = mean(atrRiseEvidence, rangeExpandEvidence, bodyExpandEvidence, efficiencyRiseEvidence, displacementRiseEvidence)
```

- [ ] **Step 1: Update VolatilityQualityEngine (already done in Task 2)**
- [ ] **Step 2: Run expansion tests to verify they pass**

---

## Task 4: Direction-agnostic quality

**Files:**
- Verify: `MarketBrain.mqh` (VolatilityQualityEngine)

Current implementation already uses `BrainEfficiencyMagnitude` (not signed). Verify bull/bear mirrors produce identical evidence scores.

- [ ] **Step 1: Write and run mirror test**
- [ ] **Step 2: Verify no signed efficiency enters quality**

---

## Task 5: Score bounding — edge cases

**Files:**
- Verify/fix: `MarketBrain.mqh`

- [ ] **Step 1: Write adversarial fixtures**
  - High-wick (range >> body)
  - Extreme ATR (ratio >> 2.0)
  - Zero efficiency (path = net directional)
  - Near-zero range
  - Zero ATR
- [ ] **Step 2: Verify all scores [0,1] and no NaN/INF**

---

## Task 6: Quality persistence — challenger dwell repair

**Files:**
- Modify: `MarketBrain.mqh` (VolatilityQualitySelect)
- Modify: `AdaptiveSurvivalEA.mq5` (add challenger globals)
- Modify: `tests/build05/reference_volatility.py` (quality_enum)

Current `VolatilityQualitySelect` uses incumbent age/dwell pattern. Must change to challenger identity + consecutive dwell.

Locked policy:
```
best == incumbent → retain incumbent, clear challenger
best != incumbent but gap < VOLQ_GAP → retain incumbent, clear challenger
best != incumbent, gap >= VOLQ_GAP:
  same challenger → dwell+1
  different challenger → dwell=1
dwell < VOLQ_DWELL → retain incumbent
dwell >= VOLQ_DWELL → commit challenger, reset
qualityConfidence = evidence[committed_quality]
```

- [ ] **Step 1: Rewrite VolatilityQualitySelect**

New signature adds challenger + challengerDwell references:
```cpp
void VolatilityQualitySelect(const double &evidence[],
                              ENUM_VOLATILITY_QUALITY &incumbent,
                              double &incumbentConf,
                              ENUM_VOLATILITY_QUALITY &challenger,
                              int &challengerDwell)
```

- [ ] **Step 2: Add challenger globals to AdaptiveSurvivalEA.mq5**

```cpp
ENUM_VOLATILITY_QUALITY b05_vol_quality_challenger = VOLQ_HEALTHY;
int b05_vol_quality_challenger_dwell = 0;
```

Update live UpdateH1Brain path and replay path to use new signature.

- [ ] **Step 3: Update Python reference quality_enum**

```python
def quality_enum(evidence, incumbent=VOL_QUALITY.HEALTHY,
                 incumbent_conf=0.0, challenger=None, challenger_dwell=0):
    """Return (state, confidence, challenger, challenger_dwell)."""
    ...
```

- [ ] **Step 4: Run quality persistence tests**

---

## Task 7: Replay invalid quality gate

**Files:**
- Modify: `AdaptiveSurvivalEA.mq5` (RebuildRegimeFusionState)

Move VolatilityQualityEngine + VolatilityQualitySelect + all quality persistence mutation inside `if(replayBrain.volatility.valid)`.

- [ ] **Step 1: Edit replay section**
- [ ] **Step 2: Add source invariant test**

---

## Task 8: Live/replay parity source invariants

**Files:**
- Modify: `tests/build05/test_source_invariants.py`

- [ ] **Step 1: Add invariant tests**
  - Replay VolatilityQualityEngine inside .valid gate
  - Replay VolatilityQualitySelect inside .valid gate
  - No quality persistence mutation outside .valid gate
  - Live and replay use same VolatilityQualitySelect signature

---

## Task 9: Full regression

- [ ] **Step 1: BUILD05** — 0 failed, 0 skipped, 0 deselected
- [ ] **Step 2: BUILD04** — 0 failed

---

## Task 10: Deploy + compile

- [ ] **Step 1: Sync all .mq5/.mqh to deployed tree**
- [ ] **Step 2: Compile — 0 errors, 0 warnings**
- [ ] **Step 3: SHA256 comparison — all MATCH**
- [ ] **Step 4: Save compile.log to evidence**

---

## Task 11: Evidence + git

- [ ] **Step 1: Generate raw evidence files**
  - pre_fix_red.txt
  - build05_pytest_vv.txt
  - build04_pytest_vv.txt
  - compile.log
  - ex5_sha256.txt
  - ex5_size.txt
  - workspace_vs_deployed_sha256.txt
  - provenance.txt (with actual Commit B SHA)

- [ ] **Step 2: Commit A — source + tests**
- [ ] **Step 3: Commit B — evidence only**
- [ ] **Step 4: Push, verify HEAD == origin/main**
- [ ] **Step 5: Copy exact SHAs, STOP**
