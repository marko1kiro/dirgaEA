#ifndef DIRGA_EXECUTION_SAFETY_MQH
#define DIRGA_EXECUTION_SAFETY_MQH
#property strict
#include "Types.mqh"
#include "BrokerEnvironment.mqh"
#define B15_SPREAD_WINDOW_SIZE 50
#define B15_MAX_SPREAD_RATIO 2.0
#define B15_MAX_SLIPPAGE_POINTS 10.0
#define B15_MIN_SAMPLES_FOR_RATIO 5

class CExecutionSafetyGuard
{
private:
   double m_spreadSamples[B15_SPREAD_WINDOW_SIZE];
   int m_spreadCount;
   int m_spreadIndex;
   double m_maxSpreadRatio;
   double m_maxSlippagePoints;
   double m_maxSpreadCeiling;
   void AppendHistoricalSample(const double spreadPoints)
   {
      if(!MathIsValidNumber(spreadPoints) || spreadPoints<=0.0) return;
      m_spreadSamples[m_spreadIndex]=spreadPoints;
      m_spreadIndex=(m_spreadIndex+1)%B15_SPREAD_WINDOW_SIZE;
      if(m_spreadCount<B15_SPREAD_WINDOW_SIZE) ++m_spreadCount;
   }
public:
   CExecutionSafetyGuard(double maxRatio=B15_MAX_SPREAD_RATIO,double maxSlippage=B15_MAX_SLIPPAGE_POINTS,double maxSpreadCeiling=35.0)
   {
      m_maxSpreadRatio=maxRatio; m_maxSlippagePoints=maxSlippage; m_maxSpreadCeiling=maxSpreadCeiling;
      m_spreadCount=0; m_spreadIndex=0; ArrayInitialize(m_spreadSamples,0.0);
   }
   double GetMedianSpread()
   {
      if(m_spreadCount==0) return m_maxSpreadCeiling>0.0?m_maxSpreadCeiling:10.0;
      double values[]; ArrayResize(values,m_spreadCount);
      for(int i=0;i<m_spreadCount;++i) values[i]=m_spreadSamples[i];
      ArraySort(values); return values[m_spreadCount/2];
   }
   void FinalizeOnTickSample(const BrokerEnvironment &env)
   {
      if(env.point<=0.0 || !MathIsValidNumber(env.tick.ask) || !MathIsValidNumber(env.tick.bid) ||
         env.tick.ask<env.tick.bid || env.tick.bid<=0.0) return;
      AppendHistoricalSample((env.tick.ask-env.tick.bid)/env.point);
   }
   bool ValidateFinalOrder(const FinalMarketOrder &plan,const BrokerEnvironment &env,
                           ExecutionSafetyResult &outResult)
   {
      ZeroMemory(outResult); outResult.passed=false;
      if(!plan.valid || !env.tradeReady || env.point<=0.0 || plan.request.symbol!=env.symbol)
      { outResult.failReason="invalid_final_plan_or_environment"; return false; }
      double spread=(env.tick.ask-env.tick.bid)/env.point;
      double median=GetMedianSpread(); double ratio=median>0.0?spread/median:1.0;
      outResult.currentSpreadPoints=spread; outResult.medianSpreadPoints=median; outResult.spreadRatio=ratio;
      if(!MathIsValidNumber(spread) || spread<0.0 || (m_maxSpreadCeiling>0.0 && spread>m_maxSpreadCeiling))
      { outResult.failReason="spread_exceeds_absolute_ceiling"; return false; }
      if(m_spreadCount>=B15_MIN_SAMPLES_FOR_RATIO && ratio>m_maxSpreadRatio)
      { outResult.failReason="spread_spike_veto"; return false; }
      double quote=plan.direction==TRADE_DIR_BUY?env.tick.ask:env.tick.bid;
      double dev=MathAbs(plan.request.price-quote)/env.point; outResult.priceDeviationPoints=dev;
      double maxDev=plan.request.deviation>0?(double)plan.request.deviation:m_maxSlippagePoints;
      if(dev>maxDev) { outResult.failReason="slippage_deviation_exceeded"; return false; }
      // F07: OrderCheck sees the exact final object; no reconstructed request or rounding.
      MqlTradeCheckResult check; ZeroMemory(check);
      if(!OrderCheck(plan.request,check) || (check.retcode!=0 && check.retcode!=TRADE_RETCODE_DONE))
      { outResult.orderCheckRetcode=check.retcode; outResult.failReason=StringFormat("order_check_failed_%u",check.retcode); return false; }
      outResult.orderCheckRetcode=check.retcode; outResult.passed=true; return true;
   }
};
#endif
