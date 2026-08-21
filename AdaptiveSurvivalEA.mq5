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
Build05DiagnosticCounters build05_diagnostic_counters;
bool b05_h1_brain_primed = false;

// BUILD 06 — H1 Regime Fusion persistence state
RegimeFusionState b06_state;
RegimeCompressionMemory b06_compression;
RegimeResult b06_result;
bool b06_primed = false;
datetime b06_last_accepted_h1 = 0;
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
     Build05DiagnosticCountersInit(build05_diagnostic_counters);
     ResetH1BrainInvalid(h1_brain);
    UpdateH1Brain();

    // BUILD 06 cold-start reconstruction (section 15b): replay synchronized
    // completed-H1 B04/B05 final outputs oldest->newest to rebuild path-dependent
    // B06 state (regime, hysteresis, compression FIFO).
     RebuildRegimeFusionState();
     if(!b06_rebuild_success)
     {
        LogError("INIT_FAILED", "REPLAY_HISTORY_UNAVAILABLE");
        return INIT_FAILED;
     }

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
        ResetB06CycleProvenance();
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
