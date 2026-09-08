//+------------------------------------------------------------------+
//|                                                RangeStrategy.mqh |
//|                                  Copyright 2026, AdaptiveSurvival |
//|                                             https://www.mql5.com |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, AdaptiveSurvival"
#property link      "https://www.mql5.com"
#property strict

#include "Types.mqh"
#include "TrendStrategy.mqh"

#define B11_STOP_BUF             0.10
#define B11_MIN_RANGE_HEIGHT_ATR 2.0

class CRangeStrategy
{
private:
   string                  m_symbol;
   RegimeResult            m_h1Regime;
   datetime                m_h1AvailableAt;
   bool                    m_hasH1Regime;

public:
                           CRangeStrategy(string symbol = "EURUSDm");
                          ~CRangeStrategy();

   void                    SetSymbol(const string symbol) { m_symbol= symbol; }
   void                    SetH1Regime(const RegimeResult &h1);
   void                    SetH1Regime(const RegimeResult &h1, const datetime availableAt);
   bool                    Evaluate(datetime t, double o, double h, double l, double c, datetime avail,
                                    double atr, const B07_Swing &swings[], int swingsCount,
                                    TradeCandidate &outCandidate);
};

//+------------------------------------------------------------------+
//| Constructor                                                      |
//+------------------------------------------------------------------+
CRangeStrategy::CRangeStrategy(string symbol = "EURUSDm")
{
   m_symbol = symbol;
   m_h1AvailableAt = 0;
   m_hasH1Regime = false;
   ZeroMemory(m_h1Regime);
}

//+------------------------------------------------------------------+
//| Destructor                                                       |
//+------------------------------------------------------------------+
CRangeStrategy::~CRangeStrategy()
{
}

//+------------------------------------------------------------------+
//| Set H1 Regime                                                    |
//+------------------------------------------------------------------+
void CRangeStrategy::SetH1Regime(const RegimeResult &h1)
{
   SetH1Regime(h1,h1.latestClosedH1);
}
void CRangeStrategy::SetH1Regime(const RegimeResult &h1,const datetime availableAt)
{
   m_h1Regime=h1; m_h1AvailableAt=availableAt; m_hasH1Regime=true;
}

//+------------------------------------------------------------------+
//| Evaluate Range Reversal Candidate                                |
//+------------------------------------------------------------------+
bool CRangeStrategy::Evaluate(datetime t, double o, double h, double l, double c, datetime avail,
                              double atr, const B07_Swing &swings[], int swingsCount,
                              TradeCandidate &outCandidate)
{
   ZeroMemory(outCandidate);

   if (!m_hasH1Regime || !m_h1Regime.valid || m_h1Regime.regime != REGIME_RANGE || atr <= 0)
      return false;

   bool hasHigh = false, hasLow = false;
   double rangeHigh = -1e9;
   double rangeLow = 1e9;

   for (int i = 0; i < swingsCount; i++)
   {
      if (swings[i].ct > avail) continue;

      if (swings[i].k == 1)
      {
         rangeHigh = MathMax(rangeHigh, swings[i].p);
         hasHigh = true;
      }
      else if (swings[i].k == -1)
      {
         rangeLow = MathMin(rangeLow, swings[i].p);
         hasLow = true;
      }
   }

   if (!hasHigh || !hasLow) return false;

   double rangeHeight = rangeHigh - rangeLow;
   if (rangeHeight < B11_MIN_RANGE_HEIGHT_ATR * atr)
      return false;

   // 1. Support Sweep Buy
   if (l < rangeLow && c > rangeLow && c < rangeHigh)
   {
      double sl = l - B11_STOP_BUF * atr;
      double tp = rangeHigh;
      if(!(sl < c && c < tp)) return false;
      double sd = c - sl;
      double rd = tp - c;
      double rr = (sd > 0) ? (rd / sd) : 0.0;

      outCandidate.valid = true;
      outCandidate.symbol = m_symbol;
      outCandidate.direction = TRADE_DIR_BUY;
      outCandidate.setupFamily = SETUP_FAMILY_RANGE_SWEEP;
      outCandidate.sourceRegime = m_h1Regime.regime;
      outCandidate.sourceRegimeQuality = m_h1Regime.quality;
      outCandidate.h1AvailableAt = m_h1AvailableAt;
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
      outCandidate.extensionReferencePrice = rangeLow;
      outCandidate.structuralReferenceTime = avail;
      outCandidate.qualificationReason = "range_support_sweep";
      return true;
   }

   // 2. Resistance Sweep Sell
   if (h > rangeHigh && c < rangeHigh && c > rangeLow)
   {
      double sl = h + B11_STOP_BUF * atr;
      double tp = rangeLow;
      if(!(tp < c && c < sl)) return false;
      double sd = sl - c;
      double rd = c - tp;
      double rr = (sd > 0) ? (rd / sd) : 0.0;

      outCandidate.valid = true;
      outCandidate.symbol = m_symbol;
      outCandidate.direction = TRADE_DIR_SELL;
      outCandidate.setupFamily = SETUP_FAMILY_RANGE_SWEEP;
      outCandidate.sourceRegime = m_h1Regime.regime;
      outCandidate.sourceRegimeQuality = m_h1Regime.quality;
      outCandidate.h1AvailableAt = m_h1AvailableAt;
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
      outCandidate.extensionReferencePrice = rangeHigh;
      outCandidate.structuralReferenceTime = avail;
      outCandidate.qualificationReason = "range_resistance_sweep";
      return true;
   }

   return false;
}
