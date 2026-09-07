# BUILD 13 — Chart HUD Dashboard & Live Telemetry Design Spec

**Status:** DESIGN (Approved by user).
**Scope:** Real-time observability HUD using clean `Comment()` and structured telemetry logger to monitor H1 Market Brain, Active Regime, Candidate Quality, and Position Lifecycle directly on MT5 chart.

---

## 1. Observability Fields

The Chart HUD will display:
1. **System Health:** EA Status (`EA_READY`), Trade Ready (`TRADE_READY`), Magic Number, Server Time.
2. **H1 Market Brain (BUILD 06):**
   - Current Regime: `TREND_BULL` / `TREND_BEAR` / `RANGE` / `BREAKOUT_BULL` / `BREAKOUT_BEAR` / `UNCERTAIN`
   - Regime Quality (`STRONG`, `NORMAL`, `WEAK`), Confidence `[0-100%]`, Age (bars).
3. **M15 Strategy Router Status (BUILD 07, 11, 12):**
   - Active Strategy Owner: Trend / Range / Breakout.
   - Last Evaluated Setup Family & Time.
4. **Quality Gate Status (BUILD 09):**
   - Last Score: `[0-100]` (Approved / Rejected reason).
5. **Active Position Status (BUILD 08, 10):**
   - Ticket, Open Price, Current SL, TP, Floating Profit / Risk.

---

## 2. Implementation Unit

```mql5
class CDashboardHUD
{
public:
   static void Update(const BrokerEnvironment &env,
                      const RegimeResult &h1Regime,
                      const TradeCandidate &lastCand,
                      const QualityGateResult &lastQuality,
                      ulong magic);
};
```
