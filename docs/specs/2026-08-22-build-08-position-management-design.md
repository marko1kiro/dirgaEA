# BUILD 08 — Position & Trade Management Design Spec

**Status:** DESIGN (Approved by user).
**Scope:** Position lifecycle management, dynamic stop loss adjustment (Breakeven & Structure-based trailing), and regime invalidation exits.
**Dependencies:** Consumes active MT5 positions, `RegimeResult` (BUILD 06), and M15 swings (BUILD 07).

---

## 1. Core Responsibilities & Invariants

1. **Deterministic Position Tracking:**
   - Tracks only positions belonging to EA (`MagicNumber` & `_Symbol`).
   - Pure state evaluation decoupled from physical execution (produces modification/close intents).

2. **Breakeven (BE) Logic:**
   - Trigger: Unrealized profit reaches `>= 1.0R` (where `1.0R = |Entry - InitialSL|`).
   - Action: Move Stop Loss to `EntryPrice + BE_Buffer` (for BUY) or `EntryPrice - BE_Buffer` (for SELL).
   - Buffer: `0.10 * ATR(M15)` to cover commission/spread.

3. **Structural Trailing Stop (M15):**
   - Active only after Breakeven is locked.
   - For BUY: Trail SL behind newly confirmed M15 Swing Low + `0.10 ATR buffer`.
   - For SELL: Trail SL behind newly confirmed M15 Swing High - `0.10 ATR buffer`.
   - Ratchet Invariant: Stop Loss can ONLY move in the favorable direction (never widens risk).

4. **Regime & Emergency Invalidation Exit:**
   - Position closed immediately (market close intent) if:
     - H1 Regime flips to opposite direction (e.g. BUY open, but H1 becomes `TREND_BEAR`).
     - H1 Regime becomes `UNCERTAIN` or `valid == false`.
     - Broker environment becomes incompatible or trading disabled.

---

## 2. Data Structures

```mql5
enum ENUM_POSITION_MANAGE_ACTION
{
   POS_ACTION_NONE,
   POS_ACTION_MODIFY_SL,
   POS_ACTION_CLOSE_MARKET
};

struct PositionManageIntent
{
   ulong                      ticket;
   ENUM_POSITION_MANAGE_ACTION action;
   double                     newStopLoss;
   double                     newTakeProfit;
   string                     reason;
};
```
