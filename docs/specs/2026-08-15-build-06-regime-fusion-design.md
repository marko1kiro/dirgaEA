# BUILD 06 — H1 Regime Fusion Design Spec

**Status:** LOCKED design (awaiting implementation).
**Scope:** Combine BUILD 04 Structure + BUILD 05 Direction/Momentum/Volatility into ONE official H1
market regime plus confidence/quality metadata.
**Out of scope:** trade signals, entries, risk, execution, M15 strategy (BUILD 07+). Session/spread/
news/liquidity/slippage/execution quality.

---

## 1. Boundaries and invariants

1. BUILD 04 and BUILD 05 semantics are immutable. No B04/B05 logic, thresholds, or struct fields are
   changed unless a proven bug is found.
2. BUILD 06 is **classification/fusion only**. It answers "what market state are we in?", never
   "should we buy or sell?".
3. BUILD 06 **consumes the final outputs** of BUILD 04 and BUILD 05. It never re-computes raw evidence
   (EMA slopes, efficiency, body/range, displacement, ADX, ATR, etc.).
4. Domains stay independent. Structure contributes independently of Direction; the anti-double-counting
   discipline established in BUILD 05 (Structure kept out of Direction scoring) is preserved.
5. BUILD 06 produces an **official enum** (`RegimeState`) + **official quality** (`RegimeQuality`) +
   continuous `confidence` `[0,1]` + supporting candidate scores (diagnostics/audit).
6. Zero trade side effects. No `CTrade`, `OrderSend`, execution `OrderCheck`, position modification,
   strategy router, signal generation, M15 execution, or risk sizing.
7. H1 completed bars only (shift-1 semantics). Fusion never mixes evidence from mismatched H1 timestamps.

---

## 2. Official enums

### 2.1 RegimeState (downstream contract)

```
TREND_BULL
TREND_BEAR
RANGE
BREAKOUT_BULL
BREAKOUT_BEAR
UNCERTAIN
```

Six states only. No additional official regime states.

### 2.2 RegimeQuality

```
WEAK
NORMAL
STRONG
```

`RegimeQuality` describes **market-state evidence health only**. Session, spread, news, liquidity,
slippage, and execution quality are explicitly outside BUILD 06.

### 2.3 RegimeTransitionReason

```
NONE              // no change / steady state
INIT              // first valid fusion (bootstrap)
OVERRIDE          // immediate override (hard incompatibility veto)
CHALLENGE_WIN     // challenger beat incumbent via gap+dwell
MATURATION        // breakout matured into trend
FAILED_BREAKOUT   // breakout failed -> uncertain
DECAY             // trend momentum decay -> uncertain/range
DEGRADED          // evidence degradation forced reclassification
RESET             // invalid critical input -> fallback
```

### 2.4 Degradation bitmask

```
REGIME_DEGRADED_NONE       0
REGIME_DEGRADED_STRUCTURE  (1<<0)
REGIME_DEGRADED_DIRECTION  (1<<1)
REGIME_DEGRADED_MOMENTUM   (1<<2)
REGIME_DEGRADED_VOLATILITY (1<<3)
```

---

## 3. RegimeResult contract (exact)

```mql5
struct RegimeResult
{
   // official downstream contract
   ENUM_REGIME_STATE      regime;           // official enum
   ENUM_REGIME_QUALITY    quality;          // WEAK / NORMAL / STRONG
   double                 confidence;       // [0,1] certainty of the FINAL reported regime
   bool                   valid;            // false => critical-input failure (regime forced UNCERTAIN)

   // temporal bookkeeping
   datetime               latestClosedH1;   // exact aligned timestamp
   int                    regimeAgeBars;    // bars since incumbent last changed
   ENUM_REGIME_STATE      previousRegime;   // prior official regime (before this bar's decision)

   // upstream FINAL evidence snapshot (read-only mirrors)
   ENUM_STRUCTURE_STATE   structureState;
   ENUM_DIRECTION_STATE   directionState;
   double                 directionScore;       // signed [-1,+1]
   ENUM_MOMENTUM_STATE    momentumState;
   double                 momentumStrength;     // [0,1]
   double                 momentumDirectionalAlignment; // DIAGNOSTIC-ONLY mirror; never used in B06 scoring
   ENUM_VOLATILITY_LEVEL  volatilityLevel;
   ENUM_VOLATILITY_QUALITY volatilityQuality;
   double                 compressionEvidence;  // [0,1] final B05 compression evidence
   double                 expansionEvidence;    // [0,1] final B05 expansion evidence

   // fusion candidate scores (diagnostic-only, deterministic)
   double                 scoreTrendBull;
   double                 scoreTrendBear;
   double                 scoreRange;
   double                 scoreBreakoutBull;
   double                 scoreBreakoutBear;
   double                 scoreUncertain;        // derived conflict/uncertainty mass

   // hysteresis observables
   ENUM_REGIME_TRANSITION_REASON transitionReason;
   ENUM_REGIME_STATE      pendingCandidateRegime; // explicit challenger identity
   int                    candidateAgeBars;       // dwell of the current pending candidate
   double                 challengerConfidence;   // challenger candidate score (this bar)
   double                 incumbentConfidence;    // incumbent candidate score RECOMPUTED this bar

   // completeness / degradation
   double                 evidenceCompleteness;   // [0,1]
   int                    degradedDomains;        // bitmask (section 2.4)
};
```

---

## 4. Candidate-score fusion model

Five directional/state candidates plus one **derived** uncertainty mass.

### 4.1 Candidate scores

```
scoreTrendBull
scoreTrendBear
scoreRange
scoreBreakoutBull
scoreBreakoutBear
scoreUncertain   // derived conflict/insufficiency mass (NOT a sixth symmetric candidate)
```

Each candidate is a **weighted sum of at most five domain-group contributions** (Structure `S`,
Direction `D`, Momentum `M`, Volatility Level `V`, Volatility Quality `Q`). BUILD 06 reads only the
**collapsed** domain results, never raw sub-inputs.

### 4.2 Domain contribution groups (anti-double-counting boundary)

| Group | Source (final output only) | Contribution |
|---|---|---|
| `S` Structure | `SwingStructureResult.state` + `breaks[]` recency flags | persistent structural bias; fresh break events (BREAKOUT only) |
| `D` Direction | `DirectionResult.state`, `.score` | signed directional conviction |
| `M` Momentum | `MomentumResult.state`, `.strengthScore` | expansion/decay state + strength |
| `M_diag` (diagnostic-only) | `MomentumResult.directionalAlignment` | NEVER enters B06 scoring; diagnostic-only mirror |
| `V` Volatility Level | `VolatilityResult.level`, `.levelScore` | trend vs range suitability |
| `Q` Quality/compression | `VolatilityResult.quality`, `.compressionScore`, `.expansionScore`, `.chaosScore` | compression setup, expansion onset, chaos |

Weights are **fixed v1 hypothesis constants** (not exposed inputs). See section 14.

### 4.3 TREND_BULL

```
scoreTrendBull = 0.35*S_bullishTrend + 0.30*D_bullish + 0.15*M_supportiveBull
               + 0.10*V_trendSuitable + 0.10*Q_clean
```

- `S_bullishTrend`: `BULLISH_STRONG→1.0`, `BULLISH_WEAK→0.6`, `MIXED→0.25`, else `0.0`.
  **Persistent StructureState supports TREND. Fresh BOS/strong-break gives NO trend bonus in v1.**
- `D_bullish`: `max(0.0, directionScore)`.
- `M_supportiveBull`: `EXPANDING→1.0`, `STRONG→1.0`, `NORMAL→0.6`, `WEAK→0.3`, `DECAYING→0.0`.
  **No `directionalAlignment` gate.** Momentum direction (bull/bear) is NOT determined by
  `momentumDirectionalAlignment`; it comes from independent Structure + Direction domains. The
  Momentum contribution is direction-agnostic strength (see section 4.8).
