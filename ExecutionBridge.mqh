//+------------------------------------------------------------------+
//| Atomic execution bridge, persistent submission journal          |
//+------------------------------------------------------------------+
#property strict
#include "Types.mqh"
#include "BrokerEnvironment.mqh"
#include "RiskEngine.mqh"
#include "Logger.mqh"
#include "InitialStopStore.mqh"

#define DIRGA_LOCK_MAX_GENERATION 9007199254740991.0
#define DIRGA_PENDING_CLEAR       0.0
#define DIRGA_PENDING_WRITING     1.0
#define DIRGA_PENDING_UNRESOLVED  2.0
#define DIRGA_PENDING_TIMEOUT     3.0

static ulong s_intentSequence=0;

class CExecutionBridge
{
private:
   string m_symbol;
   ulong m_magic;
   int m_maxPositions;
   string m_lockVarName;
   double m_lockGeneration;
   bool m_lockHeld;
   uint m_lockLeaseSeconds;
   ENUM_EXECUTION_LIFECYCLE m_lifecycle;
   ulong m_pendingOrderTicket;
   ulong m_pendingDealTicket;
   datetime m_pendingSubmitTime;
   double m_pendingInitialSl;
   double m_pendingVolume;
   ulong m_pendingIntentId;
   ENUM_TRADE_DIRECTION m_pendingDirection;
   double m_riskPercent;
   double m_hardRiskCapPercent;
   double m_minVolumeTolerancePercent;
   double m_marginReservePercent;

   string Namespace()
   { return StringFormat("%I64u.%s.%I64u",AccountInfoInteger(ACCOUNT_LOGIN),m_symbol,m_magic); }
   string LockKey() { return "D2.L."+Namespace(); }
   string PendingKey(const string suffix) { return "D2.P."+Namespace()+"."+suffix; }

   bool EnsureLockExists()
   {
      // GlobalVariableSetOnCondition cannot create an absent key. GlobalVariableTemp
      // performs the one atomic zero bootstrap; every subsequent mutation is CAS.
      if(GlobalVariableCheck(LockKey())) return true;
      return GlobalVariableTemp(LockKey());
   }

   bool CasLock(const double expected,const double replacement)
   { return GlobalVariableSetOnCondition(LockKey(),replacement,expected); }

   bool ReadLock(double &state,datetime &changedAt)
   {
      state=0.0; changedAt=0;
      if(!GlobalVariableCheck(LockKey())) return true;
      ResetLastError(); state=GlobalVariableGet(LockKey());
      if(GetLastError()!=0 || !MathIsValidNumber(state) ||
         MathFloor(MathAbs(state))!=MathAbs(state)) return false;
      changedAt=GlobalVariableTime(LockKey());
      return changedAt>0;
   }

   double PendingState()
   {
      if(!GlobalVariableCheck(PendingKey("state"))) return DIRGA_PENDING_CLEAR;
      ResetLastError(); const double v=GlobalVariableGet(PendingKey("state"));
      if(GetLastError()!=0 || !MathIsValidNumber(v)) return -1.0;
      return v;
   }

   bool SelectFilling(ENUM_ORDER_TYPE_FILLING &out)
   {
      const uint mode=(uint)SymbolInfoInteger(m_symbol,SYMBOL_FILLING_MODE);
      if((mode&SYMBOL_FILLING_FOK)!=0) { out=ORDER_FILLING_FOK; return true; }
      if((mode&SYMBOL_FILLING_IOC)!=0) { out=ORDER_FILLING_IOC; return true; }
      const ENUM_SYMBOL_TRADE_EXECUTION ex=(ENUM_SYMBOL_TRADE_EXECUTION)SymbolInfoInteger(m_symbol,SYMBOL_TRADE_EXEMODE);
      if(ex!=SYMBOL_TRADE_EXECUTION_MARKET) { out=ORDER_FILLING_RETURN; return true; }
      return false;
   }

   ulong NextIntentId()
   {
      ++s_intentSequence;
      return (ulong)TimeLocal()*1000ULL+(s_intentSequence%1000ULL);
   }

