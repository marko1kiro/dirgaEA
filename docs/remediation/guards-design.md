# Concrete remediation design — F02 daily guard and F03 news guard

**Snapshot reviewed:** `marko1kiro/dirgaEA` main at `844987eea6601379fcb534fd9aac8fe98a71c241`, extracted read-only to `/tmp/dirgaea-audit`.  This is a patch design only; no repository files were changed.

## Executive decisions

1. Make the **daily loss limit account-equity based**.  Its state key is account/day namespaced, not symbol/magic scoped.  This is the only unambiguous meaning of a daily equity loss limit when another chart, EA, or manual trade can alter the account equity.  It will therefore block this EA after loss caused elsewhere on the same account, which is the safe default.
2. Define the measured amount as

   ```text
   adjusted_equity = ACCOUNT_EQUITY - external_cashflow_since_broker_midnight
   daily_loss      = max(0, day_start_equity - adjusted_equity)
   ```

   Thus realized and floating P/L are both included exactly once through equity; a deposit cannot erase a prior loss and a withdrawal cannot create one.  Do **not** add `daily_net_pnl` to this calculation.
3. Persist an authoritative baseline on each broker-day rollover.  On restart it is loaded, never reset to current equity.  If there is no trustworthy baseline, the EA must allow position management but block **all new entries** (`daily_guard_unavailable`) until a safe bootstrap succeeds or an operator explicitly provides a reviewed baseline.
4. Build the loss/win streak from **completed position lifecycles**, not exit deals.  A partial close is merely an accumulator update.  At final close, sum every position deal's `DEAL_PROFIT + DEAL_COMMISSION + DEAL_SWAP + DEAL_FEE`, including entry-side commission and all exit-side costs.
5. Cache **relevant high-impact event data and its time coverage**, never a time-dependent `NEWS_CLEAR/LOCK/...` result.  Recalculate the state from cached timestamps on every call.  Any missing currency, calendar query error, event-resolution error, or (if used) relevant-country-resolution error returns `NEWS_UNKNOWN` and cannot be aggregated away.

These controls only gate *new* entries.  Existing position protection/exit management must continue even while history/calendar services are unavailable.

---

# F02 — persistent daily loss and full-position streak

## Why the current code cannot be repaired by a small formula change

`AdaptiveSurvivalEA.mq5:815–821` initializes `daily_start_equity` to the equity on first evaluation and then computes:

```text
daily_net_pnl + (current_equity - daily_start_equity - daily_net_pnl)
= current_equity - daily_start_equity
```

Consequently the reconstructed net P/L cancels, a restart starts at zero loss, and `current_day_start` rolls while `daily_start_equity` does not.  The current reconstruction also includes only OUT deals, omits `DEAL_FEE`, marks every partial as closed, and the transaction handler increments the streak per exit deal.

## Scope and definitions

Add a small include, for example `DailyRiskLedger.mqh`, rather than retaining ledger state as unrelated globals in the EA.

```mql5
enum ENUM_DAILY_STREAK_SCOPE
{
   DAILY_STREAK_ACCOUNT = 0,
   DAILY_STREAK_EA_SYMBOL_MAGIC = 1
};

input ENUM_DAILY_STREAK_SCOPE DailyStreakScope = DAILY_STREAK_EA_SYMBOL_MAGIC;
input bool NeutralizeExternalCashflows = true;
input int  DailyBaselineMaxCaptureDelaySeconds = 60;
// Default false: safety first.  An operator must consciously opt in.
input bool AllowUnsafeMiddayDailyBaselineBootstrap = false;
```

