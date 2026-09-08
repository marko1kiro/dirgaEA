# Strategy/remediation patch design — F06, F08, F09, F11

**Audited source:** `marko1kiro/dirgaEA` at `844987eea6601379fcb534fd9aac8fe98a71c241` (archive extracted read-only).  This is a patch design only; no repository files were changed.

## 1. Current APIs and the safe ownership model

| Component | Current public API / behaviour | Patch decision |
|---|---|---|
| `CTrendStrategy` | `SetH1Regime(const RegimeResult&)`; `FeedM15Bar(t,o,h,l,c,avail,atr,out)` mutates its M15 bar, pivot, leg and break/retest state and may emit one trend candidate; `GetM15Swings(out,count)` copies its pivot store. | It is the **sole owner of M15 bars and swing construction**. Feed it exactly once per completed M15 bar. Then copy a snapshot with `GetM15Swings` for the other two strategies. Do not call `FeedM15Bar` once per strategy. |
| `CRangeStrategy` | `SetH1Regime`; `Evaluate(t,o,h,l,c,avail,atr,const B07_Swing[],count,out)`. It holds only H1 context; `Evaluate` has no state mutation other than `out`. | Set the same authoritative H1 context, then evaluate against the immutable copied trend-swing snapshot. |
| `CBreakoutStrategy` | Same shape as range. It holds H1 context only and evaluates a supplied swing snapshot. | Same as range. |
| `CQualityGate` | Evaluates the signal-time `TradeCandidate`; current EA calls it **before** final quote/repricing. | Evaluate only a normalized, live-price candidate whose quantities are recalculated. |

This uses one shared structure producer without allowing an evaluator to mutate it. It also avoids a subtle apparent workaround: calling `FeedM15Bar` a second/third time happens not to append because `t == m_lastBarTime`, but it returns `false` and makes its use as an evaluator both misleading and fragile.

### Minimal context/provenance API addition

Do not overload `RegimeResult.latestClosedH1`: it is a **source bar open time**, not the time the result became usable. Add a separate runtime availability argument to all three setters:

```mql5
void SetH1Regime(const RegimeResult &h1, const datetime availableAt);
```

Each class stores `m_h1AvailableAt`; every produced candidate sets:

```mql5
cand.h1SourceBarTime = m_h1Regime.latestClosedH1;
cand.h1AvailableAt   = m_h1AvailableAt;
```

In the EA, set `b06_result_available_at = TimeCurrent()` only after a successful, timestamp-aligned B06 commit. Pass that value to B07/B11/B12. This represents actual live availability (rather than assuming that a closed H1 result was calculated exactly at `barOpen + 3600`) and remains fail-closed after delayed quotes/history.

`m_epochStartAvail` must use this `availableAt`, not `newH1.latestClosedH1`.

## 2. F06 — retain and classify the raw ATR ratio

### Exact source area

* `Types.mqh:118–130` (`VolatilityResult`)
* `MarketBrain.mqh:184–195` (`ProcessBuild05ClosedHistoryPrefix`)
* `MarketBrain.mqh:476–540` (`VolatilityLevelClassify`, `VolatilityEngine`)

### Patch

Add `double atrRatio;` to `VolatilityResult` (document it as `current ATR / rolling baseline`, not normalized). Set it explicitly to `0.0` in `ResetH1BrainInvalid`. In `VolatilityEngine`, after a valid baseline:

```mql5
const double ratio = atr[n] / baseline;
out.atrRatio = ratio;
out.levelScore = BrainClampUnit(ratio / VOL_EXTREME_RATIO); // diagnostics/UI only
```

Then replace the caller input:

```mql5
// old (wrong scale): VolatilityLevelClassify(result.volatility.levelScore, ...)
VolatilityLevelClassify(result.volatility.atrRatio, ...);
```

Do not change the `VOL_LOW_RATIO`, `VOL_HIGH_RATIO`, `VOL_EXTREME_RATIO`, or dwell machine. Both live and cold-replay already go through `ProcessBuild05ClosedHistoryPrefix`, so this one caller change preserves parity. `Build05RawTrace.atrRatio` remains a diagnostic mirror, not an API a downstream decision must rely on.

