//+------------------------------------------------------------------+
//|                                              PositionManager.mqh |
//|                                  Copyright 2026, AdaptiveSurvival |
//|                                             https://www.mql5.com |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, AdaptiveSurvival"
#property link      "https://www.mql5.com"
#property strict

#include "Types.mqh"
#include "TrendStrategy.mqh"

#define B08_BE_R_MULT           1.0
#define B08_BE_ATR_BUFFER       0.10
#define B08_TRAILING_ATR_BUFFER 0.10

class CPositionManager
{
private:
   string                  m_symbol;
   ulong                   m_magic;

public:
                           CPositionManager(string symbol = "EURUSDm", ulong magic = 123456);
                          ~CPositionManager();

   void                    SetSymbol(string symbol) { m_symbol = symbol; }
   void                    SetMagic(ulong magic) { m_magic = magic; }

   bool                    Evaluate(ulong ticket,
                                    ENUM_TRADE_DIRECTION dir,
                                    double openPrice,
                                    double currentSl,
                                    double currentTp,
                                    double initialSl,
                                    double currentPrice,
                                    double atrM15,
                                    const RegimeResult &h1Regime,
                                    const B07_Swing &swings[],
                                    int swingsCount,
                                    datetime now,
                                    PositionManageIntent &outIntent);
};

//+------------------------------------------------------------------+
//| Constructor                                                      |
//+------------------------------------------------------------------+
CPositionManager::CPositionManager(string symbol = "EURUSDm", ulong magic = 123456)
{
   m_symbol = symbol;
   m_magic = magic;
}

//+------------------------------------------------------------------+
//| Destructor                                                       |
//+------------------------------------------------------------------+
CPositionManager::~CPositionManager()
{
}

//+------------------------------------------------------------------+
//| Evaluate position management actions                             |
//+------------------------------------------------------------------+
bool CPositionManager::Evaluate(ulong ticket,
                                ENUM_TRADE_DIRECTION dir,
                                double openPrice,
                                double currentSl,
                                double currentTp,
                                double initialSl,
                                double currentPrice,
                                double atrM15,
                                const RegimeResult &h1Regime,
                                const B07_Swing &swings[],
                                int swingsCount,
                                datetime now,
                                PositionManageIntent &outIntent)
{
   ZeroMemory(outIntent);
   outIntent.ticket = ticket;
   outIntent.action = POS_ACTION_NONE;

   // 1. Regime Invalidation Exit Check (only when confirmed valid regime is active)
   if (h1Regime.valid)
   {
      if (dir == TRADE_DIR_BUY && h1Regime.regime == REGIME_TREND_BEAR)
      {
         outIntent.action = POS_ACTION_CLOSE_MARKET;
         outIntent.reason = "regime_bear_flip";
         return true;
      }

      if (dir == TRADE_DIR_SELL && h1Regime.regime == REGIME_TREND_BULL)
      {
         outIntent.action = POS_ACTION_CLOSE_MARKET;
         outIntent.reason = "regime_bull_flip";
         return true;
      }
   }

   // 2. Risk Distance
   double riskDist = MathAbs(openPrice - initialSl);
   if (riskDist <= 0)
      return false;

   // 3. Breakeven Check
   double beTarget = (dir == TRADE_DIR_BUY) ? (openPrice + riskDist * B08_BE_R_MULT) : (openPrice - riskDist * B08_BE_R_MULT);
   double beSl = (dir == TRADE_DIR_BUY) ? (openPrice + B08_BE_ATR_BUFFER * atrM15) : (openPrice - B08_BE_ATR_BUFFER * atrM15);

   bool isBeReached = (dir == TRADE_DIR_BUY) ? (currentPrice >= beTarget) : (currentPrice <= beTarget);

   // 4. Trailing Stop Check (Swings)
   if (isBeReached)
   {
      double candidateSl = beSl;

      for (int i = swingsCount - 1; i >= 0; i--)
      {
         if (swings[i].ct > now) continue;

         if (dir == TRADE_DIR_BUY && swings[i].k == -1)
         {
            double potentialSl = swings[i].p - B08_TRAILING_ATR_BUFFER * atrM15;
            if (potentialSl > candidateSl)
               candidateSl = potentialSl;
            break;
         }
         else if (dir == TRADE_DIR_SELL && swings[i].k == 1)
         {
            double potentialSl = swings[i].p + B08_TRAILING_ATR_BUFFER * atrM15;
            if (potentialSl < candidateSl)
               candidateSl = potentialSl;
            break;
         }
      }

      // Ratchet Protection
      if (dir == TRADE_DIR_BUY)
      {
         if (candidateSl > currentSl + 1e-6)
         {
            outIntent.action = POS_ACTION_MODIFY_SL;
            outIntent.newStopLoss = candidateSl;
            outIntent.newTakeProfit = currentTp;
            outIntent.reason = "trailing_or_be";
            return true;
         }
      }
      else
      {
         if (currentSl <= 0 || candidateSl < currentSl - 1e-6)
         {
            outIntent.action = POS_ACTION_MODIFY_SL;
            outIntent.newStopLoss = candidateSl;
            outIntent.newTakeProfit = currentTp;
            outIntent.reason = "trailing_or_be";
            return true;
         }
      }
   }

   return false;
}