* **Loss cap scope:** always account equity.  This must be documented prominently.  A symbol/magic-only *equity* loss measure cannot be reconstructed correctly from `ACCOUNT_EQUITY` when positions overlap.
* **Streak date:** a complete lifecycle is attributed to the broker day of its **final closing deal**.  Its profit is the entire lifecycle profit, even if the entry occurred earlier.  This is deliberately different from the account daily-loss calculation.
* **Broker day:** `[00:00:00, next 00:00:00)` using `TimeCurrent()` / trade-server calendar, not local PC time.
* **Cash flow:** when enabled, neutralize only balance/credit/bonus/correction operations declared external by the broker policy (see the implementation hook below).  Ordinary commissions, swaps, tax/dividend/charge adjustments should remain economic account changes unless the broker-specific mapping is reviewed.  Ambiguous types must be logged and left in loss by default, not silently neutralized.

For `DAILY_STREAK_EA_SYMBOL_MAGIC`, determine membership from the **opening** (`DEAL_ENTRY_IN` or `DEAL_ENTRY_INOUT`) deal's symbol/magic, then sum *all* financial deals of that position.  On a netting account another strategy can alter the same position identifier.  Either default streak scope to `DAILY_STREAK_ACCOUNT` on netting accounts, or fail closed for EA-scoped streak accounting until a documented per-position ownership policy exists.  Do not pretend `DEAL_MAGIC` on a final exit alone establishes lifecycle ownership.

## Persistent model and key construction

MQL terminal global variables are local to one terminal, persist across EA restart, and hold one `double`; they are not a cross-terminal database.  Use them only for restart persistence, call `GlobalVariablesFlush()` after a completed write, and state the multi-terminal limitation in the README.

Use a short versioned namespace to remain under the 63-character global-variable name limit.  Account login plus a bounded server fingerprint protects against accidental reuse of a value for a different account.  The fingerprint can be a simple deterministic 31-bit rolling hash of `AccountInfoString(ACCOUNT_SERVER)`, not a security feature.

```mql5
// Example result: D2.12345678.184759321.20260908
string DailyKeyPrefix(const datetime dayStart)
{
   MqlDateTime dt; TimeToStruct(dayStart, dt);
   const int ymd = dt.year * 10000 + dt.mon * 100 + dt.day;
   return StringFormat("D2.%I64u.%d.%08d",
                       AccountInfoInteger(ACCOUNT_LOGIN),
                       ServerFingerprint(AccountInfoString(ACCOUNT_SERVER)), ymd);
}
```

Write four variables, then an initialization marker **last**:

| suffix | value | purpose |
|---|---:|---|
| `.eq` | day-start `ACCOUNT_EQUITY` | baseline before day P/L/cash flows |
| `.bal` | day-start `ACCOUNT_BALANCE` | audit/reconstruction diagnostic |
| `.at` | capture server timestamp | confirms rollover capture timeliness |
| `.ok` | `2.0` | schema/commit marker, written last |

`LoadBaseline` accepts a record only if all fields exist, `.ok == 2.0`, the values are finite/non-negative as applicable, and `at >= dayStart && at < nextDay`.  A partially written record has no `.ok` and is invalid.  Build values first; write `.eq/.bal/.at`, write `.ok` last, check each `GlobalVariableSet` result, and call `GlobalVariablesFlush`.  On failed write set `ready=false`; never continue based only on RAM state.

Suggested state (the actual arrays can be dynamic rather than capped at 256):

```mql5
struct DailyGuardState
{
   datetime dayStart;
   double   baselineEquity;
   double   baselineBalance;
   datetime baselineCapturedAt;
   double   externalCashflow;
   double   dailyLoss;
   int      consecutiveLosses;
   int      winningStreak;
   bool     baselineReady;
   bool     historyHealthy;
   bool     dirty;
};

struct ClosedLifecycle
{
   ulong    positionId;
   datetime closeTime;
   ulong    closeDealTicket; // deterministic tiebreaker
   double   lifecycleNet;
};
```

## Compile-conscious MQL5 implementation flow

### 1. Shared helpers