- `V_trendSuitable`: `NORMAL→1.0`, `HIGH→1.0`, `LOW→0.5`, `EXTREME→0.3`.
- `Q_clean`: `HEALTHY→1.0`, `EXPANDING→0.7`, `COMPRESSED→0.4`, `SHOCK→0.2`, `CHAOTIC→0.15`.

**BOS is NOT required for strong trend classification.** Locked BUILD 04 semantic: `HH+HL` MAJOR
sequence can support bullish strong structure; `LH+LL` MAJOR can support bearish strong structure. BOS
is separate structural evidence.

### 4.4 TREND_BEAR (exact mirror)

`D_bearish = max(0.0, -directionScore)`; `M_supportiveBear = M_supportiveBull` (same direction-agnostic
strength mapping); `S_bearishTrend`: `BEARISH_STRONG→1.0`, `BEARISH_WEAK→0.6`, `MIXED→0.25`, else `0.0`.

### 4.5 RANGE

```
scoreRange = 0.40*S_range + 0.25*D_neutral + 0.15*M_nonExpansion
           + 0.10*V_rangeSuitable + 0.10*Q_twoSided
```

- `S_range`: `RANGE→1.0`, `MIXED→0.5`, else `0.0`. (EH+EL is implied by the `RANGE` state; not re-derived.)
- `D_neutral`: `1.0 - |directionScore|`.
- `M_nonExpansion`: `NORMAL→1.0`, `WEAK→0.8`, `DECAYING→0.5`, `STRONG→0.3`, `EXPANDING→0.1`.
- `V_rangeSuitable`: `LOW→1.0`, `NORMAL→0.7`, `HIGH→0.4`, `EXTREME→0.1`.
- `Q_twoSided`: `COMPRESSED→1.0`, `HEALTHY→0.7`, `EXPANDING→0.3`, `CHAOTIC→0.0`, `SHOCK→0.0`.

RANGE is NOT classified merely because Direction == NEUTRAL. NEUTRAL + chaos is UNCERTAIN, not RANGE.

### 4.6 BREAKOUT_BULL / BREAKOUT_BEAR

```
scoreBreakoutBull = 0.30*S_breakBull + 0.25*Q_compressionContext + 0.20*M_expanding
                  + 0.15*D_bullish + 0.10*V_expanding
```

- `S_breakBull`: a **fresh** bullish `StructureBreak` (BOS or strong break) within
  `BreakoutLookbackBars` (default 4) → `1.0`; older within window → `0.4`; none → `0.0`. Uses the
  already-final `breaks[]` array; no re-derivation.
- `Q_compressionContext`: **temporal memory of prior compression** (see section 7), NOT the compression
  score on the breakout bar itself. A breakout requires prior compression context; compression need not
  be high on the breakout bar.
- `M_expanding`: `EXPANDING→1.0`, `STRONG→0.7`, `NORMAL→0.3`, `WEAK→0.1`, `DECAYING→0.0`.
- `D_bullish`: as in TREND.
- `V_expanding`: **distinct from Volatility Level.** Expansion evidence (`expansionScore`) signals
  directional expansion onset; HIGH Volatility Level is not synonymous with expansion. `V_expanding =
  expansionScore` (the B05 expansion candidate score), NOT `level==HIGH`.

BREAKOUT represents a **transitional expansion state**, not a strong trend. It must not be permanently
sticky.

### 4.7 UNCERTAIN (derived conflict + insufficiency mass)

`scoreUncertain` is a **derived mass**, computed deterministically from **five** sub-masses via
`max(...)`:

```
scoreUncertain = clamp01( max(
   structuralDirectionConflict,
   chaosMass,
   balancedEvidence,
   weakWinnerMass,
   degradationMass
) )
```

Every sub-mass below is a pure function of the five real candidate scores
(`scoreTrendBull, scoreTrendBear, scoreRange, scoreBreakoutBull, scoreBreakoutBear`) plus the upstream
flags (`structureState`, `volatilityQuality`, `evidenceCompleteness`, `degradedDomains`). No randomness,
no ordering bias. `clamp01(x) = min(1.0, max(0.0, x))`.

#### 4.7.1 `structuralDirectionConflict` ∈ {0.0, 1.0}

```
bullStruct  = structureState ∈ {BULLISH_STRONG, BULLISH_WEAK}
bearStruct  = structureState ∈ {BEARISH_STRONG, BEARISH_WEAK}
bullDir     = directionScore >  +DIR_COMMIT (0.45)
bearDir     = directionScore <  -DIR_COMMIT (0.45)

structuralDirectionConflict = 1.0  if (bullStruct AND bearDir) OR (bearStruct AND bullDir)
                             = 0.0  otherwise
```

`DIR_COMMIT` is a fixed constant (not an exposed input); it matches the section 5 rule 2 threshold.

#### 4.7.2 `chaosMass` ∈ [0,1]

```
committedDir  = |directionScore| >= DIR_COMMIT   // direction is committed (bull or bear)

chaosMass = 1.00  if volatilityQuality == CHAOTIC AND (NOT committedDir)   // hard veto case
          = 0.45  if volatilityQuality == CHAOTIC AND committedDir         // chaos w/ committed direction
          = 0.50  if volatilityQuality == SHOCK
          = 0.00  otherwise
```

(Chaos/shock are read from the collapsed `volatilityQuality`; no raw wick/efficiency re-derivation. The
`1.00` value is reserved for the case where `volatilityQuality == CHAOTIC` AND `|directionScore| <
DIR_COMMIT` — the exact condition under which chaos is a hard veto per section 5 rule 2. When direction is
committed, chaos is downgraded to a non-veto mass `0.45`.)

#### 4.7.3 `balancedEvidence` ∈ [0,1] — top-1 vs top-2 margin (NOT bull/bear subpair balance)

A clearly dominant RANGE must NOT be classified UNCERTAIN merely because the bull/bear subpairs happen
to be balanced. `balancedEvidence` is therefore computed from the **margin between the single top
candidate and the single runner-up across all five real candidates**, not from any bull-vs-bear
subpair.

```
candidates = [scoreTrendBull, scoreTrendBear, scoreRange, scoreBreakoutBull, scoreBreakoutBear]
top1       = max(candidates)
top2       = second-highest distinct candidate (NOT top1; ties broken by fixed candidate order:
             TrendBull, TrendBear, Range, BreakoutBull, BreakoutBear — order only resolves which
             element is "top1" vs "top2" among equals, never adds bias to the resulting mass)
margin     = top1 - top2                // ≥ 0 by construction

balancedEvidence = clamp01( 1.0 - margin / BalancedEvidenceSpan )
```

`BalancedEvidenceSpan` is a fixed constant (hypothesis `0.20`). Interpretation: `margin ≥ 0.20` →
`balancedEvidence = 0.0` (clearly dominant, not uncertain on balance); `margin = 0.0` →
`balancedEvidence = 1.0` (perfect tie across the top two real candidates). A dominant RANGE with a
large top-1/top-2 margin therefore produces near-zero `balancedEvidence` regardless of internal
bull/bear symmetry.

#### 4.7.4 `weakWinnerMass` ∈ [0,1]

```
weakWinnerMass = clamp01( 1.0 - top1 / UncertainWeakWinnerThreshold )
```

`UncertainWeakWinnerThreshold = 0.30` (exposed input). When `top1 < 0.30`, `weakWinnerMass > 0` rises
linearly to `1.0` at `top1 = 0.0`; when `top1 ≥ 0.30`, `weakWinnerMass = 0.0`. This captures
"universally weak candidate support" without any directional conflict.

#### 4.7.5 `degradationMass` ∈ [0,1]