   bool SavePendingJournalWriting(const FinalMarketOrder &plan)
   {
      if(!m_lockHeld || !GlobalVariableSet(PendingKey("state"),DIRGA_PENDING_WRITING)) return false;
      bool ok=true;
      ok=ok && GlobalVariableSet(PendingKey("intent"),(double)plan.intentId);
      ok=ok && GlobalVariableSet(PendingKey("time"),(double)TimeCurrent());
      ok=ok && GlobalVariableSet(PendingKey("order"),0.0);
      ok=ok && GlobalVariableSet(PendingKey("deal"),0.0);
      ok=ok && GlobalVariableSet(PendingKey("side"),(double)plan.direction);
      ok=ok && GlobalVariableSet(PendingKey("sl"),plan.request.sl);
      ok=ok && GlobalVariableSet(PendingKey("tp"),plan.request.tp);
      ok=ok && GlobalVariableSet(PendingKey("vol"),plan.request.volume);
      if(!ok || !GlobalVariableSet(PendingKey("state"),DIRGA_PENDING_UNRESOLVED)) return false;
      GlobalVariablesFlush();
      m_pendingSubmitTime=TimeCurrent(); m_pendingOrderTicket=0; m_pendingDealTicket=0;
      m_pendingInitialSl=plan.request.sl; m_pendingVolume=plan.request.volume;
      m_pendingIntentId=plan.intentId; m_pendingDirection=plan.direction;
      return true;
   }

   bool MarkPendingJournalSent(const MqlTradeResult &result)
   {
      bool ok=true;
      ok=ok && GlobalVariableSet(PendingKey("order"),(double)result.order);
      ok=ok && GlobalVariableSet(PendingKey("deal"),(double)result.deal);
      ok=ok && GlobalVariableSet(PendingKey("ret"),(double)result.retcode);
      ok=ok && GlobalVariableSet(PendingKey("state"),DIRGA_PENDING_UNRESOLVED);
      GlobalVariablesFlush();
      m_pendingOrderTicket=result.order; m_pendingDealTicket=result.deal;
      return ok;
   }

   void ClearPendingJournal()
   {
      GlobalVariableSet(PendingKey("state"),DIRGA_PENDING_CLEAR);
      string suffixes[]={"intent","time","order","deal","side","sl","tp","vol","ret"};
      for(int i=0;i<ArraySize(suffixes);++i)
         if(GlobalVariableCheck(PendingKey(suffixes[i]))) GlobalVariableDel(PendingKey(suffixes[i]));
      GlobalVariablesFlush();
      m_pendingOrderTicket=0; m_pendingDealTicket=0; m_pendingSubmitTime=0;
      m_pendingInitialSl=0.0; m_pendingVolume=0.0; m_pendingIntentId=0; m_pendingDirection=TRADE_DIR_NONE;
   }

   bool IsTerminalRejection(const ENUM_ORDER_STATE state)
   { return state==ORDER_STATE_CANCELED || state==ORDER_STATE_EXPIRED || state==ORDER_STATE_REJECTED; }

   bool PersistInitialStopForDeal(const ulong deal)
   {
      if(deal==0 || !HistoryDealSelect(deal)) return false;
      if(HistoryDealGetString(deal,DEAL_SYMBOL)!=m_symbol ||
         HistoryDealGetInteger(deal,DEAL_MAGIC)!=(long)m_magic) return false;
      ENUM_DEAL_ENTRY entry=(ENUM_DEAL_ENTRY)HistoryDealGetInteger(deal,DEAL_ENTRY);
      if(entry!=DEAL_ENTRY_IN && entry!=DEAL_ENTRY_INOUT) return false;
      ulong positionId=(ulong)HistoryDealGetInteger(deal,DEAL_POSITION_ID);
      CInitialStopStore store; store.Configure(m_symbol,m_magic);
      return store.Save(positionId,m_pendingInitialSl);
   }

   bool PersistInitialStopsForOrder(const ulong order)
   {
      if(order==0) return false;
      int total=HistoryDealsTotal(); bool found=false;
      for(int i=0;i<total;++i)
      {
         ulong deal=HistoryDealGetTicket(i); if(deal==0) return false;
         if((ulong)HistoryDealGetInteger(deal,DEAL_ORDER)!=order) continue;
         ENUM_DEAL_ENTRY entry=(ENUM_DEAL_ENTRY)HistoryDealGetInteger(deal,DEAL_ENTRY);
         if(entry!=DEAL_ENTRY_IN && entry!=DEAL_ENTRY_INOUT) continue;
         if(!PersistInitialStopForDeal(deal)) return false;
         found=true;
      }
      return found;
   }

