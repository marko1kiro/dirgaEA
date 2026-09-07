# BUILD 10 — Order Execution & Broker Bridge Design Spec

**Status:** DESIGN (Approved by user).
**Scope:** Safely connects approved `TradeCandidate` instances (from BUILD 09) and position intents (from BUILD 08) to the MT5 Broker via `RiskEngine` (BUILD 03) and native `CTrade` / `OrderSend`.

---

## 1. Core Principles & Safety Invariants

1. **Strict Single Position Limit:**
   - At most 1 active position per symbol/magic number at any time.
   - If a position exists or is pending, candidate execution is ignored.

2. **Risk Engine Validation (BUILD 03):**
   - Every candidate passes through `CalculateBasicRisk(...)` to determine lot size based on `RiskPercent`, `HardRiskCapPercent`, and broker margin requirements.
   - If risk calculation rejects, order is aborted.

3. **Order Placement Safety:**
   - Validates `TRADE_READY` and broker trade permissions before calling `OrderSend`.
   - Normalizes SL and TP according to `_Digits`, `_Point`, and `MODE_STOPLEVEL`.
   - Slippage protection: maximum deviation points enforced.

4. **Position Modification & Market Close Execution:**
   - Executes modification intents (`POS_ACTION_MODIFY_SL`) from BUILD 08.
   - Executes emergency market close intents (`POS_ACTION_CLOSE_MARKET`) from BUILD 08.

---

## 2. Architecture & Data Flow

```
[BUILD 07: TradeCandidate]
           │
           ▼
[BUILD 09: Quality Gate (score >= 70)]
           │
           ▼
[BUILD 03: RiskEngine (Lot Size & Margin Check)]
           │
           ▼
[BUILD 10: ExecutionEngine -> Native MT5 OrderSend]
```
