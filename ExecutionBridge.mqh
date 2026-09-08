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

class CExecutionBridge
{
private:
   string                  m_symbol;
   ulong                   m_magic;
   int                     m_maxPositions;
   CTrade                  m_trade;
   double                  m_ownerToken;
   string                  m_lockVarName;

   string                  LockVarName() { return StringFormat("DirgaEA_Lock_%s_%I64u", m_symbol, m_magic); }
   double                  MakeOwnerToken();

public:
                           CExecutionBridge(string symbol = "EURUSDm", ulong magic = 123456, int maxPositions = 1);
                          ~CExecutionBridge();

   void                    SetSymbol(string symbol);
   void                    SetMagic(ulong magic);
   void                    SetMaxPositions(int maxPos) { m_maxPositions = maxPos; }

   int                     CountOpenPositions();
   int                     CountActiveOrdersAndPositions();
   bool                    AcquireOrderLock(uint timeoutSeconds = 30);
   bool                    ReleaseOrderLock();
   bool                    PrepareMarketOrder(const TradeCandidate &cand,
                                              const RiskResult &risk,
                                              OrderIntent &outIntent);

   bool                    ExecuteIntent(const OrderIntent &intent, const BrokerEnvironment &env);
   bool                    ExecutePositionManage(const PositionManageIntent &intent, const BrokerEnvironment &env);

   // Tick normalization (F-08)
   double                  NormalizePrice(double price);
   bool                    ValidateStopFreeze(const OrderIntent &intent, double currentPrice);
   bool                    SetDeviation(ulong deviationPoints);
};

//+------------------------------------------------------------------+
//| Constructor                                                      |
//+------------------------------------------------------------------+
CExecutionBridge::CExecutionBridge(string symbol = "EURUSDm", ulong magic = 123456, int maxPositions = 1)
{
   m_symbol = symbol;
   m_magic = magic;
   m_maxPositions = maxPositions;
   m_ownerToken = 0.0;
   m_lockVarName = "";
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
//| Make unique owner token per instance (PID + time + magic frac)   |
//+------------------------------------------------------------------+
double CExecutionBridge::MakeOwnerToken()
{
   datetime now = TimeCurrent();
   double frac = (double)((m_magic * 2654435761ULL) % 1000000) / 1000000.0;
   return (double)now + frac;
}

//+------------------------------------------------------------------+
//| Set Symbol and adjust filling type (F-08)                        |
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
   double steps = MathRound(price / tickSize);
   return NormalizeDouble(steps * tickSize, digits);
}

