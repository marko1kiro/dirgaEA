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
#include "TrendStrategy.mqh"
#include "RangeStrategy.mqh"
#include "BreakoutStrategy.mqh"
#include "PositionManager.mqh"
#include "QualityGate.mqh"
#include "ExecutionBridge.mqh"
#include "ExecutionSafety.mqh"
#include "SessionNewsEngine.mqh"
#include "DailyRiskLedger.mqh"
#include "InitialStopStore.mqh"
#include "DashboardHUD.mqh"

bool EA_READY = false;
int atr_h1_handle = INVALID_HANDLE;
SwingStructureResult swing_structure;
bool TRADE_READY = false;
datetime last_h1_bar_time = 0;
datetime last_m15_bar_time = 0;
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
Build05DiagnosticCounters build05_diagnostic_counters;
bool b05_h1_brain_primed = false;

// BUILD 06 — H1 Regime Fusion persistence state
RegimeFusionState b06_state;
RegimeCompressionMemory b06_compression;
RegimeResult b06_result;
bool b06_primed = false;
datetime b06_last_accepted_h1 = 0;
datetime b06_result_available_at = 0;
struct B06BreakTracker
{
   datetime bullTime;
   datetime bearTime;
   int bullAge;
   int bearAge;
};
B06BreakTracker b06_break_tracker;
bool b06_cycle_b04_rates_ready = false;
bool b06_cycle_b04_atr_ready = false;
bool b06_cycle_b05_rates_ready = false;
bool b06_cycle_b05_atr_ready = false;
datetime b06_cycle_b04_timestamp = 0;
datetime b06_cycle_b05_timestamp = 0;
bool b06_rebuild_success = false;

// BUILD 07 — M15 Trend Strategy
CTrendStrategy b07_trend_strategy;
int atr_m15_handle = INVALID_HANDLE;
TradeCandidate b07_last_candidate;

// BUILD 11 — M15 Range Strategy
CRangeStrategy b11_range_strategy;

// BUILD 12 — M15 Breakout Strategy
CBreakoutStrategy b12_breakout_strategy;

// BUILD 08 — Position Manager
CPositionManager b08_position_manager;

// BUILD 09 — Quality Gate
CQualityGate b09_quality_gate;
QualityGateResult b09_last_quality_result;

// BUILD 10 — Execution Bridge
CExecutionBridge b10_execution_bridge;

// BUILD 15 — Execution Safety Guard
CExecutionSafetyGuard b15_safety_guard;
CDailyRiskLedger daily_ledger;
CInitialStopStore initial_stop_store;
bool unprotected_position_present = false;

// Maximum slippage in points for quote drift check (F-03)
#define MAX_SLIPPAGE_DRIFT_POINTS 10.0

// F-04: H1 provenance — temp state for atomic commit
RegimeResult b06_pending_result;
bool b06_pending_valid = false;
datetime b06_pending_bar_time = 0;

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