```mql5
datetime BrokerDayStart(const datetime now)
{
   MqlDateTime t;
   TimeToStruct(now, t);
   t.hour = 0; t.min = 0; t.sec = 0;
   return StructToTime(t);
}

double DealEconomics(const ulong deal)
{
   return HistoryDealGetDouble(deal, DEAL_PROFIT)
        + HistoryDealGetDouble(deal, DEAL_COMMISSION)
        + HistoryDealGetDouble(deal, DEAL_SWAP)
        + HistoryDealGetDouble(deal, DEAL_FEE);
}
```

`HistorySelect` and `HistorySelectByPosition` are not interchangeable: the latter changes the terminal's selected history list.  The code must not rely on a previous `HistoryDealsTotal()` selection after calling it.  Read/copy the required identifiers first, and select afresh for each position.

For cash flows, make a narrow and unit-tested function such as:

```mql5
bool IsNeutralizedExternalCashflow(const ulong deal)
{
   if(!NeutralizeExternalCashflows)
      return false;

   const ENUM_DEAL_TYPE type =
      (ENUM_DEAL_TYPE)HistoryDealGetInteger(deal, DEAL_TYPE);
   return (type == DEAL_TYPE_BALANCE || type == DEAL_TYPE_CREDIT ||
           type == DEAL_TYPE_BONUS   || type == DEAL_TYPE_CORRECTION);
}
```

The exact broker mapping needs an account-history review.  If a broker records client deposits/withdrawals differently, extend this function with a documented `DEAL_REASON` mapping.  Do not place commission-related `DEAL_TYPE_*COMMISSION*`, `DEAL_TYPE_TAX`, or dividends in the neutralized list without an explicit risk-policy decision.

### 2. Establish/load the baseline

Call `dailyLedger.Refresh(TimeCurrent())` during `OnInit`, and at the beginning of `OnTimer` (so a 1-second timer captures midnight even without an M15 candidate).  The method does the following:

1. Compute `dayStart`.
2. If the day differs from in-memory state, clear only RAM derived counters, then try `LoadBaseline(dayStart)`.
3. If a valid persistent baseline exists, retain it exactly.
4. If no baseline exists and this is the first successful observation no more than `DailyBaselineMaxCaptureDelaySeconds` after midnight, capture `ACCOUNT_EQUITY` and `ACCOUNT_BALANCE`, persist it, and continue.
5. Otherwise run **safe bootstrap** below.  If safe bootstrap cannot prove a day-start equity, leave `baselineReady=false`.  It is not acceptable to set the baseline to current equity.

Safe bootstrap is useful after an EA restart/deployment later in the day but is intentionally restrictive:

* `HistorySelect(dayStart, now)` must succeed; otherwise return false / block entry.
* Find every position with a close deal today and every currently open position.  For each, select complete position history and check whether it began before `dayStart`.
* If any lifecycle crossed midnight, its mark-to-market at midnight is unavailable from ordinary deal history.  The initial equity cannot be proved, so block new entry unless an already persisted `.ok` record exists.  This includes a pre-midnight position that closed before the EA started.
* If there are **no** cross-midnight lifecycles, derive opening balance as:

  ```text
  opening_balance = current ACCOUNT_BALANCE
                  - sum(DealEconomics(all non-external day deals))
                  - sum(external cashflow day deals)
  ```

  Since no position existed at the boundary, `opening_balance == opening_equity`.  Validate the number is finite and non-negative, persist it as the baseline, and log `DAILY_BASELINE_SAFE_BOOTSTRAP`.

If `AllowUnsafeMiddayDailyBaselineBootstrap` is ever added for an operational emergency, it must log an ERROR, show the dashboard state as unsafe, and never be the default.  The recommended release does not use it.

A continuously running EA captures the first post-midnight account snapshot.  There is no exact historical tick-equity series in the standard terminal API, so require capture within the configured 60 seconds.  On an after-hours/weekend restart no new entry should be permitted anyway; Monday with an unresolved cross-day position remains safely blocked.  This limitation should be explicit rather than hidden by an invented baseline.

