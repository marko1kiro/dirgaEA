#property strict
#property version "1.00"

#include "Config.mqh"
#include "Types.mqh"
#include "Logger.mqh"
#include "BrokerEnvironment.mqh"
#include "RiskEngine.mqh"
#include "SwingStructure.mqh"
#include "DiagnosticCollector.mqh"
#include "MarketBrain.mqh"
#include "RegimeFusion.mqh"

bool EA_READY = false;
int atr_h1_handle = INVALID_HANDLE;
SwingStructureResult swing_structure;
bool TRADE_READY = false;
datetime last_h1_bar_time = 0;
datetime last_m15_bar_time = 0;
ENUM_EXECUTION_STATE execution_state = IDLE;
BrokerEnvironment broker_environment;
Build04DiagnosticSnapshot build04_diagnostic_snapshot;
Build04DiagnosticCounters build04_diagnostic_counters;

// BUILD 05 dedicated handles (independent of BUILD 04 ownership)
int ema_fast_h1_handle = INVALID_HANDLE;
int ema_slow_h1_handle = INVALID_HANDLE;
int adx_h1_handle = INVALID_HANDLE;
int atr_h1_handle_b05 = INVALID_HANDLE;
H1BrainResult h1_brain;
// BUILD 05 canonical behavior state (single source of truth)
Build05BehaviorState b05_state;
datetime b05_last_accepted_h1 = 0;
int g_copyBufferFailures = 0;
bool b05_h1_brain_primed = false;

// BUILD 06 — H1 Regime Fusion persistence state
RegimeFusionState b06_state;
RegimeCompressionMemory b06_compression;
RegimeResult b06_result;
bool b06_primed = false;

void BuildRegimeFusionParams(RegimeFusionParams &p)
{
   p.regimeDwell = RegimeDwell;
   p.challengerGap = ChallengerGap;
   p.uncertainVeto = UncertainVeto;
   p.uncertainExitThreshold = UncertainExitThreshold;
   p.uncertainExitDwell = UncertainExitDwell;
   p.uncertainWeakWinnerThreshold = UncertainWeakWinnerThreshold;
   p.tieEpsilon = TieEpsilon;
   p.breakoutMaturationMinBars = BreakoutMaturationMinBars;
   p.breakoutMaxAgeBars = BreakoutMaxAgeBars;
   p.breakoutLookbackBars = BreakoutLookbackBars;
}

bool PrimeBarTimes()
{
   last_h1_bar_time = iTime(_Symbol, PERIOD_H1, 0);
   last_m15_bar_time = iTime(_Symbol, PERIOD_M15, 0);

   if(last_h1_bar_time <= 0 || last_m15_bar_time <= 0)
   {
      LogError("INIT_FAILED", "Unable to prime H1/M15 bar timestamps");
      return false;
   }

   return true;
}

void RunRiskDiagnostic()
{
   RiskRequest request;
   request.symbol = _Symbol;
   request.orderType = RiskDiagnosticOrderType;
   request.entryPrice = RiskDiagnosticEntryPrice;
   request.stopLossPrice = RiskDiagnosticStopLossPrice;
   request.riskPercent = RiskDiagnosticPercent;
   request.hardRiskCapPercent = HardRiskCapPercent;
   request.minVolumeTolerancePercent = MinVolumeTolerancePercent;
   request.marginReservePercent = MarginReservePercent;

   RiskResult result;
   CalculateBasicRisk(request, broker_environment, result);
   LogRiskDiagnostic(request, result);
}

bool DetectNewBar(const ENUM_TIMEFRAMES timeframe, datetime &last_bar_time)
{
    const datetime current_bar_time = iTime(_Symbol, timeframe, 0);

    if(current_bar_time <= 0 || current_bar_time == last_bar_time)
    {
       if(timeframe == PERIOD_H1 && Build04DiagnosticMode)
          build04_diagnostic_counters.duplicateH1Attempts++;
       return false;
    }


   last_bar_time = current_bar_time;
   return true;
}

void MergeBuild04DiagnosticCounters(Build04DiagnosticCounters &target, const Build04DiagnosticCounters &persistent)
{
   target.duplicateH1Attempts += persistent.duplicateH1Attempts;
   target.duplicateEventsRejected += persistent.duplicateEventsRejected;
   target.formingBarAttempts += persistent.formingBarAttempts;
   target.invalidAtr += persistent.invalidAtr;
   target.copyBufferFailures += persistent.copyBufferFailures;
   target.zeroRange += persistent.zeroRange;
   target.abnormalSkips += persistent.abnormalSkips;
}

