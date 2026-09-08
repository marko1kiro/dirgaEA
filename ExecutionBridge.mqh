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

public:
                           CExecutionBridge(string symbol = "EURUSDm", ulong magic = 123456, int maxPositions = 1);
                          ~CExecutionBridge();

   void                    SetSymbol(string symbol);
   void                    SetMagic(ulong magic);
   void                    SetMaxPositions(int maxPos) { m_maxPositions = maxPos; }

   int                     CountOpenPositions();
   int                     CountActiveOrdersAndPositions();
   bool                    AcquireOrderLock(uint timeoutSeconds = 5);
   void                    ReleaseOrderLock();
   bool                    PrepareMarketOrder(const TradeCandidate &cand,
                                              const RiskResult &risk,
                                              OrderIntent &outIntent);

   bool                    ExecuteIntent(const OrderIntent &intent, const BrokerEnvironment &env);
   bool                    ExecutePositionManage(const PositionManageIntent &intent, const BrokerEnvironment &env);
};

//+------------------------------------------------------------------+
//| Constructor                                                      |
//+------------------------------------------------------------------+
CExecutionBridge::CExecutionBridge(string symbol = "EURUSDm", ulong magic = 123456, int maxPositions = 1)
{
   m_symbol = symbol;
   m_magic = magic;
   m_maxPositions = maxPositions;
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
//| Acquire cross-instance order lock (F-05)                         |
//+------------------------------------------------------------------+
bool CExecutionBridge::AcquireOrderLock(uint timeoutSeconds)
{
   string lockVar = StringFormat("DirgaEA_Lock_%s_%I64u", m_symbol, m_magic);
   datetime now = TimeCurrent();

   if (GlobalVariableCheck(lockVar))
   {
      datetime lockTime = (datetime)GlobalVariableGet(lockVar);
      if (now - lockTime < (int)timeoutSeconds)
         return false; // Still locked by another instance
   }

   GlobalVariableSet(lockVar, (double)now);
   return true;
}

//+------------------------------------------------------------------+
//| Release cross-instance order lock (F-05)                         |
//+------------------------------------------------------------------+
void CExecutionBridge::ReleaseOrderLock()
{
   string lockVar = StringFormat("DirgaEA_Lock_%s_%I64u", m_symbol, m_magic);
   if (GlobalVariableCheck(lockVar))
      GlobalVariableDel(lockVar);
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
//| Execute Order Intent to Broker via CTrade                        |
//+------------------------------------------------------------------+
bool CExecutionBridge::ExecuteIntent(const OrderIntent &intent, const BrokerEnvironment &env)
{
   if (!env.tradeReady || !env.environmentCompatible)
   {
      LogError("EXECUTION_ABORTED", "Broker environment not ready for trading");
      return false;
   }

   if (intent.action == ORDER_INTENT_BUY_MARKET)
   {
      double ask = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
      bool res = m_trade.Buy(intent.volume, m_symbol, ask, intent.stopLoss, intent.takeProfit, "AdaptiveSurvivalEA_BUY");
      if (res)
         LogDebug("ORDER_BUY_PLACED", StringFormat("vol=%.2f sl=%G tp=%G ticket=%I64u", intent.volume, intent.stopLoss, intent.takeProfit, m_trade.ResultOrder()));
      else
         LogError("ORDER_BUY_FAILED", StringFormat("retcode=%u desc=%s", m_trade.ResultRetcode(), m_trade.ResultRetcodeDescription()));
      return res;
   }
   else if (intent.action == ORDER_INTENT_SELL_MARKET)
   {
      double bid = SymbolInfoDouble(m_symbol, SYMBOL_BID);
      bool res = m_trade.Sell(intent.volume, m_symbol, bid, intent.stopLoss, intent.takeProfit, "AdaptiveSurvivalEA_SELL");
      if (res)
         LogDebug("ORDER_SELL_PLACED", StringFormat("vol=%.2f sl=%G tp=%G ticket=%I64u", intent.volume, intent.stopLoss, intent.takeProfit, m_trade.ResultOrder()));
      else
         LogError("ORDER_SELL_FAILED", StringFormat("retcode=%u desc=%s", m_trade.ResultRetcode(), m_trade.ResultRetcodeDescription()));
      return res;
   }

   return false;
}

//+------------------------------------------------------------------+
//| Execute Position Management Intent                               |
//+------------------------------------------------------------------+
bool CExecutionBridge::ExecutePositionManage(const PositionManageIntent &intent, const BrokerEnvironment &env)
{
   if (!env.tradeReady)
      return false;

   if (intent.action == POS_ACTION_MODIFY_SL)
   {
      bool res = m_trade.PositionModify(intent.ticket, intent.newStopLoss, intent.newTakeProfit);
      if (res)
         LogDebug("POS_MODIFIED", StringFormat("ticket=%I64u newSL=%G", intent.ticket, intent.newStopLoss));
      return res;
   }
   else if (intent.action == POS_ACTION_CLOSE_MARKET)
   {
      bool res = m_trade.PositionClose(intent.ticket);
      if (res)
         LogDebug("POS_CLOSED_MARKET", StringFormat("ticket=%I64u reason=%s", intent.ticket, intent.reason));
      return res;
   }

   return false;
}