void ResetB06CycleProvenance()
{
   b06_cycle_b04_rates_ready = false;
   b06_cycle_b04_atr_ready = false;
   b06_cycle_b05_rates_ready = false;
   b06_cycle_b05_atr_ready = false;
   b06_cycle_b04_timestamp = 0;
   b06_cycle_b05_timestamp = 0;
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
    
    if(copiedRates < 3)
    {
       ResetH1BrainInvalid(h1_brain);
       build05_diagnostic_counters.abnormalSkips++;
       if(copiedRates < 0)
          build05_diagnostic_counters.copyBufferFailures++;
       return;
    }

      const datetime closedH1 = rates[copiedRates - 1].time;
      b06_cycle_b05_rates_ready = closedH1 > 0;
      b06_cycle_b05_timestamp = closedH1;
    if(closedH1 == iTime(_Symbol, PERIOD_H1, 0))
    {
       build05_diagnostic_counters.formingBarAttempts++;
       return;
    }
    if(b05_last_accepted_h1 != 0 && closedH1 <= b05_last_accepted_h1)
    {
       build05_diagnostic_counters.duplicateH1Attempts++;
       return;
    }

    ResetH1BrainInvalid(h1_brain);
    const int copiedAtr = CopyBrainBuffer(atr_h1_handle_b05, atrB05, requested);
    const int copiedFast = CopyBrainBuffer(ema_fast_h1_handle, emaFast, requested);
    const int copiedSlow = CopyBrainBuffer(ema_slow_h1_handle, emaSlow, requested);
    const int copiedAdx = CopyBrainBuffer(adx_h1_handle, adx, requested);

      const bool atrBufferReady = copiedAtr == copiedRates;
      const bool emaBufferReady = copiedFast == copiedRates && copiedSlow == copiedRates;
      const bool adxBufferReady = copiedAdx == copiedRates;
      b06_cycle_b05_atr_ready = atrBufferReady && BrainValidAt(atrB05[copiedRates - 1]);

      const ENUM_DIRECTION_STATE prevDirection = b05_state.directionState;
      const ENUM_MOMENTUM_STATE prevMomentum = b05_state.momentumState;
      const ENUM_VOLATILITY_LEVEL prevVolLevel = b05_state.volLevel;
      const ENUM_VOLATILITY_QUALITY prevVolQuality = b05_state.volQuality;
      Build05RawTrace trace;
      if(copiedAtr != copiedRates) build05_diagnostic_counters.copyBufferFailures++;
      if(copiedFast != copiedRates) build05_diagnostic_counters.copyBufferFailures++;
      if(copiedSlow != copiedRates) build05_diagnostic_counters.copyBufferFailures++;
      if(copiedAdx != copiedRates) build05_diagnostic_counters.copyBufferFailures++;
      bool b05_ok = ProcessBuild05ClosedHistoryPrefix(rates, atrB05, emaFast, emaSlow, adx,
                                         copiedRates, atrBufferReady, emaBufferReady, adxBufferReady,
                                         b05_state, h1_brain, trace);
      if(!atrBufferReady)
         build05_diagnostic_counters.invalidAtr++;
      else if(atrBufferReady && copiedAtr >= copiedRates)
      {
         if(!BrainValidAt(atrB05[copiedRates - 1]))
            build05_diagnostic_counters.invalidAtr++;
      }
      if(!emaBufferReady) build05_diagnostic_counters.invalidEma++;
      if(!adxBufferReady) build05_diagnostic_counters.adxDegraded++;
      if(!b05_state.volQualityReady) build05_diagnostic_counters.volQualityNotReady++;
      if(!b05_ok) build05_diagnostic_counters.abnormalSkips++;

      if(b05_ok)
      {
         b05_last_accepted_h1 = closedH1;
         b05_h1_brain_primed = true;
      }

      if(b05_ok && Build05DiagnosticMode)
      {
         Build05DiagnosticTransitions(h1_brain, b05_state, prevDirection, prevMomentum, prevVolLevel, prevVolQuality);
         Build05DiagnosticCollect(h1_brain, b05_state, trace, build05_diagnostic_counters);
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
    b06_cycle_b04_rates_ready = rates[copiedRates - 1].time > 0;
    b06_cycle_b04_timestamp = rates[copiedRates - 1].time;
    b06_cycle_b04_atr_ready = copiedAtr == copiedRates && BrainValidAt(atr[copiedRates - 1]);
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

void B06BreakTrackerInit(B06BreakTracker &tracker)
{
   tracker.bullTime = 0;
   tracker.bearTime = 0;
   tracker.bullAge = -1;
   tracker.bearAge = -1;
}

datetime B06NewestBreakTime(const SwingStructureResult &structure, const bool bullish)
{
   datetime newest = 0;
   for(int i = 0; i < structure.breakCount; i++)
      if(structure.breaks[i].bullish == bullish && structure.breaks[i].time > newest)
         newest = structure.breaks[i].time;
   return newest;
}

void B06AdvanceBreakTracker(const SwingStructureResult &structure, const MqlRates &rates[], const int index,
                            const B06BreakTracker &tracker, B06BreakTracker &next)
{
   next = tracker;
   const datetime bullTime = B06NewestBreakTime(structure, true);
   const datetime bearTime = B06NewestBreakTime(structure, false);
   next.bullTime = bullTime;
   next.bearTime = bearTime;
   next.bullAge = B06ChronologicalBreakAge(rates, index, bullTime, BreakoutLookbackBars);
   next.bearAge = B06ChronologicalBreakAge(rates, index, bearTime, BreakoutLookbackBars);
}

bool BuildRegimeObservation(const SwingStructureResult &structure, const H1BrainResult &brain,
                            const datetime closedH1, const bool criticalCoreValid,
                            const B06BreakTracker &tracker,
                            RegimeObservation &out, int &nextBullAge, int &nextBearAge)
{
   if(closedH1 <= 0 || structure.latestTime != closedH1
      || brain.direction.latestClosedH1 != closedH1
      || brain.momentum.latestClosedH1 != closedH1
      || brain.volatility.latestClosedH1 != closedH1)
      return false;

   ZeroMemory(out);
   out.latestClosedH1 = closedH1;
   out.criticalCoreValid = criticalCoreValid;
   out.structureValid = structure.valid;
   out.directionValid = brain.direction.valid;
   out.momentumValid = brain.momentum.valid; // ADX helper degradation is direction-only.
   out.volatilityValid = brain.volatility.valid;
   out.structureState = structure.state;
   out.directionState = brain.direction.state;
   out.directionScore = brain.direction.score;
   out.momentumState = brain.momentum.state;
   out.momentumStrength = brain.momentum.strengthScore;
   out.momentumDirectionalAlignment = brain.momentum.directionalAlignment;
   out.volatilityLevel = brain.volatility.level;
   out.volatilityQuality = brain.volatility.quality;
   out.compressionEvidence = brain.volatility.compressionScore;
   out.expansionEvidence = brain.volatility.expansionScore;

   nextBullAge = tracker.bullAge;
   nextBearAge = tracker.bearAge;
   out.breakBullAgePresent = nextBullAge >= 0;
   out.breakBullAgeBars = nextBullAge < 0 ? 0 : nextBullAge;
   out.breakBearAgePresent = nextBearAge >= 0;
   out.breakBearAgeBars = nextBearAge < 0 ? 0 : nextBearAge;
   return true;
}

bool B06CycleCriticalCoreValid(const datetime closedH1)
{
   return b06_cycle_b04_rates_ready && b06_cycle_b04_atr_ready
          && b06_cycle_b05_rates_ready && b06_cycle_b05_atr_ready
          && b06_cycle_b04_timestamp == closedH1 && b06_cycle_b05_timestamp == closedH1;
}

void RejectB06Observation(const string reason)
{
   b06_primed = false;
   if(Build06DiagnosticMode)
      LogDebug("REGIME_ALIGN_SKIP", reason);
}

bool ProcessRegimeObservation(const SwingStructureResult &structure, const H1BrainResult &brain,
                              const datetime closedH1, const bool criticalCoreValid,
                              RegimeFusionState &state, RegimeCompressionMemory &compression,
                              RegimeResult &result, datetime &lastAccepted,
                              B06BreakTracker &tracker,
                              const MqlRates &rates[], const int rateIndex)
{
   RegimeObservation observation;
   int nextBullAge, nextBearAge;
   B06BreakTracker nextTracker;
   B06AdvanceBreakTracker(structure, rates, rateIndex, tracker, nextTracker);
   if(!BuildRegimeObservation(structure, brain, closedH1, criticalCoreValid, nextTracker,
                               observation, nextBullAge, nextBearAge))
      return false;
   RegimeFusionParams p;
   BuildRegimeFusionParams(p);
   if(!IngestRegimeObservation(state, compression, lastAccepted, observation, p, result))
      return false;
   tracker = nextTracker;
   return true;
}

void UpdateH1RegimeFusion()
{
   const datetime b04Time = swing_structure.latestTime;
   if(b04Time == 0 || h1_brain.direction.latestClosedH1 != b04Time
      || h1_brain.momentum.latestClosedH1 != b04Time
      || h1_brain.volatility.latestClosedH1 != b04Time)
   {
      RejectB06Observation(StringFormat("b04=%I64d direction=%I64d momentum=%I64d volatility=%I64d",
                           (long)b04Time, (long)h1_brain.direction.latestClosedH1,
                           (long)h1_brain.momentum.latestClosedH1, (long)h1_brain.volatility.latestClosedH1));
      return;
   }
   MqlRates liveRate[];
   ArraySetAsSeries(liveRate, true);
   const int liveCopied = CopyRates(_Symbol, PERIOD_H1, 1, BreakoutLookbackBars + 1, liveRate);
   ArraySetAsSeries(liveRate, false);
   if(liveCopied < 1 || liveRate[liveCopied - 1].time != b04Time)
   {
      RejectB06Observation("break_chronology_unavailable");
      return;
   }
   if(ProcessRegimeObservation(swing_structure, h1_brain, b04Time, B06CycleCriticalCoreValid(b04Time),
                               b06_state, b06_compression, b06_result, b06_last_accepted_h1,
                               b06_break_tracker, liveRate, liveCopied - 1))
   {
      b06_primed = true;
      Build06DiagnosticCollect(b06_result, b06_state, b06_compression);
   }
   else
      RejectB06Observation(StringFormat("ingest=%I64d last=%I64d", (long)b04Time, (long)b06_last_accepted_h1));
}

// Cold-start reconstruction (section 15b): replay synchronized completed-H1 B04/B05
// final outputs oldest->newest through the SAME B06 state machine. Re-invokes the
// existing B04/B05 pure engine functions on truncated prefixes; does NOT modify
// their locked semantics.
void RebuildRegimeFusionState()
{
   b06_rebuild_success = false;
   MqlRates rates[];
   double atrB04[], atrB05[], emaFast[], emaSlow[], adx[];

   ArraySetAsSeries(rates, true);
   ResetLastError();
   // WHOLE_ARRAY intent: reconstruct every broker-provided completed H1, never a suffix.
   const int available = Bars(_Symbol, PERIOD_H1);
   const int copiedRates = available > 1 ? CopyRates(_Symbol, PERIOD_H1, 1, available - 1, rates) : -1;
   ArraySetAsSeries(rates, false);
   if(copiedRates < 0) return;
   if(copiedRates == 0) return;

      const int copiedAtrB04 = CopyBrainBuffer(atr_h1_handle, atrB04, copiedRates);
      const int copiedAtrB05 = CopyBrainBuffer(atr_h1_handle_b05, atrB05, copiedRates);
      const int copiedFast = CopyBrainBuffer(ema_fast_h1_handle, emaFast, copiedRates);
      const int copiedSlow = CopyBrainBuffer(ema_slow_h1_handle, emaSlow, copiedRates);
      const int copiedAdx = CopyBrainBuffer(adx_h1_handle, adx, copiedRates);

    const bool atrB04Ok = copiedAtrB04 == copiedRates;
    const bool atrB05Ok = copiedAtrB05 == copiedRates;
      const bool atrBufferReady = copiedAtrB05 == copiedRates;
      const bool emaBufferReady = copiedFast == copiedRates && copiedSlow == copiedRates;
      const bool adxBufferReady = copiedAdx == copiedRates;
      if(copiedAtrB04 != copiedRates || copiedAtrB05 != copiedRates || copiedFast != copiedRates
         || copiedSlow != copiedRates || copiedAdx != copiedRates) return;

    // Replay-local state — globals change only after complete strict replay.
    SwingStructureResult replayStructure;
    ZeroMemory(replayStructure);
   Build05BehaviorState replayB05State;
   Build05BehaviorStateInit(replayB05State);

    H1BrainResult replayBrain;
    ResetH1BrainInvalid(replayBrain);
    RegimeFusionState replayB06State;
    RegimeFusionStateInit(replayB06State);
    RegimeCompressionMemory replayCompression;
    RegimeCompressionInit(replayCompression, BreakoutLookbackBars);
    RegimeResult replayResult;
    ZeroMemory(replayResult);
    datetime replayLastAccepted = 0;
    B06BreakTracker replayBreakTracker;
    B06BreakTrackerInit(replayBreakTracker);
    bool replayAligned = true;
    bool replayPublished = false;
    const int warmup = 0;

    for(int t = warmup; t < copiedRates; t++)
    {
       const int b04Count = MathMin(t + 1, MathMax(SwingLookbackBars, SwingPivotWidth * 2 + 3));
       const int b05Count = MathMin(t + 1, MathMax(SwingLookbackBars, 100));
       const int b04Start = t + 1 - b04Count;
       const int b05Start = t + 1 - b05Count;
       MqlRates b04Rates[], b05Rates[];
       double b04Atr[], b05Atr[], b05Fast[], b05Slow[], b05Adx[];
       ArrayResize(b04Rates, b04Count); ArrayResize(b04Atr, b04Count);
       ArrayResize(b05Rates, b05Count); ArrayResize(b05Atr, b05Count);
       ArrayResize(b05Fast, b05Count); ArrayResize(b05Slow, b05Count); ArrayResize(b05Adx, b05Count);
       for(int i = 0; i < b04Count; i++) { b04Rates[i] = rates[b04Start + i]; b04Atr[i] = atrB04[b04Start + i]; }
       for(int i = 0; i < b05Count; i++)
       { b05Rates[i] = rates[b05Start + i]; b05Atr[i] = atrB05[b05Start + i]; b05Fast[i] = emaFast[b05Start + i]; b05Slow[i] = emaSlow[b05Start + i]; b05Adx[i] = adx[b05Start + i]; }

       // B04 final output at prefix t
       SwingStructureResult nextStruct;
       Build04DiagnosticTrace replayTrace;
       const bool structOk = ProcessSwingStructure(b04Rates, b04Atr, b04Count, SwingPivotWidth,
                                                   SwingEqualToleranceAtr, SwingHistoryBars,
                                                   nextStruct, false, replayTrace);
      if(structOk)
      {
         PreserveSwingStructureFollowThrough(replayStructure, nextStruct);
         replayStructure = nextStruct;
      }

       // B05 final output at prefix t — canonical update
        Build05RawTrace replayB05Trace;
        ProcessBuild05ClosedHistoryPrefix(b05Rates, b05Atr, b05Fast, b05Slow, b05Adx,
                                          b05Count, atrBufferReady, emaBufferReady, adxBufferReady,
                                          replayB05State, replayBrain, replayB05Trace);
       if(!structOk)
       {
          if(!replayPublished) continue;
          replayAligned = false;
          break;
       }
       const bool coreReady = atrB04Ok && atrB05Ok && BrainValidAt(atrB04[t]) && BrainValidAt(atrB05[t]);
       if(!ProcessRegimeObservation(replayStructure, replayBrain, rates[t].time, coreReady,
                                    replayB06State, replayCompression, replayResult, replayLastAccepted,
                                    replayBreakTracker, rates, t)) { replayAligned = false; break; }
       replayPublished = true;
    }
    if(!replayAligned || !replayPublished || replayLastAccepted == 0) return;

    // Atomic hydrate after every historical completed-H1 observation succeeded.
    swing_structure = replayStructure;
    b05_state = replayB05State;
    h1_brain = replayBrain;
    b05_last_accepted_h1 = replayLastAccepted;
    b05_h1_brain_primed = true;
    b06_state = replayB06State;
    RegimeCompressionCopy(b06_compression, replayCompression);
    b06_result = replayResult;
    b06_last_accepted_h1 = replayLastAccepted;
    b06_break_tracker = replayBreakTracker;
    b06_primed = true;
    b06_rebuild_success = true;
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

   b07_trend_strategy.SetSymbol(_Symbol);
   b11_range_strategy.SetSymbol(_Symbol);
   b12_breakout_strategy.SetSymbol(_Symbol);
   b08_position_manager.SetSymbol(_Symbol);
   b08_position_manager.SetMagic(MagicNumber);

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
   atr_m15_handle = iATR(_Symbol, PERIOD_M15, 14);
   if(atr_h1_handle_b05 == INVALID_HANDLE || ema_fast_h1_handle == INVALID_HANDLE ||
      ema_slow_h1_handle == INVALID_HANDLE || adx_h1_handle == INVALID_HANDLE ||
      atr_m15_handle == INVALID_HANDLE)
   {
      LogError("INIT_FAILED", StringFormat("BUILD 05/07 indicator creation failed with error %d", GetLastError()));
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
     Build05DiagnosticCountersInit(build05_diagnostic_counters);
     ResetH1BrainInvalid(h1_brain);
    UpdateH1Brain();

    // BUILD 06 cold-start reconstruction (section 15b): replay synchronized
    // completed-H1 B04/B05 final outputs oldest->newest to rebuild path-dependent
    // B06 state (regime, hysteresis, compression FIFO).
     RebuildRegimeFusionState();
     if(!b06_rebuild_success)
     {
        LogWarning("REPLAY_HISTORY_UNAVAILABLE", "Cold-start from live bars; B06 state will build gradually");
        RegimeFusionStateInit(b06_state);
        RegimeCompressionInit(b06_compression, BreakoutLookbackBars);
        RegimeResult emptyResult;
        ZeroMemory(emptyResult);
        b06_result = emptyResult;
        B06BreakTrackerInit(b06_break_tracker);
        b06_last_accepted_h1 = 0;
        b06_primed = false;
     }

   b10_execution_bridge.SetSymbol(_Symbol);
   b10_execution_bridge.SetMagic(MagicNumber);
   b10_execution_bridge.SetMaxPositions(1);
   b10_execution_bridge.ConfigureRisk(RiskDiagnosticPercent,HardRiskCapPercent,
                                      MinVolumeTolerancePercent,MarginReservePercent);
   daily_ledger.Configure(_Symbol,MagicNumber);
   initial_stop_store.Configure(_Symbol,MagicNumber);
   daily_ledger.Refresh(TimeCurrent()); // failure blocks entries, never management
   b10_execution_bridge.RecoverPendingSubmission();
   if(b06_primed && b06_result.valid) b06_result_available_at=TimeCurrent();

   TRADE_READY = broker_environment.tradeReady;
   EA_READY = true;

   LogBrokerEnvironment(broker_environment);
   LogDebug("EA_READY", StringFormat("Initialized on %s; MagicNumber=%I64u", _Symbol, MagicNumber));
   b15_safety_guard = CExecutionSafetyGuard(2.0, 10.0, AbsoluteMaxSpreadPoints);
   if(RiskDiagnosticMode)
      RunRiskDiagnostic();
   return INIT_SUCCEEDED;
}

// ============================================================================
// Remediation helpers — F02/F04/F08/F09/F12
// ============================================================================

bool CandidateMatchesActiveRegime(const TradeCandidate &c,const RegimeResult &r,const datetime h1AvailableAt)
{
   if(!c.valid || !r.valid || c.symbol!=_Symbol || c.sourceRegime!=r.regime ||
      c.h1SourceBarTime!=r.latestClosedH1 || c.h1AvailableAt!=h1AvailableAt || c.m15AvailableAt<=0) return false;
   if(r.regime==REGIME_TREND_BULL)
      return c.direction==TRADE_DIR_BUY && (c.setupFamily==SETUP_FAMILY_PULLBACK ||
             c.setupFamily==SETUP_FAMILY_BREAK_RETEST || c.setupFamily==SETUP_FAMILY_MOMENTUM);
   if(r.regime==REGIME_TREND_BEAR)
      return c.direction==TRADE_DIR_SELL && (c.setupFamily==SETUP_FAMILY_PULLBACK ||
             c.setupFamily==SETUP_FAMILY_BREAK_RETEST || c.setupFamily==SETUP_FAMILY_MOMENTUM);
   if(r.regime==REGIME_RANGE)
      return c.setupFamily==SETUP_FAMILY_RANGE_SWEEP &&
             (c.direction==TRADE_DIR_BUY || c.direction==TRADE_DIR_SELL);
   if(r.regime==REGIME_BREAKOUT_BULL)
      return c.setupFamily==SETUP_FAMILY_BREAKOUT_DIRECT && c.direction==TRADE_DIR_BUY;
   if(r.regime==REGIME_BREAKOUT_BEAR)
      return c.setupFamily==SETUP_FAMILY_BREAKOUT_DIRECT && c.direction==TRADE_DIR_SELL;
   return false;
}

int CandidatePriority(const TradeCandidate &c)
{
   if(c.setupFamily==SETUP_FAMILY_BREAK_RETEST) return 30;
   if(c.setupFamily==SETUP_FAMILY_PULLBACK) return 20;
   if(c.setupFamily==SETUP_FAMILY_MOMENTUM) return 10;
   return 100;
}

bool PreferCandidate(const TradeCandidate &a,const TradeCandidate &b)
{
   int pa=CandidatePriority(a),pb=CandidatePriority(b);
   if(pa!=pb) return pa>pb;
   if(a.m15AvailableAt!=b.m15AvailableAt) return a.m15AvailableAt<b.m15AvailableAt;
   if(a.structuralReferenceTime!=b.structuralReferenceTime) return a.structuralReferenceTime<b.structuralReferenceTime;
   return (int)a.setupFamily<(int)b.setupFamily;
}

bool SelectActiveCandidate(const TradeCandidate &trend,const bool hasTrend,
                           const TradeCandidate &range,const bool hasRange,
                           const TradeCandidate &breakout,const bool hasBreakout,
                           TradeCandidate &selected)
{
   ZeroMemory(selected); bool found=false;
   if(hasTrend && CandidateMatchesActiveRegime(trend,b06_result,b06_result_available_at)) { selected=trend; found=true; }
   if(hasRange && CandidateMatchesActiveRegime(range,b06_result,b06_result_available_at) &&
      (!found || PreferCandidate(range,selected))) { selected=range; found=true; }
   if(hasBreakout && CandidateMatchesActiveRegime(breakout,b06_result,b06_result_available_at) &&
      (!found || PreferCandidate(breakout,selected))) { selected=breakout; found=true; }
   return found;
}

bool BuildFinalEntryCandidate(const TradeCandidate &base,const BrokerEnvironment &env,const double atr,
                              TradeCandidate &out,string &reason)
{
   ZeroMemory(out); reason="";
   if(!base.valid || atr<=0.0 || base.extensionReferencePrice<=0.0) { reason="invalid_final_candidate_input"; return false; }
   out=base;
   out.entryPrice=b10_execution_bridge.NormalizePrice(base.direction==TRADE_DIR_BUY?env.tick.ask:env.tick.bid);
   out.initialStopPrice=b10_execution_bridge.NormalizeStopPrice(base.initialStopPrice,base.direction,true);
   out.targetPrice=base.targetPrice>0.0?b10_execution_bridge.NormalizeStopPrice(base.targetPrice,base.direction,false):0.0;
   if(base.direction==TRADE_DIR_BUY)
   {
      if(!(out.initialStopPrice<out.entryPrice)) { reason="stop_wrong_side"; return false; }
      if(!(out.targetPrice>out.entryPrice)) { reason="target_passed_or_wrong_side"; return false; }
      out.extensionAtr=(out.entryPrice-base.extensionReferencePrice)/atr;
   }
   else if(base.direction==TRADE_DIR_SELL)
   {
      if(!(out.initialStopPrice>out.entryPrice)) { reason="stop_wrong_side"; return false; }
      if(!(out.targetPrice<out.entryPrice)) { reason="target_passed_or_wrong_side"; return false; }
      out.extensionAtr=(base.extensionReferencePrice-out.entryPrice)/atr;
   }
   else { reason="invalid_direction"; return false; }
   const bool breakoutFamily=base.setupFamily==SETUP_FAMILY_BREAKOUT_DIRECT;
   const double maxExtension=breakoutFamily?B12_MAX_CHASE_ATR:B07_MAX_EXT;
   const bool extensionTooLarge=breakoutFamily?out.extensionAtr>maxExtension:out.extensionAtr>=maxExtension;
   if(out.extensionAtr<0.0 || extensionTooLarge) { reason="final_extension_invalid"; return false; }
   out.stopDistance=MathAbs(out.entryPrice-out.initialStopPrice);
   out.rewardDistance=MathAbs(out.targetPrice-out.entryPrice);
   if(out.stopDistance<=0.0 || out.rewardDistance<=0.0) { reason="invalid_final_distance"; return false; }
   out.stopDistanceAtr=out.stopDistance/atr;
   const bool trendFamily=base.setupFamily==SETUP_FAMILY_PULLBACK ||
      base.setupFamily==SETUP_FAMILY_BREAK_RETEST || base.setupFamily==SETUP_FAMILY_MOMENTUM;
   if(trendFamily && (out.stopDistanceAtr<B07_MIN_STOP || out.stopDistanceAtr>B07_MAX_STOP))
   { reason="final_stop_distance_invalid"; return false; }
   out.rewardRiskRatio=out.rewardDistance/out.stopDistance;
   out.finalizedAt=TimeCurrent();
   return true;
}

RegimeResult ManagementRegime()
{
   RegimeResult r=b06_result;
   datetime expected=iTime(_Symbol,PERIOD_H1,1);
   if(!b06_primed || !r.valid || r.latestClosedH1!=expected || b06_result_available_at<=0) r.valid=false;
   return r;
}

void ManageOpenPositions()
{
   unprotected_position_present=false;
   double m15Atr[]; ArraySetAsSeries(m15Atr,true);
   bool atrReady=CopyBuffer(atr_m15_handle,0,1,1,m15Atr)==1 && m15Atr[0]>0.0;
   double atrVal=atrReady?m15Atr[0]:0.0;
   datetime now=TimeCurrent();
   B07_Swing swings[]; int swingsCount=0; b07_trend_strategy.GetM15Swings(swings,swingsCount);
   RegimeResult managementRegime=ManagementRegime();
   for(int i=PositionsTotal()-1;i>=0;--i)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol || PositionGetInteger(POSITION_MAGIC)!=(long)MagicNumber) continue;
      ENUM_TRADE_DIRECTION dir=PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY?TRADE_DIR_BUY:TRADE_DIR_SELL;
      ulong positionId=(ulong)PositionGetInteger(POSITION_IDENTIFIER);
      double sl=PositionGetDouble(POSITION_SL),tp=PositionGetDouble(POSITION_TP);
      if(sl<=0.0)
      {
         unprotected_position_present=true;
         bool protectedNow=false;
         if(atrReady && broker_environment.tick.bid>0.0 && broker_environment.tick.ask>0.0)
         {
            PositionManageIntent protect; ZeroMemory(protect); protect.ticket=ticket; protect.direction=dir;
            protect.action=POS_ACTION_MODIFY_SL; protect.newTakeProfit=tp; protect.reason="unprotected_position_recovery";
            protect.newStopLoss=dir==TRADE_DIR_BUY?broker_environment.tick.bid-RecoveryStopATRMultiple*atrVal:
                                                     broker_environment.tick.ask+RecoveryStopATRMultiple*atrVal;
            if(b10_execution_bridge.ExecutePositionManage(protect,broker_environment,DeviationPoints) &&
               PositionSelectByTicket(ticket) && PositionGetDouble(POSITION_SL)>0.0) protectedNow=true;
         }
         if(!protectedNow && CloseIfRecoveryStopCannotBeSet)
         {
            PositionManageIntent close; ZeroMemory(close); close.ticket=ticket; close.direction=dir;
            close.action=POS_ACTION_CLOSE_MARKET; close.reason="unprotected_position_fail_closed";
            b10_execution_bridge.ExecutePositionManage(close,broker_environment,DeviationPoints);
         }
         continue;
      }
      double initialSl=0.0;
      if(!initial_stop_store.Load(positionId,initialSl))
      {
         LogWarning("INITIAL_SL_UNKNOWN",StringFormat("position_id=%I64u; 1R management inhibited",positionId));
         continue; // never reconstruct initial risk from a possibly trailed broker SL
      }
      if(!atrReady) continue; // regime/1R action requires ATR; SL protection already exists
      PositionManageIntent intent;
      if(b08_position_manager.Evaluate(ticket,dir,PositionGetDouble(POSITION_PRICE_OPEN),sl,tp,initialSl,
         PositionGetDouble(POSITION_PRICE_CURRENT),atrVal,managementRegime,swings,swingsCount,now,intent))
         b10_execution_bridge.ExecutePositionManage(intent,broker_environment,DeviationPoints);
   }
}

// ============================================================================
// F-03: Final-quote atomic tick fetch — same quote for sizing+preflight+send
// ============================================================================

bool FetchFinalQuote(BrokerEnvironment &env)
{
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick))
   {
      LogWarning("FINAL_QUOTE_FAILED", "Cannot fetch final tick for dispatch");
      return false;
   }

   if(tick.ask <= 0 || tick.bid <= 0 || tick.ask <= tick.bid)
   {
      LogWarning("FINAL_QUOTE_INVALID", "Final tick has invalid prices");
      return false;
   }

   env.tick = tick;
   env.quoteFresh = true;
   return true;
}