### 3. Refresh all derived account/streak values at the entry decision

At every potential new entry (currently immediately before the check at `AdaptiveSurvivalEA.mq5:980`) call a single method:

```mql5
bool DailyGuardAllowsNewEntry(string &reason)
{
   reason = "";
   if(!Refresh(TimeCurrent()))
   {
      reason = "daily_guard_history_or_baseline_unavailable";
      return false;
   }
   if(dailyLoss >= baselineEquity * (MaxDailyLossPercent / 100.0))
   {
      reason = "daily_loss_limit";
      return false;
   }
   if(consecutiveLosses >= MaxConsecutiveLosses)
   {
      reason = "daily_consecutive_loss_limit";
      return false;
   }
   return true;
}
```

Inside `Refresh`:

1. Require a ready baseline.
2. `HistorySelect(dayStart, now)`; on `false`, set `historyHealthy=false`, log `DAILY_HISTORY_SELECT_FAILED` with `GetLastError()`, and return false.  This is the mandatory fail-closed path.
3. Scan selected **account** deals to sum external cashflow.  Any deal property read failure or unrecognized account adjustment requiring policy classification should conservatively make the guard unhealthy, not silently use zero.
4. Set `dailyLoss = MathMax(0.0, baselineEquity - (AccountInfoDouble(ACCOUNT_EQUITY) - externalCashflow))`.  The unclamped signed value is useful telemetry, but only a loss trips the loss cap.
5. Rebuild `consecutiveLosses` / `winningStreak` from lifecycle completions whose final close is today.  Rebuilding at an M15 decision point is modest work and prevents missed `OnTradeTransaction` events/restarts from changing the answer.

Do not use `daily_floating_pnl = equity - baseline - daily_net_pnl`: it is not separable reliably across a restart or a calendar boundary.  Expose `adjustedEquity`, `dailyLoss`, `externalCashflow`, baseline timestamp, and lifecycle realized P/L as separate dashboard/log telemetry instead.

### 4. Full lifecycle algorithm for the streak

1. From the current-day selected list, collect unique `DEAL_POSITION_ID` values for eligible `DEAL_ENTRY_OUT` and `DEAL_ENTRY_OUT_BY` deals.  Do not impose the old 256-record cap; a capacity/ArrayResize failure is a guard failure.
2. For every identifier, determine whether the position is still live by looping `PositionsTotal()`, using `PositionGetTicket(i)` to select each position, and comparing `POSITION_IDENTIFIER` with the identifier.  If live, it is partial/unclosed: it must contribute **no** streak result.
3. For a non-live position, call `HistorySelectByPosition(positionId)`.  Sum `DealEconomics(deal)` over the position's financial lifecycle deals, including `DEAL_ENTRY_IN`, `DEAL_ENTRY_OUT`, `DEAL_ENTRY_INOUT`, and `DEAL_ENTRY_OUT_BY` (or, more robustly, every deal with that position ID whose type is a trading deal/position charge).  Entry commissions and exit `DEAL_FEE` therefore count.
4. Determine scope membership from the opening deal(s), as described above.  For account scope this is always true.  For EA-symbol-magic scope, if ownership is ambiguous in a netting lifecycle return guard failure rather than selectively omitting cost.
5. Record a `ClosedLifecycle` only after step 2 has established full closure.  Use the last OUT/OUT_BY deal's `DEAL_TIME_MSC` if available; otherwise `DEAL_TIME` plus deal ticket as a stable tiebreaker.  Sort oldest-to-newest.
6. Fold all complete lifecycle outcomes in close order:

   ```mql5
   if(net < -epsilon) { ++consecutiveLosses; winningStreak = 0; }
   else if(net > epsilon) { ++winningStreak; consecutiveLosses = 0; }
   // exact breakeven: policy is explicit; recommended neutral/no reset
   ```

   `epsilon` should be an account-currency amount (e.g. `0.000001`), not `NormalizeDouble` or a point value.  Do not update the streak in `OnTradeTransaction` per deal.