```
degradationMass = 1.0 - evidenceCompleteness
```

`evidenceCompleteness ∈ [0,1]` (section 11). When all five domains are valid, `evidenceCompleteness =
1.0` → `degradationMass = 0.0`.

`scoreUncertain` is a veto/override mass, not a candidate competing for "win" on false balance.

### 4.8 Momentum direction-agnostic rule (locked)

BUILD 05 locked `momentumDirectionalAlignment` as **diagnostic-only**. BUILD 06 MUST NOT read it in any
decision or scoring path.

- `M_supportiveBull == M_supportiveBear == M_strength(momentumState)`: a single direction-agnostic
  strength mapping keyed ONLY on `MomentumState` + `momentumStrength` (via the enum in 4.3). Momentum
  contributes *strength*, never *which side*.
- Bull/bear side selection is determined **exclusively** by the independent Structure domain (`S_*`)
  and Direction domain (`D_bullish`/`D_bearish`).
- `momentumDirectionalAlignment` may be mirrored into `RegimeResult`/diagnostics as an audit field
  only; it is never a gate, never a veto, never a weight, never a tie-break.

---

## 5. Hard incompatibilities & conflict handling (ordered, immutable)

**HARD vs SOFT uncertainty split.** `scoreUncertain` remains the aggregate uncertainty mass (section
4.7). A separate `hardUncertainVeto` decides whether uncertainty bypasses hysteresis:

```
hardUncertainVeto =
    criticalCoreInvalid
    OR structuralDirectionConflict >= 1.0
    OR (volatilityQuality == CHAOTIC AND |directionScore| < DIR_COMMIT)
```

Only `hardUncertainVeto` bypasses dwell and forces immediate UNCERTAIN. SHOCK, committed-direction
CHAOTIC (`chaosMass = 0.45`), `balancedEvidence`, `weakWinnerMass`, and non-critical degradation are
**SOFT** uncertainty evidence and follow the hysteresis path (section 8.3).

1. **Structural-direction veto (HARD).** Bullish structure (STRONG or WEAK) + bearish committed direction
   (or mirror) → force UNCERTAIN immediately, reason `OVERRIDE`. The conflict includes **weak as well as
   strong** directional structure whenever the opposite `directionScore` exceeds `DIR_COMMIT` (see 4.7.1:
   `bullStruct`/`bearStruct` are defined over both `*_STRONG` and `*_WEAK`).
2. **Chaos veto (HARD only when uncommitted).** `volatilityQuality == CHAOTIC` AND `|directionScore| <
   DIR_COMMIT (0.45)` → force UNCERTAIN immediately, not RANGE (`chaosMass = 1.00`, hard veto). When
   direction is committed (`|directionScore| >= DIR_COMMIT`), CHAOTIC is NOT a hard veto — `chaosMass` is
   `0.45` (SOFT), which does not by itself cross `UncertainVeto` (0.55). High-confidence UNCERTAIN is
   permitted in the hard-veto case.
3. **Breakout purity.** A BREAKOUT candidate cannot be reported if the incumbent is the corresponding
   TREND and continuation is stable (prevents TREND↔BREAKOUT oscillation; maturation handles the reverse).
4. **Range suppression.** `volatilityQuality ∈ {CHAOTIC, SHOCK}` suppresses RANGE (RANGE needs clean
   two-sided movement).

---

## 6. Confidence semantics

`confidence` describes the **final official reported regime** (not a frozen incumbent value).

### 6.1 Deterministic confidence formula (computed from the FINAL REPORTED regime)

`confidence` is a pure function of the **final reported regime's own score**, its **best alternative**,
and `evidenceCompleteness`. It is **not** computed from the raw top-1 candidate when the reported regime
differs from that candidate (e.g., during hysteresis the incumbent may be reported even though a
challenger currently scores higher).

Let `R` = the final reported regime for this bar (one of the five real regimes, or UNCERTAIN).

For a **directional/state regime** `R ∈ {TREND_BULL, TREND_BEAR, RANGE, BREAKOUT_BULL, BREAKOUT_BEAR}`:

```
scoreR        = the candidate score of regime R (scoreTrendBull/Bear/Range/BreakoutBull/BreakoutBear)
bestAlt       = max( candidate score of the OTHER four real candidates )   // best alternative to R
margin        = scoreR - bestAlt      // may be NEGATIVE if R is currently behind bestAlt

// Margin bonus is applied ONLY when scoreR is the leader; when behind, no positive bonus.
marginFactor  = clamp01( margin / ConfidenceMarginSpan )   // negative margin -> clamp01 -> 0.0

confidence = clamp01( scoreR * (0.70 + 0.30 * marginFactor) * evidenceCompleteness )
```

Key consequences (this fixes the "incumbent behind" bug):

- `scoreR >= bestAlt` → `marginFactor ∈ [0,1]`; a clear leader gets the full `0.70→1.0` margin factor.
- `scoreR < bestAlt` → `margin < 0` → `marginFactor = 0.0` → the incumbent's confidence is **not**
  inflated by a positive margin bonus; it is simply `scoreR * 0.70 * evidenceCompleteness`. The incumbent
  is honestly reported as behind.

`ConfidenceMarginSpan` is a fixed constant (hypothesis `0.20`).

For **UNCERTAIN**:

```
confidence = scoreUncertain
```

UNCERTAIN can be **high** confidence — e.g., unambiguous chaos or hard structural-direction conflict
means we are highly confident the market is uncertain. Low confidence = close candidate scores OR
degraded evidence.

### 6.1.1 Hysteresis uses the same regime-relative margin

The `gap` compared against `ChallengerGap` in section 8.3 is defined as:

```
gap = scoreChallenger - scoreIncumbent     // both are the respective regime's OWN current score,
                                            // incumbent score recomputed this bar
```

This is the challenger's score minus the incumbent's **recomputed** score (never a frozen value). No
margin bonus is folded into `gap`; `ChallengerGap` compares raw regime scores directly. The positive
margin factor in 6.1 only shapes the *reported* `confidence`, never the flip decision.

### 6.2 RegimeQuality (regime-specific market-state health — NOT classification certainty)

`RegimeQuality` measures **market-state health, not classification certainty**. It MUST NOT use top-1/
top-2 candidate margin, `ConfidenceMarginSpan`, or `scoreUncertain` as a quality proxy.

All component values and the resulting `qualityEvidence` are clamped to `[0,1]`.

The formula is selected by the **final reported regime** `R`. Each formula consumes only its own
regime-health mappings plus `evidenceCompleteness` (section 11). Momentum remains direction-agnostic
(`momentumDirectionalAlignment` is NEVER used).

#### 6.2.1 TREND_BULL / TREND_BEAR

```
Q_clean:
   HEALTHY    = 1.00
   EXPANDING  = 0.70
   COMPRESSED = 0.40
   SHOCK      = 0.20
   CHAOTIC    = 0.15

V_trendSuitable:
   NORMAL  = 1.00
   HIGH    = 1.00
   LOW     = 0.50
   EXTREME = 0.30

M_supportive:
   EXPANDING = 1.00
   STRONG    = 1.00
   NORMAL    = 0.60
   WEAK      = 0.30
   DECAYING  = 0.00

qualityEvidenceTrend =
    clamp01(
        0.35 * Q_clean
      + 0.25 * V_trendSuitable
      + 0.25 * M_supportive
      + 0.15 * evidenceCompleteness
    )
```

Same formula for `TREND_BULL` and `TREND_BEAR`.

#### 6.2.2 RANGE