## 3. F08 — wire range/breakout with a deterministic max-one arbiter

### Exact source area

* `AdaptiveSurvivalEA.mq5:67–76` declares B07/B11/B12, but only B07 is called.
* `AdaptiveSurvivalEA.mq5:953–1120` is the completed-M15 dispatch path.
* `RangeStrategy.mqh:17–30, 58–154`; `BreakoutStrategy.mqh:17–30, 57–172` are current APIs and candidate construction.
* `TrendStrategy.mqh:856–953` owns the M15 update and emits its internally prioritized trend candidate.

### Per-bar sequence

On a completed M15 bar, after the existing fresh/valid B06 gate:

1. Set B07, B11 and B12 to **the same** `b06_result` and `b06_result_available_at`.
2. Call `b07_trend_strategy.FeedM15Bar(...)` once. Save its output in a local `trendCandidate` and `hasTrendCandidate`; do not use global `b07_last_candidate` as the dispatch candidate.
3. Copy the now-confirmed snapshot once:
   ```mql5
   B07_Swing swings[];
   int swingsCount = 0;
   b07_trend_strategy.GetM15Swings(swings, swingsCount);
   ```
4. Call B11 and B12 `Evaluate` with the identical completed OHLC, availability time, ATR and snapshot. Keep separate booleans/candidates.
5. Pass up to three local candidates to `SelectActiveCandidate`. Set a single global/dashboard `last_selected_candidate` only after selection. All quality/risk/execution code consumes that object.

For warm-up/no authoritative H1, either continue to call B07 only in an explicit *ingest-only* mode, or intentionally do not build M15 structure. Do not feed it with a stale valid B06 result merely to keep pivots warm. The cleaner small refactor is `IngestM15Bar(...)` (duplicate guard, bar FIFO, age advance, pivot detection) plus `EvaluateCurrentBar(...)` (H1-dependent legs/breaks/setups); the legacy `FeedM15Bar` can call both for compatibility. This permits benign structural warm-up under an invalid H1 context while candidates remain impossible.

### Eligibility is the arbiter, not a scoring contest

Use a fixed local array (capacity 3) and a helper in `AdaptiveSurvivalEA.mq5`, avoiding containers/templates that add needless MQL compile risk:

```mql5
bool CandidateMatchesActiveRegime(const TradeCandidate &c,
                                  const RegimeResult &r,
                                  const datetime h1AvailableAt)
{
   if(!c.valid || !r.valid || c.symbol != _Symbol) return false;
   if(c.sourceRegime != r.regime || c.h1SourceBarTime != r.latestClosedH1 ||
      c.h1AvailableAt != h1AvailableAt || c.m15AvailableAt <= 0) return false;

   if(r.regime == REGIME_TREND_BULL)
      return c.direction == TRADE_DIR_BUY &&
             (c.setupFamily == SETUP_FAMILY_PULLBACK ||
              c.setupFamily == SETUP_FAMILY_BREAK_RETEST ||
              c.setupFamily == SETUP_FAMILY_MOMENTUM);
   if(r.regime == REGIME_TREND_BEAR)
      return c.direction == TRADE_DIR_SELL &&
             (c.setupFamily == SETUP_FAMILY_PULLBACK ||
              c.setupFamily == SETUP_FAMILY_BREAK_RETEST ||
              c.setupFamily == SETUP_FAMILY_MOMENTUM);
   if(r.regime == REGIME_RANGE)
      return c.setupFamily == SETUP_FAMILY_RANGE_SWEEP &&
             (c.direction == TRADE_DIR_BUY || c.direction == TRADE_DIR_SELL);
   if(r.regime == REGIME_BREAKOUT_BULL)
      return c.setupFamily == SETUP_FAMILY_BREAKOUT_DIRECT && c.direction == TRADE_DIR_BUY;
   if(r.regime == REGIME_BREAKOUT_BEAR)
      return c.setupFamily == SETUP_FAMILY_BREAKOUT_DIRECT && c.direction == TRADE_DIR_SELL;
   return false; // UNCERTAIN
}
```

