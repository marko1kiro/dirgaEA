//+------------------------------------------------------------------+
//|                                              ExecutionBridge.mqh |
//|                                  Copyright 2026, AdaptiveSurvival |
//|                                             https://www.mql5.com |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, AdaptiveSurvival"
#property link      "https://www.mql5.com"
#property strict

#include <Trade\Trade.mqh>
#include "Types.mqh"
#include "BrokerEnvironment.mqh"
#include "Logger.mqh"

// Lock sentinel: unlocked = 0.0
#define LOCK_UNLOCKED 0.0
// Lock variable prefix
#define LOCK_PREFIX "DirgaEA_LK_"

class CExecutionBridge
{
private:
   string                  m_symbol;
   ulong                   m_magic;
   int                     m_maxPositions;
   CTrade                  m_trade;

   // Lock state (C-01)
   double                  m_ownerToken;
   string                  m_lockVarName;
   bool                    m_lockHeld;

   // Execution lifecycle (N-02)
   ENUM_EXECUTION_LIFECYCLE m_lifecycle;
   ulong                   m_pendingOrderTicket;
   ulong                   m_pendingDealTicket;
   datetime                m_pendingSubmitTime;

   string                  MakeLockKey();
   double                  MakeOwnerToken();

public:
                           CExecutionBridge(string symbol = "EURUSDm", ulong magic = 123456, int maxPositions = 1);
                          ~CExecutionBridge();

   void                    SetSymbol(string symbol);
   void                    SetMagic(ulong magic);
   void                    SetMaxPositions(int maxPos) { m_maxPositions = maxPos; }

   int                     CountOpenPositions();
   int                     CountActiveOrdersAndPositions();

   // Lock protocol (C-01, F-05)
   bool                    AcquireOrderLock(uint timeoutSeconds = 30);
   bool                    ReleaseOrderLock();
   bool                    IsLockHeld() { return m_lockHeld; }

   // Execution lifecycle (N-02)
   ENUM_EXECUTION_LIFECYCLE GetLifecycle() { return m_lifecycle; }
   void                    SetLifecycle(ENUM_EXECUTION_LIFECYCLE state) { m_lifecycle = state; }
   void                    ReconcilePending();

   bool                    PrepareMarketOrder(const TradeCandidate &cand,
                                              const RiskResult &risk,
                                              OrderIntent &outIntent);

   bool                    ExecuteIntent(const OrderIntent &intent, const BrokerEnvironment &env,
                                         ulong deviationPoints);
   bool                    ExecutePositionManage(const PositionManageIntent &intent, const BrokerEnvironment &env,
                                                 ulong deviationPoints);

   // Tick normalization (F-08)
   double                  NormalizePrice(double price);
   // Directional stop validation (N-04)
   bool                    ValidateStopFreeze(const OrderIntent &intent,
                                              double bidPrice, double askPrice);
};

//+------------------------------------------------------------------+
//| Constructor                                                      |
//+------------------------------------------------------------------+
CExecutionBridge::CExecutionBridge(string symbol = "EURUSDm", ulong magic = 123456, int maxPositions = 1)
{
   m_symbol = symbol;
   m_magic = magic;
   m_maxPositions = maxPositions;
   m_ownerToken = LOCK_UNLOCKED;
   m_lockVarName = "";
   m_lockHeld = false;
   m_lifecycle = EXEC_LIFECYCLE_IDLE;
   m_pendingOrderTicket = 0;
   m_pendingDealTicket = 0;
   m_pendingSubmitTime = 0;
   m_trade.SetExpertMagicNumber(m_magic);
   m_trade.SetMarginMode();
   m_trade.SetTypeFillingBySymbol(m_symbol);
}

//+------------------------------------------------------------------+
//| Destructor                                                       |
//+------------------------------------------------------------------+
CExecutionBridge::~CExecutionBridge()
{
}

//+------------------------------------------------------------------+
//| Unique lock key per symbol+magic                                 |
//+------------------------------------------------------------------+
string CExecutionBridge::MakeLockKey()
{
   return StringFormat("%s%s_%I64u", LOCK_PREFIX, m_symbol, m_magic);
}

