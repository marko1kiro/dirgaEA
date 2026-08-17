# BUILD 07 — M15 Trend Strategy Design Spec

**Status:** DESIGN (awaiting approval; NO implementation).
**Scope:** First M15 strategy layer. Consumes the locked H1 Regime (BUILD 06) and produces at most ONE
`TradeCandidate` per symbol per completed M15 bar, using three deterministic trend-setup families.
**Out of scope:** order placement, lot sizing, Quality Gate (BUILD 09), adaptive risk, position
management (BUILD 08+), M15 Range/Breakout strategies (BUILD 11/12). Execution, spread/news approval,
and broker-valid stop normalization all belong to future layers.

---

## 1. Boundaries and invariants

1. BUILD 04/05/06 are LOCKED. No B04/B05/B06 logic, thresholds, enums, or struct fields change unless a
   proven bug is found. Dependency direction is strictly one-way: `B04 → B05 → B06 → B07`.
2. BUILD 07 answers **"H1 says a trend exists; is there a structurally valid M15 trend setup right
   now?"**. It never answers "should we trade?".
3. BUILD 07 produces a `TradeCandidate` (candidate-generation only). No `CTrade`, `OrderSend`, execution
   `OrderCheck`, lot sizing, adaptive risk, position modification, or `TradePermission`. `RiskEngine`
   (BUILD 03) is untouched.
