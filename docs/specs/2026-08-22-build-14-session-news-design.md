# BUILD 14 — Session & News Engine Design Spec

**Status:** DESIGN (Approved by user).
**Scope:** Session time classification & Economic News filter to protect execution quality from low liquidity periods, wide rollover spreads, and high-impact macro shocks.
**Reference:** Master Plan v1.0 Section 27 & 28.

---

## 1. Session Engine Logic

- **Rollover Block (Hard Veto):** `23:45 – 00:15` Server Time (Daily broker rollover). New entries strictly blocked.
- **Core Session:** `08:00 – 21:00` Server Time (London & New York active hours). Normal trading.
- **Secondary Session / Low Liquidity:** `00:15 – 08:00` and `21:00 – 23:45`. Higher quality threshold required (Score >= 80).

---

## 2. News Engine Logic

- **Currencies Monitored:**
  - `EURUSD`: EUR & USD
  - `XAUUSD`: USD
- **Impact Level:** High-Impact events only (`CALENDAR_IMPORTANCE_HIGH`).
- **Gating Windows:**
  - `NEWS_LOCK`: 30 minutes before high-impact event (New entries blocked).
  - `NEWS_SHOCK`: 0 – 15 minutes after event release (New entries blocked).
  - `NEWS_RECOVERY`: 15 – 45 minutes after event (Only A+ setups with Quality Score >= 80 allowed).
  - `NEWS_CLEAR`: Normal trading permitted.

---

## 3. Data Structures

```mql5
enum ENUM_SESSION_STATE
{
   SESSION_CORE,
   SESSION_SECONDARY,
   SESSION_LOW_LIQUIDITY,
   SESSION_ROLLOVER,
   SESSION_CLOSED
};

enum ENUM_NEWS_STATE
{
   NEWS_CLEAR,
   NEWS_LOCK,
   NEWS_SHOCK,
   NEWS_RECOVERY
};

struct MarketEnvironmentState
{
   ENUM_SESSION_STATE sessionState;
   ENUM_NEWS_STATE    newsState;
   bool               allowNewEntry;
   double             requiredQualityScore;
   string             blockReason;
};
```