On `TRADE_TRANSACTION_DEAL_ADD`, merely set `dailyLedger.dirty = true`; it is safe to optionally refresh for dashboard telemetry, but failure there must set a sticky unhealthy flag until the entry-time refresh succeeds.  The change also fixes restarts because the answer comes from history, not an in-memory increment.

### 5. EA wiring

* Remove `DailyTradeRecord`, `daily_start_equity`, `daily_net_pnl`, `daily_floating_pnl`, `ReconstructDailyLedger`, `CheckAndResetDailyLedger`, and all per-OUT deal streak arithmetic at lines 692–831 and 1150–1218.
* During `OnInit`, instantiate/initialize the ledger after account/broker environment is available.  A failed first refresh should **not** make `OnInit` fail: management must remain active; the entry gate will block.
* At `OnTimer`, call `dailyLedger.RefreshIfRolloverOrDirty(TimeCurrent())` before/independent of execution reconciliation.  Log state changes once to avoid tick-log flooding.
* At the current entry point replace `IsDailyLossLimitReached()` with:

  ```mql5
  string dailyBlockReason;
  if(!dailyLedger.AllowsNewEntry(TimeCurrent(), MaxDailyLossPercent,
                                 MaxConsecutiveLosses, dailyBlockReason))
  {
     LogWarning("TRADE_BLOCKED_DAILY_GUARD", dailyBlockReason);
     return;
  }
  ```

* On deinitialization do not delete the day record.  Old dated records may be pruned only after a successful write for the current day and with a bounded retention policy; deletion failure cannot affect the current guard.

---

# F03 — fail-closed economic-calendar cache

## Current failure modes

`AggregateState(CLEAR, UNKNOWN)` returns `CLEAR`, hence the API failure cached at lines 93–100 becomes clear on the next cache-hit call.  The code caches a *state* for 3,600 seconds but fetched only `[now-1,800, now+1,800]`; a 08:00 CLEAR result does not contain an 08:45 event and remains falsely clear at 08:30.  Event/country resolution failures have the same aggregation hole; country resolution is currently skipped altogether.

## Replace the state cache with an event cache

Use these compile-safe constants aligned to existing policy windows:

```mql5
#define NEWS_PRELOCK_SECONDS          1800
#define NEWS_SHOCK_SECONDS             900
#define NEWS_RECOVERY_SECONDS         2700
#define NEWS_CACHE_FUTURE_SLACK       1800 // cache remains usable for <=30 min
#define NEWS_FAILURE_RETRY_SECONDS      30

struct CachedNewsEvent
{
   ulong    eventId;
   datetime eventTime;
};
```

The class static state should be:

```mql5
static CachedNewsEvent s_events[];
static datetime s_coverageFrom;
static datetime s_coverageTo;
static datetime s_lastFailure;
static string   s_currencyKey;    // e.g. "EUR|USD", canonicalized
static bool     s_hasValidCache;
```

Remove `s_lastFetchResult`, `s_calendarAvailable`, and the 3,600-second state TTL.  The cache is usable only when its currency key matches and it covers the **entire state-relevant interval**:

```mql5
bool CacheCovers(const datetime now)
{
   return s_hasValidCache &&
          s_coverageFrom <= now - NEWS_RECOVERY_SECONDS &&
          s_coverageTo   >= now + NEWS_PRELOCK_SECONDS;
}
```

On a fetch at `T`, request `[T - 2700, T + 3600]`.  It is sufficient through `T + 1800`, because at that point its right edge still covers the needed `now + 1800`.  The left edge remains sufficient as time advances.  At the next fetch use a new full interval, not a delta.  This is a bounded cache with no 08:45 horizon hole.

## Correct API and aggregation behavior

### Currency resolution and fetching