```
Q_twoSided:
   COMPRESSED = 1.00
   HEALTHY    = 0.70
   EXPANDING  = 0.30
   CHAOTIC    = 0.00
   SHOCK      = 0.00

V_rangeSuitable:
   LOW     = 1.00
   NORMAL  = 0.70
   HIGH    = 0.40
   EXTREME = 0.10

M_nonExpansion:
   NORMAL    = 1.00
   WEAK      = 0.80
   DECAYING  = 0.50
   STRONG    = 0.30
   EXPANDING = 0.10

qualityEvidenceRange =
    clamp01(
        0.35 * Q_twoSided
      + 0.25 * V_rangeSuitable
      + 0.25 * M_nonExpansion
      + 0.15 * evidenceCompleteness
    )
```

#### 6.2.3 BREAKOUT_BULL / BREAKOUT_BEAR

```
Q_breakoutClean:
   HEALTHY    = 1.00
   EXPANDING  = 1.00
   COMPRESSED = 0.60
   CHAOTIC    = 0.10
   SHOCK      = 0.10

expansionEvidence = final B05 expansionScore [0,1]

M_expanding:
   EXPANDING = 1.00
   STRONG    = 0.70
   NORMAL    = 0.30
   WEAK      = 0.10
   DECAYING  = 0.00

qualityEvidenceBreakout =
    clamp01(
        0.30 * Q_breakoutClean
      + 0.30 * expansionEvidence
      + 0.25 * M_expanding
      + 0.15 * evidenceCompleteness
    )
```

Same formula for `BREAKOUT_BULL` and `BREAKOUT_BEAR`.

**Important:**

- HIGH Volatility Level is NOT expansion. Use B05 `expansionEvidence` explicitly.
- Do NOT use diagnostic-only `momentumDirectionalAlignment`.
- Prior compression is classification/setup evidence for BREAKOUT candidate scoring (section 7); it is
  **not** required again in this quality equation.

#### 6.2.4 UNCERTAIN

UNCERTAIN quality answers: *"How healthy/clean is the underlying market environment even though
classification is UNCERTAIN?"* It does **not** answer how certain we are that the state is uncertain
(that is `confidence = scoreUncertain`, section 6.1).

```
Q_general:
   HEALTHY    = 1.00
   EXPANDING  = 0.80
   COMPRESSED = 0.70
   CHAOTIC    = 0.10
   SHOCK      = 0.00

V_general:
   NORMAL  = 1.00
   LOW     = 0.70
   HIGH    = 0.70
   EXTREME = 0.20

qualityEvidenceUncertain =
    clamp01(
        0.55 * Q_general
      + 0.25 * V_general
      + 0.20 * evidenceCompleteness
    )
```

This deliberately allows **UNCERTAIN + high confidence + WEAK quality** — e.g., an obviously
chaotic/shock market where we are highly confident the correct classification is UNCERTAIN.

#### 6.2.5 Common RegimeQuality thresholds

After selecting the appropriate formula based on the FINAL REPORTED regime:

```
if qualityEvidence >= 0.75:  quality = STRONG
else if qualityEvidence >= 0.45:  quality = NORMAL
else:  quality = WEAK
```

Boundaries are inclusive exactly as written: `0.750000… → STRONG`, `0.450000… → NORMAL`, below `0.45 →
WEAK`.

#### 6.2.6 Critical invalid convention

If BUILD 06 has a critical core failure (section 11.2):

```
valid = false
regime = UNCERTAIN
evidenceCompleteness = 0.0
qualityEvidence = 0.0
quality = WEAK
```

This avoids manufacturing market-health information from invalid upstream evidence.

`challengerConfidence` and `incumbentConfidence` are kept **separately observable** during hysteresis;
they are recomputed every bar (section 8) and never compared against a frozen historical incumbent score.

---

## 7. Temporal compression memory (bounded rolling window)

Breakout requires **prior compression context**, not necessarily high compression on the breakout bar.

### 7.1 Rolling observation buffer (exact)

Maintain a **bounded rolling buffer** of the last `BreakoutLookbackBars` (default 4) **finalized** B05
`compressionScore` observations. This is a true FIFO window, NOT a single max+age scalar.

**MQL5 storage requirement:** `BreakoutLookbackBars` is a runtime-configured `input int`, so the buffer
must NOT be a fixed-size member array in a struct. It is stored as a **dynamically sized array**:

```
struct CompressionMemory
{
   double obs[];     // dynamic array sized to BreakoutLookbackBars at init (values are [0,1])
   int    count;     // number of valid observations currently held (0..BreakoutLookbackBars)
   int    head;      // ring write index
}
```

`obs` is resized to `BreakoutLookbackBars` once at initialization (and re-resized if the input changes
and the buffer is re-armed). This is the MQL5-valid representation for a runtime-configured lookback; a
compile-time `double obs[BreakoutLookbackBars]` member is NOT used because `BreakoutLookbackBars` is not
a compile-time constant.

Semantics:

1. **Prior-only:** the buffer holds observations from **completed H1 bars already finalized**. The
   current (in-progress) bar's `compressionScore` is appended **only after** current-bar fusion is
   finalized (see section 15 update order). Breakout scoring reads the buffer *before* the append, so the
   current bar's own compression can never support its own breakout classification.
2. **Append:** on finalize, push the current finalized `compressionScore` onto the ring; if `count ==
   BreakoutLookbackBars`, evict the oldest observation (FIFO overwrite) first.
3. **Max recomputation:** `compressionMax` is **not stored**; it is recomputed on demand as
   `max(obs[0..count-1])` over the retained observations. When an old maximum is evicted, the
   recomputation naturally returns the new maximum. (Implementation may cache the max with an eviction
   index for efficiency, but the observable result must equal a fresh `max()` over the retained window.)
4. **Empty window:** if `count == 0`, `compressionMax = 0.0`.

### 7.2 `Q_compressionContext` for breakout scoring

```
Q_compressionContext = max( obs[0..count-1] )   // prior observations only
```

- `Q_compressionContext == 0.0` when the window is empty (no prior compression observed) → breakout is
  unsupported on that evidence axis.
- The current bar's compression is explicitly excluded (rule 1 above); it enters the buffer only after
  fusion finalizes, so it can support a *later* bar's breakout, never the current bar's.

### 7.3 Determinism

The buffer is a pure function of the finalized observation sequence. Same closed-H1 history → identical
buffer contents → identical `compressionMax` → identical breakout scores.

---

## 8. Hysteresis / persistence model

Incumbent vs challenger, gap + dwell. Independent from B05 domain hysteresis.

### 8.0 Age/dwell convention (locked, applies to every bar counter)

**`age` = number of completed H1 bars already spent in that candidate/regime. The first observed/entry
bar is age `1` (not `0`).**

Concretely, when a candidate/regime is first entered on bar *t*, the counter is set to `1` at the end of
that bar's fusion. It increments by `1` on each subsequent bar it remains. A threshold comparison
`age >= N` is satisfied only after `N` completed bars have been spent.

This exact convention applies to **all** of: `candidateAgeBars`, `regimeAgeBars`, `UncertainExitDwell`,
`BreakoutMaturationMinBars`, and `BreakoutMaxAgeBars`. No counter uses 0-based entry; boundary tests must
assert off-by-one behavior (e.g., `RegimeDwell=2` flips only on the **second** consecutive challenger
bar, not the first).

### 8.1 Per-bar recomputation

The incumbent candidate score is **recomputed on every closed H1** from current domain results. The
challenger is **never** compared against a frozen historical incumbent confidence.

### 8.2 Challenger identity tracking

`pendingCandidateRegime` is tracked **explicitly**. Candidate dwell (`candidateAgeBars`) resets to `1`
(entry bar) whenever the challenger identity changes (or a new challenger is first observed). Only a
stable challenger (same identity for `RegimeDwell` bars) with a sufficient confidence gap can flip the
incumbent.

### 8.3 Decision procedure