// Copy a native indicator buffer for completed H1 bars (shift 1).
// Returns copied count; on failure returns -1.
int CopyBrainBuffer(const int handle, double &buffer[], const int requested, const int bufferIndex = 0)
{
   ArraySetAsSeries(buffer, true);
   ResetLastError();
   const int copied = CopyBuffer(handle, bufferIndex, 1, requested, buffer);
   ArraySetAsSeries(buffer, false);
   return copied;
}

void UpdateH1Brain()
{
   const int requested = MathMax(SwingLookbackBars, 100);
   double atrB05[], emaFast[], emaSlow[], adx[];
   MqlRates rates[];

    ArraySetAsSeries(rates, true);
    ResetLastError();
    const int copiedRates = CopyRates(_Symbol, PERIOD_H1, 1, requested, rates);
    ArraySetAsSeries(rates, false);
    
    ResetH1BrainInvalid(h1_brain);
    if(copiedRates < 3)
       return;

    const int copiedAtr = CopyBrainBuffer(atr_h1_handle_b05, atrB05, requested);
    const int copiedFast = CopyBrainBuffer(ema_fast_h1_handle, emaFast, requested);
    const int copiedSlow = CopyBrainBuffer(ema_slow_h1_handle, emaSlow, requested);
    const int copiedAdx = CopyBrainBuffer(adx_h1_handle, adx, requested);

    const bool atrBufferReady = copiedAtr == copiedRates;
    const bool emaBufferReady = copiedFast == copiedRates && copiedSlow == copiedRates;
    const bool adxBufferReady = copiedAdx == copiedRates;

    // Duplicate H1 guard (live path only)
    if(b05_last_accepted_h1 != 0 && rates[copiedRates - 1].time <= b05_last_accepted_h1)
    {
        // Duplicate or older H1 bar — skip processing
        return;
    }

     int prevDirection = 0, prevMomentum = 0, prevVolLevel = 0, prevVolQuality = 0;
     if(Build05DiagnosticMode)
     {
        prevDirection = (int)b05_state.directionState;
        prevMomentum = (int)b05_state.momentumState;
        prevVolLevel = (int)b05_state.volLevel;
        prevVolQuality = (int)b05_state.volQuality;
     }

     // Canonical B05 update — single code path for live and replay
     bool b05_ok = ProcessBuild05ClosedHistoryPrefix(rates, atrB05, emaFast, emaSlow, adx,
                                       copiedRates, atrBufferReady, emaBufferReady, adxBufferReady, b05_state, h1_brain, g_copyBufferFailures);

     if(Build05DiagnosticMode)
     {
        if((int)b05_state.directionState != prevDirection)
           LogDebug("B05_DIRECTION_TRANSITION", StringFormat("%d -> %d", prevDirection, (int)b05_state.directionState));
        if((int)b05_state.momentumState != prevMomentum)
           LogDebug("B05_MOMENTUM_TRANSITION", StringFormat("%d -> %d", prevMomentum, (int)b05_state.momentumState));
        if((int)b05_state.volLevel != prevVolLevel)
           LogDebug("B05_VOLATILITY_TRANSITION", StringFormat("%d -> %d", prevVolLevel, (int)b05_state.volLevel));
        if((int)b05_state.volQuality != prevVolQuality)
           LogDebug("B05_VOLQUALITY_TRANSITION", StringFormat("%d -> %d", prevVolQuality, (int)b05_state.volQuality));
     }

    if(b05_ok)
    {
        b05_last_accepted_h1 = rates[copiedRates - 1].time;
    }
    b05_h1_brain_primed = true;

    if(Build05DiagnosticMode)
    {
       Build05RawTrace trace;
       ZeroMemory(trace);
       Build05DiagnosticCollect(h1_brain, b05_state, trace);
    }

    // Observability-only native indicator logging (BUILD 05 parity reference).
    // Reuses the existing native handles; no alternate math; no state/score changes.
    if(Build05DiagnosticMode && copiedRates >= 1)
    {
       const int n = copiedRates - 1;
       const datetime closedH1 = rates[n].time;

       // ADX helper buffers: 0=main ADX (already in `adx[]`), 1=+DI, 2=-DI.
       double plusDi[], minusDi[];
       int plusDiStatus = -1, minusDiStatus = -1;
       const int copiedPlusDi  = CopyBrainBuffer(adx_h1_handle, plusDi, requested, 1);
       const int copiedMinusDi = CopyBrainBuffer(adx_h1_handle, minusDi, requested, 2);
       plusDiStatus  = (copiedPlusDi  == copiedRates) ? 0 : copiedPlusDi;
       minusDiStatus = (copiedMinusDi == copiedRates) ? 0 : copiedMinusDi;

       double atrValue = atrBufferReady ? atrB05[n] : 0.0;
       double emaFastValue = emaBufferReady ? emaFast[n] : 0.0;
       double emaSlowValue = emaBufferReady ? emaSlow[n] : 0.0;
       double adxValue = 0.0;
       double adxPrev = 0.0;
       double adxSlope = 0.0;
       if(adxBufferReady && copiedAdx >= 2)
       {
          adxValue = BrainValidAt(adx[copiedAdx - 1]) ? adx[copiedAdx - 1] : 0.0;
          adxPrev = BrainValidAt(adx[copiedAdx - 2]) ? adx[copiedAdx - 2] : 0.0;
          adxSlope = BrainValidAt(adx[copiedAdx - 1]) && BrainValidAt(adx[copiedAdx - 2]) ? (adx[copiedAdx - 1] - adx[copiedAdx - 2]) : 0.0;
       }
       LogDebug("BRAIN_NATIVE_INDICATOR", StringFormat("atr=%.5f adx=%.5f adxPrev=%.5f adxSlope=%.5f emaFast=%.5f emaSlow=%.5f",
           atrValue, adxValue, adxPrev, adxSlope, emaFastValue, emaSlowValue));

       Build05NativeIndicatorLog(
           closedH1,
           atrValue,
           emaFastValue,
           emaSlowValue,
           adxValue,
           (copiedPlusDi == copiedRates) ? plusDi[n] : 0.0,
           (copiedMinusDi == copiedRates) ? minusDi[n] : 0.0,
           atrBufferReady ? 0 : copiedAtr,
           emaBufferReady ? 0 : ((copiedFast < 0) ? copiedFast : copiedSlow),
           adxBufferReady ? 0 : copiedAdx,
           plusDiStatus,
           minusDiStatus);
    }
}