`SelectActiveCandidate` considers only candidates matching that predicate. Therefore an active regime has one permitted strategy family: B07 in trend, B11 in range, B12 in directional breakout, none in uncertain. This is deliberately stronger than “take the best among all strategies”; it cannot issue an opposing/legacy-family order merely because a stale module emitted something.

As defence in depth, rank any unexpected duplicate with stable integer priority: `BREAK_RETEST=30`, `PULLBACK=20`, `MOMENTUM=10`, all other valid matched families `=100`, then lowest `m15AvailableAt`, then smallest `structuralReferenceTime`, then lowest enum value. The output must be copied once and the helper must return one boolean; there must be one and only one call path to `PrepareMarketOrder`.

The ranking does **not** alter B07’s existing internal order (`PULLBACK`, then `BREAK_RETEST`, then `MOMENTUM`, lines 925–948). If the intended economic priority is break-retest over pullback, separately refactor B07 to collect all current-bar trend candidates before consuming/deduplicating; do not pretend an EA-level arbiter can choose a candidate B07 never returns.

### Range dormant wrong-side target fix

`RangeStrategy.mqh:85–126` must add the missing inside-range and directional tests before constructing a BUY:

```mql5
if(l < rangeLow && c > rangeLow && c < rangeHigh)
{
   // construct only if sl < c && c < tp
}
```

Likewise at `128–169` only construct a SELL when `h > rangeHigh && c < rangeHigh && c > rangeLow`, then require `tp < c && c < sl`. Do **not** use `MathAbs` to make an invalid, passed target look like positive reward. A candle that closes through the opposite range boundary is stale/overextended; reject it, not retarget it.

## 4. F09 — bind break-retest to its actual current trigger bar

### Exact source area

* `Types.mqh:283–290` (`TrendBreakItem`)
* `TrendStrategy.mqh:497–542` (`CheckRetest`)
* `TrendStrategy.mqh:693–767` (`EvaluateBreakRetest`)
* `TrendStrategy.mqh:897–908` calls `CheckRetest` for `curB`.

### Patch

Add the trigger evidence to `TrendBreakItem`:

```mql5
datetime triggerBarTime;
datetime triggerAvailableAt;
double   triggerOpen;
double   triggerHigh;
double   triggerLow;
double   triggerClose;
```

Initialize these fields to zero in `AddBreak`. On the successful bull or bear branch in `CheckRetest`, before setting `consumed=true`, copy the passed `bar` into these fields on `m_pendingBreak` and the matching `m_breaks[]` record. A small `MarkPendingBreakConsumed(const B07_Bar &bar)` helper avoids the existing duplicated matching loops drifting apart.

Replace `EvaluateBreakRetest`’s scan for the first later acceptance bar (lines 706–714) with the recorded bar. Require `triggerAvailableAt == now`; that guarantees the signal only exists on the completed bar that touched/reclaimed the level and cannot resurrect on a later M15 bar. Use:

```mql5
B07_Bar tri;
tri.t    = m_pendingBreak.triggerBarTime;
tri.avail= m_pendingBreak.triggerAvailableAt;
tri.o    = m_pendingBreak.triggerOpen;
tri.h    = m_pendingBreak.triggerHigh;
tri.l    = m_pendingBreak.triggerLow;
tri.c    = m_pendingBreak.triggerClose;
```

For a BUY use `touchLow = MathMin(m_pendingBreak.price, tri.l)` and `inv = touchLow`; for a SELL use `touchHigh = MathMax(m_pendingBreak.price, tri.h)` and `inv = touchHigh`. This preserves a stop beyond the broken level even when the touch only reaches the top/bottom tolerance band. Use `tri.c`, `tri.avail`, and `tri.t` for entry, target eligibility and candidate timestamps; compute retest distance from `touchLow/touchHigh`. Never scan subsequent bars to make a prior setup more/less risky.

## 5. F11 — real swing FIFO, no old-pivot reinsertion

### Exact source area

* `TrendStrategy.mqh:280–362` (`DetectPivots`) only appends while `m_swingsCount < B07_MAX_SWINGS`.
* `TrendStrategy.mqh:856–895` already has a correct bar FIFO, but not a pivot FIFO.
* `TrendStrategy.mqh:364–420`, `544–592`, `596–845`, `897–904` hold references/queries that must obey epoch and removed-pivot rules.