Resolve both `SYMBOL_CURRENCY_BASE` and `SYMBOL_CURRENCY_PROFIT` after `ResetLastError()` calls.  If either is empty/unreadable, return `NEWS_UNKNOWN` for a required guard.  Canonicalize and deduplicate when base equals profit.

Use the documented currency-filtered MT5 query for each relevant currency:

```mql5
int total = CalendarValueHistory(values, fromTime, toTime, NULL, currency);
```

This avoids receiving an unrelated country/event which cannot be classified for this symbol.  For each returned value, `CalendarEventById(values[i].event_id, event)` must succeed; if it does not, discard the temporary fetch, keep any old data only for diagnostics, set `s_lastFailure=now`, and return false to the caller.  A failed relevant event is **not** CLEAR.  Store only events where `event.importance == CALENDAR_IMPORTANCE_HIGH`, deduplicated by `(event_id, time)`.

If implementation instead uses an unfiltered `CalendarValueHistory`, it must resolve country successfully before it can decide relevance.  A failed country resolution for a value in the required time range must be `NEWS_UNKNOWN`; it may not be “skip but log.”  The filtered-query approach is simpler and less exposed to unrelated API metadata failures.

Fetch into a local temporary dynamic array.  Commit `s_events`, `s_coverageFrom`, `s_coverageTo`, `s_currencyKey`, and `s_hasValidCache=true` only after **every** currency query and every event lookup succeeds.  Never overwrite a valid cache with a partial fetch.  But if the current required coverage is missing and the refresh fails, do not use stale data to permit entry: return UNKNOWN.  A failure retry throttle of 30 seconds may reduce logs/API calls, but while throttled the returned state remains UNKNOWN.

### State derivation

Derive state from the cached timestamp list every invocation; do not cache the result.  Correct aggregation makes UNKNOWN absorbing:

```mql5
static ENUM_NEWS_STATE AggregateState(ENUM_NEWS_STATE current,
                                      ENUM_NEWS_STATE candidate)
{
   if(current == NEWS_UNKNOWN || candidate == NEWS_UNKNOWN) return NEWS_UNKNOWN;
   if(current == NEWS_LOCK    || candidate == NEWS_LOCK)    return NEWS_LOCK;
   if(current == NEWS_SHOCK   || candidate == NEWS_SHOCK)   return NEWS_SHOCK;
   if(current == NEWS_RECOVERY || candidate == NEWS_RECOVERY) return NEWS_RECOVERY;
   return NEWS_CLEAR;
}
```

`EvaluateEventTimes` should use the existing inclusive/exclusive boundary policy consistently:

```mql5
if(diff >= 0 && diff <= NEWS_PRELOCK_SECONDS) return NEWS_LOCK;
if(diff < 0 && diff >= -NEWS_SHOCK_SECONDS)   state = AggregateState(state, NEWS_SHOCK);
if(diff < -NEWS_SHOCK_SECONDS && diff >= -NEWS_RECOVERY_SECONDS)
                                                   state = AggregateState(state, NEWS_RECOVERY);
```

Evaluate explicit configured timestamps and cached calendar timestamps separately, then aggregate them.  If cache fetch/resolution is unknown, the aggregate result remains UNKNOWN even when explicit timestamps happen to show CLEAR/LOCK.  Every non-CLEAR state is blocked by policy, and preserving UNKNOWN makes the operational cause auditable.

At the caller, make `NewsGuardRequired` a real policy switch.  Recommended wiring is:

```mql5
ENUM_NEWS_STATE observedNews = CSessionNewsEngine::EvaluateNews(serverTime, dummyNews, 0, _Symbol);
ENUM_NEWS_STATE gatedNews = NewsGuardRequired ? observedNews : NEWS_CLEAR;
bool allowEntry = CSessionNewsEngine::CheckGating(sessionState, gatedNews,
                                                   requiredQualityScore, gatingBlockReason);
```

Keep `observedNews` in diagnostics.  This avoids the current inconsistency where `NewsGuardRequired=false` still blocks in `CheckGating` on UNKNOWN.  The recommended production default remains `NewsGuardRequired=true`.

