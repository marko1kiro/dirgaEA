#ifndef DIRGA_DAILY_RISK_LEDGER_MQH
#define DIRGA_DAILY_RISK_LEDGER_MQH
#property strict
#include "Logger.mqh"

// Account-equity daily loss guard. Terminal globals are restart persistence only;
// they do not coordinate separate terminal/VPS instances.
struct DailyClosedLifecycle
{
   ulong positionId;
   long closeTimeMsc;
   ulong closeDeal;
   double net;
};

class CDailyRiskLedger
{
private:
   string m_symbol;
   ulong m_magic;
   datetime m_dayStart;
   double m_baselineEquity;
   double m_baselineBalance;
   datetime m_capturedAt;
   double m_externalCashflow;
   double m_dailyLoss;
   int m_consecutiveLosses;
   int m_winningStreak;
   bool m_baselineReady;
   bool m_historyHealthy;
   bool m_dirty;

   datetime BrokerDayStart(const datetime now)
   {
      MqlDateTime dt; TimeToStruct(now,dt); dt.hour=0; dt.min=0; dt.sec=0;
      return StructToTime(dt);
   }

   int ServerFingerprint()
   {
      string server=AccountInfoString(ACCOUNT_SERVER);
      uint h=2166136261;
      for(int i=0;i<StringLen(server);++i) { h^=(uint)StringGetCharacter(server,i); h*=16777619; }
      return (int)(h&0x7fffffff);
   }

   string Prefix(const datetime day)
   {
      MqlDateTime dt; TimeToStruct(day,dt);
      int ymd=dt.year*10000+dt.mon*100+dt.day;
      return StringFormat("D2.%I64u.%d.%08d",AccountInfoInteger(ACCOUNT_LOGIN),ServerFingerprint(),ymd);
   }

   bool ValidNumber(const double v) { return MathIsValidNumber(v); }

   bool LoadBaseline(const datetime day)
   {
      string p=Prefix(day);
      if(!GlobalVariableCheck(p+".ok") || GlobalVariableGet(p+".ok")!=2.0 ||
         !GlobalVariableCheck(p+".eq") || !GlobalVariableCheck(p+".bal") || !GlobalVariableCheck(p+".at")) return false;
      double eq=GlobalVariableGet(p+".eq"),bal=GlobalVariableGet(p+".bal"),at=GlobalVariableGet(p+".at");
      if(!ValidNumber(eq) || !ValidNumber(bal) || !ValidNumber(at) || eq<=0.0 || bal<0.0 ||
         at<(double)day || at>=(double)(day+86400)) return false;
      m_baselineEquity=eq; m_baselineBalance=bal; m_capturedAt=(datetime)at; return true;
   }

   bool PersistBaseline(const datetime day,const double eq,const double bal,const datetime at)
   {
      if(!ValidNumber(eq) || !ValidNumber(bal) || eq<=0.0 || bal<0.0) return false;
      string p=Prefix(day);
      if(GlobalVariableCheck(p+".ok")) GlobalVariableDel(p+".ok");
      bool ok=GlobalVariableSet(p+".eq",eq) && GlobalVariableSet(p+".bal",bal) &&
              GlobalVariableSet(p+".at",(double)at) && GlobalVariableSet(p+".ok",2.0);
      GlobalVariablesFlush();
      if(!ok) return false;
      m_baselineEquity=eq; m_baselineBalance=bal; m_capturedAt=at; return true;
   }

   bool IsExternalCashflow(const ulong deal)
   {
      ENUM_DEAL_TYPE type=(ENUM_DEAL_TYPE)HistoryDealGetInteger(deal,DEAL_TYPE);
      return type==DEAL_TYPE_BALANCE || type==DEAL_TYPE_CREDIT || type==DEAL_TYPE_BONUS || type==DEAL_TYPE_CORRECTION;
   }

   double DealEconomics(const ulong deal)
   {
      return HistoryDealGetDouble(deal,DEAL_PROFIT)+HistoryDealGetDouble(deal,DEAL_COMMISSION)+
             HistoryDealGetDouble(deal,DEAL_SWAP)+HistoryDealGetDouble(deal,DEAL_FEE);
   }

   bool PositionStillLive(const ulong id)
   {
      for(int i=PositionsTotal()-1;i>=0;--i)
      {
         if(PositionGetTicket(i)>0 && (ulong)PositionGetInteger(POSITION_IDENTIFIER)==id) return true;
      }
      return false;
   }

