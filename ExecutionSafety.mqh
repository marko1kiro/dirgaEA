//+------------------------------------------------------------------+
//|                                              ExecutionSafety.mqh |
//|                                  Copyright 2026, AdaptiveSurvival |
//|                                             https://www.mql5.com |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, AdaptiveSurvival"
#property link      "https://www.mql5.com"
#property strict

#include "Types.mqh"
#include "BrokerEnvironment.mqh"

#define B15_SPREAD_WINDOW_SIZE      50
#define B15_MAX_SPREAD_RATIO        2.0
#define B15_MAX_SLIPPAGE_POINTS     10.0

class CExecutionSafetyGuard
{
private:
   double                  m_spreadSamples[B15_SPREAD_WINDOW_SIZE];
   int                     m_spreadCount;
   int                     m_spreadIndex;
   double                  m_maxSpreadRatio;
   double                  m_maxSlippagePoints;
   double                  m_maxSpreadCeiling;

public:
                           CExecutionSafetyGuard(double maxRatio = B15_MAX_SPREAD_RATIO, double maxSlippage = B15_MAX_SLIPPAGE_POINTS, double maxSpreadCeiling = 35.0);
                          ~CExecutionSafetyGuard();

   void                    AddSpreadSample(double spreadPoints);
   double                  GetMedianSpread();
   bool                    ValidateOrder(const OrderIntent &intent,
                                         const BrokerEnvironment &env,
                                         ExecutionSafetyResult &outResult);
};

//+------------------------------------------------------------------+
//| Constructor                                                      |
//+------------------------------------------------------------------+
CExecutionSafetyGuard::CExecutionSafetyGuard(double maxRatio = B15_MAX_SPREAD_RATIO, double maxSlippage = B15_MAX_SLIPPAGE_POINTS, double maxSpreadCeiling = 35.0)
{
   m_maxSpreadRatio = maxRatio;
   m_maxSlippagePoints = maxSlippage;
   m_maxSpreadCeiling = maxSpreadCeiling;
   m_spreadCount = 0;
   m_spreadIndex = 0;
   ArrayInitialize(m_spreadSamples, 0.0);
}

//+------------------------------------------------------------------+
//| Destructor                                                       |
//+------------------------------------------------------------------+
CExecutionSafetyGuard::~CExecutionSafetyGuard()
{
}

//+------------------------------------------------------------------+
//| Add Spread Sample                                                |
//+------------------------------------------------------------------+
void CExecutionSafetyGuard::AddSpreadSample(double spreadPoints)
{
   if (spreadPoints <= 0)
      return;
   m_spreadSamples[m_spreadIndex] = spreadPoints;
   m_spreadIndex = (m_spreadIndex + 1) % B15_SPREAD_WINDOW_SIZE;
   if (m_spreadCount < B15_SPREAD_WINDOW_SIZE)
      m_spreadCount++;
}

//+------------------------------------------------------------------+
//| Get Median Spread                                                |
//+------------------------------------------------------------------+
double CExecutionSafetyGuard::GetMedianSpread()
{
   if (m_spreadCount == 0) return 10.0;

   double temp[];
   ArrayResize(temp, m_spreadCount);
   for (int i = 0; i < m_spreadCount; i++)
      temp[i] = m_spreadSamples[i];

   ArraySort(temp);
   return temp[m_spreadCount / 2];
}

//+------------------------------------------------------------------+
//| Validate Order Pre-Flight Safety                                 |
//+------------------------------------------------------------------+
bool CExecutionSafetyGuard::ValidateOrder(const OrderIntent &intent,
                                          const BrokerEnvironment &env,
                                          ExecutionSafetyResult &outResult)
{
   ZeroMemory(outResult);
   outResult.passed = false;

   double curSpread = (env.tick.ask - env.tick.bid) / (env.point > 0 ? env.point : 0.00001);
   double medSpread = GetMedianSpread();
   double ratio = (medSpread > 0) ? (curSpread / medSpread) : 1.0;

   // Record sample only AFTER computing baseline comparison (F-06)
   AddSpreadSample(curSpread);

   outResult.currentSpreadPoints = curSpread;
   outResult.medianSpreadPoints = medSpread;
   outResult.spreadRatio = ratio;

   // 0. Absolute Spread Ceiling Guard (F-06)
   if (m_maxSpreadCeiling > 0 && curSpread > m_maxSpreadCeiling)
   {
      outResult.failReason = "spread_exceeds_absolute_ceiling";
      return false;
   }

   // 1. Spread Spike Veto (require at least 5 samples before strict ratio veto)
   if (m_spreadCount >= 5 && ratio > m_maxSpreadRatio)
   {
      outResult.failReason = "spread_spike_veto";
      return false;
   }

   // 2. Slippage Deviation Guard
   double currentPrice = (intent.action == ORDER_INTENT_BUY_MARKET) ? env.tick.ask : env.tick.bid;
   double devPts = MathAbs(intent.price - currentPrice) / (env.point > 0 ? env.point : 0.00001);
   outResult.priceDeviationPoints = devPts;

   if (devPts > m_maxSlippagePoints)
   {
      outResult.failReason = "slippage_deviation_exceeded";
      return false;
   }

   // 3. Native MT5 OrderCheck with Symbol-Aware Filling Mode (F-08)
   MqlTradeRequest req;
   ZeroMemory(req);
   req.action = TRADE_ACTION_DEAL;
   req.symbol = env.symbol;
   req.volume = intent.volume;
   req.type = (intent.action == ORDER_INTENT_BUY_MARKET) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   req.price = currentPrice;
   req.sl = intent.stopLoss;
   req.tp = intent.takeProfit;
   req.deviation = (ulong)m_maxSlippagePoints;

   uint fillingMode = (uint)SymbolInfoInteger(env.symbol, SYMBOL_FILLING_MODE);
   if ((fillingMode & SYMBOL_FILLING_FOK) != 0)
      req.type_filling = ORDER_FILLING_FOK;
   else if ((fillingMode & SYMBOL_FILLING_IOC) != 0)
      req.type_filling = ORDER_FILLING_IOC;
   else
      req.type_filling = ORDER_FILLING_RETURN;

   MqlTradeCheckResult checkRes;
   ZeroMemory(checkRes);

   if (!OrderCheck(req, checkRes) || checkRes.retcode != 0)
   {
      outResult.orderCheckRetcode = checkRes.retcode;
      outResult.failReason = StringFormat("order_check_failed_%u", checkRes.retcode);
      return false;
   }

   outResult.passed = true;
   outResult.failReason = "";
   return true;
}