void ProcessCompletedM15Bar(const datetime completedH1Time)
{
   datetime curM15Time=iTime(_Symbol,PERIOD_M15,0);
   MqlRates bars[]; double atrs[];
   ArraySetAsSeries(bars,true); ArraySetAsSeries(atrs,true);
   if(CopyRates(_Symbol,PERIOD_M15,1,1,bars)!=1 ||
      CopyBuffer(atr_m15_handle,0,1,1,atrs)!=1 || atrs[0]<=0.0)
   {
      LogWarning("M15_UPDATE_FAILED","Completed M15 bar/ATR unavailable");
      return;
   }
   last_m15_bar_time=curM15Time;
   const datetime completedTime=bars[0].time;
   const datetime availableAt=TimeCurrent();
   LogDebug("NEW_M15_BAR",TimeToString(curM15Time,TIME_DATE|TIME_MINUTES));

   // An unavailable/stale H1 result cannot originate a fresh entry. B07 still owns
   // the one M15 feed and swing timeline; B11/B12 consume its one copied snapshot.
   RegimeResult strategyRegime=b06_result;
   if(!b06_primed || !strategyRegime.valid || strategyRegime.latestClosedH1!=completedH1Time ||
      b06_result_available_at<=0) strategyRegime.valid=false;
   b07_trend_strategy.SetH1Regime(strategyRegime,b06_result_available_at);
   b11_range_strategy.SetH1Regime(strategyRegime,b06_result_available_at);
   b12_breakout_strategy.SetH1Regime(strategyRegime,b06_result_available_at);

   TradeCandidate trend,range,breakout,selected;
   ZeroMemory(trend); ZeroMemory(range); ZeroMemory(breakout); ZeroMemory(selected);
   const bool hasTrend=b07_trend_strategy.FeedM15Bar(completedTime,bars[0].open,bars[0].high,
      bars[0].low,bars[0].close,availableAt,atrs[0],trend);
   B07_Swing swings[]; int swingCount=0;
   b07_trend_strategy.GetM15Swings(swings,swingCount);
   const bool hasRange=b11_range_strategy.Evaluate(completedTime,bars[0].open,bars[0].high,
      bars[0].low,bars[0].close,availableAt,atrs[0],swings,swingCount,range);
   const bool hasBreakout=b12_breakout_strategy.Evaluate(completedTime,bars[0].open,bars[0].high,
      bars[0].low,bars[0].close,availableAt,atrs[0],swings,swingCount,breakout);

   if(!strategyRegime.valid || !SelectActiveCandidate(trend,hasTrend,range,hasRange,breakout,hasBreakout,selected))
   {
      ZeroMemory(b07_last_candidate);
      return;
   }
   b07_last_candidate=selected;

   // Every unresolved/unknown submission and every unprotected EA position is
   // absorbing for entry dispatch, independently of visible exposure.
   if(unprotected_position_present || b10_execution_bridge.EntrySubmissionBlocked())
   {
      LogWarning("TRADE_BLOCKED_RECOVERY","Pending execution or position protection is unresolved");
      return;
   }
   if(b10_execution_bridge.CountActiveOrdersAndPositions()>=1) return;

   string dailyReason="";
   if(!daily_ledger.AllowsNewEntry(TimeCurrent(),MaxDailyLossPercent,MaxConsecutiveLosses,dailyReason))
   {
      LogWarning("TRADE_BLOCKED_DAILY_RISK",dailyReason);
      return;
   }

   const datetime now=TimeCurrent();
   const ENUM_SESSION_STATE session=CSessionNewsEngine::EvaluateSession(now);
   datetime explicitNews[];
   const ENUM_NEWS_STATE observedNews=CSessionNewsEngine::EvaluateNews(now,explicitNews,0,_Symbol);
   const ENUM_NEWS_STATE gatedNews=NewsGuardRequired?observedNews:NEWS_CLEAR;
   double requiredScore=70.0; string gateReason="";
   if(!CSessionNewsEngine::CheckGating(session,gatedNews,requiredScore,gateReason))
   {
      LogWarning("TRADE_BLOCKED_SESSION_NEWS",gateReason);
      return;
   }

   if(!b10_execution_bridge.AcquireOrderLock())
   {
      LogWarning("ORDER_LOCK_BLOCKED","Terminal-global order lock unavailable");
      return;
   }
   // Re-check both invisible submission state and visible exposure after winning CAS.
   if(b10_execution_bridge.EntrySubmissionBlocked() || unprotected_position_present ||
      b10_execution_bridge.CountActiveOrdersAndPositions()>=1)
   {
      b10_execution_bridge.ReleaseOrderLock();
      return;
   }
   if(!FetchFinalQuote(broker_environment))
   {
      b10_execution_bridge.ReleaseOrderLock();
      return;
   }

   TradeCandidate finalCandidate; string finalReason="";
   if(!BuildFinalEntryCandidate(selected,broker_environment,atrs[0],finalCandidate,finalReason))
   {
      LogWarning("FINAL_CANDIDATE_REJECTED",finalReason);
      b10_execution_bridge.ReleaseOrderLock();
      return;
   }
   const double spreadPrice=broker_environment.tick.ask-broker_environment.tick.bid;
   if(!b09_quality_gate.Evaluate(finalCandidate,strategyRegime,spreadPrice,b09_last_quality_result) ||
      b09_last_quality_result.totalScore<requiredScore)
   {
      LogDebug("B09_QUALITY_REJECTED",StringFormat("score=%.1f reason=%s",b09_last_quality_result.totalScore,
               b09_last_quality_result.rejectReason));
      b10_execution_bridge.ReleaseOrderLock();
      return;
   }

   FinalMarketOrder plan;
   if(!b10_execution_bridge.BuildFinalMarketOrder(finalCandidate,broker_environment,DeviationPoints,plan))
   {
      LogWarning("FINAL_ORDER_REJECTED",plan.rejectReason);
      b10_execution_bridge.ReleaseOrderLock();
      return;
   }
   ExecutionSafetyResult safety;
   if(!b15_safety_guard.ValidateFinalOrder(plan,broker_environment,safety))
   {
      LogWarning("EXECUTION_BLOCKED_SAFETY",safety.failReason);
      b10_execution_bridge.ReleaseOrderLock();
      return;
   }

   MqlTradeResult sendResult;
   b10_execution_bridge.SendFinalMarketOrder(plan,sendResult);
   ENUM_EXECUTION_LIFECYCLE lifecycle=b10_execution_bridge.GetLifecycle();
   if(lifecycle==EXEC_LIFECYCLE_CONFIRMED || lifecycle==EXEC_LIFECYCLE_REJECTED)
      b10_execution_bridge.ReleaseOrderLock();
}