4. No Quality Gate. BUILD 07 may compute raw setup metrics, but must NOT produce a 0–100 gate score and
   must NOT reject candidates *solely* because `RegimeQuality == WEAK` (that is BUILD 09's job).
5. H1 is the authoritative market context (explicit `PERIOD_H1`). M15 is the execution/setup timeframe
   (explicit `PERIOD_M15`). Core EA behavior is **independent of chart `_Period`**; the chart timeframe
   is observability-only.
6. M15 completed bars only (shift-1 semantics). Bar 0 (forming) never qualifies a setup. One completed
   M15 timestamp is processed at most once; multiple ticks on the same bar never duplicate a candidate
   or advance setup state twice.
7. Price/structure is primary evidence; indicators (if any) are supporting witnesses only. BUILD 07 is
   NOT an EMA-cross / ADX-threshold / RSI-threshold strategy.

---

## 2. Timeframe architecture (locked)

```
H1 Brain   (B04 Structure + B05 Direction/Momentum/Volatility + B06 Regime)
   │
   │  official regime ∈ {TREND_BULL, TREND_BEAR}
   ▼
M15 Trend Strategy   (B07)
   │
   ▼
TradeCandidate  ──►  (future) BUILD 09 Quality Gate ──► (future) Risk/Execution
```

All timeframe constants are explicit. `_Period`/`_Symbol` of the chart never drives strategy behavior;
the EA always reads `PERIOD_H1` and `PERIOD_M15` explicitly.

---

## 3. H1 Regime Gate + transition lifecycle

BUILD 07 may generate a trend candidate ONLY when:

```
B06.valid == true
AND official regime ∈ { TREND_BULL, TREND_BEAR }
```

**No trend candidate** when regime is `RANGE`, `BREAKOUT_BULL`, `BREAKOUT_BEAR`, or `UNCERTAIN`.
BREAKOUT regimes belong to BUILD 12 — TrendStrategy must not steal them.

`RegimeQuality` is mirrored into the candidate as context (`sourceRegimeQuality`) but is **not** a
rejection condition in BUILD 07.

**Transition lifecycle (locked).** M15 swing/context collection **continues regardless of H1 regime**
(the M15 structure bookkeeping is independent of the H1 gate). But pending trend-setup state is
**cleared/expired** when any of:

1. `B06.valid == false`, OR
2. H1 leaves `TREND_BULL`/`TREND_BEAR` (i.e., becomes RANGE/BREAKOUT/UNCERTAIN), OR
3. the trend direction flips (TREND_BULL → TREND_BEAR or vice-versa).

On any of these, the pending break-retest slot is expired, in-flight pullback/momentum legs are reset,
and the last-emitted-candidate identity is cleared. **Old pending trend setups must never survive
RANGE/BREAKOUT/UNCERTAIN and later fire as if nothing happened.**

### 3.1 Trend-setup epoch barrier (locked)

Resetting `impulsePrimed` alone is insufficient: old confirmed swings remain stored, so old geometry
could be re-derived later and resurrect an old setup. BUILD 07 therefore holds persistent epoch state:

```
trendEpochId
trendEpochStartAvailableAt
trendEpochDirection   // BUY / SELL / NONE
```

**A new epoch starts whenever:**

- invalid/non-trend → `TREND_BULL`/`TREND_BEAR` (entering a trend), OR
- `TREND_BULL` → `TREND_BEAR` (direction flip), OR
- `TREND_BEAR` → `TREND_BULL` (direction flip).

Pending setup state is tagged to the current epoch; when the epoch changes, all pending trend-setup
state is cleared with it.

**Epoch-tagged creation semantics (required):**

- **PULLBACK:** pullback pivot `C` must become **confirmed within the current trend epoch**.
- **BREAK_RETEST:** the break event must occur **within the current trend epoch**.
- **MOMENTUM:** the trigger must occur **within the current trend epoch** (the leg-base swing may
  predate the epoch; it is a structural reference only).

This preserves continuous M15 structure history while guaranteeing old setup intent cannot cross regime
boundaries.

---

## 4. M15 completed-bar semantics (native bar-transition)

Native bar semantics (locked project rule): **bar 0 = current/forming; bar 1 = latest completed**. A bar
becomes available to completed-bar strategy logic when the **next actual native bar appears** and the
prior bar moves from shift-0 to shift-1. Wall-clock arithmetic is NOT the authority.

Two distinct concepts:

```
barOpenTime  = MqlRates.time          // stable bar identity (open-time)
availableAt  = native event time when this bar became shift-1
```

In a normal uninterrupted session `availableAt == barOpenTime + PeriodSeconds(timeframe)`, but that
equality is **NOT assumed** across session closures, weekends, stale-tick periods, or trading halts.

### 4.0 Live M15 semantics

When a new M15 bar with open time `Tnew` is detected:

```
completedBar.barOpenTime = previous native bar open time
completedBar.availableAt = Tnew            // the event that made it shift-1
```

Process the completed bar exactly once at that event.

### 4.1 Historical / replay semantics

For chronological native bars:

```
bars[k]   = bar being evaluated
bars[k+1] = next ACTUAL native bar (the one that made bars[k] shift-1)

bars[k].availableAt = bars[k+1].time
```

Do **not** synthesize missing timeframe boundaries (session gaps produce no phantom events).

### 4.2 Setup ages

Setup ages (`setupAgeBars`, retest age, retest `ageBars`, etc.) count **actual completed M15 bar
events**, not elapsed wall-clock 15-minute buckets.

### 4.3 H1 context (adapter snapshot)

`latestClosedH1` is NOT reinterpreted or modified (BUILD 06 locked; its existing semantics — the closed
H1 bar's native timestamp identity — are preserved as-is). BUILD 07 introduces an adapter snapshot:

```mql5
struct H1ContextSnapshot
{
   datetime sourceBarTime;  // raw locked B06 timestamp identity (latestClosedH1)
   datetime availableAt;    // native H1 event time when this bar became shift-1
   ENUM_REGIME_STATE   regime;
   ENUM_REGIME_QUALITY quality;
   bool                valid;
};
```

- **H1 replay:** `H1Result for bar[k]` has `availableAt = next ACTUAL H1 bar open time`.
- **Live:** newly detected H1 bar-0 open time.
- No B04/B05/B06 struct or semantics change.

### 4.4 M15 swing pivot confirmation (width-2 strict pivots, ACTUAL bars)

`M15PivotWidth = 2` (fixed v1). A confirmed pivot requires:

- **high pivot:** `high[i] > high[i-1..i-2]` AND `high[i] > high[i+1..i+2]` (strictly greater than every
  left/right neighbor).
- **low pivot:** `low[i] < low[i-1..i-2]` AND `low[i] < low[i+1..i+2]` (strictly less than every
  neighbor).
- **Ties are NOT pivots** (strict comparison; equal neighbor disqualifies).
- **`bar 0` never participates** (only completed bars; index 0 = forming is excluded from confirmation).
- **Confirmation uses ACTUAL bars, not arithmetic time.** A width-2 pivot becomes usable only after two
  actual right-side completed M15 bars exist:
  ```
  chronological:  P, R1, R2, NEXT
  P.confirmedAtTime = availability time of R2   = NEXT.barOpenTime
  ```
  Session/weekend gaps must NOT cause confirmation merely because 45 wall-clock minutes elapsed. If fewer
  than 2 actual right-side bars exist, the pivot is NOT confirmed regardless of elapsed time.

**No setup trigger may use bars that occurred before the required swing was actually confirmed.**
Concretely, a setup whose trigger references pivot `P` may only fire on a completed M15 bar whose
`availableAt >= P.confirmedAtTime`.

---

## 5. M15 execution context (state contract) — exact

A **lightweight** structural context. NOT a second Market Brain. No regime, no quality, no EMA/ADX
machinery, no label/follow-through system. Only confirmed swings, legs, a single pending break-retest
slot, and bounded consumed-level memory.

```mql5
struct M15SwingPoint
{
   datetime barOpenTime;     // rates[i].time — bar OPEN-TIME identity of the pivot bar
   datetime confirmedAtTime; // native event time when the pivot became usable (2 actual
                             // right-side completed bars: == next-bar barOpenTime)
   double   price;           // pivot price (high or low)
   int      kind;            // +1 high, -1 low
};

struct M15BreakLevel
{
   datetime barOpenTime;     // pivot-bar OPEN-TIME identity that produced this level
   double   price;           // broken level price
   bool     bullish;         // broken above (bull) / below (bear)
   datetime breakAvailableAt;// availableAt of the completed M15 bar that broke the level
   int      ageBars;         // actual completed M15 bar events since the break
   bool     consumed;        // retest fired
   bool     expired;         // retest window elapsed / superseded / failed
};

#define M15_MAX_SWINGS  16    // bounded confirmed-swing history
#define M15_MAX_BREAKS  8     // bounded recent-break history

struct TrendExecutionContext   // M15
{
   // trend epoch (section: epoch barrier)
   int      trendEpochId;              // increments on non-trend->trend or direction flip
   datetime trendEpochStartAvailableAt;// availableAt of first M15 bar in this epoch
   ENUM_TREND_DIRECTION trendEpochDirection;  // BUY / SELL / NONE

   M15SwingPoint swings[M15_MAX_SWINGS];   // confirmed pivots, chronological
   int           swingCount;

   // latest impulse leg + latest pullback leg, derived from confirmed swings
   // (direction relative to the active H1 trend):
   datetime      impulseOriginTime;        // swing confirmedAtTime at leg base
   double        impulseOriginPrice;
   datetime      impulseEndTime;           // swing confirmedAtTime at leg end (top/bottom)
   double        impulseEndPrice;
   double        impulseLengthATR;         // |end-origin| / M15 ATR
   datetime      pullbackEndTime;          // swing confirmedAtTime at pullback terminus
   double        pullbackEndPrice;
   double        pullbackDepthATR;         // |impulseEnd - pullbackEnd| / M15 ATR
   bool          impulsePrimed;            // a valid directional impulse exists in this epoch

   M15BreakLevel pendingRetest;            // single pending break-retest slot
   M15BreakLevel breaks[M15_MAX_BREAKS];   // recent break history (identity/consume)
   int           breakCount;

   datetime      lastM15BarOpenTime;       // dedup guard (native M15 bar open-time identity)
   datetime      lastM15AvailableAt;       // native event time of the last processed M15 bar
};
```

Derived helpers (pure): `TrendLegDirection(a,b)`, `TrendLegLengthATR(a,b,atr)`,
`TrendExtensionATR(refPrice, price, atr)`, `TrendNearestSwingAbove/Below`.

**Impulse vs pullback (bull):** with H1 `TREND_BULL`, the most recent up-leg between two consecutive
confirmed swings is the **impulse**; a subsequent down-leg is the **pullback**. Bear is exact mirror.
Both legs are defined over **confirmed** swings only (usable at `confirmedAtTime`).

---

## 6. TradeCandidate contract — exact

```mql5
enum ENUM_TREND_SETUP_FAMILY
{
   TREND_SETUP_NONE,
   TREND_SETUP_PULLBACK_CONTINUATION,
   TREND_SETUP_BREAK_RETEST_CONTINUATION,
   TREND_SETUP_MOMENTUM_CONTINUATION
};

enum ENUM_TREND_DIRECTION
{
   TREND_DIR_NONE,
   TREND_DIR_BUY,
   TREND_DIR_SELL
};

struct TradeCandidate
{
   bool                     valid;
   string                   symbol;             // _Symbol (semantic; not a trade)
   ENUM_TREND_DIRECTION     direction;          // BUY / SELL
   ENUM_TREND_SETUP_FAMILY  strategyFamily;

   ENUM_REGIME_STATE        sourceRegime;       // H1 regime that gated this candidate
   ENUM_REGIME_QUALITY      sourceRegimeQuality;// mirrored context (NOT a gate)

   datetime                 h1ContextTime;      // H1 context AVAILABILITY time (adapter availableAt)
   datetime                 h1SourceBarTime;    // raw locked B06 source timestamp (audit; latestClosedH1)
   datetime                 m15BarOpenTime;     // rates[i].time (bar OPEN-TIME identity) of the trigger bar
   datetime                 m15SignalTime;      // availableAt of the trigger bar (native shift-1 event)

   double                   referenceEntryPrice;// deterministic reference entry (section 9)
   double                   structuralInvalidationPrice;
   double                   proposedStopPrice;
   double                   stopDistance;       // |entry - stop|
   double                   stopDistanceATR;

   double                   targetReferencePrice;
   double                   availableRewardDistance;
   double                   availableRewardR;   // rewardDistance / stopDistance (truthful)

   // setup-specific audit metrics (raw, for BUILD 09)
   double                   pullbackDepthATR;   // PULLBACK only
   double                   displacementATR;    // MOMENTUM only
   double                   retestDistanceATR;  // BREAK_RETEST only
   double                   extensionATR;       // anti-chase, all families
   datetime                 structureReferenceTime; // identity of structural reference
   int                      setupAgeBars;

   string                   reason;             // human-readable accept/decline note
   string                   invalidReason;      // non-empty when a setup was rejected
};
```

`TradeCandidate` is NOT a `TradePermission`: it contains no lot size, no final risk %, no order ticket,
no execution approval, no spread/news approval.

---

## 7. H1 ↔ M15 alignment (no-lookahead) — exact rule

Alignment uses **native availability times**, never wall-clock arithmetic or bar open-times.

```
activeH1 = latest H1ContextSnapshot with H1ContextSnapshot.availableAt <= m15CompletedBar.availableAt
```

Where:
- `m15CompletedBar.availableAt` = native event time when the M15 bar became shift-1 (section 4).
- `H1ContextSnapshot.availableAt` = native event time when the H1 bar became shift-1 (section 4.3).

**Coincident availableAt:** when `H1ContextSnapshot.availableAt == m15CompletedBar.availableAt` (e.g., both
at `:00`), **event order is H1 first, then M15**. The fresh H1 context (just finalized) is visible to the
coincident M15 bar. No look-ahead by construction.

- BUILD 07 holds a single **active H1 context slot** (`H1ContextSnapshot`): `(sourceBarTime, availableAt,
  regime, valid, quality)`. During replay it is advanced chronologically in lockstep with M15 bars
  (section 18). The signature hashes both `sourceBarTime` and `availableAt` (section 20).
- Historical M15 bars are NEVER stamped with today's latest H1 state.

---

## 8. Setup 1 — PULLBACK_CONTINUATION

Preferred family. Bull description (bear is exact mirror).

**Context:** active H1 regime == `TREND_BULL`, `B06.valid == true`.

**Geometry (all ATR-normalized, confirmed/completed bars only):**

1. **Impulse** = the most recent up-leg between two consecutive confirmed M15 swings
   (`swingLow_A` → `swingHigh_B`, `swingHigh_B` newer; both confirmed at their `confirmedAtTime`).
   Requires `impulseLengthATR = (B.price - A.price)/ATR >= ImpulseMinATR`.
2. **Pullback** = a NEWER confirmed down-swing `swingLow_C` after `swingHigh_B` with
   `pullbackDepthATR = (B.price - C.price)/ATR` in `[PullbackMinATR, PullbackMaxATR]`.
   - **Not invalidation:** `C.price >= A.price` (does not close below impulse origin).
   - **Inside BOTH value-zone bounds:**
     ```
     ZoneLowPrice  = A.price + ZoneLowFrac  * (B.price - A.price)
     ZoneHighPrice = A.price + ZoneHighFrac * (B.price - A.price)
     ZoneLowPrice <= C.price <= ZoneHighPrice      // REQUIRED (both bounds)
     ```
     The value zone is a broad normalized band (NOT a Fibonacci ladder).
3. **Reclaim trigger** = the FIRST completed M15 bar after `swingLow_C.confirmedAtTime` whose close is
   `> (B.price + C.price) / 2` (reclaims the pullback midpoint). No trigger may fire before `C` is
   confirmed.

**Candidate (bull):**
- `referenceEntryPrice` = close of trigger bar.
- `structuralInvalidationPrice` = `C.price` (pullback low).
- `proposedStopPrice` = `C.price - StopBufferATR * ATR`.
- `targetReferencePrice` = nearest prior confirmed M15 swing high above entry within lookback (section
  16); if none, `availableRewardR` truthfully reflects 0/absent room.
- `pullbackDepthATR` recorded.
- `extensionATR` = `(entry - C.price)/ATR` — **anti-chase reference is the pullback/value pivot `C`**
  (section 12).
- `structureReferenceTime` = `C.confirmedAtTime` (identity of the pullback pivot).

**Rejections (with `invalidReason`):**
- impulse too small (`ImpulseMinATR`); pullback too shallow (`PullbackMinATR` → noise); pullback too
  deep (`PullbackMaxATR`) or closed below impulse origin (structure invalidated); pullback did not land
  inside BOTH value-zone bounds; `extensionATR >= MaxExtensionATR`; stop geometry invalid (section 15).

**Consumption:** once a pullback candidate fires, the current impulse+retrace pair is consumed; the next
pullback candidate requires a new impulse leg.

**`setupAgeBars` (PULLBACK)** = number of actual completed M15 bar events from `C.confirmedAtTime` to the
trigger bar's `availableAt`, inclusive (i.e., bars since pullback pivot `C` became confirmed through
trigger).

---

## 9. Setup 2 — BREAK_RETEST_CONTINUATION

Bull description (bear mirror).

**Context:** H1 `TREND_BULL`, valid.

1. **Fresh break:** a completed M15 bar closes **above** a confirmed M15 swing high `R` (resistance) by
   `>= BreakPenetrationATR * ATR`. Record `M15BreakLevel{ identity = R.barOpenTime, price = R.price,
   breakAvailableAt = break-bar availableAt, bullish = true }`. **One pivot identity can create only ONE
   break object** (stable identity = `R.barOpenTime`).
2. **Retest touch (bounded band):** within `RetestMaxAgeBars` actual completed M15 bar events after the
   break, a completed M15 bar touches the level only if its **low** falls inside the bounded band
   `[R.price - RetestToleranceATR*ATR, R.price + RetestToleranceATR*ATR]`. **Retest cannot occur on the
   breakout bar itself** (`retest.availableAt > break.availableAt`). **Deep overshoots do NOT qualify as a
   clean trend retest** (a bar whose low is `< R.price - RetestToleranceATR*ATR` is a failed retest, not
   a touch).
3. **Acceptance (reclaim):** after a valid touch, a completed M15 bar (the touch bar or a subsequent bar
   within the window) closes back **above** `R.price` (reclaim). The acceptance bar is the trigger.

**Post-touch state machine (deterministic):**
- **Minor close below/above level may remain pending** for a later reclaim within the window.
- **Failed (expired):** a bull bar closes `<= R.price - BreakPenetrationATR*ATR` (bear mirror: closes
  `>= R.price + BreakPenetrationATR*ATR`) → the level is marked `expired`, cannot fire.
- **Superseded:** if a NEWER same-direction break level is **structurally more advanced** while an old
  level is still pending, the old level is marked `expired`/`superseded` and replaced by the new one
  (single pending-retest slot). "Structurally more advanced" is defined exactly: for bull breaks,
  `newLevel.price > pendingLevel.price`; for bear breaks, `newLevel.price < pendingLevel.price`. The
  newer pivot must also have a newer pivot identity (not merely a newer break bar).

**Candidate (bull):**
- `referenceEntryPrice` = close of acceptance bar.
- `structuralInvalidationPrice` = the **actual low of the retest-touch bar** (the bar that touched the
  band). No ambiguous fallback.
- `proposedStopPrice` = invalidation − `StopBufferATR * ATR`.
- `retestDistanceATR` = `(R.price - retestLow)/ATR` recorded.
- `extensionATR` = `(entry - R.price)/ATR` — **anti-chase reference is the broken level `R`**.
- `structureReferenceTime` = `R.barOpenTime` (broken level identity).
- `targetReferencePrice` = nearest prior confirmed M15 swing high above entry.

**Level semantics (deterministic consumption/expiration):**
- A break level has **stable identity** = the pivot-bar `barOpenTime` that produced it.
- Age convention: break bar = age 1; next actual completed M15 bar = age 2; etc.
- `age == RetestMaxAgeBars` is still eligible for touch/reclaim on that bar. If no successful candidate
  exists after processing the max-age bar, the level is expired.
- `age > RetestMaxAgeBars` must never be evaluated as valid.
- On a successful retest, the level is marked `consumed` — it can never fire again.
- The same old break/retest level cannot generate repeated candidates forever.

**`setupAgeBars` (BREAK_RETEST)** = number of actual completed M15 bar events since the break event,
using the entry-bar age-1 convention (break bar = age 1).

---

## 10. Setup 3 — MOMENTUM_CONTINUATION

Lowest priority, strictest. For healthy continuation with no clean pullback/retest.

**Context:** H1 `TREND_BULL`, valid. No valid pullback or break-retest on this bar.

1. **Directional continuation (displacement):** `displacementATR` = directional net close movement over
   the last `MomentumLookbackBars = 3` **completed** M15 bars, divided by the current completed-M15 ATR:
   ```
   displacementATR = (close[bar1] - close[bar1+2]) / ATR    // bull, net over 3 completed bars
   ```
   Requires `displacementATR >= MomentumMinDisplacementATR`.
2. **Healthy (not contracted):** `ATR` available and finite (no separate expansion machinery).
3. **NOT extended (anti-chase):** `extensionATR < MaxExtensionATR`, where
   `extensionATR = (triggerClose - legBasePrice)/ATR` and `legBasePrice` = the most recent **confirmed**
   swing low (leg base) for bull. `extensionATR` and `displacementATR` are **distinct** metrics (section
   12); they are NOT aliases.

**Candidate (bull):**
- `referenceEntryPrice` = close of trigger bar.
- `structuralInvalidationPrice` = last confirmed swing low (leg base).
- `proposedStopPrice` = swing low − `StopBufferATR * ATR`.
- `displacementATR` and `extensionATR` recorded (two separate fields).
- `structureReferenceTime` = leg-base swing `confirmedAtTime`.

**Anti-chase (first-class):** momentum continuation is NOT "price moved strongly → enter". If
`extensionATR >= MaxExtensionATR`, NO candidate (reason `chase_extension`). This is especially important
on XAUUSD.

**`setupAgeBars` (MOMENTUM)** = `1` on the trigger bar (the setup is born and fired on the same
completed bar).

---

## 11. Setup priority / collision handling (locked)

```
PULLBACK_CONTINUATION
>
BREAK_RETEST_CONTINUATION
>
MOMENTUM_CONTINUATION
```

On a completed M15 bar where multiple setups are valid, emit **exactly one** candidate using this fixed
priority. Evaluation is deterministic and side-effect-free until the winner is selected, so evaluating
all families and then picking the highest-priority valid one is safe.

---

## 12. Anti-chase model

`extensionATR` is computed for every family and recorded on the candidate (audit). A setup that is
directional but already `extensionATR >= MaxExtensionATR` is rejected. `MaxExtensionATR` is a single
fixed v1 constant (hypothesis `2.5`), NOT a "chase-threshold zoo". One knob, one structural meaning:
*distance from the family's structural reference, normalized by M15 ATR*.

**Anti-chase reference is family-specific (locked):**

| Family | `extensionATR` reference |
|---|---|
| PULLBACK_CONTINUATION | pullback/value pivot `C` |
| BREAK_RETEST_CONTINUATION | broken structural level `R` |
| MOMENTUM_CONTINUATION | confirmed leg base (swing low/high) |

`extensionATR` (distance from the structural reference to trigger close, normalized by ATR) and
`displacementATR` (net directional movement over the last 3 completed bars, normalized by ATR) are
**distinct, non-duplicate** metrics. `extensionATR` measures "how far past value/structure we already
are"; `displacementATR` measures "how much clean directional progress the last bars made". They are
computed independently and stored in separate fields.

---

## 13. Local M15 contradiction / invalidation

Setup-local validity only (no second regime state). For a bullish setup, a **material local
contradiction** is any of:

1. A completed M15 bar closes **below** the setup's `structuralInvalidationPrice` (impulse origin /
   retest low / leg base) → structure broken.