   bool RecoverUnknownTicketFromHistory()
   {
      if(m_pendingSubmitTime<=0 || !HistorySelect(m_pendingSubmitTime-120,TimeCurrent())) return false;
      string token=StringFormat("D2:%I64u",m_pendingIntentId);
      ulong tokenDeal=0,heuristicDeal=0; int tokenMatches=0,heuristicMatches=0;
      int total=HistoryDealsTotal();
      for(int i=0;i<total;++i)
      {
         ulong deal=HistoryDealGetTicket(i); if(deal==0) continue;
         if(HistoryDealGetString(deal,DEAL_SYMBOL)!=m_symbol || HistoryDealGetInteger(deal,DEAL_MAGIC)!=(long)m_magic) continue;
         ENUM_DEAL_TYPE type=(ENUM_DEAL_TYPE)HistoryDealGetInteger(deal,DEAL_TYPE);
         if((m_pendingDirection==TRADE_DIR_BUY && type!=DEAL_TYPE_BUY) ||
            (m_pendingDirection==TRADE_DIR_SELL && type!=DEAL_TYPE_SELL)) continue;
         string comment=HistoryDealGetString(deal,DEAL_COMMENT);
         if(m_pendingIntentId>0 && StringFind(comment,token)>=0)
         { tokenDeal=deal; ++tokenMatches; continue; }
         // Legacy/no-comment fallback is deliberately exact and unique.
         if(comment!="") continue;
         double volume=HistoryDealGetDouble(deal,DEAL_VOLUME);
         if(MathAbs(volume-m_pendingVolume)>MathMax(0.0000001,SymbolInfoDouble(m_symbol,SYMBOL_VOLUME_STEP)/2.0)) continue;
         heuristicDeal=deal; ++heuristicMatches;
      }
      if(tokenMatches>0) { m_pendingDealTicket=tokenDeal; return true; } // partial fills share one correlation
      if(heuristicMatches==1) { m_pendingDealTicket=heuristicDeal; return true; }
      if(heuristicMatches>1) m_lifecycle=EXEC_LIFECYCLE_RECOVERY_BLOCKED;
      return false;
   }

public:
   CExecutionBridge(string symbol="EURUSDm",ulong magic=123456,int maxPositions=1)
   {
      m_symbol=symbol; m_magic=magic; m_maxPositions=maxPositions;
      m_lockVarName=""; m_lockGeneration=0.0; m_lockHeld=false; m_lockLeaseSeconds=30;
      m_lifecycle=EXEC_LIFECYCLE_IDLE; m_pendingOrderTicket=0; m_pendingDealTicket=0;
      m_pendingSubmitTime=0; m_pendingInitialSl=0.0; m_pendingVolume=0.0; m_pendingIntentId=0;
      m_pendingDirection=TRADE_DIR_NONE;
      m_riskPercent=0.5; m_hardRiskCapPercent=0.8; m_minVolumeTolerancePercent=0.05; m_marginReservePercent=5.0;
   }
   ~CExecutionBridge() { /* unresolved journals deliberately survive deinit */ }
   void SetSymbol(string symbol) { m_symbol=symbol; m_lockVarName=LockKey(); }
   void SetMagic(ulong magic) { m_magic=magic; m_lockVarName=LockKey(); }
   void SetMaxPositions(int n) { m_maxPositions=n; }
   void ConfigureRisk(double risk,double hardCap,double minTolerance,double marginReserve)
   { m_riskPercent=risk; m_hardRiskCapPercent=hardCap; m_minVolumeTolerancePercent=minTolerance; m_marginReservePercent=marginReserve; }