### Patch

Add a private `AppendSwing(const B07_Swing &value)`:

```mql5
void CTrendStrategy::AppendSwing(const B07_Swing &value)
{
   if(m_swingsCount < B07_MAX_SWINGS)
   {
      m_swings[m_swingsCount++] = value;
      return;
   }
   for(int i = 1; i < B07_MAX_SWINGS; ++i)
      m_swings[i - 1] = m_swings[i];
   m_swings[B07_MAX_SWINGS - 1] = value;
}
```

Do not retain the full-history `DetectPivots` scan and merely substitute `AppendSwing`: after eviction, that scan would rediscover an old pivot still inside the 512-bar buffer and evict newer swings again. Because input is one chronological completed bar at a time, detect only the single pivot whose second right-hand completed bar has just arrived:

* Let `p = m_barsCount - 3`; return until `m_barsCount >= 5`.
* Compare `m_bars[p]` against `p-2`, `p-1`, `p+1`, `p+2`.
* Its confirmation time is `m_bars[p+2].avail`.
* Deduplicate by `bt`, then `AppendSwing` the qualifying high/low.

This directly replaces the current index translation (`n = 1 + m_barsCount`, lines 282–304), which also contains a hazardous `m_bars[i-3]` access when `i==2`. The new direct indexing is easier to prove bounds-safe and preserves the specified two actual right-side bar confirmations.

### References after eviction and epoch transition

`m_pendingBreak`/`m_breaks` copy price/time into `TrendBreakItem`; they must not dereference the swing store. Bound the break array too (FIFO or proactively remove consumed/expired oldest before append), even though an 8-bar expiry normally makes 128 unreachable. When a new epoch begins:

* expire/clear pending and stored break/retest items;
* clear impulse/pullback state (`m_iot` through `m_pbd`, `m_iprimed`), and reset `m_lastCandidateIdentity`;
* keep raw swing history only as observational data, but require `sw.ct >= m_epochStartAvail` in `UpdateLegs`, the break scan in `FeedM15Bar`, pullback/momentum lookup, and target lookup for a trend candidate.

The last rule is the conservative contract: **no pre-epoch trend geometry, break, retest, leg base, or target can create an entry in a new trend epoch**. B11/B12 can continue to use confirmed raw pivots as market context because they have no carried pending setup; document this intentional distinction. If the product instead wants range/breakout context to be epoch-local, pass an explicit cutoff to their `Evaluate` calls and test the longer warm-up consequence.

## 6. Live-entry reprice, directional validity and quality ordering

This is required to close F09 in the actual dispatch path and aligns with F07’s final-stop sizing rule.

### Exact source area

* `AdaptiveSurvivalEA.mq5:1017–1023` quality evaluates `b07_last_candidate` before live quote.
* `AdaptiveSurvivalEA.mq5:1054–1077` only replaces live entry for sizing; it leaves candidate metrics/quality/target stale.
* `ExecutionBridge.mqh:186–205, 480–526, 550–579` exposes normalizers, builds intent from candidate, then normalizes again at send.
* `ExecutionSafety.mqh:128–175` independently nearest-rounds its OrderCheck stops.

### Candidate data and helper

Add `double extensionReferencePrice;` to `TradeCandidate`. Populate it from the structural point used by the corresponding setup: pullback C, break-retest break level, momentum leg-base, range support/resistance, and breakout level. This is necessary: `invalidationPrice` is a retest extreme for break-retest and is not always the extension anchor.

After order lock/exposure check and **after** `FetchFinalQuote`, call a pure EA helper, e.g. `BuildFinalEntryCandidate(base, liveQuote, atr, out, rejectReason)`:

1. Copy `base`; replace entry with `NormalizePrice(Ask)` for BUY or `NormalizePrice(Bid)` for SELL.
2. Normalize SL directionally with `NormalizeStopPrice(..., dir, true)` and TP with `NormalizeStopPrice(..., dir, false)` before every metric/risk calculation.
3. Enforce strict directed geometry, not absolute distances:
   * BUY: `stop < entry && target > entry`;
   * SELL: `stop > entry && target < entry`.
   Reject `target_passed_or_wrong_side` or `stop_wrong_side`; never “repair” these by moving a structural target/stop.