bool UpdateSwingStructure()
{
   MqlRates rates[];
   double atr[];
   ArraySetAsSeries(rates, true);
   ArraySetAsSeries(atr, true);
   const int requested = MathMax(SwingLookbackBars, SwingPivotWidth * 2 + 3);
   ResetLastError();
   const int copiedRates = CopyRates(_Symbol, PERIOD_H1, 1, requested, rates);
   const int ratesError = GetLastError();
   ResetLastError();
   const int copiedAtr = CopyBuffer(atr_h1_handle, 0, 1, requested, atr);
   const int atrError = GetLastError();
    if(copiedRates != copiedAtr || copiedRates < SwingPivotWidth * 2 + 3)
    {
       if(Build04DiagnosticMode)
       {
          Build04DiagnosticTrace failureTrace;
          ZeroMemory(failureTrace);
          failureTrace.counters = build04_diagnostic_counters;
          failureTrace.counters.copyBufferFailures++;
          if(copiedAtr < 0 || atrError != 0) failureTrace.counters.invalidAtr++;
          Build04DiagnosticSafety(failureTrace, "copy_failure");
          build04_diagnostic_counters = failureTrace.counters;
       }
       swing_structure.valid = false;

      LogWarning("SWING_STRUCTURE_UNAVAILABLE", StringFormat("rates=%d rates_error=%d atr=%d atr_error=%d", copiedRates, ratesError, copiedAtr, atrError));
      return false;
   }
   ArraySetAsSeries(rates, false);
   ArraySetAsSeries(atr, false);
    SwingStructureResult next;
     Build04DiagnosticTrace trace;
     if(!ProcessSwingStructure(rates, atr, copiedRates, SwingPivotWidth, SwingEqualToleranceAtr, SwingHistoryBars, next, Build04DiagnosticMode, trace))


    {
       if(Build04DiagnosticMode)
       {
          MergeBuild04DiagnosticCounters(trace.counters, build04_diagnostic_counters);
          Build04DiagnosticSafety(trace, "processing_failure");
          build04_diagnostic_counters = trace.counters;
       }
       swing_structure.valid = false;
       LogWarning("SWING_STRUCTURE_INVALID", "Rejected H1 rates/ATR input");

      return false;
   }
    PreserveSwingStructureFollowThrough(swing_structure, next);
    if(Build04DiagnosticMode)
    {
       trace.symbol = _Symbol;
       trace.requestedBars = requested;
       trace.copiedRates = copiedRates;
       trace.copiedAtr = copiedAtr;
        trace.atrError = atrError;
        MergeBuild04DiagnosticCounters(trace.counters, build04_diagnostic_counters);

    }
     swing_structure = next;
      Build04DiagnosticCollect(build04_diagnostic_snapshot, swing_structure, trace);
      if(Build04DiagnosticMode)
         build04_diagnostic_counters = trace.counters;
 

    LogDebug("SWING_STRUCTURE", StringFormat("time=%s swings=%d breaks=%d state=%d sweep=%s", TimeToString(swing_structure.latestTime, TIME_DATE | TIME_MINUTES), swing_structure.swingCount, swing_structure.breakCount, swing_structure.state, swing_structure.sweep ? "true" : "false"));

   return true;
}

