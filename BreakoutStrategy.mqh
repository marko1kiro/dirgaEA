//+------------------------------------------------------------------+
//|                                             BreakoutStrategy.mqh |
//|                                  Copyright 2026, AdaptiveSurvival |
//|                                             https://www.mql5.com |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, AdaptiveSurvival"
#property link      "https://www.mql5.com"
#property strict

#include "Types.mqh"
#include "TrendStrategy.mqh"

#define B12_STOP_BUF             0.10
#define B12_MIN_PENETRATION_ATR  0.15
#define B12_MAX_CHASE_ATR        1.5

class CBreakoutStrategy
{
private:
   string                  m_symbol;
   RegimeResult            m_h1Regime;
   bool                    m_hasH1Regime;

public:
                           CBreakoutStrategy(string symbol = "EURUSDm");
                          ~CBreakoutStrategy();

   void                    SetH1Regime(const RegimeResult &h1);
   bool                    Evaluate(datetime t, double o, double h, double l, double c, datetime avail,
                                    double atr, const B07_Swing &swings[], int swingsCount,
                                    TradeCandidate &outCandidate);
};

//+------------------------------------------------------------------+
//| Constructor                                                      |
//+------------------------------------------------------------------+
CBreakoutStrategy::CBreakoutStrategy(string symbol = "EURUSDm")
{
   m_symbol = symbol;
   m_hasH1Regime = false;
   ZeroMemory(m_h1Regime);
}

//+------------------------------------------------------------------+
//| Destructor                                                       |
//+------------------------------------------------------------------+
CBreakoutStrategy::~CBreakoutStrategy()
{
}

//+------------------------------------------------------------------+
//| Set H1 Regime                                                    |
//+------------------------------------------------------------------+
void CBreakoutStrategy::SetH1Regime(const RegimeResult &h1)
{
   m_h1Regime = h1;
   m_hasH1Regime = true;
}

//+------------------------------------------------------------------+
//| Evaluate Breakout Candidate                                      |
//+------------------------------------------------------------------+
bool CBreakoutStrategy::Evaluate(datetime t, double o, double h, double l, double c, datetime avail,
                                 double atr, const B07_Swing &swings[], int swingsCount,
                                 TradeCandidate &outCandidate)
{
   ZeroMemory(outCandidate);

   if (!m_hasH1Regime || !m_h1Regime.valid || atr <= 0)
      return false;

   // 1. Bullish Breakout
   if (m_h1Regime.regime == REGIME_BREAKOUT_BULL)
   {
      bool foundLevel = false;
      double level = -1e9;

      for (int i = 0; i < swingsCount; i++)
      {
         if (swings[i].ct > avail) continue;
         if (swings[i].k == 1)
         {
            level = MathMax(level, swings[i].p);
            foundLevel = true;
         }
      }

      if (!foundLevel) return false;

      double penetration = c - level;
      if (penetration < B12_MIN_PENETRATION_ATR * atr)
         return false;
      if (penetration > B12_MAX_CHASE_ATR * atr)
         return false;

      double sl = l - B12_STOP_BUF * atr;
      double sd = MathAbs(c - sl);
      double tp = c + 1.5 * sd;
      double rd = MathAbs(tp - c);
      double rr = (sd > 0) ? (rd / sd) : 0.0;

      outCandidate.valid = true;
      outCandidate.symbol = m_symbol;
      outCandidate.direction = TRADE_DIR_BUY;
      outCandidate.setupFamily = SETUP_FAMILY_BREAKOUT_DIRECT;
      outCandidate.sourceRegime = m_h1Regime.regime;
      outCandidate.sourceRegimeQuality = m_h1Regime.quality;
      outCandidate.h1AvailableAt = m_h1Regime.latestClosedH1;
      outCandidate.h1SourceBarTime = m_h1Regime.latestClosedH1;
      outCandidate.m15BarTime = t;
      outCandidate.m15AvailableAt = avail;
      outCandidate.entryPrice = c;
      outCandidate.invalidationPrice = l;
      outCandidate.initialStopPrice = sl;
      outCandidate.stopDistance = sd;
      outCandidate.stopDistanceAtr = (atr > 0) ? (sd / atr) : 0.0;
      outCandidate.targetPrice = tp;
      outCandidate.rewardDistance = rd;
      outCandidate.rewardRiskRatio = rr;
      outCandidate.qualificationReason = "breakout_direct_bull";
      return true;
   }

   // 2. Bearish Breakout
   if (m_h1Regime.regime == REGIME_BREAKOUT_BEAR)
   {
      bool foundLevel = false;
      double level = 1e9;

      for (int i = 0; i < swingsCount; i++)
      {
         if (swings[i].ct > avail) continue;
         if (swings[i].k == -1)
         {
            level = MathMin(level, swings[i].p);
            foundLevel = true;
         }
      }

      if (!foundLevel) return false;

      double penetration = level - c;
      if (penetration < B12_MIN_PENETRATION_ATR * atr)
         return false;
      if (penetration > B12_MAX_CHASE_ATR * atr)
         return false;

      double sl = h + B12_STOP_BUF * atr;
      double sd = MathAbs(sl - c);
      double tp = c - 1.5 * sd;
      double rd = MathAbs(c - tp);
      double rr = (sd > 0) ? (rd / sd) : 0.0;

      outCandidate.valid = true;
      outCandidate.symbol = m_symbol;
      outCandidate.direction = TRADE_DIR_SELL;
      outCandidate.setupFamily = SETUP_FAMILY_BREAKOUT_DIRECT;
      outCandidate.sourceRegime = m_h1Regime.regime;
      outCandidate.sourceRegimeQuality = m_h1Regime.quality;
      outCandidate.h1AvailableAt = m_h1Regime.latestClosedH1;
      outCandidate.h1SourceBarTime = m_h1Regime.latestClosedH1;
      outCandidate.m15BarTime = t;
      outCandidate.m15AvailableAt = avail;
      outCandidate.entryPrice = c;
      outCandidate.invalidationPrice = h;
      outCandidate.initialStopPrice = sl;
      outCandidate.stopDistance = sd;
      outCandidate.stopDistanceAtr = (atr > 0) ? (sd / atr) : 0.0;
      outCandidate.targetPrice = tp;
      outCandidate.rewardDistance = rd;
      outCandidate.rewardRiskRatio = rr;
      outCandidate.qualificationReason = "breakout_direct_bear";
      return true;
   }

   return false;
}