   int CountOpenPositions()
   {
      int count=0;
      for(int i=PositionsTotal()-1;i>=0;--i)
      {
         const ulong ticket=PositionGetTicket(i);
         if(ticket>0 && PositionGetString(POSITION_SYMBOL)==m_symbol &&
            PositionGetInteger(POSITION_MAGIC)==(long)m_magic) ++count;
      }
      return count;
   }
   int CountActiveOrdersAndPositions()
   {
      int count=CountOpenPositions();
      for(int i=OrdersTotal()-1;i>=0;--i)
      {
         const ulong ticket=OrderGetTicket(i);
         if(ticket>0 && OrderGetString(ORDER_SYMBOL)==m_symbol &&
            OrderGetInteger(ORDER_MAGIC)==(long)m_magic) ++count;
      }
      return count;
   }

   bool AcquireOrderLock(const uint leaseSeconds=30)
   {
      if(m_lockHeld) return RenewOrderLock();
      m_lockLeaseSeconds=MathMax(leaseSeconds,2); m_lockVarName=LockKey();
      for(int attempt=0;attempt<3;++attempt)
      {
         if(!EnsureLockExists()) return false;
         double state=0.0; datetime changedAt=0;
         if(!ReadLock(state,changedAt)) return false;
         const bool released=state<=0.0;
         const bool expired=state>0.0 && changedAt>0 && TimeLocal()-changedAt>=(int)m_lockLeaseSeconds;
         if(!released && !expired) return false;
         const double oldGeneration=MathAbs(state);
         if(oldGeneration>=DIRGA_LOCK_MAX_GENERATION) return false;
         const double mine=oldGeneration+1.0;
         if(CasLock(state,mine))
         {
            m_lockGeneration=mine; m_lockHeld=true;
            if(expired) LogWarning("LOCK_STALE_TAKEOVER",StringFormat("old=%G new=%G",state,mine));
            return true;
         }
      }
      return false;
   }

   bool RenewOrderLock()
   {
      if(!m_lockHeld || m_lockGeneration<=0.0 || m_lockGeneration>=DIRGA_LOCK_MAX_GENERATION)
      { m_lockHeld=false; return false; }
      const double next=m_lockGeneration+1.0;
      if(!CasLock(m_lockGeneration,next)) { m_lockHeld=false; return false; }
      m_lockGeneration=next; return true;
   }
   bool RenewLockLease() { return RenewOrderLock(); }

   bool ReleaseOrderLock()
   {
      if(EntrySubmissionBlocked()) return false;
      if(!m_lockHeld || m_lockGeneration<=0.0 || m_lockGeneration>=DIRGA_LOCK_MAX_GENERATION)
      { m_lockHeld=false; return false; }
      const double released=-(m_lockGeneration+1.0);
      const bool ok=CasLock(m_lockGeneration,released);
      m_lockHeld=false; m_lockGeneration=0.0; return ok;
   }
   bool IsLockHeld() { return m_lockHeld; }

   bool EntrySubmissionBlocked()
   {
      const double state=PendingState();
      return state!=DIRGA_PENDING_CLEAR ||
             m_lifecycle==EXEC_LIFECYCLE_ORDER_PENDING ||
             m_lifecycle==EXEC_LIFECYCLE_PARTIAL_FILL ||
             m_lifecycle==EXEC_LIFECYCLE_TIMEOUT_RECONCILE ||
             m_lifecycle==EXEC_LIFECYCLE_RECOVERY_BLOCKED;
   }