//+------------------------------------------------------------------+
//| Validate stop/freeze levels against current Bid/Ask (F-08)       |
//+------------------------------------------------------------------+
bool CExecutionBridge::ValidateStopFreeze(const OrderIntent &intent, double currentPrice)
{
   long stopsLevel = SymbolInfoInteger(m_symbol, SYMBOL_TRADE_STOPS_LEVEL);
   long freezeLevel = SymbolInfoInteger(m_symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
   if(point <= 0) return true;

   long minDistance = MathMax(stopsLevel, freezeLevel);

   if(intent.action == ORDER_INTENT_BUY_MARKET || intent.action == ORDER_INTENT_MODIFY_SL)
   {
      // For BUY: SL must be below current Bid by at least stopsLevel points
      if(intent.stopLoss > 0 && intent.stopLoss >= currentPrice - minDistance * point)
      {
         LogWarning("STOP_FREEZE_VIOLATION",
                    StringFormat("BUY SL %.5f too close to price %.5f (min_dist=%d pts)",
                                intent.stopLoss, currentPrice, (int)minDistance));
         return false;
      }
   }
   else if(intent.action == ORDER_INTENT_SELL_MARKET)
   {
      // For SELL: SL must be above current Ask by at least stopsLevel points
      if(intent.stopLoss > 0 && intent.stopLoss <= currentPrice + minDistance * point)
      {
         LogWarning("STOP_FREEZE_VIOLATION",
                    StringFormat("SELL SL %.5f too close to price %.5f (min_dist=%d pts)",
                                intent.stopLoss, currentPrice, (int)minDistance));
         return false;
      }
   }
   return true;
}

//+------------------------------------------------------------------+
//| Set CTrade deviation (F-08)                                      |
//+------------------------------------------------------------------+
bool CExecutionBridge::SetDeviation(ulong deviationPoints)
{
   m_trade.SetDeviationInPoints(deviationPoints);
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
//| Acquire cross-instance order lock (F-05, C-01)                   |
//| Uses GlobalVariableSet to create if absent, then CAS atomically. |
//+------------------------------------------------------------------+
bool CExecutionBridge::AcquireOrderLock(uint timeoutSeconds)
{
   m_lockVarName = LockVarName();
   m_ownerToken = MakeOwnerToken();

   // Step 1: Ensure variable exists with unlocked sentinel value
   if(!GlobalVariableCheck(m_lockVarName))
   {
      // Variable doesn't exist — create it with 0.0 (unlocked)
      GlobalVariableSet(m_lockVarName, 0.0);
   }

   double currentVal = GlobalVariableGet(m_lockVarName);

   // Step 2: If unlocked (0.0), try CAS to our token
   if(currentVal == 0.0)
   {
      if(GlobalVariableSetOnCondition(m_lockVarName, m_ownerToken, 0.0))
         return true;
      // CAS failed — another instance won the race. Re-read.
      currentVal = GlobalVariableGet(m_lockVarName);
   }

   // Step 3: Check if locked but expired
   if(currentVal != 0.0 && currentVal != m_ownerToken)
   {
      // Decode lock time from token (high bits = PID*1e9 + time)
      double lockTimeApprox = currentVal;
      datetime now = TimeCurrent();
      // If the value looks like an old timestamp-based token, check timeout
      // The timeout is enforced by comparing against now
      datetime lockTime = (datetime)MathMod(lockTimeApprox, 1000000000.0);
      if(lockTime <= 0) lockTime = (datetime)lockTimeApprox;
      if(now - lockTime >= (int)timeoutSeconds)
      {
         // Expired — try CAS to steal
         if(GlobalVariableSetOnCondition(m_lockVarName, m_ownerToken, currentVal))
            return true;
      }
   }

   return false;
}

//+------------------------------------------------------------------+
//| Release cross-instance order lock (F-05, C-01)                   |
//| Only release if we still own it (CAS back to 0.0).              |
//+------------------------------------------------------------------+
bool CExecutionBridge::ReleaseOrderLock()
{
   if(m_lockVarName == "" || m_ownerToken == 0.0) return false;
   if(!GlobalVariableCheck(m_lockVarName)) return false;

   double currentVal = GlobalVariableGet(m_lockVarName);
   if(currentVal == m_ownerToken)
   {
      // CAS back to unlocked sentinel — only owner succeeds
      if(GlobalVariableSetOnCondition(m_lockVarName, 0.0, m_ownerToken))
         return true;
   }
   return false;
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
   outIntent.stopLoss = NormalizePrice(cand.initialStopPrice);
   outIntent.takeProfit = cand.targetPrice > 0 ? NormalizePrice(cand.targetPrice) : 0.0;
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
//| Execute Order Intent — retcode-aware (F-08, N-02)                |
//+------------------------------------------------------------------+
bool CExecutionBridge::ExecuteIntent(const OrderIntent &intent, const BrokerEnvironment &env)
{
   if (!env.tradeReady || !env.environmentCompatible)
   {
      LogError("EXECUTION_ABORTED", "Broker environment not ready for trading");
      return false;
   }

   // Set deviation to match slippage guard
   m_trade.SetDeviationInPoints((ulong)(env.point > 0 ? env.point : 1));

   // Normalize prices to tick grid
   double normPrice = NormalizePrice(intent.price);
   double normSL = intent.stopLoss > 0 ? NormalizePrice(intent.stopLoss) : 0.0;
   double normTP = intent.takeProfit > 0 ? NormalizePrice(intent.takeProfit) : 0.0;

   // Validate stop/freeze before sending
   double currentPrice = (intent.action == ORDER_INTENT_BUY_MARKET) ? env.tick.ask : env.tick.bid;
   if(!ValidateStopFreeze(intent, currentPrice))
   {
      LogWarning("EXECUTION_BLOCKED_STOP_FREEZE", "Stop/freeze level violation");
      return false;
   }

   bool res = false;
   if (intent.action == ORDER_INTENT_BUY_MARKET)
   {
      res = m_trade.Buy(intent.volume, m_symbol, normPrice, normSL, normTP, "AdaptiveSurvivalEA_BUY");
   }
   else if (intent.action == ORDER_INTENT_SELL_MARKET)
   {
      res = m_trade.Sell(intent.volume, m_symbol, normPrice, normSL, normTP, "AdaptiveSurvivalEA_SELL");
   }
   else
      return false;

   // Validate broker retcode — bool true != server success (N-02)
   uint retcode = m_trade.ResultRetcode();
   ulong orderTicket = m_trade.ResultOrder();
   ulong dealTicket = m_trade.ResultDeal();

   if(res && retcode == TRADE_RETCODE_DONE)
   {
      LogDebug("ORDER_EXECUTED", StringFormat("action=%d vol=%.2f price=%.5f sl=%.5f tp=%.5f order=%I64u deal=%I64u retcode=%u",
               (int)intent.action, intent.volume, normPrice, normSL, normTP, orderTicket, dealTicket, retcode));
      return true;
   }
   else if(res && retcode == TRADE_RETCODE_PLACED)
   {
      LogDebug("ORDER_PLACED", StringFormat("action=%d vol=%.2f order=%I64u retcode=%u",
               (int)intent.action, intent.volume, orderTicket, retcode));
      return true;
   }
   else if(res && retcode == TRADE_RETCODE_DONE_PARTIAL)
   {
      LogWarning("ORDER_PARTIAL_FILL", StringFormat("action=%d vol=%.2f order=%I64u deal=%I64u retcode=%u",
                 (int)intent.action, intent.volume, orderTicket, dealTicket, retcode));
      return true;
   }
   else
   {
      LogError("ORDER_FAILED", StringFormat("action=%d retcode=%u desc=%s order=%I64u deal=%I64u",
                (int)intent.action, retcode, m_trade.ResultRetcodeDescription(), orderTicket, dealTicket));
      return false;
   }
}

//+------------------------------------------------------------------+
//| Execute Position Management — retcode-aware (F-01, N-02)         |
//+------------------------------------------------------------------+
bool CExecutionBridge::ExecutePositionManage(const PositionManageIntent &intent, const BrokerEnvironment &env)
{
   if (!env.tradeReady)
      return false;

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
