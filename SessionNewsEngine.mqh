#ifndef DIRGA_SESSION_NEWS_ENGINE_MQH
#define DIRGA_SESSION_NEWS_ENGINE_MQH
#property strict
#include "Types.mqh"
#include "Logger.mqh"

#define NEWS_PRELOCK_SECONDS       1800
#define NEWS_SHOCK_SECONDS          900
#define NEWS_RECOVERY_SECONDS      2700
#define NEWS_CACHE_FUTURE_SLACK    1800
#define NEWS_FAILURE_RETRY_SECONDS   30

struct CachedNewsEvent
{
   ulong eventId;
   datetime eventTime;
};

class CSessionNewsEngine
{
private:
   static CachedNewsEvent s_events[];
   static datetime s_coverageFrom;
   static datetime s_coverageTo;
   static datetime s_lastFailure;
   static string s_currencyKey;
   static bool s_hasValidCache;

   static ENUM_NEWS_STATE AggregateState(ENUM_NEWS_STATE current,ENUM_NEWS_STATE candidate)
   {
      if(current==NEWS_UNKNOWN || candidate==NEWS_UNKNOWN) return NEWS_UNKNOWN;
      if(current==NEWS_LOCK || candidate==NEWS_LOCK) return NEWS_LOCK;
      if(current==NEWS_SHOCK || candidate==NEWS_SHOCK) return NEWS_SHOCK;
      if(current==NEWS_RECOVERY || candidate==NEWS_RECOVERY) return NEWS_RECOVERY;
      return NEWS_CLEAR;
   }
   static string CurrencyKey(string a,string b)
   {
      if(a==b) return a;
      return a<b ? a+"|"+b : b+"|"+a;
   }
   static bool CacheCovers(const datetime now,const string key)
   {
      return s_hasValidCache && s_currencyKey==key &&
             s_coverageFrom<=now-NEWS_RECOVERY_SECONDS &&
             s_coverageTo>=now+NEWS_PRELOCK_SECONDS;
   }
   static bool AppendUnique(CachedNewsEvent &events[],int &count,const ulong id,const datetime when)
   {
      for(int i=0;i<count;++i) if(events[i].eventId==id && events[i].eventTime==when) return true;
      if(ArrayResize(events,count+1)!=count+1) return false;
      events[count].eventId=id; events[count].eventTime=when; ++count; return true;
   }
   static bool FetchCurrency(const string currency,const datetime fromTime,const datetime toTime,
                             CachedNewsEvent &events[],int &count)
   {
      MqlCalendarValue values[];
      ResetLastError();
      int total=CalendarValueHistory(values,fromTime,toTime,NULL,currency);
      if(total<0) { LogWarning("CALENDAR_API_FAILED",StringFormat("currency=%s error=%d",currency,GetLastError())); return false; }
      for(int i=0;i<total;++i)
      {
         MqlCalendarEvent event;
         ResetLastError();
         if(!CalendarEventById(values[i].event_id,event))
         { LogWarning("CALENDAR_EVENT_RESOLVE_FAILED",StringFormat("event_id=%I64u error=%d",values[i].event_id,GetLastError())); return false; }
         if(event.importance==CALENDAR_IMPORTANCE_HIGH && !AppendUnique(events,count,values[i].event_id,values[i].time)) return false;
      }
      return true;
   }
   static bool RefreshCache(const datetime now,const string base,const string profit,const string key)
   {
      if(s_lastFailure>0 && now-s_lastFailure<NEWS_FAILURE_RETRY_SECONDS) return false;
      datetime fromTime=now-NEWS_RECOVERY_SECONDS;
      datetime toTime=now+NEWS_PRELOCK_SECONDS+NEWS_CACHE_FUTURE_SLACK;
      CachedNewsEvent temp[]; int count=0;
      if(!FetchCurrency(base,fromTime,toTime,temp,count) ||
         (profit!=base && !FetchCurrency(profit,fromTime,toTime,temp,count)))
      { s_lastFailure=now; return false; }
      ArrayResize(s_events,count); for(int i=0;i<count;++i) s_events[i]=temp[i];
      s_coverageFrom=fromTime; s_coverageTo=toTime; s_currencyKey=key; s_hasValidCache=true; s_lastFailure=0;
      return true;
   }
   static ENUM_NEWS_STATE EvaluateTimes(const datetime now,const datetime &times[],const int count)
   {
      ENUM_NEWS_STATE state=NEWS_CLEAR;
      for(int i=0;i<count;++i)
      {
         long diff=(long)times[i]-(long)now;
         if(diff>=0 && diff<=NEWS_PRELOCK_SECONDS) state=AggregateState(state,NEWS_LOCK);
         else if(diff<0 && diff>=-NEWS_SHOCK_SECONDS) state=AggregateState(state,NEWS_SHOCK);
         else if(diff<-NEWS_SHOCK_SECONDS && diff>=-NEWS_RECOVERY_SECONDS) state=AggregateState(state,NEWS_RECOVERY);
      }
      return state;
   }
public:
   static ENUM_SESSION_STATE EvaluateSession(datetime serverTime)
   {
      MqlDateTime dt; TimeToStruct(serverTime,dt); int mins=dt.hour*60+dt.min;
      if(mins>=1425 || mins<15) return SESSION_ROLLOVER;
      if(mins>=480 && mins<1260) return SESSION_CORE;
      return SESSION_SECONDARY;
   }
   static ENUM_NEWS_STATE EvaluateNews(datetime serverTime,const datetime &highImpactTimes[],int count,string symbol="")
   {
      ENUM_NEWS_STATE explicitState=EvaluateTimes(serverTime,highImpactTimes,count);
      if(symbol=="") return explicitState;
      ResetLastError(); string base=SymbolInfoString(symbol,SYMBOL_CURRENCY_BASE);
      if(base=="" || GetLastError()!=0) return AggregateState(explicitState,NEWS_UNKNOWN);
      ResetLastError(); string profit=SymbolInfoString(symbol,SYMBOL_CURRENCY_PROFIT);
      if(profit=="" || GetLastError()!=0) return AggregateState(explicitState,NEWS_UNKNOWN);
      string key=CurrencyKey(base,profit);
      if(!CacheCovers(serverTime,key) && !RefreshCache(serverTime,base,profit,key))
         return AggregateState(explicitState,NEWS_UNKNOWN);
      datetime times[]; int n=ArraySize(s_events); ArrayResize(times,n);
      for(int i=0;i<n;++i) times[i]=s_events[i].eventTime;
      return AggregateState(explicitState,EvaluateTimes(serverTime,times,n));
   }
   static bool CheckGating(ENUM_SESSION_STATE session,ENUM_NEWS_STATE news,double &outMinQualityScore,string &outBlockReason)
   {
      outBlockReason=""; outMinQualityScore=70.0;
      if(session==SESSION_ROLLOVER) { outBlockReason="session_rollover_block"; return false; }
      if(news==NEWS_UNKNOWN) { outBlockReason="news_calendar_unavailable"; return false; }
      if(news==NEWS_LOCK) { outBlockReason="news_lock_pre_event"; return false; }
      if(news==NEWS_SHOCK) { outBlockReason="news_shock_post_event"; return false; }
      if(session==SESSION_SECONDARY || news==NEWS_RECOVERY) outMinQualityScore=80.0;
      return true;
   }
};
CachedNewsEvent CSessionNewsEngine::s_events[];
datetime CSessionNewsEngine::s_coverageFrom=0;
datetime CSessionNewsEngine::s_coverageTo=0;
datetime CSessionNewsEngine::s_lastFailure=0;
string CSessionNewsEngine::s_currencyKey="";
bool CSessionNewsEngine::s_hasValidCache=false;
#endif