   bool RecoverPendingSubmission()
   {
      const double state=PendingState();
      if(state==DIRGA_PENDING_CLEAR) { m_lifecycle=EXEC_LIFECYCLE_IDLE; return true; }
      if(state!=DIRGA_PENDING_WRITING && state!=DIRGA_PENDING_UNRESOLVED && state!=DIRGA_PENDING_TIMEOUT)
      { m_lifecycle=EXEC_LIFECYCLE_RECOVERY_BLOCKED; return false; }
      if(!GlobalVariableCheck(PendingKey("time")) || !GlobalVariableCheck(PendingKey("sl")) ||
         !GlobalVariableCheck(PendingKey("side")))
      { m_lifecycle=EXEC_LIFECYCLE_RECOVERY_BLOCKED; return false; }
      m_pendingSubmitTime=(datetime)GlobalVariableGet(PendingKey("time"));
      m_pendingOrderTicket=(ulong)GlobalVariableGet(PendingKey("order"));
      m_pendingDealTicket=(ulong)GlobalVariableGet(PendingKey("deal"));
      m_pendingInitialSl=GlobalVariableGet(PendingKey("sl"));
      m_pendingVolume=GlobalVariableCheck(PendingKey("vol"))?GlobalVariableGet(PendingKey("vol")):0.0;
      m_pendingIntentId=GlobalVariableCheck(PendingKey("intent"))?(ulong)GlobalVariableGet(PendingKey("intent")):0;
      m_pendingDirection=(ENUM_TRADE_DIRECTION)(int)GlobalVariableGet(PendingKey("side"));
      if(m_pendingSubmitTime<=0 || m_pendingInitialSl<=0.0 || m_pendingVolume<=0.0 ||
         (m_pendingDirection!=TRADE_DIR_BUY && m_pendingDirection!=TRADE_DIR_SELL))
      { m_lifecycle=EXEC_LIFECYCLE_RECOVERY_BLOCKED; return false; }
      m_lifecycle=(state==DIRGA_PENDING_TIMEOUT) ? EXEC_LIFECYCLE_TIMEOUT_RECONCILE : EXEC_LIFECYCLE_ORDER_PENDING;
      if(!m_lockHeld && !AcquireOrderLock(m_lockLeaseSeconds)) return false;
      ReconcilePending();
      return !EntrySubmissionBlocked();
   }

   ENUM_EXECUTION_LIFECYCLE GetLifecycle() { return m_lifecycle; }
   double GetPendingInitialStop() { return m_pendingInitialSl; }
   ENUM_TRADE_DIRECTION GetPendingDirection() { return m_pendingDirection; }

   double NormalizePrice(double price)
   {
      const double tick=SymbolInfoDouble(m_symbol,SYMBOL_TRADE_TICK_SIZE);
      const int digits=(int)SymbolInfoInteger(m_symbol,SYMBOL_DIGITS);
      if(tick<=0.0) return NormalizeDouble(price,digits);
      return NormalizeDouble(MathFloor(price/tick+0.5)*tick,digits);
   }
   double NormalizeStopPrice(double price,ENUM_TRADE_DIRECTION dir,bool isStopLoss)
   {
      const double tick=SymbolInfoDouble(m_symbol,SYMBOL_TRADE_TICK_SIZE);
      const int digits=(int)SymbolInfoInteger(m_symbol,SYMBOL_DIGITS);
      if(tick<=0.0) return NormalizeDouble(price,digits);
      double steps=price/tick;
      if(isStopLoss) steps=(dir==TRADE_DIR_BUY)?MathFloor(steps):MathCeil(steps);
      else steps=(dir==TRADE_DIR_BUY)?MathFloor(steps):MathCeil(steps);
      return NormalizeDouble(steps*tick,digits);
   }

   bool ValidateStopFreeze(const ENUM_TRADE_DIRECTION direction,const double stopLoss,
                           const double takeProfit,const double bid,const double ask,
                           const bool isModification,string &outReason)
   {
      outReason="";
      if(direction==TRADE_DIR_NONE || !MathIsValidNumber(stopLoss) || stopLoss<=0.0 ||
         !MathIsValidNumber(bid) || !MathIsValidNumber(ask) || bid<=0.0 || ask<bid)
      { outReason="invalid_stop_or_direction"; return false; }
      const double point=SymbolInfoDouble(m_symbol,SYMBOL_POINT);
      if(point<=0.0) { outReason="invalid_symbol_point"; return false; }
      const long stopsLevel=SymbolInfoInteger(m_symbol,SYMBOL_TRADE_STOPS_LEVEL);
      const long freezeLevel=SymbolInfoInteger(m_symbol,SYMBOL_TRADE_FREEZE_LEVEL);
      const double distance=(double)MathMax(stopsLevel,freezeLevel)*point;
      const string phase=isModification?"modify_":"entry_";
      if(direction==TRADE_DIR_BUY)
      {
         if(stopLoss>bid-distance) { outReason=phase+"buy_sl_too_close"; return false; }
         if(takeProfit>0.0 && takeProfit<ask+distance) { outReason=phase+"buy_tp_wrong_or_close"; return false; }
      }
      else
      {
         if(stopLoss<ask+distance) { outReason=phase+"sell_sl_too_close"; return false; }
         if(takeProfit>0.0 && takeProfit>bid-distance) { outReason=phase+"sell_tp_wrong_or_close"; return false; }
      }
      return true;
   }