   bool HasCrossMidnightLifecycle(const datetime day,const ulong &closedIds[],const int idCount)
   {
      for(int i=PositionsTotal()-1;i>=0;--i)
      {
         if(PositionGetTicket(i)>0 && (datetime)PositionGetInteger(POSITION_TIME)<day) return true;
      }
      for(int i=0;i<idCount;++i)
      {
         if(!HistorySelectByPosition(closedIds[i])) return true;
         int n=HistoryDealsTotal();
         for(int j=0;j<n;++j)
         {
            ulong d=HistoryDealGetTicket(j);
            if(d>0 && (datetime)HistoryDealGetInteger(d,DEAL_TIME)<day) return true;
         }
      }
      return false;
   }

   bool AddUniqueId(ulong &ids[],int &count,const ulong id)
   {
      if(id==0) return true;
      for(int i=0;i<count;++i) if(ids[i]==id) return true;
      if(ArrayResize(ids,count+1)!=count+1) return false;
      ids[count++]=id; return true;
   }

   bool BuildStreak(const datetime now,const ulong &closedIds[],const int idCount)
   {
      DailyClosedLifecycle rows[]; int count=0;
      for(int i=0;i<idCount;++i)
      {
         ulong id=closedIds[i];
         if(PositionStillLive(id)) continue; // partial close is not a lifecycle outcome
         if(!HistorySelectByPosition(id)) return false;
         int n=HistoryDealsTotal(); bool owned=false; bool hasOpen=false; double net=0.0;
         long lastMsc=0; ulong lastDeal=0; bool finalToday=false;
         for(int j=0;j<n;++j)
         {
            ulong d=HistoryDealGetTicket(j); if(d==0) return false;
            ENUM_DEAL_ENTRY entry=(ENUM_DEAL_ENTRY)HistoryDealGetInteger(d,DEAL_ENTRY);
            string symbol=HistoryDealGetString(d,DEAL_SYMBOL);
            long magic=HistoryDealGetInteger(d,DEAL_MAGIC);
            if(entry==DEAL_ENTRY_IN || entry==DEAL_ENTRY_INOUT)
            {
               hasOpen=true;
               if(symbol==m_symbol && magic==(long)m_magic) owned=true;
            }
            net+=DealEconomics(d); // includes entry commission and exit fee
            if(entry==DEAL_ENTRY_OUT || entry==DEAL_ENTRY_OUT_BY || entry==DEAL_ENTRY_INOUT)
            {
               long msc=HistoryDealGetInteger(d,DEAL_TIME_MSC);
               if(msc>lastMsc || (msc==lastMsc && d>lastDeal)) { lastMsc=msc; lastDeal=d; }
            }
         }
         if(!hasOpen || !owned || lastDeal==0) continue;
         datetime closeTime=(datetime)(lastMsc/1000);
         finalToday=closeTime>=m_dayStart && closeTime<now+1;
         if(!finalToday) continue;
         if(ArrayResize(rows,count+1)!=count+1) return false;
         rows[count].positionId=id; rows[count].closeTimeMsc=lastMsc; rows[count].closeDeal=lastDeal; rows[count].net=net; ++count;
      }
      for(int i=0;i<count-1;++i) for(int j=i+1;j<count;++j)
      {
         if(rows[j].closeTimeMsc<rows[i].closeTimeMsc ||
            (rows[j].closeTimeMsc==rows[i].closeTimeMsc && rows[j].closeDeal<rows[i].closeDeal))
         { DailyClosedLifecycle t=rows[i]; rows[i]=rows[j]; rows[j]=t; }
      }
      m_consecutiveLosses=0; m_winningStreak=0;
      for(int i=0;i<count;++i)
      {
         if(rows[i].net<-0.000001) { ++m_consecutiveLosses; m_winningStreak=0; }
         else if(rows[i].net>0.000001) { ++m_winningStreak; m_consecutiveLosses=0; }
      }
      return true;
   }

public:
   CDailyRiskLedger()
   {
      m_symbol=""; m_magic=0; m_dayStart=0; m_baselineEquity=0; m_baselineBalance=0; m_capturedAt=0;
      m_externalCashflow=0; m_dailyLoss=0; m_consecutiveLosses=0; m_winningStreak=0;
      m_baselineReady=false; m_historyHealthy=false; m_dirty=true;
   }
   void Configure(const string symbol,const ulong magic) { m_symbol=symbol; m_magic=magic; }
   void MarkDirty() { m_dirty=true; }
   bool RefreshIfRolloverOrDirty(const datetime now)
   {
      datetime day=BrokerDayStart(now);
      if(day!=m_dayStart || m_dirty) return Refresh(now);
      return m_baselineReady && m_historyHealthy;
   }
   bool Refresh(const datetime now)
   {
      datetime day=BrokerDayStart(now);
      if(day!=m_dayStart)
      {
         m_dayStart=day; m_baselineReady=LoadBaseline(day); m_historyHealthy=false; m_dirty=true;
         m_externalCashflow=0; m_dailyLoss=0; m_consecutiveLosses=0; m_winningStreak=0;
      }
      if(!HistorySelect(day,now)) { m_historyHealthy=false; LogWarning("DAILY_HISTORY_SELECT_FAILED",StringFormat("error=%d",GetLastError())); return false; }
      int total=HistoryDealsTotal(); ulong tickets[]; ArrayResize(tickets,total); ulong closedIds[]; int idCount=0;
      for(int i=0;i<total;++i)
      {
         tickets[i]=HistoryDealGetTicket(i); if(tickets[i]==0) { m_historyHealthy=false; return false; }
         ENUM_DEAL_ENTRY entry=(ENUM_DEAL_ENTRY)HistoryDealGetInteger(tickets[i],DEAL_ENTRY);
         if((entry==DEAL_ENTRY_OUT || entry==DEAL_ENTRY_OUT_BY || entry==DEAL_ENTRY_INOUT) &&
            !AddUniqueId(closedIds,idCount,(ulong)HistoryDealGetInteger(tickets[i],DEAL_POSITION_ID)))
         { m_historyHealthy=false; return false; }
      }
      if(!m_baselineReady)
      {
         if(now-day<=60)
            m_baselineReady=PersistBaseline(day,AccountInfoDouble(ACCOUNT_EQUITY),AccountInfoDouble(ACCOUNT_BALANCE),now);
         else if(!HasCrossMidnightLifecycle(day,closedIds,idCount))
         {
            double dayEconomics=0.0;
            for(int i=0;i<total;++i) dayEconomics+=DealEconomics(tickets[i]);
            double opening=AccountInfoDouble(ACCOUNT_BALANCE)-dayEconomics;
            m_baselineReady=PersistBaseline(day,opening,opening,now);
            if(m_baselineReady) LogWarning("DAILY_BASELINE_SAFE_BOOTSTRAP",StringFormat("equity=%.2f",opening));
         }
         if(!m_baselineReady) { m_historyHealthy=false; return false; }
      }
      m_externalCashflow=0.0;
      // Re-select because HistorySelectByPosition changes the selected history list.
      if(!HistorySelect(day,now)) { m_historyHealthy=false; return false; }
      total=HistoryDealsTotal();
      for(int i=0;i<total;++i)
      {
         ulong d=HistoryDealGetTicket(i); if(d==0) { m_historyHealthy=false; return false; }
         if(IsExternalCashflow(d)) m_externalCashflow+=HistoryDealGetDouble(d,DEAL_PROFIT);
      }
      double adjusted=AccountInfoDouble(ACCOUNT_EQUITY)-m_externalCashflow;
      if(!ValidNumber(adjusted)) { m_historyHealthy=false; return false; }
      m_dailyLoss=MathMax(0.0,m_baselineEquity-adjusted);
      if(!BuildStreak(now,closedIds,idCount)) { m_historyHealthy=false; return false; }
      m_historyHealthy=true; m_dirty=false; return true;
   }
   bool AllowsNewEntry(const datetime now,const double maxLossPercent,const int maxLosses,string &reason)
   {
      reason="";
      if(!Refresh(now)) { reason="daily_guard_history_or_baseline_unavailable"; return false; }
      if(m_dailyLoss>=m_baselineEquity*(maxLossPercent/100.0)) { reason="daily_loss_limit"; return false; }
      if(m_consecutiveLosses>=maxLosses) { reason="daily_consecutive_loss_limit"; return false; }
      return true;
   }
   bool IsReady() { return m_baselineReady && m_historyHealthy; }
   double DailyLoss() { return m_dailyLoss; }
   int ConsecutiveLosses() { return m_consecutiveLosses; }
};
#endif
