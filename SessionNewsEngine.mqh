//+------------------------------------------------------------------+
//|                                                SessionNewsEngine.mqh |
//|                                  Copyright 2026, AdaptiveSurvival |
//|                                             https://www.mql5.com |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, AdaptiveSurvival"
#property link      "https://www.mql5.com"
#property strict

#include "Types.mqh"

// Calendar freshness TTL: re-fetch every 5 minutes so the 30-minute pre-news
// LOCK window (H-1) can never be masked by a stale cached CLEAR. Must stay
// << NEWS_LOCK_WINDOW_SECONDS (1800).
#define NEWS_CALENDAR_TTL_SECONDS 300
// On calendar API failure the fail-closed NEWS_UNKNOWN state is cached only
// briefly (M-4) so a transient error retries quickly instead of halting
// trading for a full TTL.
#define NEWS_CALENDAR_FAILURE_TTL_SECONDS 120
// Maximum age for calendar data before considering it stale
#define NEWS_CALENDAR_MAX_AGE 1800
// Calendar query lookback: must cover the full NEWS_RECOVERY window
// (diff in [-2700, -900)) so post-news quality tightening applies (M-1)
#define NEWS_RECOVERY_LOOKBACK_SECONDS 2700

class CSessionNewsEngine
{
private:
   // Cache: last fetch time and result (N-05)
   static datetime s_lastFetchTime;
   static ENUM_NEWS_STATE s_lastFetchResult;
   static bool s_calendarAvailable;

   // Aggregate events with priority: LOCK > SHOCK > RECOVERY > CLEAR
   static ENUM_NEWS_STATE AggregateState(ENUM_NEWS_STATE current, ENUM_NEWS_STATE candidate)
   {
      if(candidate == NEWS_LOCK) return NEWS_LOCK;
      if(candidate == NEWS_SHOCK && current != NEWS_LOCK) return NEWS_SHOCK;
      if(candidate == NEWS_RECOVERY && current == NEWS_CLEAR) return NEWS_RECOVERY;
      return current;
   }

public:
   static ENUM_SESSION_STATE EvaluateSession(datetime serverTime)
   {
      MqlDateTime dt;
      TimeToStruct(serverTime, dt);
      int totalMins = dt.hour * 60 + dt.min;

      if (totalMins >= 1425 || totalMins < 15)
         return SESSION_ROLLOVER;

      if (totalMins >= 480 && totalMins < 1260)
         return SESSION_CORE;

      return SESSION_SECONDARY;
   }

