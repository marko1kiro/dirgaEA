# Execution/risk/position remediation design (F01, F04, F05, F07, F10, F12)

**Source reviewed:** extracted audit snapshot at `/tmp/dirgaEA-remediation` (read-only source).  This is a design, not a change to the authoritative repository.  The patch should replace the current split owner/lease lock, rather than attempting to repair it with another unguarded `GlobalVariableSet`.

## 1. Scope and safety invariants

1. A single terminal/account/symbol/magic namespace has at most one live **submission owner**.  This is a terminal-global lock, not an inter-terminal distributed lock.
2. A submission that might have reached the trade server blocks every new entry—even after EA restart—until positive terminal evidence establishes a terminal outcome or an explicit operator recovery clears it.
3. The `MqlTradeRequest` submitted to `OrderSend` is the *same final normalized object* used for risk sizing, final stop validation, and `OrderCheck`.  It is not reconstructed or rounded at a later step.
4. Initial stop metadata belongs to the stable `POSITION_IDENTIFIER`, is created from the accepted entry plan, and is removed only once no matching live position remains.  It must never be recreated from a trailed stop.
5. An EA-owned live position with `SL == 0` is an active protection incident: attempt a broker-side protective stop; if that cannot be done safely, attempt fail-closed close/retry and keep entries inhibited.

The examples below assume the EA continues to intentionally support only `ACCOUNT_MARGIN_MODE_RETAIL_HEDGING`; do not silently rely on hedging ticket semantics on netting accounts.

---

## 2. F01: replace lock and lease with one atomic versioned terminal-global variable

### Why the present protocol is unsafe

`AcquireOrderLock()` currently has a `GlobalVariableCheck()` / `GlobalVariableSet(lock, 0)` bootstrap (ExecutionBridge.mqh:312–318).  A second instance can perform that set after the first has CAS-acquired the owner value.  In addition, owner and lease timestamp are separate variables: an owner may renew the lease between another instance reading it and CAS-taking the owner, so the CAS does not attest to the lease version that was judged stale.  `AcquireOrderLock()` also creates a new token before its purported reentrant check, so that check can never reliably identify the holder.

### Namespace and state encoding

Delete `LOCK_UNLOCKED`, `m_ownerToken`, `m_leaseVarName`, `m_instanceSalt`, `s_lockSeq`, `MakeLeaseKey()`, and `MakeOwnerToken()`.  Add one permanent terminal global value:

```mql5
#define DIRGA_LOCK_PREFIX "DirgaEA.v2.lock"
#define DIRGA_LOCK_MAX_GENERATION 9007199254740991.0 // 2^53-1, exact in double

string LockKey();
// Example: DirgaEA.v2.lock.<ACCOUNT_LOGIN>.<symbol>.<magic>
// Keep it below the terminal global-variable name limit; use a stable short
// symbol namespace if broker names can make it too long.

double m_lockGeneration;   // positive, exact integer capability held locally
bool   m_lockHeld;
uint   m_lockLeaseSeconds; // configured e.g. 30; timer must be shorter
```

The one global value is a signed, exact-integer **generation**:

* absent / `0`: only bootstrap state;
* `+g`: held; its *last modification time* is its lease heartbeat;
* `-g`: released; it is immediately acquirable;
* a locally held capability is the exact positive `g`, not a random floating-point token.

Use generations below `2^53`, where all integer doubles and equality comparisons are exact.  Never reset the variable to zero.  If generation exhaustion is ever reached, fail closed and require an intentional namespace migration; do not wrap and introduce ABA.

`GlobalVariableSetOnCondition(name, value, check_value)` is the only mutating primitive for this lock.  Its documented terminal-global-variable semantics atomically test and replace a value; bootstrap must use that primitive with `check_value == 0`, which atomically creates/acquires the missing zero state in supported MQL5 terminals.  **Do not use `GlobalVariableCheck` followed by `GlobalVariableSet` to initialize it.** Add a native probe to the CI/manual MetaEditor suite confirming that two fresh charts both attempting this operation result in one success on the target terminal build.  If a terminal build did not provide atomic create-on-condition semantics, a correct cross-instance lock cannot be built from check/set alone and that build must be rejected rather than downgraded.