```
candidateRegime = argmax(scoreTrendBull, scoreTrendBear, scoreRange,
                         scoreBreakoutBull, scoreBreakoutBear)
candidateConfidence = winning candidate score

if hardUncertainVeto:                          // HARD veto (section 5): immediate, no dwell
    force UNCERTAIN (reason OVERRIDE / RESET as applicable)

else if incumbent == UNCERTAIN:
    if candidateConfidence >= UncertainExitThreshold
       AND candidateAgeBars >= UncertainExitDwell:
        commit candidate (CHALLENGE_WIN)
    else keep UNCERTAIN

else:
    // SOFT uncertainty: UNCERTAIN becomes a special derived challenger.
    softUncertain = scoreUncertain >= UncertainVeto        // and NOT hardUncertainVeto
    if softUncertain:
        challengerRegime  = UNCERTAIN
        challengerScore   = scoreUncertain
    else:
        challengerRegime  = candidateRegime
        challengerScore   = candidateConfidence

    if challengerRegime == incumbent:
        pendingCandidateRegime = NONE
        candidateAgeBars = 0
        regimeAgeBars++
    else:
        if challengerRegime != pendingCandidateRegime:
            pendingCandidateRegime = challengerRegime
            candidateAgeBars = 1              // first bar of this challenger = age 1
        else:
            candidateAgeBars++                 // subsequent bars

        gap = challengerScore - incumbentConfidence   // incumbent recomputed this bar
        if gap >= ChallengerGap AND candidateAgeBars >= RegimeDwell:
            commit challenger (CHALLENGE_WIN)
        else keep incumbent (regimeAgeBars++)
```

**Soft uncertainty semantics.** When `hardUncertainVeto` is false but `scoreUncertain >= UncertainVeto`,
`UNCERTAIN` is treated as a **special derived challenger** (still NOT a sixth symmetric candidate):

- `pendingCandidateRegime = UNCERTAIN`
- `challengerConfidence = scoreUncertain`
- `incumbentConfidence = current score of the incumbent`
- `gap = scoreUncertain - incumbentConfidence`

It transitions to UNCERTAIN only when `candidateAgeBars >= RegimeDwell` AND `gap >= ChallengerGap`, using
the 1-based candidate-age convention. If soft uncertainty disappears before dwell completes, the pending
UNCERTAIN challenger resets normally. So **one ambiguous/tied H1 bar retains the incumbent; persistent
ambiguity → UNCERTAIN after hysteresis**.

**Bootstrap / no valid incumbent.** On the first valid fusion: hard uncertainty → UNCERTAIN immediately;
effective real-candidate tie → UNCERTAIN; soft `scoreUncertain >= UncertainVeto` → UNCERTAIN; otherwise
initialize the winning real candidate.

**Existing UNCERTAIN incumbent** keeps the `UncertainExitThreshold` + `UncertainExitDwell` logic for
leaving UNCERTAIN (unchanged).

On commit (CHALLENGE_WIN / MATURATION), the newly committed regime's `regimeAgeBars` is set to `1` (the
commit bar is its first bar). `regimeAgeBars` increments on **every** closed H1 the incumbent survives,
including bars where a challenger exists but fails to commit.

### 8.4 Immediate override

Only the HARD vetoes (section 5 rules 1 and 2, i.e. `hardUncertainVeto`) and critical-input failure bypass
dwell. These represent contradictory/poor core evidence, not a close call. SOFT uncertainty never bypasses
dwell.

### 8.5 Tie handling

**No bullish-biased enum-ordinal tie-breaking.** On an effective tie (winning and runner-up scores
within `TieEpsilon`):
- If a valid incumbent exists, **retain the incumbent**.
- If no valid incumbent, classify **UNCERTAIN**.

---

## 9. BREAKOUT aging + maturation

Two scalar parameters (split, per architect decision):

| Param | Default | Meaning |
|---|---|---|
| `BreakoutMaturationMinBars` | 2 | minimum completed bars (age) before a breakout may mature |
| `BreakoutMaxAgeBars` | 6 | breakout must mature or fail by this age (age ≥ this) |

`regimeAgeBars` uses the section 8.0 convention: the breakout's entry bar is age `1`.

- **Maturation:** if incumbent is `BREAKOUT_BULL` and `regimeAgeBars >= BreakoutMaturationMinBars` with
  sustained directional evidence (Structure now `BULLISH_*`, Direction `BULL/STRONG_BULL`, Momentum not
  `DECAYING`) → transition to `TREND_BULL`, reason `MATURATION`. The original breakout event remains
  immutable evidence; no new BOS is required per bar. `BreakoutMaturationMinBars=2` means maturation is
  first *eligible* on the breakout's second completed bar (age 2), never on its first.
- **Aging/expiration:** if the breakout has not matured by `regimeAgeBars >= BreakoutMaxAgeBars`, the
  failed-breakout path triggers (section 10). `BreakoutMaxAgeBars=6` means failure triggers at age 6.

BREAKOUT is never permanently sticky: it matures or fails within `BreakoutMaxAgeBars`.

---

## 10. Failed-breakout handoff

A breakout (incumbent `BREAKOUT_BULL` or `BREAKOUT_BEAR`) fails via **exactly two** triggers, checked in
this order each bar (no vague "expansion faded" early exit):

### 10.1 Trigger 1 — immediate opposing/conflict evidence

If, on any bar, **explicit opposing core evidence or a hard conflict** appears, the breakout fails
immediately (regardless of age):

- `structureState` flips to the **opposing** side: `BREAKOUT_BULL` with `BEARISH_STRONG`/`BEARISH_WEAK`
  (or mirror for `BREAKOUT_BEAR`), OR
- **opposing committed Direction**: `BREAKOUT_BULL` with `directionScore <= -DIR_COMMIT` (or
  `BREAKOUT_BEAR` with `directionScore >= +DIR_COMMIT`), OR
- a HARD incompatibility veto from section 5 fires (`hardUncertainVeto` true — structural-direction
  conflict, or uncommitted CHAOTIC).

→ `UNCERTAIN`, reason `FAILED_BREAKOUT`. This is the only early (pre-`BreakoutMaxAgeBars`) failure path.

### 10.2 Trigger 2 — age expiration without maturation

If the breakout has neither matured (section 9) nor triggered the immediate failure above by
`regimeAgeBars >= BreakoutMaxAgeBars`, it fails on reaching the age cap.

→ `UNCERTAIN`, reason `FAILED_BREAKOUT`.

### 10.3 Handoff to RANGE (never a direct jump)

```
BREAKOUT_BULL/BEAR
   -> maturation condition met                -> TREND_BULL/BEAR            [MATURATION]
   -> trigger 1 (opposing/conflict) OR trigger 2 (age cap)
        -> UNCERTAIN                                                         [FAILED_BREAKOUT]
             -> (Structure==RANGE AND non-chaotic AND low directional conviction)
                  -> RANGE                                                  [CHALLENGE_WIN via gap+dwell]
```

Failed breakout does **not** jump straight to RANGE. It first becomes UNCERTAIN, then RANGE only after
range structure is re-confirmed. This is the seam for the future Range Strategy handoff.

There is **no** "expansion faded" early-failure clause in v1. Any future early-failure expansion
condition must specify an exact upstream threshold (which field, which value) and be tested before it may
be added.

---

## 11. Invalid / degraded input behavior

### 11.1 `evidenceCompleteness` (exact)

`evidenceCompleteness ∈ [0,1]` is the sum of **four independent B06 domain weights**, each worth **0.25**:

| Domain | Weight | Source (final B04/B05 output) |
|---|---|---|
| Structure | 0.25 | `SwingStructureResult` valid |
| Direction | 0.25 | `DirectionResult` valid |
| Momentum | 0.25 | `MomentumResult` valid |
| Volatility | 0.25 | `VolatilityResult` valid |