---

# Focused regression tests

Add a new `tests/build16/` (or a clearly named `tests/guards/`) rather than disguising these safety tests as Build 14 session-unit tests.  The Python model is a specification aid; source contracts ensure it is actually wired to native source.  Neither replaces MetaEditor compilation.

## Python/reference tests — daily guard

Implement a pure reference model accepting `baseline`, `equity`, `cashflow deals`, `position lifecycles`, and `history_ok`.  Minimum cases:

1. **Restart loss is retained:** persisted 10,000 baseline, current equity 9,750; `daily_loss == 250`, not zero after reconstruct/EA object re-creation.
2. **Rollover establishes a new baseline:** prior-day baseline 10,000/current 10,800; at new-day capture baseline is 10,800; a fall to 10,570 is a 230 loss and exceeds a 2% cap.
3. **No persisted baseline + cross-midnight position:** safe bootstrap reports unavailable and `allows_entry == false`; it never uses current equity.
4. **Safe midday bootstrap:** no cross-day lifecycle, starting balance 10,000, entry commission -2, closed net +100, balance 10,098; reconstructed opening equity remains 10,000.
5. **Deposit/withdrawal neutralization:** baseline 10,000, loss 500 then +1,000 deposit has equity 10,500 and adjusted equity 9,500 => 500 loss; symmetric withdrawal does not create loss.  Test disabling the option preserves raw equity behavior deliberately.
6. **History failure:** `HistorySelect=false` returns a non-empty block reason and `allows_entry=false`; no existing values permit an entry.
7. **Partial exits do not affect streak:** an entry fee -2, partial exit +30, position still live gives no streak result; final exit -40 plus exit fees makes total lifecycle negative and increments the loss streak once.
8. **Entry commission and DEAL_FEE count:** a gross +5 lifecycle with entry commission -4 and exit fee -2 is a loss.
9. **Close ordering:** lifecycle A/B close in timestamp order independent of deal-array order; loss/loss/win produces `consecutive=0, winning=1`; breakeven follows the selected neutral policy.
10. **Overflow/selection failure:** more than the old 256 identifiers is processed or fails closed; never silently truncates.

## Python/reference tests — news

Extend `NEWS_STATE` to include `NEWS_UNKNOWN` and model fetch results as `(events, coverage, success)`.  Minimum cases:

1. First API failure, a second call inside retry throttle, and a later retry failure all return UNKNOWN; UNKNOWN cannot aggregate to CLEAR.
2. Event or relevant currency resolution failure returns UNKNOWN and blocks when required.
3. Cache horizon counterexample: fetch CLEAR at 08:00 with an event at 08:45.  At 08:30 the cache lacks required `now+1800` coverage, refetches, and returns LOCK—not CLEAR.
4. Cached data time progression with no refetch required: event transitions CLEAR → LOCK → SHOCK → RECOVERY → CLEAR at the exact 30m/0/15m/45m boundaries.
5. Base equals profit invokes one query and does not double-count.
6. Cache key changes (symbol/currency pair) invalidates cached results; stale EUR/USD data cannot authorize GBP/USD.
7. A partial two-currency fetch failure leaves no partially committed cache and returns UNKNOWN.
8. `NewsGuardRequired=false` permits based on session despite observed UNKNOWN; `true` blocks.

## Native-source contract tests

Use `Path(...).read_text()` checks sparingly but make them pin the repaired architecture.  Examples:

```python
assert "DEAL_FEE" in DAILY_LEDGER
assert "HistorySelectByPosition" in DAILY_LEDGER
assert "daily_start_equity = AccountInfoDouble" not in EA
assert "daily_net_pnl + floatingPnl" not in EA
assert re.search(r"if\s*\(!HistorySelect\([^)]*\)\)\s*return false", DAILY_LEDGER)
assert "daily_guard_history_or_baseline_unavailable" in EA

assert "CachedNewsEvent" in NEWS
assert "CalendarValueHistory(values, fromTime, toTime, NULL, currency)" in NEWS
assert "s_lastFetchResult" not in NEWS
assert "candidate == NEWS_UNKNOWN" in NEWS
assert "s_coverageTo" in NEWS and "NEWS_CACHE_FUTURE_SLACK" in NEWS
```