void OnTick()
{
   if(!EA_READY) return;
   RefreshEnvironmentStatus(broker_environment);

   // Consume the newest completed H1 first. A failed cycle leaves old provenance
   // visible but invalid for regime flips/entries; protective BE/trailing still runs.
   datetime completedH1Time=iTime(_Symbol,PERIOD_H1,1);
   if(DetectNewBar(PERIOD_H1,last_h1_bar_time))
   {
      const datetime currentH1Time=iTime(_Symbol,PERIOD_H1,0);
      ResetB06CycleProvenance();
      const bool structureReady=UpdateSwingStructure();
      UpdateH1Brain();
      UpdateH1RegimeFusion();
      if(structureReady && b06_result.valid && b06_result.latestClosedH1==completedH1Time)
      {
         last_h1_bar_time=currentH1Time;
         b06_result_available_at=TimeCurrent();
      }
      else LogWarning("H1_UPDATE_FAILED","Fresh H1 fusion unavailable; entries and regime exits suppressed");
   }

   ManageOpenPositions();
   if(DetectNewBar(PERIOD_M15,last_m15_bar_time)) ProcessCompletedM15Bar(completedH1Time);

   // F10: exactly one epilogue append for every valid tick, after all decisions.
   b15_safety_guard.FinalizeOnTickSample(broker_environment);
   CDashboardHUD::Update(broker_environment,b06_result,b07_last_candidate,b09_last_quality_result,
                         MagicNumber,b10_execution_bridge.CountOpenPositions());
}