```
evidenceCompleteness = 0.25 * ( structureValid?1:0
                              + directionValid?1:0
                              + momentumValid?1:0
                              + volatilityValid?1:0 )
```

- Each domain contributes `0.25` when its final result is valid, `0.0` when individually invalid
  (non-critical degradation).
- **ADX helper degradation (`helperDegraded`) does NOT reduce `evidenceCompleteness`.** ADX is a
  supporting-only input already collapsed into B05 momentum; a missing ADX helper leaves `MomentumResult`
  valid, so the Momentum domain still contributes its full `0.25`.
- **Critical rates/ATR failure** (no valid H1 rates / ATR core) forces `evidenceCompleteness = 0.0`
  regardless of the four-domain sum, because the entire B04/B05 update path is invalid.

### 11.2 Critical vs non-critical

**Critical required-input failure** (no valid H1 rates / ATR core): → `valid=false`, regime forced
`UNCERTAIN`, `evidenceCompleteness=0.0`, reason `RESET`.

**Non-critical degradation** (structure/direction/momentum/volatility individually invalid): →
`valid=true`, that domain's group contributes 0.0 to candidate scores, corresponding degradation bit set,
`evidenceCompleteness` reduced per 11.1, confidence reduced. ADX helper missing does NOT invalidate.

No silent fallback: `degradedDomains` bitmask + `evidenceCompleteness` are always exposed.

---

## 12. Anti-double-counting audit

| Raw signal | Collapsed into (B05) | Counted by B06? |
|---|---|---|
| EMA slope | Direction | ✅ once (via `directionScore`) |
| positioning (price vs EMA) | Direction | ✅ once |
| displacement | Direction | ✅ once |
| efficiency | Direction, Momentum, VolQ | ✅ **zero extra** — B06 reads collapsed results |
| body/range, close-location | Momentum | ✅ once (via `strengthScore`) |
| progression | Momentum | ✅ once |
| ADX | Momentum (helper) | ❌ never directly |
| wick/chaos | VolQ | ✅ once (via `quality`/`chaosScore`) |
| compression/expansion | VolQ | ✅ once (via `compressionScore`/`expansionScore`) |
| BOS / strong break | Structure `breaks[]` | ✅ once (via `S_break*`, BREAKOUT only) |

Each domain result is consumed exactly once per candidate. Structure and Direction remain independent
contributions (preserving the B05 discipline of keeping Structure out of Direction scoring).

---

## 13. Diagnostic architecture

`Build06DiagnosticMode = false` (default).

### 13.1 Fusion record (bounded, one per completed H1 update)

`[REGIME_FUSION]` with: timestamp; structure/direction/momentum/vol-level/vol-quality/compression/
expansion snapshot; six scores; winner; incumbent; confidence; quality; pendingCandidate; candidateAge;
regimeAge; hysteresis decision; transitionReason; degradedDomains; completeness; signature.

### 13.2 Transition-only event

`[REGIME_TRANSITION]` with: previous regime, new regime, timestamp, challenger confidence, incumbent
confidence, reason, age/dwell. Emitted only on a regime change — no replay spam.

---

## 14. Deterministic signature

`B06D1:<hex>` — FNV-1a (consistent with B04/B05) over a canonical string of **finalized** fusion state.

The signature MUST hash **all behavior-affecting persistent state**, not only the visible per-bar result.
Two runs whose per-bar `RegimeResult` looks identical but whose hidden state differs (different
`pendingCandidateRegime`, different compression FIFO contents/count) MUST produce different signatures.
This prevents silent collision where the next bar's behavior diverges.

```
v=B06D1;regime=<enum>;quality=<enum>;confidence=<decimal>;valid=<0|1>;
latest=<epoch>;age=<int>;prev=<enum>;structure=<enum>;direction=<enum>;
dscore=<decimal>;momentum=<enum>;mstrength=<decimal>;mda=<decimal>;vlevel=<enum>;vquality=<enum>;
comp=<decimal>;exp=<decimal>;sTB=<d>;sTBe=<d>;sR=<d>;sBB=<d>;sBBe=<d>;sU=<d>;
tx=<enum>;candAge=<int>;pend=<enum>;complete=<decimal>;degraded=<int>;
cm_count=<int>;cm_obs=<d0>,<d1>,...,<dN-1>       // chronological compression FIFO contents + count
```

Added fields (relative to the pre-audit string):

- `mda=<decimal>`: `momentumDirectionalAlignment` diagnostic mirror (always hashed for determinism, even
  though it never enters scoring).
- `pend=<enum>`: `pendingCandidateRegime` (hidden hysteresis state).
- `cm_count=<int>` + `cm_obs=<d0>,<d1>,...,<dN-1>`: the chronological compression FIFO buffer (oldest→
  newest) and its count. The **full contents** are hashed, not just the recomputed max, so an eviction
  that leaves the same `max` but changes retained history still changes the signature.

Excludes wall-clock, process identity, and pointer/address values. High-precision decimals (reuse the
BUILD 05 native serializer). Same completed H1 history + same upstream B04/B05 state + same persistent
state → identical signature on reload. ASCII-guard + `:ASCII_REJECTED` fallback.

**Collision-prevention acceptance:** a dedicated test must construct two runs whose *visible* per-bar
result (regime/quality/confidence/scores) is identical but whose hidden `pendingCandidateRegime` or
compression FIFO differs, and assert the signatures differ.

---

## 15. Update order (locked)

On each NEW CLOSED H1:

1. update BUILD 04 Structure
2. update BUILD 05 Direction / Momentum / Volatility
3. verify timestamps aligned (`B04.latestTime == B05.latestClosedH1`)
4. run BUILD 06 Regime Fusion
5. publish/store `H1BrainResult` + `RegimeResult`
6. diagnostics

If timestamps do not align: **skip fusion**, emit explicit diagnostic, never silently mix states.

---

## 15b. Cold-start / reload reconstruction (deterministic bootstrap replay)

BUILD 06 is **path-dependent**: its output on bar *t* depends on `regimeAgeBars`, `pendingCandidateRegime`,
`candidateAgeBars`, and the compression FIFO accumulated over prior bars. It therefore MUST NOT reset
semantic state on EA restart; a continuous run and a cold-start replay over the same history must reach
identical final state and signature.

### 15b.1 Reconstruction procedure

On EA restart (or first attach), BUILD 06 state is reconstructed by **replaying** the synchronized
completed-H1 B04/B05 **final outputs**, oldest → newest, through the *same* BUILD 06 state machine used
live:

```
for each completed H1 bar t in chronological order (oldest -> newest):
    (B04Final[t], B05Final[t]) = synchronized final outputs for bar t   // already locked/locked-snapshot
    if timestamps aligned:
        RegimeResult[t] = UpdateRegimeFusion(B04Final[t], B05Final[t], persistentState[t-1])
        persistentState[t] = persistentState[t-1] advanced by the above
```

The replay uses the **final** (already-collapsed) B04/B05 outputs — the exact same structs the live path
consumes — so BUILD 06 never re-derives raw evidence and never calls B04/B05 internals.

### 15b.2 Data source for replay

The replay requires that synchronized historical B04/B05 **final outputs** are available oldest→newest.
In native MQL5 this is satisfied by re-running the B04 and B05 update over the closed H1 history on
attach (both are deterministic, completed-bar, shift-1 engines with no persistent state that affects
their own output), producing the same final structs as a continuous run would have at each bar.

> **Integration constraint guard:** if implementing this reveals that B04/B05 CANNOT expose synchronized
> historical final outputs without changing their locked semantics, DO NOT modify B04/B05. Stop and
> report the constraint instead. B04/B05 remain immutable.

### 15b.3 Acceptance