`GlobalVariableTime(lockKey)` is the lease timestamp.  It is tied to the same global value and is refreshed by every successful CAS that changes that value.  Confirm in the native probe that it is the **last modification time** (not an access/read time) and use `TimeLocal()` for both lease-age comparison and the same-terminal terminal-global timestamp domain.  A terminal global is local to a client terminal; locking EAs in different terminals/VPS instances needs a broker/account-level idempotency design and is out of scope for this API.

### Concrete CExecutionBridge interface and algorithm

```mql5
private:
   string LockKey();
   bool ReadLock(double &state, datetime &changedAt);
   bool CasLock(const double expected, const double replacement);
   bool IsUnresolvedSubmission();
   bool LoadPendingJournal();
   bool SavePendingJournalWriting(const FinalMarketOrder &plan);
   bool MarkPendingJournalSent(const MqlTradeResult &result);
   void ClearPendingJournal();

public:
   bool AcquireOrderLock(const uint leaseSeconds = 30);
   bool RenewOrderLock();
   bool ReleaseOrderLock();
   bool RecoverPendingSubmission(); // invoked on init before entries
   bool EntrySubmissionBlocked();
```

The methods use a bounded retry loop (for example, three reads/CAS attempts; never sleep inside `OnTick`).  Pseudocode deliberately uses values that differ on every successful holder action:

```mql5
bool CExecutionBridge::AcquireOrderLock(const uint leaseSeconds)
{
   if(m_lockHeld) return RenewOrderLock();        // genuine same-instance reentry
   m_lockLeaseSeconds = MathMax(leaseSeconds, 2); // configured timer < lease
   const string key = LockKey();

   for(int attempt=0; attempt<3; ++attempt)
   {
      double state = 0.0;
      datetime changed = 0;
      const bool exists = GlobalVariableCheck(key);
      if(exists)
      {
         ResetLastError();
         state = GlobalVariableGet(key);
         if(GetLastError()!=0 || !MathIsValidNumber(state) ||
            MathFloor(MathAbs(state)) != MathAbs(state))
            return false;                         // corrupt state => fail closed
         changed = GlobalVariableTime(key);
      }

      // absent/zero or a released generation may be acquired immediately.
      const bool released = (!exists || state <= 0.0);
      const bool expired  = (state > 0.0 && changed > 0 &&
                             (TimeLocal() - changed) >= (int)m_lockLeaseSeconds);
      if(!released && !expired) return false;

      const double oldG = MathAbs(state);
      if(oldG >= DIRGA_LOCK_MAX_GENERATION) return false;
      const double mine = oldG + 1.0;
      // On absent variable, this is the documented atomic create-if-zero CAS.
      if(GlobalVariableSetOnCondition(key, mine, state))
      {
         m_lockGeneration = mine;
         m_lockHeld = true;
         if(expired)
            LogWarning("LOCK_STALE_TAKEOVER", StringFormat("old=%G new=%G",state,mine));
         return true;
      }
   }
   return false;
}

bool CExecutionBridge::RenewOrderLock()
{
   if(!m_lockHeld || m_lockGeneration <= 0.0) return false;
   if(m_lockGeneration >= DIRGA_LOCK_MAX_GENERATION) { m_lockHeld=false; return false; }
   const double next = m_lockGeneration + 1.0;
   if(!GlobalVariableSetOnCondition(LockKey(), next, m_lockGeneration))
   { m_lockHeld=false; return false; }
   m_lockGeneration=next;                         // CAS updates lock modification time
   return true;
}

bool CExecutionBridge::ReleaseOrderLock()
{
   if(!m_lockHeld || m_lockGeneration <= 0.0) return false;
   if(m_lockGeneration >= DIRGA_LOCK_MAX_GENERATION) { m_lockHeld=false; return false; }
   const double released = -(m_lockGeneration + 1.0);
   const bool ok=GlobalVariableSetOnCondition(LockKey(), released, m_lockGeneration);
   m_lockHeld=false;
   return ok;
}
```