   bool BuildFinalMarketOrder(const TradeCandidate &cand,BrokerEnvironment &env,
                              const ulong deviationPoints,FinalMarketOrder &outPlan)
   {
      ZeroMemory(outPlan);
      if(!cand.valid || cand.symbol!=m_symbol ||
         (cand.direction!=TRADE_DIR_BUY && cand.direction!=TRADE_DIR_SELL) ||
         !env.tradeReady || !env.environmentCompatible)
      { outPlan.rejectReason="invalid_candidate_or_environment"; return false; }
      const long tradeMode=SymbolInfoInteger(m_symbol,SYMBOL_TRADE_MODE);
      if(tradeMode==SYMBOL_TRADE_MODE_DISABLED || tradeMode==SYMBOL_TRADE_MODE_CLOSEONLY ||
         (cand.direction==TRADE_DIR_BUY && tradeMode==SYMBOL_TRADE_MODE_SHORTONLY) ||
         (cand.direction==TRADE_DIR_SELL && tradeMode==SYMBOL_TRADE_MODE_LONGONLY))
      { outPlan.rejectReason="symbol_direction_not_tradeable"; return false; }

      outPlan.direction=cand.direction; outPlan.intentId=NextIntentId();
      outPlan.request.action=TRADE_ACTION_DEAL; outPlan.request.magic=m_magic;
      outPlan.request.symbol=m_symbol;
      outPlan.request.type=(cand.direction==TRADE_DIR_BUY)?ORDER_TYPE_BUY:ORDER_TYPE_SELL;
      // BuildFinalEntryCandidate has already normalized these fields and recomputed
      // every metric. Assert idempotence, then copy without a second rounding pass.
      const double normalizedPrice=NormalizePrice(cand.entryPrice);
      const double normalizedSl=NormalizeStopPrice(cand.initialStopPrice,cand.direction,true);
      const double normalizedTp=cand.targetPrice>0.0?NormalizeStopPrice(cand.targetPrice,cand.direction,false):0.0;
      const double epsilon=MathMax(1.0,MathAbs(cand.entryPrice))*1e-12;
      if(MathAbs(normalizedPrice-cand.entryPrice)>epsilon || MathAbs(normalizedSl-cand.initialStopPrice)>epsilon ||
         MathAbs(normalizedTp-cand.targetPrice)>epsilon)
      { outPlan.rejectReason="final_candidate_not_normalized"; return false; }
      outPlan.request.price=cand.entryPrice;
      outPlan.request.sl=cand.initialStopPrice;
      outPlan.request.tp=cand.targetPrice;
      outPlan.request.deviation=deviationPoints;
      if(!SelectFilling(outPlan.request.type_filling)) { outPlan.rejectReason="unsupported_filling_mode"; return false; }
      outPlan.request.comment=StringFormat("D2:%I64u",outPlan.intentId);

      const bool geometry=(cand.direction==TRADE_DIR_BUY)
         ? (outPlan.request.sl<outPlan.request.price && (outPlan.request.tp<=0.0 || outPlan.request.price<outPlan.request.tp))
         : (outPlan.request.tp<=0.0 || outPlan.request.tp<outPlan.request.price) && outPlan.request.price<outPlan.request.sl;
      if(!geometry) { outPlan.rejectReason="final_geometry_invalid"; return false; }
      string stopReason;
      if(!ValidateStopFreeze(cand.direction,outPlan.request.sl,outPlan.request.tp,
                             env.tick.bid,env.tick.ask,false,stopReason))
      { outPlan.rejectReason=stopReason; return false; }

      outPlan.riskRequest.symbol=outPlan.request.symbol;
      outPlan.riskRequest.orderType=outPlan.request.type;
      outPlan.riskRequest.entryPrice=outPlan.request.price;
      outPlan.riskRequest.stopLossPrice=outPlan.request.sl;
      outPlan.riskRequest.riskPercent=m_riskPercent;
      outPlan.riskRequest.hardRiskCapPercent=m_hardRiskCapPercent;
      outPlan.riskRequest.minVolumeTolerancePercent=m_minVolumeTolerancePercent;
      outPlan.riskRequest.marginReservePercent=m_marginReservePercent;
      if(!CalculateBasicRisk(outPlan.riskRequest,env,outPlan.risk))
      { outPlan.rejectReason=RiskRejectReasonToString(outPlan.risk.rejectReason); return false; }
      outPlan.request.volume=outPlan.risk.normalizedVolume;
      outPlan.valid=true; return true;
   }

