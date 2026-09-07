//+------------------------------------------------------------------+
//|                                                 DashboardHUD.mqh |
//|                                  Copyright 2026, AdaptiveSurvival |
//|                                             https://www.mql5.com |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, AdaptiveSurvival"
#property link      "https://www.mql5.com"
#property strict

#include "Types.mqh"
#include "BrokerEnvironment.mqh"

class CDashboardHUD
{
public:
   static void Update(const BrokerEnvironment &env,
                      const RegimeResult &h1Regime,
                      const TradeCandidate &lastCand,
                      const QualityGateResult &lastQuality,
                      ulong magic,
                      int openPositions)
   {
      string regimeStr = "UNCERTAIN";
      switch(h1Regime.regime)
      {
         case REGIME_TREND_BULL:    regimeStr = "TREND_BULL"; break;
         case REGIME_TREND_BEAR:    regimeStr = "TREND_BEAR"; break;
         case REGIME_RANGE:         regimeStr = "RANGE"; break;
         case REGIME_BREAKOUT_BULL: regimeStr = "BREAKOUT_BULL"; break;
         case REGIME_BREAKOUT_BEAR: regimeStr = "BREAKOUT_BEAR"; break;
         default:                   regimeStr = "UNCERTAIN"; break;
      }

      string qualityStr = "NORMAL";
      switch(h1Regime.quality)
      {
         case REGIME_QUALITY_STRONG: qualityStr = "STRONG"; break;
         case REGIME_QUALITY_NORMAL: qualityStr = "NORMAL"; break;
         case REGIME_QUALITY_WEAK:   qualityStr = "WEAK"; break;
      }

      string activeStrategy = "NONE";
      if(h1Regime.regime == REGIME_TREND_BULL || h1Regime.regime == REGIME_TREND_BEAR)
         activeStrategy = "M15_TREND";
      else if(h1Regime.regime == REGIME_RANGE)
         activeStrategy = "M15_RANGE";
      else if(h1Regime.regime == REGIME_BREAKOUT_BULL || h1Regime.regime == REGIME_BREAKOUT_BEAR)
         activeStrategy = "M15_BREAKOUT";

      string text = "";
      text += "========================================\n";
      text += StringFormat(" ADAPTIVE SURVIVAL EA — [%s]\n", env.symbol);
      text += "========================================\n";
      text += StringFormat("EA Ready: %s | Trade Ready: %s\n", (env.tradeReady ? "YES" : "NO"), (env.tradeReady ? "YES" : "NO"));
      text += StringFormat("H1 Regime: %s | Quality: %s\n", regimeStr, qualityStr);
      text += StringFormat("Confidence: %.1f%%\n", h1Regime.confidence * 100.0);
      text += "----------------------------------------\n";
      text += StringFormat("Active Strategy: %s\n", activeStrategy);
      text += StringFormat("Quality Score: %.1f/100 (%s)\n", lastQuality.totalScore, (lastQuality.approved ? "APPROVED" : lastQuality.rejectReason));
      text += StringFormat("Open Positions: %d\n", openPositions);
      text += "========================================";

      Comment(text);
   }
};