The stale-takeover race is safe: a contender reads `+g` and its modification time; a valid owner heartbeat CASes `+g -> +(g+1)`.  The contender's `CAS(+g -> +new)` then fails.  Unlike the current independent lease key, it cannot seize after a renewal it did not observe.  A stale owner likewise cannot renew/release after a takeover because its expected generation no longer matches.

Call `RenewOrderLock()` on every `OnTimer` while held, before reconciliation, and immediately before `OrderSend`.  A renewal failure changes the lifecycle to an unresolved/fail-closed state and prevents send.  Choose timer `<= lease/3`; reject configuration otherwise.  Do **not** have the destructor or `OnDeinit` release a lock for an unresolved submission—stopping heartbeat lets the lease expire, while the persistent journal below keeps a restarted EA blocked.  Releasing is permissible only for a demonstrated terminal lifecycle and cleared journal.

### Persistent pending-submission journal (F01/F05 restart boundary)

A lock alone cannot protect after a process/EA restart: its lease necessarily expires while an ambiguous request may still be in flight.  Add terminal-global keys under the same account/symbol/magic namespace, e.g. `DirgaEA.v2.pending.<ns>.state`, `.submit_time`, `.order`, `.deal`, `.intent_id`, `.sl`, `.tp`, `.volume`, `.side`.  Values are doubles; intent ID is also an exact-integer generation/sequence.  The static string `comment` should contain a short `D2:<intent_id>` correlation token, subject to the broker comment-length/rewriting caveat below.

There is no multi-key transaction in terminal globals.  Therefore write in fail-closed order while holding the lock:

1. CAS/set `state=WRITING` first;
2. write plan details including final SL, side, submit time and `intent_id`;
3. set `state=UNRESOLVED` before `OrderSend`;
4. after `OrderSend`, write returned order/deal ticket but leave state unresolved for `PLACED`, partial, timeout, unknown return, or transport uncertainty;
5. only after reconciliation has positive terminal evidence of filled/rejected/cancelled/expired does the holder set `state=CLEAR` and then delete auxiliary keys.

Any non-clear, missing, corrupt, or partially written journal is `EntrySubmissionBlocked()==true`.  This errs toward an operator-visible entry block, never toward a duplicate request.  `OnInit` loads it before enabling entries; it may acquire/reclaim the lock only to reconcile it.  It must not treat “ticket not currently visible” or a failed/unavailable `HistorySelect` as rejection.  Unknown ticket recovery searches the selected interval for matching symbol, magic, side, volume tolerance and (where preserved) the correlation comment, logs an ambiguity if not unique, and stays blocked until an operator recovery procedure decides it.

---

## 3. F05: complete lifecycle and timeout handling

### State changes

Retain `EXEC_LIFECYCLE_TIMEOUT_RECONCILE`, but make it a nonterminal member of the reconciliation set.  Add `EXEC_LIFECYCLE_RECOVERY_BLOCKED` for corrupt/missing journal or ambiguous restart recovery.  Do not let generic `SetLifecycle` bypass journal operations; make it private or remove it.

```mql5
bool IsSubmissionUnresolved(const ENUM_EXECUTION_LIFECYCLE s)
{
   return s==EXEC_LIFECYCLE_ORDER_PENDING || s==EXEC_LIFECYCLE_PARTIAL_FILL ||
          s==EXEC_LIFECYCLE_TIMEOUT_RECONCILE || s==EXEC_LIFECYCLE_RECOVERY_BLOCKED;
}
```

At the start of *every* entry path (before candidate dispatch and again after lock acquisition), reject if in this set or if the journal is non-clear.  `ExecuteIntent` must do the same.  Do not rely only on `CountActiveOrdersAndPositions`: an order may not yet appear locally while a server outcome remains ambiguous.