- **Reference (Python):** a test feeds the same chronological sequence of `(B04Final, B05Final)` tuples to
  a continuous-run state machine (bars fed one-at-a-time as they "close") and to a cold-start replay
  (all bars replayed from empty state). Assert the final `RegimeResult`, `B06D1` signature, and all hidden
  persistent state (`pendingCandidateRegime`, `candidateAgeBars`, `regimeAgeBars`, compression FIFO) are
  identical.
- **Native (MQL5):** after a detach/re-attach at the same history point, assert the reconstructed state and
  `B06D1` equal the pre-restart values (via `[REGIME_FUSION]`/`[REGIME_TRANSITION]` records).

---

## 16. Parameter surface (small, grouped)

Fixed v1 hypothesis weights (not exposed inputs):

| Group | Weight |
|---|---|
| TREND `S/D/M/V/Q` | 0.35 / 0.30 / 0.15 / 0.10 / 0.10 |
| RANGE `S/D/M/V/Q` | 0.40 / 0.25 / 0.15 / 0.10 / 0.10 |
| BREAKOUT `S/Q/M/D/V` | 0.30 / 0.25 / 0.20 / 0.15 / 0.10 |

Exposed inputs (10 parameters + 1 diagnostic flag):

| Input | Default | Meaning |
|---|---|---|
| `Build06DiagnosticMode` | false | diagnostic flag |
| `RegimeDwell` | 2 | bars a stable challenger must lead before flip |
| `ChallengerGap` | 0.10 | min confidence gap to flip |
| `UncertainVeto` | 0.55 | conflict/insufficiency mass forcing UNCERTAIN |
| `UncertainExitThreshold` | 0.45 | min winner confidence to leave UNCERTAIN |
| `UncertainExitDwell` | 1 | bars to confirm exiting UNCERTAIN |
| `UncertainWeakWinnerThreshold` | 0.30 | leading candidate below this → weak-winner UNCERTAIN |
| `BreakoutMaturationMinBars` | 2 | min bars before breakout matures |
| `BreakoutMaxAgeBars` | 6 | breakout must mature/fail by this age |
| `BreakoutLookbackBars` | 4 | recency window for structural break + compression memory |
| `TieEpsilon` | 1e-6 | effective-tie threshold |

All thresholds/weights are Balanced-Aggressive v1 hypotheses, labeled as such, not sacred optimization
targets.

Fixed v1 constants (NOT exposed inputs):

| Constant | Value | Used by |
|---|---|---|
| `DIR_COMMIT` | 0.45 | structural-direction conflict + chaos veto |
| `BalancedEvidenceSpan` | 0.20 | `balancedEvidence` (top-1/top-2 margin normalization) |
| `ConfidenceMarginSpan` | 0.20 | `confidence` margin factor |

These constants are hardcoded in v1 (consistent with the fixed-weights approach). They may become exposed
inputs in a later build only if accompanied by a re-validation of the synthetic scenarios.

---

## 17. Python synthetic test plan

`tests/build06/` — reference state machine, independently derived from this spec, no MQL5 import.

| ID | Scenario | Expected |
|---|---|---|
| A | aligned bull (BULL_STRONG + BULL + EXPANDING + NORMAL/HIGH + HEALTHY) | TREND_BULL |
| B | mirror bear | TREND_BEAR |
| C | strong bull structure, **no BOS** | TREND_BULL (proves BOS not mandatory) |
| D | RANGE structure + low |dscore| + non-chaotic | RANGE |
| E | NEUTRAL + CHAOTIC | UNCERTAIN (not RANGE) |
| F | compression + bull break + EXPANDING | BREAKOUT_BULL |
| G | mirror | BREAKOUT_BEAR |
| H | BREAKOUT persists + structure accepts + dir bull | BREAKOUT→TREND (maturation) |
| I | breakout fades → UNCERTAIN → (RANGE re-est.) → RANGE | handoff chain |
| J | bull structure + bear direction | UNCERTAIN (conflict) |
| K | unambiguous chaos/conflict | UNCERTAIN with **high** confidence |
| K2 | universally weak candidates (no conflict) | UNCERTAIN (weak-winner insufficiency) |
| L | challenger leads but gap < threshold | incumbent kept |
| L2 | challenger identity changes → dwell resets | no premature flip |
| M | one-bar spike candidate | no flip-flop (persistence) |
| N | breakout aging/expiration beyond MaxAge | fails → UNCERTAIN |
| O | ADX helper degraded | fusion valid, momentum still fused |
| P | invalid core (no ATR) | valid=false, UNCERTAIN |
| Q | effective tie → retain incumbent; no incumbent → UNCERTAIN | deterministic |
| R | identical sequence → identical signature | deterministic |
| S1 | compression buffer: old max evicted → max recomputed from retained obs | deterministic rolling max |
| S2 | compression buffer: current bar's compression excluded from its own breakout | prior-only |
| S3 | compression buffer: window overflow (FIFO evict) | bounded size |
| T1 | `RegimeDwell=2` flips only on 2nd consecutive challenger bar (age 1 → age 2) | off-by-one |
| T2 | `BreakoutMaturationMinBars=2` not eligible at age 1 | off-by-one |
| T3 | `BreakoutMaxAgeBars` triggers at age == max (not max+1) | boundary |
| U1 | dominant RANGE with balanced bull/bear subpairs → NOT UNCERTAIN (top-1/top-2 margin) | balancedEvidence |
| V1 | two runs with identical visible result but different `pendingCandidateRegime` → different signature | collision-prevention |
| V2 | two runs with identical visible result + same max but different compression FIFO contents → different signature | collision-prevention |
| V3 | CHAOTIC + committed direction (`|dscore| >= DIR_COMMIT`) → NOT a hard veto (chaosMass 0.45) | chaos resolution |
| V4 | incumbent reported while behind → `confidence` has NO positive margin bonus | behind-incumbent confidence |
| V5 | ADX helper degraded → `evidenceCompleteness` unchanged (still 1.0 when 4 domains valid) | completeness |
| V6 | one non-critical domain degraded → `evidenceCompleteness = 0.75` | completeness |
| W1 | continuous run vs cold-start replay of same B04/B05 final outputs → identical final state + signature | reload reconstruction |
| W2 | replay is oldest→newest; out-of-order replay → mismatch detected | replay ordering |
| Q1 | TREND healthy + suitable vol + strong momentum + complete → STRONG | quality |
| Q2 | TREND SHOCK/EXTREME + DECAYING despite clear classification → WEAK | quality |
| Q3 | RANGE clean/compressed + LOW/NORMAL vol + non-expanding momentum → STRONG/NORMAL per equation | quality |
| Q4 | RANGE CHAOTIC/SHOCK → poor quality | quality |
| Q5 | BREAKOUT EXPANDING + high expansionEvidence + EXPANDING momentum → STRONG | quality |
| Q6 | BREAKOUT clear classification but SHOCK + weak expansion/momentum → WEAK | quality |
| Q7 | UNCERTAIN caused by CHAOTIC → high confidence coexists with WEAK quality | quality |
| Q8 | exact threshold boundaries 0.75 / 0.45 | quality |
| Q9 | critical-invalid → qualityEvidence=0, WEAK | quality |
| Q10 | changing momentumDirectionalAlignment alone does not change quality | quality |

Tie handling is **not** enum-ordinal; it is incumbent-retention / UNCERTAIN (section 8.5).

---

## 18. Native runtime validation plan

- Symbols: **EURUSDm**, **XAUUSDm** (H1 completed shift-1).
- Capture activity identity before/after → must remain 0/0/0 unchanged.
- Show representative fusion records (regime, quality, confidence, upstream snapshot, candidate scores,
  hysteresis state, regime age, signature).
- Verify determinism: two identical reloads → identical `B06D1`.
- Verify timestamp alignment: `B04.latestTime == B05.latestClosedH1 == B06.latestClosedH1`; mismatch →
  skip fusion + explicit diagnostic.