void OnTimer()
{
   if(!EA_READY) return;
   const bool oldCompatible=broker_environment.environmentCompatible;
   const bool oldReady=TRADE_READY;
   RefreshEnvironmentStatus(broker_environment); TRADE_READY=broker_environment.tradeReady;
   if(oldCompatible!=broker_environment.environmentCompatible || oldReady!=TRADE_READY)
      LogBrokerEnvironment(broker_environment);

   if(b10_execution_bridge.EntrySubmissionBlocked())
   {
      if(b10_execution_bridge.IsLockHeld()) b10_execution_bridge.ReconcilePending();
      else b10_execution_bridge.RecoverPendingSubmission();
   }
   ENUM_EXECUTION_LIFECYCLE lifecycle=b10_execution_bridge.GetLifecycle();
   if((lifecycle==EXEC_LIFECYCLE_CONFIRMED || lifecycle==EXEC_LIFECYCLE_REJECTED) &&
      b10_execution_bridge.IsLockHeld()) b10_execution_bridge.ReleaseOrderLock();
   daily_ledger.RefreshIfRolloverOrDirty(TimeCurrent());
}

void OnTradeTransaction(const MqlTradeTransaction &transaction,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   if(transaction.type==TRADE_TRANSACTION_DEAL_ADD && transaction.deal>0 &&
      HistoryDealSelect(transaction.deal) &&
      HistoryDealGetString(transaction.deal,DEAL_SYMBOL)==_Symbol &&
      HistoryDealGetInteger(transaction.deal,DEAL_MAGIC)==(long)MagicNumber)
   {
      const ENUM_DEAL_ENTRY entry=(ENUM_DEAL_ENTRY)HistoryDealGetInteger(transaction.deal,DEAL_ENTRY);
      const ulong positionId=(ulong)HistoryDealGetInteger(transaction.deal,DEAL_POSITION_ID);
      if(entry==DEAL_ENTRY_IN || entry==DEAL_ENTRY_INOUT)
      {
         const double acceptedInitialSl=b10_execution_bridge.GetPendingInitialStop();
         if(acceptedInitialSl>0.0 && !initial_stop_store.Save(positionId,acceptedInitialSl))
            LogError("INITIAL_SL_PERSIST_FAILED",StringFormat("position_id=%I64u",positionId));
      }
      daily_ledger.MarkDirty();
      b10_execution_bridge.ReconcilePending();
      if(entry==DEAL_ENTRY_OUT || entry==DEAL_ENTRY_OUT_BY || entry==DEAL_ENTRY_INOUT)
         initial_stop_store.RemoveIfFullyClosed(positionId); // partial closes retain the identifier key
   }
   else if(transaction.type==TRADE_TRANSACTION_ORDER_ADD ||
           transaction.type==TRADE_TRANSACTION_ORDER_UPDATE ||
           transaction.type==TRADE_TRANSACTION_ORDER_DELETE)
      b10_execution_bridge.ReconcilePending();

   if(EA_READY && DebugMode)
      LogDebug("TRADE_TRANSACTION",StringFormat("type=%d order=%I64u deal=%I64u request_action=%d retcode=%u state=%d",
         transaction.type,transaction.order,transaction.deal,request.action,result.retcode,
         b10_execution_bridge.GetLifecycle()));
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
    if(atr_m15_handle != INVALID_HANDLE)
        IndicatorRelease(atr_m15_handle);
    atr_h1_handle_b05 = INVALID_HANDLE;
    ema_fast_h1_handle = INVALID_HANDLE;
    ema_slow_h1_handle = INVALID_HANDLE;
    adx_h1_handle = INVALID_HANDLE;
    atr_m15_handle = INVALID_HANDLE;
    LogDebug("EA_STOPPED", StringFormat("Deinitialized; reason=%d", reason));

}