Change `ReconcilePending()` to process `ORDER_PENDING`, `PARTIAL_FILL`, `TIMEOUT_RECONCILE`, and `RECOVERY_BLOCKED` (the last can only move out with definitive evidence).  It must:

* select current order by recorded ticket, then select/order history after a checked `HistorySelect(submitTime - recoveryMargin, TimeCurrent())`;
* distinguish `ORDER_STATE_FILLED`, `ORDER_STATE_PARTIAL` and each documented terminal cancellation/rejection state; keep partial unresolved if an order/remaining exposure can still change;
* inspect relevant deals/positions by saved identity where necessary, because market execution can produce a deal without a useful active-order ticket;
* on `now - submit > PendingTimeoutSeconds`, log and transition to `TIMEOUT_RECONCILE`, **but keep heartbeating lock and journal**;
* clear journal/release lock only after a definitive terminal result has been recorded.  A history API error, no result, `TRADE_RETCODE_TIMEOUT`, or a disappeared uncorrelated ticket remains unresolved.

`OnTimer` must call `RenewOrderLock()` then `ReconcilePending()` while unresolved.  `OnTradeTransaction` should update recorded tickets and call reconciliation, but must not assume transaction arrival is ordered or fully complete; the MQL5 transaction queue can contain multiple transaction types for one request.  Dispatching no new market request during all ambiguity is the required behavior.

---

## 4. F07: construct one final request, then size/check/send it unchanged

### Types and signatures

Add to `Types.mqh` after the execution types:

```mql5
struct FinalMarketOrder
{
   bool                 valid;
   ENUM_TRADE_DIRECTION direction;
   ulong                intentId;
   MqlTradeRequest      request;       // sole send/check object
   RiskRequest          riskRequest;   // exact request price/SL/side
   RiskResult           risk;
   string               rejectReason;
};
```

`MqlTradeRequest` is a built-in MQL5 struct and can be an aggregate member.  Always `ZeroMemory(plan)` before assigning it.  Add `direction` to `OrderIntent` if that intermediate type remains; preferably retire market `OrderIntent` in favor of `FinalMarketOrder`, retaining `OrderIntent` only for non-market/management intents.  No function should infer a modifying position's direction from generic `ORDER_INTENT_MODIFY_SL`.

Replace these APIs:

```mql5
// Remove PrepareMarketOrder(cand, risk, outIntent) for the dispatch path.
bool BuildFinalMarketOrder(const TradeCandidate &cand,
                           const BrokerEnvironment &env,
                           const ulong deviationPoints,
                           FinalMarketOrder &outPlan);

bool CExecutionSafetyGuard::ValidateFinalOrder(const FinalMarketOrder &plan,
                                               const BrokerEnvironment &env,
                                               ExecutionSafetyResult &outResult);

bool CExecutionBridge::SendFinalMarketOrder(FinalMarketOrder &plan,
                                            MqlTradeResult &outResult);
```

### Required pipeline

After acquiring the lock, rechecking no exposure/unresolved journal, and fetching one final quote:

