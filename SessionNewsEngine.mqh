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

   static ENUM_NEWS_STATE EvaluateNews(datetime serverTime, const datetime &highImpactTimes[], int count, string symbol = "")
   {
      ENUM_NEWS_STATE aggregatedState = NEWS_CLEAR;

      // 1. If explicit high-impact times are passed, evaluate them
      if (count > 0)
      {
         for (int i = 0; i < count; i++)
         {
            long diff = (long)highImpactTimes[i] - (long)serverTime;

            if (diff >= 0 && diff <= 1800)
               return NEWS_LOCK;
            if (diff < 0 && diff >= -900)
            {
               if (aggregatedState != NEWS_LOCK) aggregatedState = NEWS_SHOCK;
            }
            if (diff < -900 && diff >= -2700)
            {
               if (aggregatedState == NEWS_CLEAR) aggregatedState = NEWS_RECOVERY;
            }
         }
      }

      // 2. MT5 Native Economic Calendar evaluation (F-02) with currency filtering
      string baseCurr = "";
      string profitCurr = "";
      if (symbol != "")
      {
         baseCurr = SymbolInfoString(symbol, SYMBOL_CURRENCY_BASE);
         profitCurr = SymbolInfoString(symbol, SYMBOL_CURRENCY_PROFIT);
      }

      MqlCalendarValue values[];
      datetime fromTime = serverTime - 3600;
      datetime toTime = serverTime + 3600;

      int totalEvents = CalendarValueHistory(values, fromTime, toTime);
      if (totalEvents > 0)
      {
         for (int i = 0; i < totalEvents; i++)
         {
            MqlCalendarEvent event;
            if (CalendarEventById(values[i].event_id, event))
            {
               // Filter currency if specified
               if (baseCurr != "" && profitCurr != "")
               {
                  MqlCalendarCountry country;
                  if (CalendarCountryById(event.country_id, country))
                  {
                     if (country.currency != baseCurr && country.currency != profitCurr && country.currency != "USD")
                        continue;
                  }
               }

               if (event.importance == CALENDAR_IMPORTANCE_HIGH)
               {
                  long diff = (long)values[i].time - (long)serverTime;
                  if (diff >= 0 && diff <= 1800)
                     return NEWS_LOCK;
                  if (diff < 0 && diff >= -900)
                  {
                     if (aggregatedState != NEWS_LOCK) aggregatedState = NEWS_SHOCK;
                  }
                  if (diff < -900 && diff >= -2700)
                  {
                     if (aggregatedState == NEWS_CLEAR) aggregatedState = NEWS_RECOVERY;
                  }
               }
            }
         }
      }

      return aggregatedState;
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
