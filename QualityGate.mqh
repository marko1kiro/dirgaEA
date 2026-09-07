//+------------------------------------------------------------------+
//|                                                  QualityGate.mqh |
//|                                  Copyright 2026, AdaptiveSurvival |
//|                                             https://www.mql5.com |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, AdaptiveSurvival"
#property link      "https://www.mql5.com"
#property strict

#include "Types.mqh"

#define B09_QUALITY_THRESHOLD    70.0
#define B09_MAX_SPREAD_RATIO     0.25

class CQualityGate
{
private:
   double                  m_threshold;

public:
                           CQualityGate(double threshold = B09_QUALITY_THRESHOLD);
                          ~CQualityGate();

   bool                    Evaluate(const TradeCandidate &cand,
                                    const RegimeResult &h1Regime,
                                    double currentSpreadPrice,
                                    QualityGateResult &outResult);
};

//+------------------------------------------------------------------+
//| Constructor                                                      |
//+------------------------------------------------------------------+
CQualityGate::CQualityGate(double threshold = B09_QUALITY_THRESHOLD)
{
   m_threshold = threshold;
}

//+------------------------------------------------------------------+
//| Destructor                                                       |
//+------------------------------------------------------------------+
CQualityGate::~CQualityGate()
{
}

//+------------------------------------------------------------------+
//| Evaluate TradeCandidate Quality                                  |
//+------------------------------------------------------------------+
bool CQualityGate::Evaluate(const TradeCandidate &cand,
                            const RegimeResult &h1Regime,
                            double currentSpreadPrice,
                            QualityGateResult &outResult)
{
   ZeroMemory(outResult);
   outResult.approved = false;
   outResult.totalScore = 0.0;

   // 1. Hard Veto Checks
   if (!cand.valid || cand.stopDistance <= 0)
   {
      outResult.rejectReason = "invalid_metrics";
      return false;
   }

   if (currentSpreadPrice > B09_MAX_SPREAD_RATIO * cand.stopDistance)
   {
      outResult.rejectReason = "excessive_spread";
      return false;
   }

   // 2. Reward-to-Risk Score (35 max)
   double scoreRR = 0.0;
   if (cand.rewardRiskRatio >= 2.0)
      scoreRR = 35.0;
   else if (cand.rewardRiskRatio >= 1.5)
      scoreRR = 25.0;
   else if (cand.rewardRiskRatio >= 1.0)
      scoreRR = 15.0;

   // 3. Regime Quality & Confidence Score (30 max)
   double scoreRegime = 5.0;
   if (h1Regime.quality == REGIME_QUALITY_STRONG && h1Regime.confidence >= 0.80)
      scoreRegime = 30.0;
   else if (h1Regime.quality == REGIME_QUALITY_NORMAL && h1Regime.confidence >= 0.60)
      scoreRegime = 20.0;

   // 4. Extension Score (20 max)
   double scoreExt = 0.0;
   if (cand.extensionAtr <= 1.8)
      scoreExt = 20.0;
   else if (cand.extensionAtr <= 2.2)
      scoreExt = 10.0;

   // 5. Spread Friction Score (15 max)
   double scoreSpread = 0.0;
   if (currentSpreadPrice <= 0.05 * cand.stopDistance)
      scoreSpread = 15.0;
   else if (currentSpreadPrice <= 0.10 * cand.stopDistance)
      scoreSpread = 10.0;

   double total = scoreRR + scoreRegime + scoreExt + scoreSpread;

   outResult.totalScore = total;
   outResult.scoreRewardRisk = scoreRR;
   outResult.scoreRegime = scoreRegime;
   outResult.scoreExtension = scoreExt;
   outResult.scoreSpread = scoreSpread;

   if (total >= m_threshold)
   {
      outResult.approved = true;
      outResult.rejectReason = "";
      return true;
   }

   outResult.approved = false;
   outResult.rejectReason = "low_quality_score";
   return false;
}