// Compute B06 evidenceCompleteness (section 11.1: 4 independent domains x 0.25).
double B06EvidenceCompleteness(const SwingStructureResult &structure, const H1BrainResult &brain)
{
   return 0.25 * (structure.valid ? 1.0 : 0.0)
        + 0.25 * (brain.direction.valid ? 1.0 : 0.0)
        + 0.25 * (brain.momentum.valid ? 1.0 : 0.0)
        + 0.25 * (brain.volatility.valid ? 1.0 : 0.0);
}

// B06 critical-core validity (section 11.2): at least one domain valid.
bool B06CoreValid(const SwingStructureResult &structure, const H1BrainResult &brain)
{
   return structure.valid || brain.direction.valid || brain.momentum.valid || brain.volatility.valid;
}

// Live B06 fusion for one closed-H1 update (called after B04 + B05).
void UpdateH1RegimeFusion()
{
   // Timestamp alignment (section 15): skip + diagnostic if mismatched.
   const datetime b04Time = swing_structure.latestTime;
   datetime b05Time = h1_brain.direction.latestClosedH1;
   if(b05Time == 0) b05Time = h1_brain.momentum.latestClosedH1;
   if(b05Time == 0) b05Time = h1_brain.volatility.latestClosedH1;
   if(b04Time != 0 && b05Time != 0 && b04Time != b05Time)
   {
      if(Build06DiagnosticMode)
         LogDebug("REGIME_ALIGN_SKIP", StringFormat("b04=%I64d b05=%I64d", (long)b04Time, (long)b05Time));
      return;
   }

   const double completeness = B06EvidenceCompleteness(swing_structure, h1_brain);
   const bool valid = B06CoreValid(swing_structure, h1_brain);

   RegimeFusionParams p;
   BuildRegimeFusionParams(p);

   // Prior-only compression context (read BEFORE appending the current bar).
   const double compressionContext = RegimeCompressionMax(b06_compression);

   UpdateRegimeFusion(b06_state, swing_structure, h1_brain, p, completeness, valid,
                      compressionContext, b06_result);

   // Append current bar compression AFTER fusion finalizes (section 7.1 prior-only).
   RegimeCompressionAppend(b06_compression, h1_brain.volatility.compressionScore, BreakoutLookbackBars);

   b06_primed = true;
   Build06DiagnosticCollect(b06_result, b06_compression);
}

