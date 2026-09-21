# Hardening Audit — AdaptiveSurvivalEA

**Scope:** RiskEngine.mqh (+ PositionManager.mqh, Config.mqh), SessionNewsEngine.mqh,
QualityGate.mqh, and interaction gaps with ExecutionSafety.mqh / ExecutionBridge.mqh.
**HEAD:** `844987e` · **Date:** 2026-09-22 · **Mode:** read-only, no source modified.

**Verdict up front:** the core risk math is genuinely solid (proper
`OrderCalcProfit`/`OrderCalcMargin` usage, NaN guards, volume-grid normalization,
margin reserve). The account-blowing risks found are **not** in lot-size arithmetic —
they are in (1) the news-calendar polling cadence defeating the pre-news lock,
(2) the "daily" loss guard measuring from the wrong baseline, and (3) a dead-end
execution-lifecycle state that can permit a duplicate order.

---

## HIGH

### H-1 — News calendar cache TTL (3600 s) defeats the pre-news LOCK window (1800 s)
**File:** `SessionNewsEngine.mqh:13` (`NEWS_CALENDAR_TTL_SECONDS 3600`), `:82–86`

`EvaluateNews` caches the calendar result for **60 minutes**, but the pre-news
`NEWS_LOCK` window is only **30 minutes** (`diff <= 1800`, `:111`). Any high-impact
event that enters the 30-min pre-window *between* fetches is invisible until the TTL
expires. Concrete timeline: fetch at T returns CLEAR (event at T+50 min is outside the
±30 min query window); at T+20 min the event is 30 min out and should LOCK, but the
cache still returns CLEAR; the EA can open a position minutes before high-impact news.
At T+60 min the re-fetch finally sees it — as post-event SHOCK. The single most
important news protection (don't enter *before* news) has guaranteed blind spots.

**Fix (15 min):**
```cpp
#define NEWS_CALENDAR_TTL_SECONDS 300   // was 3600 — must be << 1800 s LOCK window
```
Better still: cache the *event timestamps* instead of the derived state, so LOCK/
SHOCK/RECOVERY are recomputed against current `serverTime` on every call.

### H-2 — `daily_start_equity` is never re-baselined: the "daily" loss limit is not daily
**File:** `AdaptiveSurvivalEA.mq5:707, 811–821` (`IsDailyLossLimitReached`,
`CheckAndResetDailyLedger`, `ReconstructDailyLedger`)

`ReconstructDailyLedger()` (called on init *and* on every day-boundary rollover)
resets `daily_net_pnl`, streaks and trade records — but **not** `daily_start_equity`.
That variable is assigned exactly once, the first time `IsDailyLossLimitReached()`
runs (`if(daily_start_equity <= 0)`). From day 2 on:

```
totalLoss = daily_start_equity(day 1) − currentEquity
```

So the 2% cap measures drawdown **since the EA first ran**, not since today 00:00.
After profitable days the guard gains a phantom cushion (late to protect); after
losing days it trips prematurely (blocks legitimate trading). The primary
account-level kill-switch is miscalibrated by construction.

**Fix (10 min):** re-anchor the baseline whenever the ledger rolls over:
```cpp
void CheckAndResetDailyLedger()
{
   ...
   if(todayStart != current_day_start)
   {
      ReconstructDailyLedger();
      daily_start_equity = AccountInfoDouble(ACCOUNT_EQUITY); // NEW
   }
}
```
(Equity-anchored baselines that include floating P/L are the standard approach;
the existing `floatingPnl` decomposition already assumes it.)

### H-3 — `EXEC_LIFECYCLE_TIMEOUT_RECONCILE` is a dead-end state: duplicate-order path
**File:** `ExecutionBridge.mqh:460–474` (`ReconcilePending`), `ExecuteIntent`;
`AdaptiveSurvivalEA.mq5:1140–1146` (`OnTimer`)

If an order gets no terminal confirmation within 30 s, the lifecycle moves to
`EXEC_LIFECYCLE_TIMEOUT_RECONCILE` — and then **nothing handles it**:
- `ReconcilePending()` early-returns for any state other than `ORDER_PENDING`/`PARTIAL_FILL`;
- `OnTimer` releases the lock only for `CONFIRMED`/`REJECTED` → lock stays held;
- `ExecuteIntent()` only blocks on `ORDER_PENDING`/`PARTIAL_FILL` → on the next
  candidate it sails past into `PREFLIGHT` and sends a **second order** while the
  first order's fate (filled? lost?) is unknown.

In practice the exposure re-check (`CountActiveOrdersAndPositions`) catches the
common cases (filled → position exists; still working → order exists), but if the
original order vanished from the pool with no history trace (broker-side weirdness,
terminal restart race), a duplicate position is sent — silent overexposure.

**Fix (30–45 min):** treat the timeout state as blocking until resolved:
```cpp
// in ExecuteIntent(), alongside the existing PENDING/PARTIAL_FILL guard:
if(m_lifecycle == EXEC_LIFECYCLE_TIMEOUT_RECONCILE)
{
   // Force a history-deal lookup for m_pendingDealTicket / order ticket
   // before any new order may be sent; only clear on positive proof
   // of fill (→ CONFIRMED) or of no-fill (→ REJECTED).
   LogError("EXECUTION_BLOCKED_TIMEOUT_UNRESOLVED", ...);
   return false;
}
```
And add an explicit terminal transition out of `TIMEOUT_RECONCILE` inside
`ReconcilePending()` (resolve via `HistoryOrderSelect`/`HistoryDealSelect`
before giving up).

---

## MEDIUM

### M-1 — Calendar query window (±1800 s) truncates the RECOVERY window (−2700 s)
**File:** `SessionNewsEngine.mqh:15, 86–89`

`NEWS_CALENDAR_MAX_AGE = 1800` is used as the ± query half-window, but the
RECOVERY state covers `diff ∈ [−2700, −900)` (`:118`). Events 30–45 min old never
enter the result set, so calendar-driven RECOVERY is unreachable for that slice —
the post-news quality tightening (70 → 80, `CheckGating`) silently doesn't apply.

**Fix:** query `fromTime = serverTime − 2700` (or a named `NEWS_RECOVERY_LOOKBACK`).

### M-2 — `CalendarCountryById` failure is fail-open; `CalendarEventById` failure is fail-closed
**File:** `SessionNewsEngine.mqh:107–128`

Event-resolution failure → `NEWS_UNKNOWN` (fail-closed, correct). Country-resolution
failure → `continue` (event silently skipped — fail-open). A HIGH-importance event
whose country can't be resolved is dropped without a trace, in a subsystem whose
contract is fail-closed.

**Fix:** treat country-resolution failure like event-resolution failure:
```cpp
if(!CalendarCountryById(event.country_id, country))
{
   LogWarning("CALENDAR_COUNTRY_RESOLVE_FAILED", ...);
   calendarState = AggregateState(calendarState, NEWS_UNKNOWN); // was: continue
   continue;
}
```

### M-3 — `NewsGuardRequired=false` does not actually relax the news guard
**File:** `SessionNewsEngine.mqh:160–166` vs `AdaptiveSurvivalEA.mq5:1006–1011`

`CheckGating` blocks `NEWS_UNKNOWN` **unconditionally**. The pipeline's earlier
`if(NewsGuardRequired && newsState == NEWS_UNKNOWN)` check is therefore redundant —
with `NewsGuardRequired=false` the user expects trading to continue without a
calendar, but `CheckGating` blocks anyway. The input is a config lie.

**Fix (pick one, 10 min):** either honor the flag in `CheckGating`
(`if(news == NEWS_UNKNOWN && newsGuardRequired)`) or remove the input and document
that the guard is always fail-closed.

### M-4 — One transient calendar API failure halts *all* trading for up to 60 minutes
**File:** `SessionNewsEngine.mqh:93–100`

On `CalendarValueHistory` failure the code caches `NEWS_UNKNOWN` for the full
3600 s TTL → every candidate blocked for up to an hour on a single failed call.
Fail-closed is the right default, but the retry horizon should be short.

**Fix:** separate failure TTL, e.g. cache `NEWS_UNKNOWN` for 60–120 s, then retry.

### M-5 — `RiskDiagnosticPercent` (0.50) is the *live* risk parameter, not a diagnostic
**File:** `Config.mqh:12`, `AdaptiveSurvivalEA.mq5:1062`

The input named "RiskDiagnostic…" feeds `riskReq.riskPercent` in the **live**
sizing path (line 1062), not just `RunRiskDiagnostic()` (line 134). An operator
could reasonably set it to 0 thinking it only affects diagnostics — which would
then reject every trade (`riskPercent <= 0` → `REJECT_INVALID_REQUEST`), or
misread it while tuning live risk.

**Fix (10 min):** rename to `RiskPercent` (keep old name as deprecated alias if
`.set` files exist in the wild).

---

## LOW

### L-1 — QualityGate: NaN spread passes the hard veto
**File:** `QualityGate.mqh:64`

`currentSpreadPrice > 0.25 * stopDistance` is `false` when spread is NaN → veto
skipped; NaN then scores 0 spread points, but 35+30+20+0 = **85 ≥ 70 → approved**
with unknown spread. `ExecutionSafety` re-checks with a fresh tick downstream, so
this is defense-in-depth rather than an open hole — but the gate should not bless
what it can't measure.

**Fix:** `if(!MathIsValidNumber(currentSpreadPrice) || currentSpreadPrice > ...)`.

### L-2 — QualityGate scores a fabricated 10-point spread when spread ≤ 0
**File:** `AdaptiveSurvivalEA.mq5:998`

`if(currentSpreadPrice <= 0) currentSpreadPrice = 10 * point;` invents data and can
award full spread score. Prefer `return` (no quote, no trade) over synthetic input.

### L-3 — `ReconstructDailyLedger` omits `DEAL_FEE`; live path includes it
**File:** `AdaptiveSurvivalEA.mq5:745` vs `:1153`

Restart-time ledger: `profit + commission + swap`. Live: `+ fee`. Post-restart
P/L is systematically understated by fees (guard slightly looser after restarts).

### L-4 — `consecutive_losses` counts per *deal*, ledger groups per *position*; breakeven doesn't reset
**File:** `AdaptiveSurvivalEA.mq5:1197–1205`

No partial-close intent exists today, so 1 deal ≈ 1 trade and impact is nil — but
the day the EA (or a manual intervention) closes in parts, one losing trade can
add 2 to the streak. Also `netPnL == 0` touches neither streak (a breakeven trade
arguably should reset `consecutive_losses`).

### L-5 — `QUOTE_DRIFTED` check is vacuous
**File:** `AdaptiveSurvivalEA.mq5:1080–1088`

Both `liveEntryPrice` and `verifyPrice` are read from the **same** `env.tick`
snapshot (`FetchFinalQuote` runs once) → drift is always 0. The real slippage
guard is `deviation = 10` on the actual send. Either re-fetch for a genuine
check or remove the dead check to avoid false confidence.

### L-6 — `ExecutePositionManage` reads direction from ambient position selection
**File:** `ExecutionBridge.mqh` (`ExecutePositionManage`, MODIFY_SL branch)

`PositionGetInteger(POSITION_TYPE)` is called **without** `PositionSelectByTicket(intent.ticket)`
first. Correct today only because the sole caller (`ManageOpenPositions`) happens
to have that position selected. One refactor away from modifying the wrong
position's SL.

**Fix:** `if(!PositionSelectByTicket(intent.ticket)) return false;` at the top.

### L-7 — `AcquireOrderLock` "re-entrancy" branch is dead code (benign)
**File:** `ExecutionBridge.mqh` (`AcquireOrderLock`)

A fresh owner token is minted on every call, so `currentOwner == m_ownerToken`
can never be true for a lock this instance already holds. Harmless in practice
(the post-lock exposure re-check covers it), but the invariant comment lies.

---

## INFO (no action required, recorded for completeness)

- **I-1** — `CSessionNewsEngine::s_calendarAvailable` is written (`:98,:104`) but
  never read. Dead flag.
- **I-2** — `NEWS_CALENDAR_MAX_AGE` is a misnomer: it's the ± query half-window,
  not a staleness bound.
- **I-3** — `SESSION_LOW_LIQUIDITY` / `SESSION_CLOSED` are never returned by
  `EvaluateSession` (only CORE / SECONDARY / ROLLOVER). Dead enum values.
- **I-4** — `RenewLockLease()` and `SetMaxSlippagePoints()` are never called.
- **I-5** — Risk explicitly excludes commission/swap (`RISK_DIAGNOSTIC` log says
  `risk_definition=price_loss_to_sl_excludes_costs`). Documented; true risk is
  marginally higher than sized.
- **I-6** — The 80-score secondary-session tightening *is* enforced: `Evaluate`
  approves at its internal 70, then the EA's `totalScore >= requiredQualityScore`
  applies the 80. Redundant but correct.
- **I-7** — `SYMBOL_TRADE_MODE` LONGONLY/SHORTONLY/CLOSEONLY rely on
  `OrderCheck` to fail (only DISABLED is excluded up front). Safe direction,
  wasted cycle at most.
- **I-8** — `CExecutionBridge` is correctly configured at init
  (`SetSymbol/SetMagic/SetMaxPositions`, `AdaptiveSurvivalEA.mq5:676–678`); the
  `EURUSDm`/123456 constructor defaults are fully overridden.

## What's genuinely good (don't regress)

- `RiskEngine`: `OrderCalcProfit`/`OrderCalcMargin` used properly (no hand-rolled
  tick-value math), NaN validation on every input, epsilon-aware volume-grid
  flooring, min-volume exception capped at the hard cap, margin check with
  reserve (`marginReservePercent < 100` validated → no div-by-zero), `equity > 0`
  enforced before the `actualRiskPercent` division.
- `ExecutionSafety`: spread-spike veto with warm-up policy (ceiling-only while
  cold = fail-closed), `OrderCheck` preflight, filling-mode awareness,
  **directional** tick normalization (SL never rounded toward market).
- `ExecutionBridge`: CAS-based cross-instance lock with lease + steal-safety,
  stops/freeze validation on *normalized* values, lifecycle machine with
  `OnTradeTransaction` reconciliation.
- `SessionNewsEngine`: fail-closed by design (`NEWS_UNKNOWN` blocks); cache
  exists to avoid hammering the calendar API.
- Daily ledger reconstructs from deal history on restart (good idea — just fix
  the baseline, H-2).

---

## Prioritized hardening plan

| # | Item | Effort |
|---|------|--------|
| 1 | **H-2** re-anchor `daily_start_equity` on day rollover | ~10 min |
| 2 | **H-1** news TTL 3600 → 300 s (and consider caching event times, not states) | ~15 min |
| 3 | **H-3** block `ExecuteIntent` on `TIMEOUT_RECONCILE`; add terminal resolution via history lookup | ~30–45 min |
| 4 | **M-4** short failure-TTL for calendar errors; **M-1** widen query to −2700 s; **M-2** fail-closed on country-resolve failure | ~30 min batch |
| 5 | **M-3** decide `NewsGuardRequired` semantics; **M-5** rename `RiskDiagnosticPercent` | ~15 min |
| 6 | Lows L-1…L-7 (spread NaN veto, drop fabricated spread, add `DEAL_FEE` to reconstruct, per-position streak, remove/repair drift check, `PositionSelectByTicket`, fix lock comment) | ~60–90 min total |

**Suggested order for a live account:** 1 → 2 → 3 before anything else. Items 1 and 2
are the two guards most likely to matter in production (account-level loss cap and
news blackout); item 3 closes the only realistic duplicate-execution path found.