2. Strong opposite displacement: a completed M15 bear bar with
   `oppositeBodyATR = abs(close - open) / currentCompletedM15ATR >= ContradictionDisplacementATR`
   (fixed constant `1.5`) against the trend. This is the **only** contradiction metric in v1; no
   alternate metric (bar displacement, wick, range) is used.
3. A broken retest level fails acceptance (retest bar closes below the level and continues down).
4. Candidate stop geometry becomes nonsensical (section 15).

Any of these → no candidate (or invalidates a pending setup), with `invalidReason`. Bear is mirror.

---

## 14. Entry price semantics

BUILD 07 uses a **deterministic reference entry** = **close of the completed trigger M15 bar** for all
three families. Never `Ask`/`Bid`. The future ExecutionEngine translates this reference intent into a
real executable price. (Alternatives like "break-of-trigger-candle" are deferred to Execution.)

---

## 15. Structural stop / invalidation model

Philosophy: **structural invalidation + small ATR buffer**, NOT fixed pip/dollar/1-ATR stops.

- **Structural reference selection** (per family): pullback low `C` (PULLBACK), actual retest-touch bar
  extreme (BREAK_RETEST), leg base swing (MOMENTUM).
- **ATR buffer:** `proposedStop = invalidation − StopBufferATR * ATR` (bull; `+` for bear).
- **Validity bounds:** `stopDistanceATR = |entry − stop|/ATR` must satisfy
  `MinStopATR <= stopDistanceATR <= MaxStopATR`. Outside → candidate rejected (`invalidReason =
  stop_out_of_bounds`). No broker tick-size/stop-level normalization here (that is Execution/Risk).