// Cold-start reconstruction (section 15b): replay synchronized completed-H1 B04/B05
// final outputs oldest->newest through the SAME B06 state machine. Re-invokes the
// existing B04/B05 pure engine functions on truncated prefixes; does NOT modify
// their locked semantics.
void RebuildRegimeFusionState()
{
   const int requested = MathMax(SwingLookbackBars, 100);
   MqlRates rates[];
   double atrB04[], atrB05[], emaFast[], emaSlow[], adx[];

   ArraySetAsSeries(rates, true);
   ResetLastError();
   const int copiedRates = CopyRates(_Symbol, PERIOD_H1, 1, requested, rates);
   ArraySetAsSeries(rates, false);
   if(copiedRates < 3)
      return;

    const int copiedAtrB04 = CopyBrainBuffer(atr_h1_handle, atrB04, requested);
    const int copiedAtrB05 = CopyBrainBuffer(atr_h1_handle_b05, atrB05, requested);
    const int copiedFast = CopyBrainBuffer(ema_fast_h1_handle, emaFast, requested);
    const int copiedSlow = CopyBrainBuffer(ema_slow_h1_handle, emaSlow, requested);
    const int copiedAdx = CopyBrainBuffer(adx_h1_handle, adx, requested);

    const bool atrB04Ok = copiedAtrB04 == copiedRates;
    const bool atrB05Ok = copiedAtrB05 == copiedRates;
    const bool atrBufferReady = copiedAtrB05 == copiedRates;
    const bool emaBufferReady = copiedFast == copiedRates && copiedSlow == copiedRates;
    const bool adxBufferReady = copiedAdx == copiedRates;

   RegimeFusionStateInit(b06_state);
   RegimeCompressionInit(b06_compression, BreakoutLookbackBars);

   RegimeFusionParams p;
   BuildRegimeFusionParams(p);

   // Replay-local state — will be hydrated into live globals after replay
   SwingStructureResult replayStructure;
   ZeroMemory(replayStructure);
   Build05BehaviorState replayB05State;
   Build05BehaviorStateInit(replayB05State);

   H1BrainResult replayBrain;
   ResetH1BrainInvalid(replayBrain);

   const int warmup = SwingPivotWidth * 2 + 3;
   if(warmup < 3) return;

   for(int t = warmup; t < copiedRates; t++)
   {
      const int count = t + 1;

      // B04 final output at prefix t
      SwingStructureResult nextStruct;
      Build04DiagnosticTrace replayTrace;
      const bool structOk = ProcessSwingStructure(rates, atrB04, count, SwingPivotWidth,
                                                  SwingEqualToleranceAtr, SwingHistoryBars,
                                                  nextStruct, false, replayTrace);
      if(structOk)
      {
         PreserveSwingStructureFollowThrough(replayStructure, nextStruct);
         replayStructure = nextStruct;
      }

      // B05 final output at prefix t — canonical update
      ProcessBuild05ClosedHistoryPrefix(rates, atrB05, emaFast, emaSlow, adx,
                                        count, atrBufferReady, emaBufferReady, adxBufferReady, replayB05State, replayBrain, g_copyBufferFailures);

      // B06 fusion at prefix t (advance the same state machine)
      const double completeness = B06EvidenceCompleteness(replayStructure, replayBrain);
      const bool valid = B06CoreValid(replayStructure, replayBrain);
      const double compressionContext = RegimeCompressionMax(b06_compression);
      UpdateRegimeFusion(b06_state, replayStructure, replayBrain, p, completeness, valid,
                         compressionContext, b06_result);
      RegimeCompressionAppend(b06_compression, replayBrain.volatility.compressionScore, BreakoutLookbackBars);
   }

   // HYDRATE: copy replay-final B05 state into live globals
   b05_state = replayB05State;
   h1_brain = replayBrain;

   b06_primed = true;
   // Emit the reconstructed final state (section 15b native acceptance).
   Build06DiagnosticCollect(b06_result, b06_compression);
}

