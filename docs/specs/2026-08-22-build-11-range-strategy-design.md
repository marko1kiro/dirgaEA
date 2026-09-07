# BUILD 11 — M15 Range / Mean-Reversion Strategy Design Spec

**Status:** DESIGN (Approved by user).
**Scope:** M15 Strategy layer active ONLY when `H1 Regime == REGIME_RANGE`. Identifies Support & Resistance boundaries from confirmed swing structure and generates mean-reversion `TradeCandidate` instances upon Liquidity Sweeps / False Breakouts.

---

## 1. Core Rules & Boundary Conditions

1. **Activation Gate:**
   - Active only when `H1.valid == true` AND `H1.regime == REGIME_RANGE`.
   - Setup state is completely cleared if H1 leaves `REGIME_RANGE`.

2. **Range Boundary Identification:**
   - **Range High (Resistance):** Highest confirmed swing high in the current range epoch.
   - **Range Low (Support):** Lowest confirmed swing low in the current range epoch.
   - Minimum range height: `>= 2.0 * ATR(M15)`.

3. **Sweep & Rejection Trigger:**
   - **BUY at Support:** Bar sweeps below Support (Low < Support), but closes firmly inside range (Close > Support).
   - **SELL at Resistance:** Bar sweeps above Resistance (High > Resistance), but closes firmly inside range (Close < Resistance).
   - Invalidation (SL): Placed beyond the sweep extreme + `0.10 * ATR(M15)` buffer.
   - Target (TP): Opposite boundary (or Range Midpoint). Target price = Range High for BUY, Range Low for SELL.

---

## 2. Data Structures

```mql5
enum ENUM_RANGE_SETUP_TYPE
{
   RANGE_SETUP_NONE,
   RANGE_SETUP_SUPPORT_SWEEP_BUY,
   RANGE_SETUP_RESISTANCE_SWEEP_SELL
};
```
