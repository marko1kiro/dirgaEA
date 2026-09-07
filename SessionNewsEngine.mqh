//+------------------------------------------------------------------+
//|                                                SessionNewsEngine.mqh |
//|                                  Copyright 2026, AdaptiveSurvival |
//|                                             https://www.mql5.com |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, AdaptiveSurvival"
#property link      "https://www.mql5.com"
#property strict

#include "Types.mqh"

class CSessionNewsEngine
{
public:
   static ENUM_SESSION_STATE EvaluateSession(datetime serverTime)
   {
      MqlDateTime dt;
      TimeToStruct(serverTime, dt);
      int totalMins = dt.hour * 60 + dt.min;

      // Rollover: 23:45 to 00:15
      if (totalMins >= 1425 || totalMins < 15)
         return SESSION_ROLLOVER;

      // Core: 08:00 to 21:00
      if (totalMins >= 480 && totalMins < 1260)
         return SESSION_CORE;

      return SESSION_SECONDARY;
   }

   static ENUM_NEWS_STATE EvaluateNews(datetime serverTime, const datetime &highImpactTimes[], int count)
   {
      for (int i = 0; i < count; i++)
      {
         long diff = (long)highImpactTimes[i] - (long)serverTime;

         // 30 mins before
         if (diff >= 0 && diff <= 1800)
            return NEWS_LOCK;

         // 0 to 15 mins after
         if (diff < 0 && diff >= -900)
            return NEWS_SHOCK;

         // 15 to 45 mins after
         if (diff < -900 && diff >= -2700)
            return NEWS_RECOVERY;
      }
      return NEWS_CLEAR;
   }

   static bool CheckGating(ENUM_SESSION_STATE session, ENUM_NEWS_STATE news, double &outMinQualityScore, string &outBlockReason)
   {
      outBlockReason = "";
      outMinQualityScore = 70.0;

      if (session == SESSION_ROLLOVER)
      {
         outBlockReason = "session_rollover_block";
         return false;
      }

      if (news == NEWS_LOCK)
      {
         outBlockReason = "news_lock_pre_event";
         return false;
      }

      if (news == NEWS_SHOCK)
      {
         outBlockReason = "news_shock_post_event";
         return false;
      }

      if (session == SESSION_SECONDARY || news == NEWS_RECOVERY)
      {
         outMinQualityScore = 80.0; // Higher threshold required
      }

      return true;
   }
};