   bool SendFinalMarketOrder(FinalMarketOrder &plan,MqlTradeResult &outResult)
   {
      ZeroMemory(outResult);
      if(!plan.valid || !m_lockHeld || EntrySubmissionBlocked()) return false;
      if(CountActiveOrdersAndPositions()>=m_maxPositions) return false;
      if(!RenewOrderLock()) { m_lifecycle=EXEC_LIFECYCLE_RECOVERY_BLOCKED; return false; }
      if(!SavePendingJournalWriting(plan)) { m_lifecycle=EXEC_LIFECYCLE_RECOVERY_BLOCKED; return false; }
      m_lifecycle=EXEC_LIFECYCLE_ORDER_PENDING;
      if(!RenewOrderLock()) { m_lifecycle=EXEC_LIFECYCLE_RECOVERY_BLOCKED; return false; }
      const bool submitted=OrderSend(plan.request,outResult);
      if(!MarkPendingJournalSent(outResult)) { m_lifecycle=EXEC_LIFECYCLE_RECOVERY_BLOCKED; return false; }
      if(submitted && (outResult.retcode==TRADE_RETCODE_DONE_PARTIAL)) m_lifecycle=EXEC_LIFECYCLE_PARTIAL_FILL;
      else if(submitted && (outResult.retcode==TRADE_RETCODE_DONE || outResult.retcode==TRADE_RETCODE_PLACED))
         m_lifecycle=EXEC_LIFECYCLE_ORDER_PENDING; // even DONE waits for terminal deal/history evidence
      else if(outResult.retcode==TRADE_RETCODE_REJECT || outResult.retcode==TRADE_RETCODE_INVALID ||
              outResult.retcode==TRADE_RETCODE_INVALID_VOLUME || outResult.retcode==TRADE_RETCODE_INVALID_PRICE ||
              outResult.retcode==TRADE_RETCODE_INVALID_STOPS || outResult.retcode==TRADE_RETCODE_NO_MONEY ||
              outResult.retcode==TRADE_RETCODE_TRADE_DISABLED || outResult.retcode==TRADE_RETCODE_MARKET_CLOSED)
      { m_lifecycle=EXEC_LIFECYCLE_REJECTED; ClearPendingJournal(); }
      else m_lifecycle=EXEC_LIFECYCLE_TIMEOUT_RECONCILE; // transport/unknown outcome stays blocked
      if(EntrySubmissionBlocked()) ReconcilePending();
      return submitted;
   }