- Report any regime states NOT naturally present as `NOT OBSERVED IN VALIDATION WINDOW`. Never tune to
  manufacture them.

---

## 19. Files / modules proposed

| File | Change |
|---|---|
| `Types.mqh` | append `ENUM_REGIME_STATE`, `ENUM_REGIME_QUALITY`, `ENUM_REGIME_TRANSITION_REASON`, `RegimeResult`, degradation bit defines |
| `RegimeFusion.mqh` | **new** — pure engines: candidate scoring, compression memory, conflict/veto, hysteresis classify, maturation, `RegimeResult` builder |
| `Config.mqh` | append `Build06DiagnosticMode=false` + small B06 params (section 16) |
| `AdaptiveSurvivalEA.mq5` | add B06 persistence state; call `UpdateRegimeFusion()` after B04+B05 for same closed H1; verify alignment; store `RegimeResult` |
| `DiagnosticCollector.mqh` | append `Build06DiagnosticCollect`, `[REGIME_FUSION]`/`[REGIME_TRANSITION]`, `B06D1` signature (B04/B05 helpers untouched) |

---

## 20. Locked architect decisions (recorded)

1. UNCERTAIN = derived conflict/insufficiency mass, **not** a sixth symmetric candidate. Weak-winner
   insufficiency evidence included so a market with universally weak candidate support becomes UNCERTAIN
   without strong directional conflict.
2. `RegimeQuality` = market-state health only. Session/spread/news/liquidity/slippage/execution quality
   outside BUILD 06.
3. Breakout timing split: `BreakoutMaturationMinBars=2`, `BreakoutMaxAgeBars=6`. May mature after the
   minimum; must mature or fail by the maximum.
4. Critical required-input failure → `valid=false` + `regime=UNCERTAIN`. Non-critical degradation →
   `valid=true` with reduced completeness/confidence + explicit degradation bits.
5. No bullish-biased enum-ordinal tie-breaking. Effective tie → retain incumbent (if valid), else
   UNCERTAIN.
6. Track `pendingCandidateRegime` explicitly; candidate dwell resets on challenger identity change.
7. Recompute incumbent candidate score every bar; never compare against frozen historical confidence.
8. Temporal compression memory is a **bounded rolling window** over the last `BreakoutLookbackBars`
   finalized compression observations (true FIFO, max recomputed on eviction), NOT a single max+age
   scalar. Breakout uses **prior** compression only; the current bar's compression is appended after
   current-bar fusion finalizes.
9. Distinguish `expansionEvidence` from Volatility Level; HIGH volatility ≠ expansion.
10. No fresh BOS/strong-break bonus in TREND scoring (v1). Persistent StructureState supports TREND;
    fresh breaks support BREAKOUT. BOS remains unnecessary for strong trend classification.
11. `RegimeResult.confidence` describes the final official reported regime; `challengerConfidence` and
    `incumbentConfidence` remain separately observable during hysteresis.
12. `confidence` is computed from the **final reported regime's own score** vs its **best alternative**
    (not raw top-1); the positive margin factor is applied ONLY when the reported regime is currently the
    leader — a behind incumbent gets no margin bonus.
13. `RegimeQuality` is **regime-specific market-state health** (TREND/RANGE/BREAKOUT/UNCERTAIN formulas,
    section 6.2), not a classification-certainty margin. It never uses top-1/top-2 candidate margin,
    `ConfidenceMarginSpan`, or `scoreUncertain`; `momentumDirectionalAlignment` never enters it.
    `QualityMarginSpan` is removed.
14. Chaos hard-veto resolves: `volatilityQuality == CHAOTIC` vetoes ONLY when `|directionScore| <
    DIR_COMMIT`; `chaosMass` = 1.00 (veto) / 0.45 (committed-direction CHAOTIC) / 0.50 (SHOCK) / 0.00.
15. `evidenceCompleteness` = four independent B06 domains × 0.25 each (Structure/Direction/Momentum/
    Volatility); ADX helper degradation does NOT reduce completeness; critical rates/ATR failure forces 0.
16. `B06D1` hashes ALL behavior-affecting persistent state (`pendingCandidateRegime`, chronological
    compression FIFO contents+count, `momentumDirectionalAlignment` mirror), with collision-prevention
    tests.
17. BUILD 06 is path-dependent and reconstructs its state on cold-start via deterministic replay of
    synchronized completed-H1 B04/B05 final outputs (oldest→newest) through the same state machine;
    continuous-run final state == cold-start replay final state/signature. B04/B05 are never modified.
18. **HARD vs SOFT uncertainty split.** Only `hardUncertainVeto` (critical-core-invalid,
    `structuralDirectionConflict >= 1.0`, or uncommitted `CHAOTIC`) bypasses dwell. SHOCK, committed
    CHAOTIC (`chaosMass=0.45`), `balancedEvidence`, `weakWinnerMass`, and non-critical degradation are
    SOFT; `scoreUncertain >= UncertainVeto` from SOFT sources makes UNCERTAIN a derived challenger
    (gap + dwell, 1-based age), never an immediate override.
19. **Breakout incumbents** use their dedicated mature/fail/stay lifecycle and do NOT participate in
    generic direct challenger flips; `regimeAgeBars` increments on every closed H1 the incumbent
    survives, including bars where a challenger exists but fails to commit.
20. **Breakout opposing-Direction failure:** `BREAKOUT_BULL` fails immediately on `directionScore <=
    -DIR_COMMIT`; `BREAKOUT_BEAR` fails immediately on `directionScore >= +DIR_COMMIT` (in addition to
    opposing Structure and the hard uncertainty veto).
21. **BUILD06-R1 forensic clarification:** Structure, Direction, Momentum, and Volatility validity are
    independent inputs. An invalid non-critical domain contributes zero everywhere, including regime
    quality and veto inputs, sets its exact degradation bit, and removes exactly `0.25` completeness.
    `criticalCoreValid` is a separate explicit contract and is never inferred from those four flags.
22. Candidate eligibility is applied after raw diagnostic scoring. Valid CHAOTIC/SHOCK Volatility masks
    RANGE. Stable same-side TREND continuation masks its corresponding BREAKOUT only when Structure,
    Direction enum, and non-decaying Momentum are all valid. Raw scores remain unchanged.
23. Structural break recency uses completed-H1 age and the actual `BreakoutLookbackBars`: age `0 -> 1.0`,
    `0 < age < lookback -> 0.4`, otherwise `0.0`. Maturation uses valid Direction enum state, not
    `directionScore`; opposing-direction failure remains score-threshold based.
24. Effective tie with an initialized UNCERTAIN incumbent retains UNCERTAIN, clears fake pending state,
    increments incumbent age, and cannot emit self `CHALLENGE_WIN`. `B06D1` includes `initialized` plus
    every other behavior-affecting persistent field.
25. Cold replay resets state, then reconstructs chronological history through a replay entry distinct from
    incremental live ingestion. Acceptance compares complete final `RegimeResult`, all persistent fields,
    compression FIFO, and repeated replay signatures. Replay consumes complete synchronized available
    history unless a tested convergence boundary proves a shorter suffix sufficient; no fixed `512`-bar
    sufficiency claim exists.
26. Invalid-domain zeroing and the separate `0.25` completeness reduction intentionally both apply: the
    missing group contributes zero before scoring/quality, then completeness reduces confidence and its
    explicit completeness term. This double impact is locked degradation semantics, not weight tuning.
27. BUILD06-R1 defines Python reference truth only. Reference `B06D1` canonical order includes all Python
    behavior-affecting hidden state, including `initialized`; native signature parity and native MQL
    integration are explicitly deferred to BUILD06-R2.