1. Derive direction from candidate; set raw entry `ask` for BUY / `bid` for SELL.
2. Normalize entry once with tick-grid nearest normalization.  Normalize SL directionally: BUY uses `floor(sl/tickSize)`, SELL uses `ceil(sl/tickSize)`.  Normalize TP once using an explicitly documented target policy (nearest is acceptable only if post-normalization ordering is validated; directional target rounding is preferable).
3. Validate final geometry (`BUY: SL < price < TP if TP`, `SELL: TP < price < SL`), finite positive values, and final SL stops/freeze distance with the final quote.  An entry with no SL is rejected; recovery is a separate position-management path.
4. Populate `RiskRequest` from **`plan.request.type`, `plan.request.symbol`, `plan.request.price`, and `plan.request.sl`**.  Run `CalculateBasicRisk`; only then place `risk.normalizedVolume` into `plan.request.volume`.  Do not use candidate price/SL for this calculation.
5. Fill every other request field once: `action=TRADE_ACTION_DEAL`, `magic=MagicNumber`, `symbol`, `type`, `price`, `sl`, `tp`, `volume`, `deviation`, `type_filling`, and the intent correlation comment.  `type_filling` must be selected from `SYMBOL_FILLING_MODE`; do not assume RETURN is allowed.  Ensure the symbol supports the requested direction/trade mode.
6. `ValidateFinalOrder()` calculates safety spread from historical samples (section 6), compares `plan.request.price` with this quote, and calls `OrderCheck(plan.request, checkResult)`.  It performs **no** rounding or request reconstruction.
7. Write journal UNRESOLVED, renew lock, call `OrderSend(plan.request, result)`, then journal the returned tickets/result.  No `CTrade::Buy/Sell` call occurs in this path.

This removes the present three-way inconsistency: `CalculateBasicRisk` sees the raw candidate SL, `ExecutionSafetyGuard::ValidateOrder` sends a nearest-rounded SL in its temporary request, and `ExecuteIntent` sends a directionally rounded SL via `CTrade`.

`OrderCheck` tests the request but does not reserve the price or guarantee the server execution result.  `OrderSend()==true` means the terminal accepted the request for processing, not that it was filled; inspect documented trade retcodes and reconciliation.  Likewise, a broker can fill a market order at a different price (and execution modes differ in how `deviation` is applied).  To make the risk *bound* conservative, size from the adverse bounded entry: BUY `ask + deviation*point`, SELL `bid - deviation*point`, normalized consistently, if the broker mode honors deviation; otherwise document that the hard cap is a requested-price cap and add post-fill excess-risk detection/mitigation.  This caveat is separate from, and does not excuse, sending different values than were sized/checked.

`CTrade` currently hides/rebuilds the eventual `MqlTradeRequest`; raw `OrderSend` is the compile-conscious way to ensure byte-for-field logical identity.  It also makes `m_trade.ResultRetcode()` inappropriate in the new market path; use `MqlTradeResult.retcode`.

---

## 5. F04: make SELL/BUY modification validation explicit

Replace:

```mql5
bool ValidateStopFreeze(const OrderIntent &intent, double bid, double ask);
```

with:

```mql5
bool ValidateStopFreeze(const ENUM_TRADE_DIRECTION direction,
                        const double stopLoss,
                        const double takeProfit,
                        const double bid,
                        const double ask,
                        const bool isModification,
                        string &outReason);
```

Reject `TRADE_DIR_NONE`, nonfinite quote/level values, and zero SL in normal entry or protective-update paths.  Compute `minDistance = MathMax(SYMBOL_TRADE_STOPS_LEVEL, SYMBOL_TRADE_FREEZE_LEVEL) * SYMBOL_POINT` (the terminal/broker remains authoritative via `OrderCheck`/retcode).  Check final normalized SL against **Bid for BUY** and **Ask for SELL**:

```mql5
BUY : stopLoss <= bid - minDistance
SELL: stopLoss >= ask + minDistance
```

Validate TP on its correct side too when nonzero.  `SYMBOL_TRADE_STOPS_LEVEL` and `SYMBOL_TRADE_FREEZE_LEVEL` are expressed in points, not tick-size units; tick-grid normalization and distance validation are both required.  Brokers may apply freeze rules more specifically to modification than to initial placement, so a successful local rule is only preflight—do not hide the trade-server retcode.

Extend `PositionManageIntent`:

```mql5
struct PositionManageIntent
{
   ulong ticket;
   ENUM_TRADE_DIRECTION direction;
   ENUM_POSITION_MANAGE_ACTION action;
   double newStopLoss;
   double newTakeProfit;
   string reason;
};
```