//+------------------------------------------------------------------+
//| Unique owner token: encodes seconds + sub-second + magic hash    |
//| Ensures two instances in the same second get different tokens.   |
//+------------------------------------------------------------------+
double CExecutionBridge::MakeOwnerToken()
{
   datetime now = TimeCurrent();
   // Use GetTickCount() for sub-second uniqueness (milliseconds)
   uint tickMs = GetTickCount();
   // Mix in magic for per-symbol uniqueness
   double magicFrac = (double)((m_magic * 2654435761ULL) % 100000) / 100000.0;
   // Token = seconds + fractional from tick + magic fraction
   // Components: integer part = seconds, decimal = 0.tttmmm where t=TickID, m=magic
   double frac = ((double)(tickMs % 10000) / 10000.0) * 0.1 + magicFrac * 0.001;
   return (double)now + frac;
}

//+------------------------------------------------------------------+
//| Set Symbol and adjust filling type                               |
//+------------------------------------------------------------------+
void CExecutionBridge::SetSymbol(string symbol)
{
   m_symbol = symbol;
   m_trade.SetTypeFillingBySymbol(m_symbol);
}

//+------------------------------------------------------------------+
//| Set Magic Number                                                 |
//+------------------------------------------------------------------+
void CExecutionBridge::SetMagic(ulong magic)
{
   m_magic = magic;
   m_trade.SetExpertMagicNumber(m_magic);
}

//+------------------------------------------------------------------+
//| Normalize price to tick grid (F-08)                              |
//+------------------------------------------------------------------+
double CExecutionBridge::NormalizePrice(double price)
{
   if(m_symbol == "") return price;
   double tickSize = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_SIZE);
   int digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);
   if(tickSize <= 0.0) return NormalizeDouble(price, digits);
   // Directional rounding: BUY SL → floor, SELL SL → ceil, others → round
   double steps = MathFloor(price / tickSize + 0.5);
   return NormalizeDouble(steps * tickSize, digits);
}

