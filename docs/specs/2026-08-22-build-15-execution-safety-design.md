# BUILD 15 — Full Execution Safety & Broker OrderCheck Design Spec

**Status:** DESIGN (Approved by user).
**Scope:** Hard pre-execution safety layer: dynamic rolling median spread profiler, price slippage deviation guard, native MT5 `OrderCheck` validation, execution lock, and transaction lifecycle synchronization.
**Reference:** Master Plan v1.0 Section 29, 31, and BUILD 15.

---

## 1. Safety Invariants & Execution Pipeline

1. **Dynamic Spread Profiler:**
   - Maintains a rolling buffer of the last 50 spread samples.
   - Calculates `medianSpread`.
   - **Veto Rule:** If `currentSpread > 2.0 * medianSpread`, order execution is aborted (`spread_spike_veto`).

2. **Price Deviation / Slippage Guard:**
   - Refresh latest tick immediately before dispatch.
   - **Deviation Limit:** Deviation between planned entry price and latest market tick must be `<= 10 points`.

3. **Native MT5 OrderCheck:**
   - Construct native `MqlTradeRequest` and `MqlTradeCheckResult`.
   - Call `OrderCheck(request, checkResult)`.
   - If `checkResult.retcode != 0`, abort order and log specific broker error reason.

4. **Execution Lock & Duplicate Event Guard:**
   - Atomic lock during network transit to prevent duplicate `OrderSend`.
   - Transaction confirmation via `OnTradeTransaction`.

---

## 2. Data Structures

```mql5
struct ExecutionSafetyResult
{
   bool   passed;
   double currentSpread;
   double medianSpread;
   double spreadRatio;
   double priceDeviationPoints;
   uint   orderCheckRetcode;
   string failReason;
};
```