4. Recalculate `stopDistance`, `stopDistanceAtr`, `rewardDistance`, `rewardRiskRatio`, and the signed extension: `(entry-extensionReferencePrice)/atr` BUY, `(extensionReferencePrice-entry)/atr` SELL. Reject negative extension or an extension over the family’s maximum. Retain signal-time values only for telemetry if desired; do not send/evaluate them.
5. Update `entryPrice`, `initialStopPrice`, `targetPrice`, metrics, and a `finalizedAt`/final-quote diagnostic field (if added).

The target is intentionally kept at its signal-derived structural price; the final entry changes the achievable RR. Thus a live quote that has already reached/passed a range target or old swing target is rejected rather than accepted after `MathAbs` produces a plausible reward.

### Correct dispatch order

1. Candidate selection and session/news gating.
2. Acquire order lock; recheck exposure.
3. Fetch final immutable quote.
4. Build/validate the final candidate as above.
5. Compute current spread from that quote and run `CQualityGate::Evaluate(finalCandidate, ...)`.
6. Size risk with exactly `finalCandidate.entryPrice` and `finalCandidate.initialStopPrice`.
7. `PrepareMarketOrder(finalCandidate, risk, intent)`.
8. Preflight and execute exactly the resulting normalized intent.

Make normalization idempotent and have `ExecutionSafety::ValidateOrder` pass the already-normalized `intent.price`, `intent.stopLoss`, and `intent.takeProfit` to `OrderCheck`, rather than a second independently nearest-rounded version. `ExecuteIntent` may keep its normalizers as assertions/idempotent defence, but should reject a mismatch rather than silently change a checked request. This is important for both the F09 metric truthfulness and F07 hard-risk-cap guarantee.

## 7. H1 update/position-management ordering

### Exact source area

* `AdaptiveSurvivalEA.mq5:915–952` calls `ManageOpenPositions()` before the completed-H1 processing despite its comment saying the opposite.
* `AdaptiveSurvivalEA.mq5:838–911` passes `b06_result` directly into position management.
* `PositionManager.mqh:70–92` immediately uses any `h1Regime.valid` for a regime-flip exit.

Reorder `OnTick` as:

```
Refresh environment
Process/attempt completed H1 update and provenance commit
Manage open positions
Process completed M15/new entries
Dashboard
```

For management, derive `managementRegime = b06_result` only when its source H1 and runtime availability are fresh for the current completed H1. Otherwise copy it and set `managementRegime.valid = false` before calling `CPositionManager::Evaluate`. This suppresses a stale regime-flip close, while leaving BE/trailing protective management available. Do not return from `ManageOpenPositions` merely because a regime update failed; it must still perform non-regime protective actions. (The separate no-ATR management gap deserves its own safety patch.)

This ordering gives a coincident H1/M15 close the new H1 provenance before management and candidate selection, without allowing a failed/delayed update to masquerade as a fresh regime.

## 8. Regression and contract tests

All tests below should be added first; each is expected to fail against the audited archive.

### F06 (`tests/build05`)

1. Add an end-to-end canonical-path test that supplies ATR/baseline ratios `1.0, 1.6, 1.6, 2.2, 2.2` through the equivalent of `ProcessBuild05ClosedHistoryPrefix`, asserting NORMAL, NORMAL, HIGH-after-dwell, HIGH, EXTREME-after-dwell. A raw ratio `4.0` must reach EXTREME after the same dwell. The old `ratio/2` caller can never produce HIGH/EXTREME.
2. Add a source-contract test asserting the `VolatilityLevelClassify` call uses `result.volatility.atrRatio`, while `levelScore = BrainClampUnit(...)` remains diagnostics only.
3. Run the same vector through cold replay and live reference state and require identical result/dwell/challenger fields.

### F08 / range / breakout (`tests/build11`, `tests/build12`, new EA wiring reference test)

