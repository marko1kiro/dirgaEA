#property strict

#include "../../../TrendStrategy.mqh"

int failures = 0;

void RunVectorTest()
{
   Print("Starting BUILD 07 Native Parity Probe...");

   CTrendStrategy strat("EURUSDm");
   RegimeResult h1;
   ZeroMemory(h1);
   h1.valid = true;
   h1.regime = REGIME_TREND_BULL;
   h1.quality = REGIME_QUALITY_NORMAL;
   h1.latestClosedH1 = 1700000000;
   strat.SetH1Regime(h1);

   datetime t = 1700000000;
   double atr = 0.0010;
   TradeCandidate cand;

   // Synthetic run of bars
   for (int i = 0; i < 20; i++)
   {
      datetime barT = t + i * 900;
      datetime availT = barT + 900;
      double o = 1.0500 + i * 0.0002;
      double h = o + 0.0005;
      double l = o - 0.0002;
      double c = o + 0.0003;

      bool emitted = strat.FeedM15Bar(barT, o, h, l, c, availT, atr, cand);
      string hash = strat.GetB07D1Hash(cand);
      Print(StringFormat("bar=%d|emitted=%d|hash=%s", i, (emitted ? 1 : 0), hash));
   }

   Print("BUILD 07 Parity Probe completed. Failures: ", failures);
}

void OnStart()
{
   RunVectorTest();
}