   void ReconcilePending()
   {
      if(!EntrySubmissionBlocked()) return;
      if(m_lockHeld && !RenewOrderLock()) { m_lifecycle=EXEC_LIFECYCLE_RECOVERY_BLOCKED; return; }

      if(m_pendingOrderTicket>0 && OrderSelect(m_pendingOrderTicket))
      {
         const ENUM_ORDER_STATE state=(ENUM_ORDER_STATE)OrderGetInteger(ORDER_STATE);
         if(state==ORDER_STATE_PARTIAL) m_lifecycle=EXEC_LIFECYCLE_PARTIAL_FILL;
         return;
      }

      bool historyHealthy=false;
      if(m_pendingSubmitTime>0)
         historyHealthy=HistorySelect(m_pendingSubmitTime-120,TimeCurrent());
      if(historyHealthy && m_pendingOrderTicket>0 && HistoryOrderSelect(m_pendingOrderTicket))
      {
         const ENUM_ORDER_STATE state=(ENUM_ORDER_STATE)HistoryOrderGetInteger(m_pendingOrderTicket,ORDER_STATE);
         if(state==ORDER_STATE_FILLED)
         {
            if(!PersistInitialStopsForOrder(m_pendingOrderTicket))
            { m_lifecycle=EXEC_LIFECYCLE_RECOVERY_BLOCKED; return; }
            m_lifecycle=EXEC_LIFECYCLE_CONFIRMED; ClearPendingJournal(); return;
         }
         if(IsTerminalRejection(state))
         { m_lifecycle=EXEC_LIFECYCLE_REJECTED; ClearPendingJournal(); return; }
         if(state==ORDER_STATE_PARTIAL) { m_lifecycle=EXEC_LIFECYCLE_PARTIAL_FILL; return; }
      }
      if(historyHealthy && m_pendingDealTicket>0 && HistoryDealSelect(m_pendingDealTicket))
      {
         if(!PersistInitialStopForDeal(m_pendingDealTicket))
         { m_lifecycle=EXEC_LIFECYCLE_RECOVERY_BLOCKED; return; }
         m_lifecycle=EXEC_LIFECYCLE_CONFIRMED; ClearPendingJournal(); return;
      }
      if(historyHealthy && m_pendingOrderTicket==0 && m_pendingDealTicket==0 && RecoverUnknownTicketFromHistory() &&
         m_pendingDealTicket>0 && HistoryDealSelect(m_pendingDealTicket))
      {
         if(!PersistInitialStopForDeal(m_pendingDealTicket))
         { m_lifecycle=EXEC_LIFECYCLE_RECOVERY_BLOCKED; return; }
         m_lifecycle=EXEC_LIFECYCLE_CONFIRMED; ClearPendingJournal(); return;
      }

      if(m_pendingSubmitTime>0 && TimeCurrent()-m_pendingSubmitTime>30)
      {
         m_lifecycle=EXEC_LIFECYCLE_TIMEOUT_RECONCILE;
         GlobalVariableSet(PendingKey("state"),DIRGA_PENDING_TIMEOUT);
         GlobalVariablesFlush();
         LogWarning("LIFECYCLE_TIMEOUT","Submission remains unresolved; entry remains blocked");
      }
      else if(!historyHealthy) m_lifecycle=EXEC_LIFECYCLE_RECOVERY_BLOCKED;
   }

   bool ExecutePositionManage(const PositionManageIntent &intent,const BrokerEnvironment &env,
                              const ulong deviationPoints)
   {
      if(!env.tradeReady || !PositionSelectByTicket(intent.ticket)) return false;
      if(PositionGetString(POSITION_SYMBOL)!=m_symbol || PositionGetInteger(POSITION_MAGIC)!=(long)m_magic) return false;
      const ENUM_POSITION_TYPE positionType=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      const ENUM_TRADE_DIRECTION actual=(positionType==POSITION_TYPE_BUY)?TRADE_DIR_BUY:TRADE_DIR_SELL;
      if(actual!=intent.direction) return false;

      MqlTradeRequest request; MqlTradeResult result; MqlTradeCheckResult check;
      ZeroMemory(request); ZeroMemory(result); ZeroMemory(check);
      request.magic=m_magic; request.symbol=m_symbol; request.position=intent.ticket; request.deviation=deviationPoints;
      if(intent.action==POS_ACTION_MODIFY_SL)
      {
         request.action=TRADE_ACTION_SLTP;
         request.sl=NormalizeStopPrice(intent.newStopLoss,intent.direction,true);
         request.tp=intent.newTakeProfit>0.0?NormalizeStopPrice(intent.newTakeProfit,intent.direction,false):0.0;
         string reason;
         if(!ValidateStopFreeze(intent.direction,request.sl,request.tp,env.tick.bid,env.tick.ask,true,reason)) return false;
         if(!OrderCheck(request,check) || (check.retcode!=0 && check.retcode!=TRADE_RETCODE_DONE)) return false;
      }
      else if(intent.action==POS_ACTION_CLOSE_MARKET)
      {
         request.action=TRADE_ACTION_DEAL; request.volume=PositionGetDouble(POSITION_VOLUME);
         request.type=(actual==TRADE_DIR_BUY)?ORDER_TYPE_SELL:ORDER_TYPE_BUY;
         request.price=(actual==TRADE_DIR_BUY)?env.tick.bid:env.tick.ask;
         if(!SelectFilling(request.type_filling)) return false;
         request.comment=intent.reason;
      }
      else return false;
      if(!OrderSend(request,result)) return false;
      return result.retcode==TRADE_RETCODE_DONE || result.retcode==TRADE_RETCODE_DONE_PARTIAL;
   }
};