`CPositionManager::Evaluate` assigns `outIntent.direction=dir`.  In `ExecutePositionManage`, first call `PositionSelectByTicket(intent.ticket)` and verify symbol/magic/type; do not read `PositionGetInteger(POSITION_TYPE)` from whichever position was selected by a prior enumeration.  Cross-check the selected position type against `intent.direction` and fail closed if different.

For an SL/TP modification, normalize once, validate with `intent.direction`, build a raw `MqlTradeRequest` with `action=TRADE_ACTION_SLTP`, `position=intent.ticket`, `symbol=m_symbol`, `sl`, and `tp`, optionally preflight with `OrderCheck`, and `OrderSend` that request.  Setting `position` is essential for hedging accounts, where symbol-only modification is ambiguous.  Do not use a generic MODIFY action to choose the BUY branch.

---

## 6. F10: historical-only spread baseline and one sampling cadence

`CExecutionSafetyGuard` already has an array ring, but the caller appends the final current spread at AdaptiveSurvivalEA.mq5:1051 **before** `ValidateOrder`, contaminating the baseline; it also samples only when a candidate makes it past lock acquisition.

Keep `AddSpreadSample(double)` private or rename it `AppendHistoricalSample`.  Expose only:

```mql5
bool ValidateFinalOrder(const FinalMarketOrder &plan,
                        const BrokerEnvironment &env,
                        ExecutionSafetyResult &outResult);
void FinalizeOnTickSample(const BrokerEnvironment &env);
```

`ValidateFinalOrder` takes its median before `FinalizeOnTickSample` and never mutates samples.  Refactor `OnTick` so it has one epilogue:

```mql5
void OnTick()
{
   if(!EA_READY) return;
   RefreshEnvironmentStatus(broker_environment);
   // All candidate/management work is in helpers; helpers may return to OnTick,
   // not return from OnTick.
   ProcessTick();
   b15_safety_guard.FinalizeOnTickSample(broker_environment); // one call, last
}
```

`FinalizeOnTickSample` appends `(ask-bid)/point` only when the refreshed/final quote is finite, `ask>=bid`, and `point>0`; it never runs from `OnTimer`.  If a final quote was fetched for dispatch, sample that same final quote.  In MQL5, `OnTick` events are serialized/coalesced; record `tick.time_msc` only for diagnostic duplicate detection, not to skip distinct events merely because a broker emits identical millisecond timestamps.  Refactor the M15 early returns into a `TryDispatchEntry()` helper so the sampling epilogue runs after candidates, rejected entries, no-signal ticks, and errors alike.  Warm-up behavior must be specified: before five historical samples, enforce absolute ceiling but do not claim a ratio baseline; at five and above use the historical median strictly before current append.

---

## 7. F12: initial-SL lifecycle and SL=0 recovery

### Stable metadata identity and persistence

Add a small `CInitialStopStore` (or private EA helpers) whose namespace includes `ACCOUNT_LOGIN`, symbol, magic, and `POSITION_IDENTIFIER`, e.g. `DirgaEA.v2.isl.<login>.<symbol>.<magic>.<id>`.  Ticket is not acceptable as the primary key: `POSITION_TICKET` may change with service operations, whereas `POSITION_IDENTIFIER` remains the position lifecycle identifier.

Store at least `initialSl` and an `origin`/schema marker using separate globals.  Writes use a `WRITING` marker first and a `VALID` marker last; a malformed marker is not treated as valid metadata.  Normal flow is:

* before send, the pending journal carries the plan's final `request.sl`;
* when an IN deal/fill is correlated, get `DEAL_POSITION_ID` and persist that planned normalized SL under that identifier;
* on restart, `RecoverInitialStopMetadata()` iterates filtered live positions, reads `POSITION_IDENTIFIER`, and restores missing metadata only from a valid correlated pending journal.  It must **not** store `POSITION_SL` as the “initial” SL, because it may already have been trailed.

For a preexisting EA position whose original SL cannot be proven, mark `initial SL unknown`, inhibit BE/1R trailing (rather than inventing a new 1R), and log an operator-visible recovery condition.  It can still receive the SL=0 protection policy below.