Also add a source test that the entry path calls `DailyGuardAllowsNewEntry` before candidate dispatch and maps `NewsGuardRequired ? observedNews : NEWS_CLEAR` (or the equivalent explicit policy) before `CheckGating`.  Source tests should not claim native API execution.

---

# Native demo / Strategy Tester evidence plan

MetaEditor and a demo account are required; none were available for this design.  Compile the patched EA with `#property strict`, record MetaEditor build/version, source SHA-256 and EX5 SHA-256, then retain journal excerpts and a CSV/dashboard trace with server time, day key, baseline, adjusted equity, cashflow, daily loss, streak, news state, cache coverage, and block reason.

1. **Restart after loss:** On demo/tester, create a known realized/floating account loss, restart/re-attach the EA during the same broker day, and verify the same persisted day key/baseline and an entry block.  Do not accept a fresh zero-loss baseline.
2. **Rollover with an open position:** Have the EA running through broker midnight with a position whose price is changing; verify the new record captures promptly, survives restart, and next-day loss uses the recorded baseline.  Repeat restart after midnight without a persisted baseline: the EA must block entry if a lifecycle crossed midnight.
3. **Cash flow:** On a demo account perform a deposit and, if permitted, withdrawal/correction simulation.  Verify exact broker deal type/reason, the configured classification log, and that adjusted equity preserves prior loss.  If a broker uses a different type, leave it non-neutralized until a reviewed mapping/test exists.
4. **Partial/full close:** Open a position with an entry commission; partially close it, restart the EA, then fully close it with a fee.  Verify no streak movement after partial and exactly one lifecycle outcome including all four monetary components at full close.
5. **History outage/delay:** Disconnect terminal or use a harness to force `HistorySelect` failure before an entry.  Management continues, but journal records `DAILY_HISTORY_SELECT_FAILED` and no `OrderSend` entry follows.
6. **Calendar unavailable:** Disable/disconnect economic-calendar availability or use a test seam around the calendar provider.  Verify UNKNOWN persists through repeated evaluations/cache retry and no entry is sent with `NewsGuardRequired=true`.
7. **Calendar horizon:** Arrange/highlight a high-impact event 45 minutes ahead.  Evaluate at T-45 then T-30 without restart.  The trace must show a coverage-triggered refresh and LOCK at T-30.
8. **Calendar transitions/resolution failure:** Test event-time state boundaries and force `CalendarEventById`/currency lookup failure via an injectable provider in a native probe.  Required guard produces UNKNOWN/block.  If retaining unfiltered queries, also force country lookup failure.

A useful test seam is an `INewsCalendarProvider`-style thin wrapper (production implementation calls `CalendarValueHistory`/`CalendarEventById`; native probe fake returns controlled results).  It permits deterministic failures and horizons without relying on the live public calendar, while keeping production code’s MQL signatures compile-checked.

## Acceptance criteria

* A loss before restart or after rollover never becomes zero solely because the EA was restarted or the date changed.
* Without provable baseline/history, only new entry is blocked; no silently invented baseline is used.
* Daily account loss includes floating changes and all account loss but neutralizes only reviewed external cash flow.
* A partial close cannot count as a completed trade; full lifecycle streak includes entry/exit commission, swap, and fee.
* `HistorySelect` / required history failures block new entry.
* Calendar UNKNOWN is stable/fail-closed, cache contents cover the whole evaluated horizon, and cached state is recalculated as time advances.
* Native build and the above demo/probe evidence are attached before marking F02/F03 closed.
