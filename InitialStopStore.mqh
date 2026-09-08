#ifndef DIRGA_INITIAL_STOP_STORE_MQH
#define DIRGA_INITIAL_STOP_STORE_MQH
#property strict

class CInitialStopStore
{
private:
   string m_symbol;
   ulong m_magic;
   string Prefix(const ulong positionId)
   {
      return StringFormat("D2.I.%I64u.%s.%I64u.%I64u",AccountInfoInteger(ACCOUNT_LOGIN),m_symbol,m_magic,positionId);
   }
public:
   CInitialStopStore() { m_symbol=""; m_magic=0; }
   void Configure(const string symbol,const ulong magic) { m_symbol=symbol; m_magic=magic; }
   bool Save(const ulong positionId,const double initialSl)
   {
      if(positionId==0 || !MathIsValidNumber(initialSl) || initialSl<=0.0) return false;
      string p=Prefix(positionId);
      if(GlobalVariableCheck(p+".ok")) GlobalVariableDel(p+".ok"); // WRITING
      bool ok=GlobalVariableSet(p+".sl",initialSl) && GlobalVariableSet(p+".schema",2.0) && GlobalVariableSet(p+".ok",2.0);
      GlobalVariablesFlush(); return ok;
   }
   bool Load(const ulong positionId,double &initialSl)
   {
      initialSl=0.0; string p=Prefix(positionId);
      if(!GlobalVariableCheck(p+".ok") || GlobalVariableGet(p+".ok")!=2.0 ||
         !GlobalVariableCheck(p+".schema") || GlobalVariableGet(p+".schema")!=2.0 ||
         !GlobalVariableCheck(p+".sl")) return false;
      initialSl=GlobalVariableGet(p+".sl");
      return MathIsValidNumber(initialSl) && initialSl>0.0;
   }
   bool PositionIsLive(const ulong positionId)
   {
      for(int i=PositionsTotal()-1;i>=0;--i)
      {
         ulong ticket=PositionGetTicket(i);
         if(ticket>0 && PositionGetString(POSITION_SYMBOL)==m_symbol &&
            PositionGetInteger(POSITION_MAGIC)==(long)m_magic &&
            (ulong)PositionGetInteger(POSITION_IDENTIFIER)==positionId) return true;
      }
      return false;
   }
   bool RemoveIfFullyClosed(const ulong positionId)
   {
      if(positionId==0 || PositionIsLive(positionId)) return false;
      string p=Prefix(positionId); string suffixes[]={"ok","schema","sl"};
      for(int i=0;i<ArraySize(suffixes);++i) if(GlobalVariableCheck(p+"."+suffixes[i])) GlobalVariableDel(p+"."+suffixes[i]);
      GlobalVariablesFlush(); return true;
   }
};
#endif