   // Evaluate news with full fail-closed calendar handling (F-02, N-05)
   static ENUM_NEWS_STATE EvaluateNews(datetime serverTime, const datetime &highImpactTimes[],
                                        int count, string symbol = "")
   {
      ENUM_NEWS_STATE aggregatedState = NEWS_CLEAR;

      // 1. Evaluate explicit high-impact times
      if (count > 0)
      {
         for (int i = 0; i < count; i++)
         {
            long diff = (long)highImpactTimes[i] - (long)serverTime;

            if (diff >= 0 && diff <= 1800)
               return NEWS_LOCK;
            if (diff < 0 && diff >= -900)
               aggregatedState = AggregateState(aggregatedState, NEWS_SHOCK);
            if (diff < -900 && diff >= -2700)
               aggregatedState = AggregateState(aggregatedState, NEWS_RECOVERY);
         }
      }

      // 2. MT5 Native Economic Calendar (F-02)
      if(symbol == "")
         return aggregatedState;

      string baseCurr = SymbolInfoString(symbol, SYMBOL_CURRENCY_BASE);
      string profitCurr = SymbolInfoString(symbol, SYMBOL_CURRENCY_PROFIT);
      if(baseCurr == "" || profitCurr == "")
         return aggregatedState;

      // Check freshness: if we fetched recently, use cached result
      if(s_lastFetchTime > 0 && serverTime - s_lastFetchTime < NEWS_CALENDAR_TTL_SECONDS)
         return AggregateState(aggregatedState, s_lastFetchResult);

      MqlCalendarValue values[];
      datetime fromTime = serverTime - NEWS_RECOVERY_LOOKBACK_SECONDS;
      datetime toTime = serverTime + NEWS_CALENDAR_MAX_AGE;

      ResetLastError();
      int totalEvents = CalendarValueHistory(values, fromTime, toTime);
      int calError = GetLastError();

      // Calendar API failed → NEWS_UNKNOWN (fail-closed), cached only for the
      // short failure TTL so a transient error retries within minutes (M-4).
      if(totalEvents < 0)
      {
         s_lastFetchTime = serverTime - (NEWS_CALENDAR_TTL_SECONDS - NEWS_CALENDAR_FAILURE_TTL_SECONDS);
         s_lastFetchResult = NEWS_UNKNOWN;
         s_calendarAvailable = false;
         LogWarning("CALENDAR_API_FAILED", StringFormat("error=%d", calError));
         return NEWS_UNKNOWN;
      }

      // No events returned — valid empty result
      s_calendarAvailable = true;
      ENUM_NEWS_STATE calendarState = NEWS_CLEAR;

      if(totalEvents > 0)
      {
         for(int i = 0; i < totalEvents; i++)
         {
            MqlCalendarEvent event;
            if(!CalendarEventById(values[i].event_id, event))
            {
               // Event resolution failed — treat as unknown (fail-closed)
               LogWarning("CALENDAR_EVENT_RESOLVE_FAILED",
                         StringFormat("event_id=%d", values[i].event_id));
               calendarState = AggregateState(calendarState, NEWS_UNKNOWN);
               continue;
            }

            // Filter by relevant currencies only
            MqlCalendarCountry country;
            if(!CalendarCountryById(event.country_id, country))
            {
               // Country resolution failed — fail-closed like event resolution
               // (M-2): a HIGH-importance event must never be silently skipped.
               LogWarning("CALENDAR_COUNTRY_RESOLVE_FAILED",
                         StringFormat("country_id=%d", event.country_id));
               calendarState = AggregateState(calendarState, NEWS_UNKNOWN);
               continue;
            }

            bool relevant = (country.currency == baseCurr || country.currency == profitCurr);
            if(!relevant)
               continue;

            if(event.importance == CALENDAR_IMPORTANCE_HIGH)
            {
               long diff = (long)values[i].time - (long)serverTime;
               if(diff >= 0 && diff <= 1800)
               {
                  s_lastFetchTime = serverTime;
                  s_lastFetchResult = NEWS_LOCK;
                  return NEWS_LOCK;
               }
               if(diff < 0 && diff >= -900)
                  calendarState = AggregateState(calendarState, NEWS_SHOCK);
               if(diff < -900 && diff >= -2700)
                  calendarState = AggregateState(calendarState, NEWS_RECOVERY);
            }
         }
      }

      // Cache result (N-05)
      s_lastFetchTime = serverTime;
      s_lastFetchResult = calendarState;

      return AggregateState(aggregatedState, calendarState);
   }

   // M-3: the NewsGuardRequired input is honored here. When true (default)
   // the guard stays fail-closed; when false, NEWS_UNKNOWN no longer blocks
   // entry — the operator explicitly trades without a calendar, at own risk.
   static bool CheckGating(ENUM_SESSION_STATE session, ENUM_NEWS_STATE news, double &outMinQualityScore, string &outBlockReason, bool newsGuardRequired = true)
   {
      outBlockReason = "";
      outMinQualityScore = 70.0;

      if (session == SESSION_ROLLOVER)
      {
         outBlockReason = "session_rollover_block";
         return false;
      }

      // Fail-closed: NEWS_UNKNOWN blocks entry unless the guard is disabled (F-02, N-05, M-3)
      if (news == NEWS_UNKNOWN && newsGuardRequired)
      {
         outBlockReason = "news_calendar_unavailable";
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
         outMinQualityScore = 80.0;
      }

      return true;
   }
};

// Static member initialization
datetime CSessionNewsEngine::s_lastFetchTime = 0;
ENUM_NEWS_STATE CSessionNewsEngine::s_lastFetchResult = NEWS_CLEAR;
bool CSessionNewsEngine::s_calendarAvailable = true;