In `OnTradeTransaction`, do not delete initial metadata merely because an `OUT`/`OUT_BY` deal arrived.  After that event, enumerate live positions filtering symbol/magic and compare `POSITION_IDENTIFIER` with `DEAL_POSITION_ID`.  Delete only when there is no live match.  This preserves metadata through partial closes and ticket changes, and removes it only after confirmed full closure.  Include an OnInit garbage collector for old metadata whose identifiers are no longer live and are not referenced by an unresolved journal; avoid deleting indiscriminately if history is unavailable.

### Explicit broker protection recovery

Refactor `ManageOpenPositions()` to process protection before 1R evaluation and to avoid the current early return when ATR copy fails.  Add configuration such as:

```mql5
input double RecoveryStopATRMultiple = 2.0;
input bool CloseIfRecoveryStopCannotBeSet = true; // default true
```

For each filtered live position:

1. select by ticket; read its stable `POSITION_IDENTIFIER`, volume, current SL/TP and direction;
2. if `SL > 0`, load only verified initial metadata and run normal manager logic;
3. if `SL == 0`, set an `unprotectedPositionPresent` gate that blocks all new entries.  With a valid closed-bar ATR and fresh quote, calculate a recovery SL from current protective side (`BUY: bid - mult*ATR`; `SELL: ask + mult*ATR`), directionally normalize, then run the explicit F04 validation and raw `TRADE_ACTION_SLTP` request;
4. verify result retcode and then reselect the position to confirm it has a nonzero SL.  Only then mark recovery success.  Do not record this recovery SL as historical initial risk unless policy explicitly defines a new recovery risk baseline;
5. if ATR/quote is unavailable, level is invalid/frozen, modification fails, or confirmation fails, issue raw `TRADE_ACTION_DEAL` close (or retain/retry close if server rejects) with `reason="unprotected_position_fail_closed"`.  Maintain the entry block until the position is confirmed gone or protected.

This is not a promise that a broker will accept a stop during a gap/freeze.  It is an explicit, auditable protection/close/retry policy; the current code merely saves an ATR-derived number internally and leaves the broker position unprotected.

---

## 8. Wiring changes in AdaptiveSurvivalEA.mq5

1. In `OnInit`, configure lock namespace after symbol/magic, call `RecoverPendingSubmission()` and `RecoverInitialStopMetadata()` before setting `EA_READY=true`; an unresolved journal or unprotected position leaves management enabled but entry disabled.
2. In `OnTimer`, if `IsLockHeld()` renew before reconciliation; reconcile all unresolved states; release only after journal terminal clear.  Timer failure cannot clear pending state.
3. Move the long new-entry M15 body into `TryDispatchEntry()`.  Its checks are, in order: entry enabled/no protection incident; session/news/daily gate; candidate quality; no unresolved journal; acquire; renew/recheck no active exposure/no journal; fetch final quote; build `FinalMarketOrder`; safety/`OrderCheck`; journal; renew; raw `OrderSend`; reconciliation/release only on terminal.  Every failed path releases only a clean, non-pending lock.
4. Delete the current `AddSpreadSample()` at 1047–1052 and the same-snapshot “drift” comparison at 1079–1088.  The latter is necessarily zero because both operands derive from `broker_environment.tick`; it is not a live recheck.
5. Route all management modifications through the selected-position, explicit-direction F04 function.  On a direct broker fill, OnTradeTransaction must establish initial metadata from the journal before any manager can trail it.

---

## 9. Regression tests and native contract probes

### Model/reference tests to add or replace