**M15 ATR semantics (locked).** Native `iATR` on `PERIOD_M15`, period `14` (fixed v1). Completed-bar
values only (shift-1); the forming ATR value is never used. Every evaluation uses the ATR of the
**current evaluation/trigger completed bar** consistently (the completed M15 bar at `bar 1` at the time
of evaluation; during replay, the ATR value at the replayed bar's index).

---

## 16. Target / reward reference

`targetReferencePrice` = **nearest prior confirmed M15 swing high above entry** (bull) within a bounded
lookback; bear = nearest swing low below. Represents the nearest credible structural obstacle, not a
forced 2R objective. **Target lookup must only use swings whose `confirmedAtTime <= triggerAvailableAt`**,
so structural reward reference cannot leak future-confirmed swings.

- `availableRewardDistance = |target − entry|`.
- `availableRewardR = availableRewardDistance / stopDistance` (truthful; may be poor).
- If no credible structural room exists, `availableRewardR` truthfully reflects the poor/zero reward;
  BUILD 07 does NOT silently upgrade or reject it. BUILD 09 judges reward quality.

---

## 17. Candidate identity / dedup

Deterministic identity:

```
identity = symbol | m15AvailableAt | strategyFamily | structureReferenceTime
```

- `m15AvailableAt` = availableAt of the trigger bar (native shift-1 event time).
- `structureReferenceTime` = `C.confirmedAtTime` (PULLBACK), `R.barOpenTime` (BREAK_RETEST), leg-base
  `confirmedAtTime` (MOMENTUM).
- Primary dedup: B07 evaluates **once per completed M15 bar** (`lastM15BarOpenTime` / `lastM15AvailableAt`
  guard).
- Secondary dedup: `lastEmittedIdentity` — if a newly computed candidate's identity equals the last
  emitted one, it is suppressed. Consumption/expiration (section 9) is the real repeat-prevention.

---

## 18. Temporal state + cold-start replay

Path-dependent BUILD 07 state: confirmed swings (with `confirmedAtTime`), pending retest level (+age),
consumed/expired level identities, last candidate identity, active H1 context slot, trend epoch state.

**Cold-start reconstruction (unified chronological replay, no look-ahead):**

1. Copy completed H1 bars (shift-1) and completed M15 bars (shift-1).
2. **Run the H1 replay ONCE** using the existing locked BUILD 06 replay machinery, producing the
   historical finalized B06 contexts (`sourceBarTime`/`availableAt`, `regime`, `valid`, `quality`)
   oldest→newest. Do **NOT** re-invoke B04/B05/B06 per M15 bar.
3. Build a merged chronological event stream over **native availability times** (H1
   `H1ContextSnapshot.availableAt` and M15 `completedBar.availableAt`; coincident → H1 first).
4. Process oldest→newest, merging the precomputed H1 context stream with M15 events ONCE:
   - **H1 context:** advance the **active H1 context slot** from the precomputed context stream.
   - **M15 event:** advance the B07 Trend engine using the current active H1 context (which, by
     construction, has `H1ContextSnapshot.availableAt <= m15CompletedBar.availableAt`).
5. After the stream, BUILD 07 state == continuous-run state; `B07D1` identical.

> **Integration guard:** if the historical finalized B06 contexts CANNOT be exposed to BUILD 07 without
> modifying locked B04/B05/B06 semantics, STOP and report the constraint — do NOT modify B04/B05/B06.

B07's own persistent state resets to empty before replay. BUILD 04/05/06 remain immutable.

---

## 19. Diagnostic architecture

`Build07DiagnosticMode = false` (default).

Bounded records, no per-tick spam:

- `[TREND_M15_CONTEXT]` — one per new completed M15 bar: H1 regime/time, M15 time, swings count, last
  impulse/pullback lengths, pending retest age, extensionATR.
- `[TREND_SETUP]` — per-bar setup evaluation: family candidate scores/validity, selected family.
- `[TREND_CANDIDATE]` — event-only: emitted when a candidate is produced (full candidate + identity).
- `[TREND_SETUP_REJECT]` — event-only: a setup was evaluated and rejected, with `invalidReason`.
- `[TREND_REPLAY]` — one summary on cold-start reconstruction (bars replayed, final `B07D1`).

Each record includes the `B07D1` signature.

---

## 20. B07D1 signature

`B07D1:<hex>` — FNV-1a 64-bit (same as B04/B05/B06), over a canonical string of **finalized** BUILD 07
state. Hashes ALL behavior-affecting persistent state as **semantic chronological state** (not physical
array/ring representation):

```
v=B07D1;
h1src=<epoch>;h1avail=<epoch>;h1regime=<enum>;h1valid=<0|1>;h1quality=<enum>;   // H1 context: raw source + availableAt
epoch=<id>;<epochStartAvail>;<epochDir>;                                        // trend epoch state
m15barOpen=<epoch>;m15avail=<epoch>;                                            // native M15 bar identity + availability
family=<enum>;dir=<enum>;candValid=<0|1>;
entry=<dec>;inv=<dec>;stop=<dec>;target=<dec>;
extension=<dec>;displacement=<dec>;                                              // separate metrics
structRef=<epoch>;setupAge=<int>;
swings=<sw0>,<sw1>,...;    // each: kind|barOpenTime|price|confirmedAtTime (chronological)
impulse=<0|1>;<originTime>;<originPrice>;<endTime>;<endPrice>;<lenATR>;
pullback=<endTime>;<endPrice>;<depthATR>;
breaks=<b0>,<b1>,...;      // each: kind|barOpenTime|price|bullish|breakAvailableAt|age|consumed|expired
pendRetest=<0|1>;<levelBarOpen>;<levelPrice>;<breakAvailableAt>;<age>;
consumed=<id0>,<id1>,...;  // chronological consumed/expired level identities
lastIdentity=<str>;        // last emitted candidate identity (ASCII-guarded)
```

Excludes wall-clock, process IDs, pointer values, log emission time, and physical ring order. Same
H1+M15 completed history → same final `B07D1` after reload. Two runs with identical *visible* output but
different hidden state (pending retest, swing identities, consumed identities) MUST produce different
signatures — enforced by collision-prevention tests.

---

## 21. Parameter surface (small, grouped)

Fixed v1 constants (NOT exposed): `M15PivotWidth=2`, `ZoneLowFrac=0.33`, `ZoneHighFrac=0.66`,
`ContradictionDisplacementATR=1.5`, `TargetLookbackSwings=8`, `MomentumLookbackBars=3`,
`M15AtrPeriod=14`.

(`M15EqualToleranceAtr` is **removed** — it has no defined role in this design; no unused strategy
constant is kept.)

Exposed inputs (grouped, every knob has structural meaning):

| Input | Default | Meaning |
|---|---|---|
| `Build07DiagnosticMode` | false | diagnostic flag |
| `ImpulseMinATR` | 1.0 | min impulse leg length (ATR) |
| `PullbackMinATR` | 0.30 | min pullback depth (ATR) — below = noise |
| `PullbackMaxATR` | 1.5 | max pullback depth (ATR) — above = too deep |
| `BreakPenetrationATR` | 0.10 | break close penetration (ATR) |
| `RetestToleranceATR` | 0.20 | retest touch band half-width (ATR) |
| `RetestMaxAgeBars` | 8 | max completed M15 bars for a retest |
| `StopBufferATR` | 0.10 | ATR stop buffer beyond invalidation |
| `MinStopATR` | 0.5 | min meaningful stop distance (ATR) |
| `MaxStopATR` | 3.0 | max reasonable stop distance (ATR) |
| `MaxExtensionATR` | 2.5 | anti-chase extension limit (ATR) |
| `MomentumMinDisplacementATR` | 0.8 | min momentum continuation displacement (ATR) |

All are Balanced-Aggressive v1 hypotheses, labeled as such.

---

## 22. Python TDD plan

`tests/build07/` — independent reference harness (no MQL5 import), same discipline as BUILD 05/06.
Scenario matrix (exact):

| ID | Scenario | Expected |
|---|---|---|
| A | TREND_BULL + valid pullback | bullish PULLBACK candidate |
| B | TREND_BEAR mirror | bearish PULLBACK candidate |
| C | pullback too shallow / noise | no candidate |
| D | pullback too deep / origin broken | no candidate |
| E | valid bull break + retest | BREAK_RETEST candidate |
| F | bear mirror | BREAK_RETEST candidate |
| G | stale/expired retest | no candidate |
| H | consumed retest cannot fire twice | no duplicate |
| I | pullback + momentum both valid same bar | PULLBACK wins |
| J | break-retest + momentum both valid | BREAK_RETEST wins |
| K | clean momentum continuation | MOMENTUM candidate |
| L | momentum excessively extended | rejected by anti-chase |
| M | H1 RANGE | no candidate |
| N | H1 BREAKOUT_BULL/BEAR | no candidate |
| O | H1 UNCERTAIN | no candidate |
| P | B06 valid=false | no candidate |
| Q | M15 local contradiction | no candidate |
| R | structural stop geometry valid | candidate with stop |
| S | stop impossible/unreasonable | candidate invalid/rejected |
| T | reward room computed truthfully | correct availableRewardR |
| U | poor reward NOT silently upgraded/rejected | candidate still valid, reward truthfully low |
| V | forming M15 bar0 never qualifies | ignored |
| W | same M15 timestamp twice | no duplicate/state advance |
| X | continuous == cold-start replay | identical final state/signature |
| Y | replay uses historically correct H1 context | no look-ahead |
| Z | changing chart timeframe | semantics unchanged |
| AA | momentum/retest/pullback priority deterministic | fixed order |
| AB | candidate identity deterministic | stable identity |
| AC | no QualityGate score / lot / execution | absent from candidate |
| AD | hidden-state collision: identical visible candidate, different pending retest/swing identity | different `B07D1` |
| AE | transition lifecycle: H1 leaves TREND → pending setup cleared | no late fire |
| AF | confirmedAtTime gate: setup cannot fire before required swing confirmed | no premature fire |
| AG1 | session/weekend gap: wall clock advances but no next native M15 bar → prior bar NOT synthetically processed | no phantom bar |
| AG2 | H1 context availability: raw H1 source timestamp must not be mistaken for availability time | correct availableAt |
| AG3 | coincident native H1/M15 availability: H1 first → M15 sees fresh H1 context | correct event order |
| AG4 | pivot across session gap: elapsed time alone cannot confirm pivot | pivot NOT confirmed |
| AG5 | trend epoch: pre-RANGE pullback cannot resurrect after new TREND_BULL epoch | old pullback rejected |
| AG6 | retest lower tolerance exact boundary: == boundary valid, below boundary failed | correct touch pass/fail |
| AG7 | max retest age: age == max eligible; after processing it expires if unresolved | expire after max-age bar |
| AG8 | newer advanced level supersedes; non-advanced newer level does not | correct supersede logic |
| AG9 | contradiction uses bodyATR only | no alternate metric |
| AG10 | target swing confirmed after trigger is excluded | future swing not used |

Boundary tests for every age/lookback/ATR-normalized threshold (pullback min/max, retest age, extension
limit, stop bounds, `MomentumLookbackBars`, `confirmedAtTime` off-by-one). Also assert `displacementATR`
and `extensionATR` are computed from distinct references and never equal aliases.

---

## 23. Native runtime validation plan

Symbols **EURUSDm** + **XAUUSDm**, execution timeframe M15, H1 context explicit `PERIOD_H1`.

- Compile 0 errors / 0 warnings; forbidden trade/strategy API scan = 0.
- H1/M15 timestamps correctly aligned (no look-ahead); completed M15 shift-1 only.
- Candidate/state update once per new M15 bar (no tick duplication).
- Two identical reloads → identical `B07D1`.
- Cold-start replay == continuous state.
- Zero positions/orders/deals caused by BUILD 07.
- Representative `[TREND_CANDIDATE]`/`[TREND_SETUP_REJECT]` diagnostics.
- No stale project source/dependency.
- If no natural trend setup appears → `NOT OBSERVED IN VALIDATION WINDOW` (never tune to manufacture).

**BUILD 06 live-H1 post-lock smoke** (run opportunistically during BUILD 07 validation; do NOT block on
it): on a genuinely new H1 close, verify exactly one B06 update, aligned B04/B05/B06 timestamps, no
`REGIME_ALIGN_SKIP`, compression FIFO + regime/candidate ages advance exactly once, no tick duplication,
B06D1 changes/stays per new finalized state, zero side effects. If no H1 close occurs → `NOT OBSERVED
IN VALIDATION WINDOW`.

---

## 24. Deployment plan (mandatory)

Automated, no manual copy/paste:
1. Resolve active connected MT5 `data_path` programmatically (`get_terminal_info`).
2. Synchronize ALL Adaptive Survival EA runtime sources (`.mq5` + every referenced `.mqh`, incl. the new
   `TrendStrategy.mqh` and any `TrendExecutionContext.mqh`) into `MQL5\Experts\AdaptiveSurvivalEA`.
3. Compile from the deployed location (MetaEditor). Require 0 errors / 0 warnings.
4. Verify workspace source revision == deployed source revision (SHA-256 manifest).
5. Verify freshly compiled `.ex5` SHA-256 + size; confirm it is the runtime-loaded artifact.
6. No stale project dependency; deploy only to the active terminal; never overwrite unrelated files.
7. Report `DEPLOYMENT INTEGRITY` block: active data_path, deployed source root, files synchronized,
   source manifest/hash, compile result, EX5 size, EX5 SHA-256, runtime-loaded artifact verified, stale
   dependency check, manual user action required = NO.

Diagnostic defaults locked false: `Build04DiagnosticMode`, `Build05DiagnosticMode`,
`Build06DiagnosticMode`, `Build07DiagnosticMode` all `= false` in deployed `Config.mqh`.

---

## 25. Locked decisions / items requiring approval

These are the architectural choices I am proposing as Balanced-Aggressive v1 hypotheses. I will NOT code
until these are accepted (or corrected). No broad multiple-choice questions — each is a concrete
proposal:

1. **M15 structure model** = width-2 strict confirmed swings (ties NOT pivots, bar0 excluded,
   `confirmedAtTime` = availability time of 2nd actual right-side completed bar = NEXT.barOpenTime) +
   leg model + single pending break-retest slot + bounded consumed-level memory. No
   significance/label/follow-through system, no regime/quality on M15.
2. **Entry price model** = close of completed trigger M15 bar (all three families). Live Ask/Bid never
   used.
3. **Pullback value zone** = broad normalized band `[0.33, 0.66]` of impulse length (constants), with
   `C.price` required INSIDE BOTH bounds; not a Fibonacci ladder. Trigger = close reclaims pullback
   midpoint.
4. **Anti-chase** = single `extensionATR` knob (`MaxExtensionATR=2.5`) with **family-specific reference**
   (pullback pivot `C` / broken level `R` / confirmed leg base), applied to ALL families. Distinct from
   `displacementATR` (3-bar net movement).
5. **Target reference** = nearest prior confirmed M15 swing high/low above/below entry (bounded
   lookback 8) with `confirmedAtTime <= triggerAvailableAt`; reward truthfully reported, no forced 2R.
6. **Stop model** = structural invalidation + `StopBufferATR=0.10`, bounded by `[MinStopATR=0.5,
   MaxStopATR=3.0]`; invalid geometry → reject. M15 ATR = native iATR(PERIOD_M15, 14), completed bars.
7. **No-lookahead alignment** = single "active H1 context slot" (`H1ContextSnapshot`) advanced
   chronologically over **native availability times**; `H1ContextSnapshot.availableAt <=
   m15CompletedBar.availableAt`; coincident availableAt processed H1-first-then-M15.
8. **Cold-start replay** = run the locked B06 H1 replay ONCE to produce historical B06 contexts
   (mapped to `H1ContextSnapshot` with both `sourceBarTime` and `availableAt`), then merge that context
   stream with M15 events ONCE (no per-M15-bar re-invocation of B04/B05/B06). If historical B06
   contexts cannot be exposed without modifying locked B04/B05/B06 semantics → STOP under the
   integration guard.
9. **Candidate dedup identity** = `symbol | m15AvailableAt | strategyFamily | structureReferenceTime`.
10. **Trend epoch barrier** = persistent `trendEpochId`/`trendEpochStartAvailableAt`/`trendEpochDirection`;
    new epoch on regime-enter-trend or direction-flip; old setup cannot cross epoch boundary.
11. **Retest boundaries** = touch bounded band `R ± RetestToleranceATR*ATR`; `retest.availableAt >
    break.availableAt`; `age == RetestMaxAgeBars` eligible then expire; supersede =
    `structurally more advanced` (directional price comparison + newer pivot identity).
12. **Contradiction** = `oppositeBodyATR = abs(close - open) / ATR` only; no alternate metric in v1.

BUILD 04/05/06 remain LOCKED. BUILD 08+ remain BLOCKED.
