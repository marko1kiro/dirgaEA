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
#define B15_MIN_SAMPLES_FOR_RATIO   5

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

   // Record spread sample — call ONCE per tick, AFTER evaluation (F-06)
   void                    AddSpreadSample(double spreadPoints);
   // Get median from historical samples only (excludes current tick)
   double                  GetMedianSpread();
   // Validate: uses env.tick (no re-fetch, no re-sample)
   bool                    ValidateOrder(const OrderIntent &intent,
                                         const BrokerEnvironment &env,
                                         ExecutionSafetyResult &outResult,
                                         ulong configuredDeviationPoints = 0);
   // Get max slippage in points for external use
   ulong                   GetMaxSlippagePoints() { return (ulong)m_maxSlippagePoints; }
   void                    SetMaxSlippagePoints(double pts) { m_maxSlippagePoints = pts; }
};

//+------------------------------------------------------------------+
//| Constructor                                                      |
//+------------------------------------------------------------------+
CExecutionSafetyGuard::CExecutionSafetyGuard(double maxRatio, double maxSlippage, double maxSpreadCeiling)
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
//| Add spread sample (call ONCE per tick, AFTER ValidateOrder)      |
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
//| Get median from PREVIOUS samples only (F-06: no double-count)   |
//+------------------------------------------------------------------+
double CExecutionSafetyGuard::GetMedianSpread()
{
   if (m_spreadCount == 0)
      return m_maxSpreadCeiling > 0 ? m_maxSpreadCeiling : 10.0;

   double temp[];
   ArrayResize(temp, m_spreadCount);
   for (int i = 0; i < m_spreadCount; i++)
      temp[i] = m_spreadSamples[i];

   ArraySort(temp);
   return temp[m_spreadCount / 2];
}

//+------------------------------------------------------------------+
//| Validate Order Pre-Flight Safety                                 |
//| Uses env.tick directly — no additional tick fetch or sampling.   |
//+------------------------------------------------------------------+
bool CExecutionSafetyGuard::ValidateOrder(const OrderIntent &intent,
                                           const BrokerEnvironment &env,
                                           ExecutionSafetyResult &outResult,
                                           ulong configuredDeviationPoints)
{
   ZeroMemory(outResult);
   outResult.passed = false;

   double maxDev = (configuredDeviationPoints > 0) ? (double)configuredDeviationPoints : m_maxSlippagePoints;

   // Current spread from env.tick (no re-fetch)
   double curSpread = (env.tick.ask - env.tick.bid) / (env.point > 0 ? env.point : 0.00001);

   // Median from HISTORICAL samples only (F-06: current sample NOT yet added)
   double medSpread = GetMedianSpread();
   double ratio = (medSpread > 0) ? (curSpread / medSpread) : 1.0;

   outResult.currentSpreadPoints = curSpread;
   outResult.medianSpreadPoints = medSpread;
   outResult.spreadRatio = ratio;

   // 0. Absolute Spread Ceiling
   if (m_maxSpreadCeiling > 0 && curSpread > m_maxSpreadCeiling)
   {
      outResult.failReason = "spread_exceeds_absolute_ceiling";
      return false;
   }

   // 1. Spread Spike Veto — require minimum history (F-06 warm-up policy)
   if (m_spreadCount >= B15_MIN_SAMPLES_FOR_RATIO && ratio > m_maxSpreadRatio)
   {
      outResult.failReason = "spread_spike_veto";
      return false;
   }

   // During warm-up (< B15_MIN_SAMPLES): block if spread > ceiling (already checked above)
   // otherwise allow — fail-closed via ceiling, not ratio

   // 2. Slippage Deviation Guard using configured deviation
   double currentPrice = (intent.action == ORDER_INTENT_BUY_MARKET) ? env.tick.ask : env.tick.bid;
   double devPts = MathAbs(intent.price - currentPrice) / (env.point > 0 ? env.point : 0.00001);
   outResult.priceDeviationPoints = devPts;

   if (devPts > maxDev)
   {
      outResult.failReason = "slippage_deviation_exceeded";
      return false;
   }

   // 3. Native MT5 OrderCheck with Symbol-Aware Filling (F-08)
   MqlTradeRequest req;
   ZeroMemory(req);
   req.action = TRADE_ACTION_DEAL;
   req.symbol = env.symbol;
   req.volume = intent.volume;
   req.type = (intent.action == ORDER_INTENT_BUY_MARKET) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   req.price = currentPrice;

   // Normalize SL/TP to tick grid for OrderCheck
   double tickSize = SymbolInfoDouble(env.symbol, SYMBOL_TRADE_TICK_SIZE);
   int symDigits = (int)SymbolInfoInteger(env.symbol, SYMBOL_DIGITS);
   if(tickSize > 0 && intent.stopLoss > 0)
   {
      double steps = MathFloor(intent.stopLoss / tickSize + 0.5);
      req.sl = NormalizeDouble(steps * tickSize, symDigits);
   }
   else
      req.sl = intent.stopLoss;

   if(tickSize > 0 && intent.takeProfit > 0)
   {
      double steps = MathFloor(intent.takeProfit / tickSize + 0.5);
      req.tp = NormalizeDouble(steps * tickSize, symDigits);
   }
   else
      req.tp = intent.takeProfit;

   req.deviation = (ulong)maxDev;

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