* **F01 bootstrap interleaving:** two actors read absent state then CAS `0 -> +1`; exactly one succeeds; loser cannot overwrite it.  Test `+g` heartbeat before stale contender CAS, stale takeover winner uniqueness, stale former owner renewal/release failure, released-state reacquisition, genuine same-instance reentry, malformed/noninteger state fail-closed, and generation exhaustion fail-closed.
* **F01/F05 restart:** journal state `WRITING`, unresolved with ticket 0, `PLACED`, partial, timeout, missing history, late fill, rejected/cancelled.  Assert no second `OrderSend` before positive terminal reconciliation; a timeout continues reconciliation and heartbeat rather than becoming entry-permissive.
* **F07 grid/risk identity:** tick size different from point; BUY floor and SELL ceil SL; a raw SL whose directional normalization expands risk; risk near hard cap; min-volume exception; target/wrong-side rejection.  Assert equality of every relevant field of the sized `RiskRequest`, `OrderCheck` request, and sent request—price, SL, TP, volume, type, symbol, deviation and filling policy.  Add a test for adverse-fill caveat/conservative sizing policy.
* **F04:** BUY and SELL each pass/fail exactly at stops/freeze boundary; SELL trailing SL above Ask is accepted while below/too-near SL is rejected; selected ticket’s direction is used even when a different position was last enumerated; raw SLTP request contains `position` ticket.
* **F10:** historical `[5,5,5,30,30]`, current `30` must calculate median `5` and reject ratio `6` before append.  Next tick sees the appended history.  Test five-sample warm-up, absolute ceiling, one append for every valid `OnTick` regardless of candidate, and no timer append.
* **F12:** partial OUT retains key; final OUT deletes key; ticket differs from identifier; simulated rollover/new ticket reloads original SL; restart after a trailing SL does not rewrite it as initial; correlated journal creates initial key on fill; missing metadata inhibits 1R; `SL=0` produces a broker SLTP recovery request, then confirmation; failed/ATR-unavailable recovery attempts close and keeps entries blocked.

### Native MQL probes (must be compiled/run before asserting native coverage)

1. Two EA/chart instances or a dedicated script synchronize with terminal globals and attempt `GlobalVariableSetOnCondition(absentKey, 1, 0)` simultaneously; record successes and final value.  Also test `GlobalVariableTime` modification behavior and stale/heartbeat CAS race.
2. A script sends no live trades but builds and prints `MqlTradeRequest`/`OrderCheck` fields for a symbol where tick size differs from point; compile catches field/signature errors.
3. Strategy Tester/demo-only harness injects delayed transaction/history ordering, partial close and changed ticket/identifier behavior, then inspects actual `TRADE_ACTION_SLTP` result retcodes.

### Existing-test conflicts to resolve deliberately

* `tests/build10/reference_execution.py` and `test_execution_bridge.py` model only `prepare_market_order(candidate, already-sized-risk)`.  Replacing that path with `BuildFinalMarketOrder(candidate, quote, deviation)` changes its API and expected reference semantics.  Update/delete the obsolete model rather than preserving it as evidence for final-request safety.
* `tests/build15/test_execution_safety.py::test_spread_spike_veto` appends the current 25-point spread to the reference profiler before using its median.  It happens to pass because nine prior 10s retain median 10, but it contradicts the required historical-only contract.  Change it to validate-before-append and add the `[5,5,5,30,30]` counterexample; update `reference_execution_safety.py` to a stateful guard with finalization.
* `tests/build08/reference_position_manager.py` treats an invalid/UNCERTAIN H1 regime as an immediate close, while current native `PositionManager.mqh` only closes valid opposing trend.  This is pre-existing parity drift, outside the six findings, but any altered position-manager test run will expose it.  Decide/document the desired regime-exit contract before claiming build08 parity.
* Existing Python tests do not exercise native terminal globals, `OrderSend`/`OrderCheck`, account hedging semantics, global-variable persistence, or transaction queue ordering.  Passing them cannot validate the MQL API claims above.

## Acceptance evidence

A patch is ready for review only after the updated Python models/contracts pass, source checks assert the new single-CAS lock/raw-request paths, and a real MetaEditor compile plus the named native probes provide logs/version/hash.  This design does not claim those native steps have been run.