int OnInit()
{
   if(MagicNumber == 0)
   {
      LogError("INIT_FAILED", "MagicNumber must be greater than zero");
      return INIT_PARAMETERS_INCORRECT;
   }

   if(TimerSeconds <= 0)
   {
      LogError("INIT_FAILED", "TimerSeconds must be greater than zero");
      return INIT_PARAMETERS_INCORRECT;
   }

   if(SwingHistoryBars < 1 || SwingHistoryBars > SWING_STRUCTURE_MAX_HISTORY ||
      SwingLookbackBars < SwingPivotWidth * 2 + 3 || SwingPivotWidth < 1)
   {
      LogError("INIT_FAILED", "Swing structure inputs are out of bounds");
      return INIT_PARAMETERS_INCORRECT;
   }

   if(!LoadBrokerEnvironment(broker_environment))
      return INIT_FAILED;

   atr_h1_handle = iATR(_Symbol, PERIOD_H1, 14);
   if(atr_h1_handle == INVALID_HANDLE)
   {
      LogError("INIT_FAILED", StringFormat("iATR H1(14) failed with error %d", GetLastError()));
      return INIT_FAILED;
   }

   // BUILD 05 dedicated native handles (independent of BUILD 04 ATR handle)
   atr_h1_handle_b05 = iATR(_Symbol, PERIOD_H1, BRAIN_ATR_PERIOD);
   ema_fast_h1_handle = iMA(_Symbol, PERIOD_H1, DirectionFastPeriod, 0, MODE_EMA, PRICE_CLOSE);
   ema_slow_h1_handle = iMA(_Symbol, PERIOD_H1, DirectionSlowPeriod, 0, MODE_EMA, PRICE_CLOSE);
   adx_h1_handle = iADX(_Symbol, PERIOD_H1, MomentumAdxPeriod);
   if(atr_h1_handle_b05 == INVALID_HANDLE || ema_fast_h1_handle == INVALID_HANDLE ||
      ema_slow_h1_handle == INVALID_HANDLE || adx_h1_handle == INVALID_HANDLE)
   {
      LogError("INIT_FAILED", StringFormat("BUILD 05 indicator creation failed with error %d", GetLastError()));
      return INIT_FAILED;
   }

   if(!PrimeBarTimes())
      return INIT_FAILED;

    if(!EventSetTimer(TimerSeconds))
    {
       LogError("INIT_FAILED", StringFormat("EventSetTimer failed with error %d", GetLastError()));
       return INIT_FAILED;
    }

    if(!UpdateSwingStructure())
       LogWarning("SWING_STRUCTURE_UNAVAILABLE", "Waiting for sufficient completed H1 history");

    Build05BehaviorStateInit(b05_state);
    ResetH1BrainInvalid(h1_brain);
    UpdateH1Brain();

    // BUILD 06 cold-start reconstruction (section 15b): replay synchronized
    // completed-H1 B04/B05 final outputs oldest->newest to rebuild path-dependent
    // B06 state (regime, hysteresis, compression FIFO).
    RebuildRegimeFusionState();

    TRADE_READY = broker_environment.tradeReady;
    EA_READY = true;

   LogBrokerEnvironment(broker_environment);
   LogDebug("EA_READY", StringFormat("Initialized on %s; MagicNumber=%I64u", _Symbol, MagicNumber));
   if(RiskDiagnosticMode)
      RunRiskDiagnostic();
   return INIT_SUCCEEDED;
}

void OnTick()
{
   if(!EA_READY)
      return;

    if(DetectNewBar(PERIOD_H1, last_h1_bar_time))
    {
       LogDebug("NEW_H1_BAR", TimeToString(last_h1_bar_time, TIME_DATE | TIME_MINUTES));
       UpdateSwingStructure();
       UpdateH1Brain();
       UpdateH1RegimeFusion();
    }


   if(DetectNewBar(PERIOD_M15, last_m15_bar_time))
      LogDebug("NEW_M15_BAR", TimeToString(last_m15_bar_time, TIME_DATE | TIME_MINUTES));
}

void OnTimer()
{
   if(!EA_READY)
      return;

   const bool previousCompatibility = broker_environment.environmentCompatible;
   const bool previousTradeReady = TRADE_READY;
   RefreshEnvironmentStatus(broker_environment);
   TRADE_READY = broker_environment.tradeReady;

   if(previousCompatibility != broker_environment.environmentCompatible ||
      previousTradeReady != TRADE_READY)
      LogBrokerEnvironment(broker_environment);
}

void OnTradeTransaction(const MqlTradeTransaction &transaction,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   if(!EA_READY || !DebugMode)
      return;

   LogDebug("TRADE_TRANSACTION",
            StringFormat("type=%d order=%I64u deal=%I64u request_action=%d retcode=%u state=%d",
                         transaction.type,
                         transaction.order,
                         transaction.deal,
                         request.action,
                         result.retcode,
                         execution_state));
}

void OnDeinit(const int reason)
{
   EA_READY = false;
   TRADE_READY = false;
    EventKillTimer();
    if(atr_h1_handle != INVALID_HANDLE)
       IndicatorRelease(atr_h1_handle);
    atr_h1_handle = INVALID_HANDLE;
    if(atr_h1_handle_b05 != INVALID_HANDLE)
       IndicatorRelease(atr_h1_handle_b05);
    if(ema_fast_h1_handle != INVALID_HANDLE)
       IndicatorRelease(ema_fast_h1_handle);
    if(ema_slow_h1_handle != INVALID_HANDLE)
       IndicatorRelease(ema_slow_h1_handle);
    if(adx_h1_handle != INVALID_HANDLE)
       IndicatorRelease(adx_h1_handle);
    atr_h1_handle_b05 = INVALID_HANDLE;
    ema_fast_h1_handle = INVALID_HANDLE;
    ema_slow_h1_handle = INVALID_HANDLE;
    adx_h1_handle = INVALID_HANDLE;
    LogDebug("EA_STOPPED", StringFormat("Deinitialized; reason=%d", reason));

}
