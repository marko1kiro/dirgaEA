# BUILD 12 — M15 Breakout Strategy Design Spec

**Status:** DESIGN (Approved by user).
**Scope:** M15 Strategy layer active ONLY when `H1 Regime == REGIME_BREAKOUT_BULL` or `REGIME_BREAKOUT_BEAR`. Implements Dual-Mode Breakout execution (Direct Impulse Breakout and Break-Retest).
**Reference:** Master Plan v1.0 Section 16.

---

## 1. Core Rules & Modes

1. **Activation Gate:**
   - Active only when `H1.valid == true` AND `H1.regime ∈ { REGIME_BREAKOUT_BULL, REGIME_BREAKOUT_BEAR }`.
   - Setup state clears immediately if H1 leaves breakout regime.

2. **Mode A: Direct Impulse Breakout (A+ Quality):**
   - **Trigger:** Solid candle close breaking through structural swing level in regime direction.
   - **Meaningful Penetration:** Break candle close exceeds level by `>= 0.15 * ATR(M15)`.
   - **Anti-Chase Invariant:** Distance from break level to entry close `<= 1.5 * ATR(M15)`.
   - **Stop Loss:** Placed behind break candle low (for Bull) or high (for Bear) with `0.10 * ATR(M15)` buffer.
   - **Target:** Measured move `1.5x - 2.0x` of breakout expansion range.

3. **Mode B: Break-Retest (A Quality):**
   - **Trigger:** Triggered when Direct Breakout was skipped or when price retests broken level within `0.20 * ATR(M15)` tolerance within 6 bars.
   - **Stop Loss:** Placed behind retest swing rejection point with `0.10 * ATR(M15)` buffer.
   - **Target:** Continuation target beyond breakout swing high/low.

---

## 2. Data Structures

```mql5
enum ENUM_BREAKOUT_SETUP_TYPE
{
   BREAKOUT_SETUP_NONE,
   BREAKOUT_SETUP_DIRECT_BULL,
   BREAKOUT_SETUP_DIRECT_BEAR,
   BREAKOUT_SETUP_RETEST_BULL,
   BREAKOUT_SETUP_RETEST_BEAR
};
```