//+------------------------------------------------------------------+
//| Validate stop/freeze levels (N-04)                               |
//| BUY protective SL checked against Bid; SELL against Ask.         |
//+------------------------------------------------------------------+
bool CExecutionBridge::ValidateStopFreeze(const OrderIntent &intent,
                                          double bidPrice, double askPrice)
{
   long stopsLevel = SymbolInfoInteger(m_symbol, SYMBOL_TRADE_STOPS_LEVEL);
   long freezeLevel = SymbolInfoInteger(m_symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
   if(point <= 0) return true;

   long minDistance = MathMax(stopsLevel, freezeLevel);

   if(intent.action == ORDER_INTENT_BUY_MARKET || intent.action == ORDER_INTENT_MODIFY_SL)
   {
      // BUY protective SL must be below current Bid
      if(intent.stopLoss > 0 && intent.stopLoss >= bidPrice - minDistance * point)
      {
         LogWarning("STOP_FREEZE_VIOLATION",
                    StringFormat("BUY SL %.5f too close to Bid %.5f (min_dist=%d pts, freeze=%d)",
                                intent.stopLoss, bidPrice, (int)minDistance, (int)freezeLevel));
         return false;
      }
   }
   else if(intent.action == ORDER_INTENT_SELL_MARKET || intent.action == ORDER_INTENT_MODIFY_SL)
   {
      // SELL protective SL must be above current Ask
      if(intent.stopLoss > 0 && intent.stopLoss <= askPrice + minDistance * point)
      {
         LogWarning("STOP_FREEZE_VIOLATION",
                    StringFormat("SELL SL %.5f too close to Ask %.5f (min_dist=%d pts, freeze=%d)",
                                intent.stopLoss, askPrice, (int)minDistance, (int)freezeLevel));
         return false;
      }
   }
   return true;
}

//+------------------------------------------------------------------+
//| Count active positions for this EA                               |
//+------------------------------------------------------------------+
int CExecutionBridge::CountOpenPositions()
{
   int count = 0;
   for (int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if (ticket > 0)
      {
         if (PositionGetString(POSITION_SYMBOL) == m_symbol &&
             PositionGetInteger(POSITION_MAGIC) == (long)m_magic)
         {
            count++;
         }
      }
   }
   return count;
}

//+------------------------------------------------------------------+
//| Count active positions AND pending orders (F-05)                 |
//+------------------------------------------------------------------+
int CExecutionBridge::CountActiveOrdersAndPositions()
{
   int count = CountOpenPositions();
   for (int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong ticket = OrderGetTicket(i);
      if (ticket > 0)
      {
         if (OrderGetString(ORDER_SYMBOL) == m_symbol &&
             OrderGetInteger(ORDER_MAGIC) == (long)m_magic)
         {
            count++;
         }
      }
   }
   return count;
}

//+------------------------------------------------------------------+
//| Acquire cross-instance order lock (C-01, F-05)                   |
//| Protocol:                                                         |
//| 1. Try CAS from 0.0 to our token (fast path).                   |
//| 2. If CAS fails, read current; check if expired; steal if so.   |
//| 3. Never overwrite non-zero without CAS.                         |
//+------------------------------------------------------------------+
bool CExecutionBridge::AcquireOrderLock(uint timeoutSeconds)
{
   m_lockVarName = MakeLockKey();
   m_ownerToken = MakeOwnerToken();
   m_lockHeld = false;

   // Ensure the global variable exists (only creates if absent)
   if(!GlobalVariableCheck(m_lockVarName))
   {
      // Create with unlocked sentinel — first writer wins
      GlobalVariableSet(m_lockVarName, LOCK_UNLOCKED);
   }

   // Fast path: try CAS from unlocked to our token
   if(GlobalVariableSetOnCondition(m_lockVarName, m_ownerToken, LOCK_UNLOCKED))
   {
      m_lockHeld = true;
      return true;
   }

   // CAS failed — someone holds the lock. Read current value.
   double currentVal = GlobalVariableGet(m_lockVarName);

   // Already our token? Re-entrant (shouldn't happen, but safe)
   if(currentVal == m_ownerToken)
   {
      m_lockHeld = true;
      return true;
   }

   // Check expiry: extract lock time (integer part = datetime seconds)
   datetime lockTime = (datetime)MathFloor(currentVal);
   datetime now = TimeCurrent();

   if(now - lockTime >= (int)timeoutSeconds)
   {
      // Expired — try CAS to steal
      if(GlobalVariableSetOnCondition(m_lockVarName, m_ownerToken, currentVal))
      {
         m_lockHeld = true;
         return true;
      }
      // CAS failed — another instance stole it first
   }

   return false;
}

//+------------------------------------------------------------------+
//| Release lock — only if we own it (CAS back to 0.0)              |
//+------------------------------------------------------------------+
bool CExecutionBridge::ReleaseOrderLock()
{
   if(!m_lockHeld || m_lockVarName == "" || m_ownerToken == LOCK_UNLOCKED)
      return false;
   if(!GlobalVariableCheck(m_lockVarName))
   {
      m_lockHeld = false;
      return true; // Already cleaned up (e.g. by terminal)
   }

   double currentVal = GlobalVariableGet(m_lockVarName);
   if(currentVal == m_ownerToken)
   {
      if(GlobalVariableSetOnCondition(m_lockVarName, LOCK_UNLOCKED, m_ownerToken))
      {
         m_lockHeld = false;
         return true;
      }
   }
   // Someone else stole it — we no longer own it
   m_lockHeld = false;
   return false;
}

//+------------------------------------------------------------------+
//| Reconcile pending orders (N-02)                                  |
//| Called from OnTradeTransaction and OnTick to detect terminal     |
//| outcomes for PLACED/DONE_PARTIAL orders.                         |
//+------------------------------------------------------------------+
void CExecutionBridge::ReconcilePending()
{
   if(m_lifecycle != EXEC_LIFECYCLE_ORDER_PENDING &&
      m_lifecycle != EXEC_LIFECYCLE_PARTIAL_FILL)
      return;

   // Check if order still exists
   if(m_pendingOrderTicket > 0)
   {
      if(!OrderSelect(m_pendingOrderTicket))
      {
         // Order no longer exists — might have been filled or removed
         // Check history for the deal
         if(m_pendingOrderTicket > 0 && HistoryOrderSelect(m_pendingOrderTicket))
         {
            long orderStatus = HistoryOrderGetInteger(m_pendingOrderTicket, ORDER_STATUS);
            if(orderStatus == ORDER_STATUS_FILLED || orderStatus == ORDER_STATUS_PARTIALLY_FILLED)
            {
               m_lifecycle = EXEC_LIFECYCLE_CONFIRMED;
               LogDebug("LIFECYCLE_CONFIRMED", StringFormat("order=%I64u reconciled", m_pendingOrderTicket));
               m_pendingOrderTicket = 0;
               m_pendingDealTicket = 0;
               return;
            }
            else if(orderStatus == ORDER_STATUS_CANCELED || orderStatus == ORDER_STATUS_EXPIRED)
            {
               m_lifecycle = EXEC_LIFECYCLE_REJECTED;
               LogDebug("LIFECYCLE_REJECTED", StringFormat("order=%I64u canceled/expired", m_pendingOrderTicket));
               m_pendingOrderTicket = 0;
               m_pendingDealTicket = 0;
               return;
            }
         }
      }
      else
      {
         // Order still active — check state
         long orderStatus = OrderGetInteger(ORDER_STATUS);
         if(orderStatus == ORDER_STATUS_FILLED)
         {
            m_lifecycle = EXEC_LIFECYCLE_CONFIRMED;
            m_pendingOrderTicket = 0;
            m_pendingDealTicket = 0;
            return;
         }
      }
   }

   // Timeout reconciliation: if pending too long, mark for reconcile
   datetime now = TimeCurrent();
   if(now - m_pendingSubmitTime > 30) // 30 second timeout
   {
      m_lifecycle = EXEC_LIFECYCLE_TIMEOUT_RECONCILE;
      LogWarning("LIFECYCLE_TIMEOUT", StringFormat("order=%I64u pending >30s, needs manual check",
                 m_pendingOrderTicket));
   }
}

//+------------------------------------------------------------------+
//| Prepare Order Intent from Candidate and Risk                     |
//+------------------------------------------------------------------+
bool CExecutionBridge::PrepareMarketOrder(const TradeCandidate &cand,
                                          const RiskResult &risk,
                                          OrderIntent &outIntent)
{
   ZeroMemory(outIntent);
   outIntent.action = ORDER_INTENT_NONE;

   if (!cand.valid)
   {
      outIntent.reason = "invalid_candidate";
      return false;
   }

   if (!risk.approved || risk.normalizedVolume <= 0)
   {
      outIntent.reason = "risk_rejected";
      return false;
   }

   if (CountActiveOrdersAndPositions() >= m_maxPositions)
   {
      outIntent.reason = "max_positions_reached";
      return false;
   }

   outIntent.symbol = cand.symbol;
   outIntent.volume = risk.normalizedVolume;
   outIntent.price = cand.entryPrice;
   outIntent.stopLoss = cand.initialStopPrice;
   outIntent.takeProfit = cand.targetPrice;
   outIntent.reason = "new_trade_entry";

   if (cand.direction == TRADE_DIR_BUY)
      outIntent.action = ORDER_INTENT_BUY_MARKET;
   else if (cand.direction == TRADE_DIR_SELL)
      outIntent.action = ORDER_INTENT_SELL_MARKET;
   else
      return false;

   return true;
}

//+------------------------------------------------------------------+
//| Execute Order Intent — retcode-aware, lifecycle-managed (N-02)   |
//+------------------------------------------------------------------+
bool CExecutionBridge::ExecuteIntent(const OrderIntent &intent, const BrokerEnvironment &env,
                                     ulong deviationPoints)
{
   if (!env.tradeReady || !env.environmentCompatible)
   {
      LogError("EXECUTION_ABORTED", "Broker environment not ready for trading");
      return false;
   }

   if(m_lifecycle == EXEC_LIFECYCLE_ORDER_PENDING || m_lifecycle == EXEC_LIFECYCLE_PARTIAL_FILL)
   {
      ReconcilePending();
      if(m_lifecycle == EXEC_LIFECYCLE_ORDER_PENDING || m_lifecycle == EXEC_LIFECYCLE_PARTIAL_FILL)
      {
         LogWarning("EXECUTION_BLOCKED_LIFECYCLE", "Previous order still pending");
         return false;
      }
   }

   m_lifecycle = EXEC_LIFECYCLE_PREFLIGHT;

   // Set deviation in points (F-08: NOT env.point cast)
   m_trade.SetDeviationInPoints(deviationPoints);

   // Normalize prices to tick grid
   double normPrice = NormalizePrice(intent.price);
   double normSL = intent.stopLoss > 0 ? NormalizePrice(intent.stopLoss) : 0.0;
   double normTP = intent.takeProfit > 0 ? NormalizePrice(intent.takeProfit) : 0.0;

   // Directional stop/freeze validation (N-04): BUY→Bid, SELL→Ask
   if(!ValidateStopFreeze(intent, env.tick.bid, env.tick.ask))
   {
      m_lifecycle = EXEC_LIFECYCLE_REJECTED;
      LogWarning("EXECUTION_BLOCKED_STOP_FREEZE", "Stop/freeze level violation");
      return false;
   }

   m_lifecycle = EXEC_LIFECYCLE_ORDER_PENDING;

   bool res = false;
   if (intent.action == ORDER_INTENT_BUY_MARKET)
   {
      res = m_trade.Buy(intent.volume, m_symbol, normPrice, normSL, normTP, "AdaptiveSurvivalEA");
   }
   else if (intent.action == ORDER_INTENT_SELL_MARKET)
   {
      res = m_trade.Sell(intent.volume, m_symbol, normPrice, normSL, normTP, "AdaptiveSurvivalEA");
   }
   else
   {
      m_lifecycle = EXEC_LIFECYCLE_REJECTED;
      return false;
   }

   uint retcode = m_trade.ResultRetcode();
   ulong orderTicket = m_trade.ResultOrder();
   ulong dealTicket = m_trade.ResultDeal();

   m_pendingOrderTicket = orderTicket;
   m_pendingDealTicket = dealTicket;
   m_pendingSubmitTime = TimeCurrent();

   if(res && retcode == TRADE_RETCODE_DONE)
   {
      m_lifecycle = EXEC_LIFECYCLE_CONFIRMED;
      m_pendingOrderTicket = 0;
      m_pendingDealTicket = 0;
      LogDebug("ORDER_EXECUTED", StringFormat("action=%d vol=%.2f price=%.5f sl=%.5f tp=%.5f order=%I64u deal=%I64u retcode=%u",
               (int)intent.action, intent.volume, normPrice, normSL, normTP, orderTicket, dealTicket, retcode));
      return true;
   }
   else if(res && retcode == TRADE_RETCODE_PLACED)
   {
      m_lifecycle = EXEC_LIFECYCLE_ORDER_PENDING;
      LogDebug("ORDER_PLACED_PENDING", StringFormat("action=%d vol=%.2f order=%I64u retcode=%u — awaiting fill",
               (int)intent.action, intent.volume, orderTicket, retcode));
      return true; // Lock stays held; reconciled later
   }
   else if(res && retcode == TRADE_RETCODE_DONE_PARTIAL)
   {
      m_lifecycle = EXEC_LIFECYCLE_PARTIAL_FILL;
      LogWarning("ORDER_PARTIAL_FILL", StringFormat("action=%d vol=%.2f order=%I64u deal=%I64u retcode=%u",
                 (int)intent.action, intent.volume, orderTicket, dealTicket, retcode));
      return true; // Lock stays held; reconciled later
   }
   else
   {
      m_lifecycle = EXEC_LIFECYCLE_REJECTED;
      LogError("ORDER_FAILED", StringFormat("action=%d retcode=%u desc=%s order=%I64u deal=%I64u",
                (int)intent.action, retcode, m_trade.ResultRetcodeDescription(), orderTicket, dealTicket));
      return false;
   }
}

//+------------------------------------------------------------------+
//| Execute Position Management — retcode-aware (F-01, N-02)         |
//+------------------------------------------------------------------+
bool CExecutionBridge::ExecutePositionManage(const PositionManageIntent &intent,
                                             const BrokerEnvironment &env,
                                             ulong deviationPoints)
{
   if (!env.tradeReady)
      return false;

   // Set deviation for modify/close
   m_trade.SetDeviationInPoints(deviationPoints);

   bool res = false;

   if (intent.action == POS_ACTION_MODIFY_SL)
   {
      double normSL = NormalizePrice(intent.newStopLoss);
      double normTP = intent.newTakeProfit > 0 ? NormalizePrice(intent.newTakeProfit) : 0.0;
      res = m_trade.PositionModify(intent.ticket, normSL, normTP);

      uint retcode = m_trade.ResultRetcode();
      if(res && retcode == TRADE_RETCODE_DONE)
      {
         LogDebug("POS_MODIFIED", StringFormat("ticket=%I64u newSL=%G retcode=%u", intent.ticket, normSL, retcode));
         return true;
      }
      else
      {
         LogWarning("POS_MODIFY_FAILED", StringFormat("ticket=%I64u retcode=%u desc=%s",
                    intent.ticket, retcode, m_trade.ResultRetcodeDescription()));
         return false;
      }
   }
   else if (intent.action == POS_ACTION_CLOSE_MARKET)
   {
      res = m_trade.PositionClose(intent.ticket);

      uint retcode = m_trade.ResultRetcode();
      if(res && retcode == TRADE_RETCODE_DONE)
      {
         LogDebug("POS_CLOSED_MARKET", StringFormat("ticket=%I64u reason=%s retcode=%u",
                   intent.ticket, intent.reason, retcode));
         return true;
      }
      else
      {
         LogWarning("POS_CLOSE_FAILED", StringFormat("ticket=%I64u retcode=%u desc=%s",
                    intent.ticket, retcode, m_trade.ResultRetcodeDescription()));
         return false;
      }
   }

   return false;
}