1. A valid range support sweep whose close is **above `rangeHigh`** must return no candidate; symmetric close below `rangeLow` for sell also returns none. Existing B11 emits a wrong-side TP.
2. Directly test valid B11 and B12 candidates still reach their existing correct directional TP.
3. Model a completed M15 bar and one swing snapshot. Assert the trend owner is fed once, B11/B12 see the same snapshot, and each active B06 regime permits exactly its intended family/direction: trend→B07, range→B11, breakout bull/bear→B12 buy/sell, uncertain→none.
4. Supply stale/wrong-regime candidates alongside a valid candidate; assert arbiter rejects the stale candidates and dispatch count is 0 or 1, never 2. Add source-contract checks for B11/B12 setters/evaluations and a single `PrepareMarketOrder(selectedCandidate,...)` call.

### F09 / final quote (`tests/build07`, `tests/build09`, integration reference)

1. Break → continuation/acceptance → retest: assert emitted candidate’s `m15BarTime`, entry, touch extreme, stop and target eligibility are the **retest** bar’s values, not the earliest post-break continuation bar. Feed one later M15 bar and assert no re-emission.
2. Bull and bear tests at the retest tolerance boundary: stop must be beyond `min(level,retestLow)` / `max(level,retestHigh)`.
3. Signal-time BUY `entry=100, SL=99, TP=102`, live Ask `100.8`: recomputed RR is `1.2/1.8`, not 2.0, and quality must use the recomputed values. Symmetric SELL test.
4. A BUY live Ask at/above target and SELL live Bid at/below target must reject `target_passed_or_wrong_side`; wrong-side normalized SL must reject before quality/risk/send.
5. Tick-grid vector (`tickSize != point`) verifies final normalized stop/TP/entry are identical in quality, risk request, OrderCheck request and send request.

### F11 / epoch / provenance / ordering (`tests/build07`, new source contracts)

1. Feed enough alternating pivot-producing bars for more than `B07_MAX_SWINGS + 20` confirmed pivots. Assert count stays 256, oldest stored confirmation advances, newest pivot remains present, and no pre-eviction pivot is reinserted on the next bar.
2. With only four completed bars assert no pivot; fifth/right-side completion confirms exactly the center pivot. This catches the existing unsafe `i-3` indexing and enforces two real right bars.
3. Build a trend impulse/break, transition trend→range→same trend, then feed a trigger. Assert no old break/retest, leg, target, or candidate survives; a new post-epoch structure is required.
4. H1 close and M15 close on the same tick: assert H1 commit precedes management and M15 selection and candidates carry source H1 time plus actual result availability. A failed/delayed H1 update yields `managementRegime.valid=false` for regime exits but does not skip trailing/BE logic.

Python reference models need the same field/API updates; source-regex contracts alone are not adequate evidence for the native data flow. Add/update a native MQL probe for the raw-volatility sequence, pivot FIFO, retest trigger provenance, and candidate arbiter if MetaEditor becomes available.

## 9. Main implementation risks / review gates

* The audited `TrendStrategy::DetectPivots` indexing should be corrected as part of FIFO work; merely adding an eviction shift is not safe because it reintroduces old pivots and leaves a negative index path.
* `TrendBreakItem` is copied in several places. Centralize consumed/expired synchronization so `m_pendingBreak` and `m_breaks[]` cannot disagree after trigger capture or supersession.
* B07’s current candidate identity includes source `m15AvailableAt` and structural reference. Reset it on epoch; otherwise a valid structurally similar setup can be accidentally suppressed across epochs.
* Repricing requires one quote snapshot, not a comparison of a snapshot to itself. Do not claim `MAX_SLIPPAGE_DRIFT_POINTS` checks movement while only rereading `broker_environment.tick`.
* Do not activate B11/B12 merely because they compile. The arbiter, live repricing, and directional geometry tests must land together; range/breakout are otherwise new executable paths.
* Compile verification remains required: MQL5 fixed arrays, `const` array parameters, `ZeroMemory` for added struct fields, and new setter signatures must be updated consistently at all declarations/call sites. No MetaEditor compiler was present during this design review.
