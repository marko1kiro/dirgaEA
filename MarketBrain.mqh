#ifndef ADAPTIVE_SURVIVAL_EA_MARKET_BRAIN_MQH
#define ADAPTIVE_SURVIVAL_EA_MARKET_BRAIN_MQH

#include "Types.mqh"
#include "DiagnosticCollector.mqh"

// ---------------------------------------------------------------------------
// BUILD 05 — H1 Direction / Momentum / Volatility
//
// Pure functions over chronological arrays (index 0 = oldest, last = newest
// completed H1 bar). Engines do NOT mutate BUILD 04 state and produce no trade
// signals. Hysteresis/dwell/age is tracked by the caller (the EA) across
// consecutive completed-H1 updates; the functions below compute the raw
// evidence and the per-bar classification. Fixed evidence weights are internal
// constants (small parameter surface), never inputs.
// ---------------------------------------------------------------------------

#define BRAIN_EMA_FAST 20
#define BRAIN_EMA_SLOW 50
#define BRAIN_ADX_PERIOD 14
#define BRAIN_ATR_PERIOD 14
#define BRAIN_DISPLACEMENT_BARS 20
#define BRAIN_MOM_PROGRESSION_BARS 5

#define DIR_STRONG_COMMIT 0.75
#define DIR_COMMIT 0.45
#define DIR_NEUTRAL_DROP 0.20
#define DIR_DWELL 2

#define MOM_STRONG 0.60
#define MOM_WEAK 0.40
#define MOM_SLOPE_UP 0.05
#define MOM_SLOPE_DOWN -0.05
#define MOM_PERSISTENCE 2

#define VOL_HIGH_RATIO 1.5
#define VOL_EXTREME_RATIO 2.0
#define VOL_LOW_RATIO 0.7
#define VOL_LEVEL_DWELL 2

#define VOLQ_GAP 0.10
#define VOLQ_DWELL 2

double BrainClampSigned(const double v) { return MathMax(-1.0, MathMin(1.0, v)); }
double BrainClampUnit(const double v)  { return MathMax(0.0, MathMin(1.0, v)); }

double BrainMean3(const double a, const double b, const double c)
{ return (a + b + c) / 3.0; }

double BrainMean5(const double a, const double b, const double c,
                  const double d, const double e)
{ return (a + b + c + d + e) / 5.0; }

double BrainShrinkEvidence(const double recentAvg, const double priorAvg)
{
   if(priorAvg <= 0.0) return 0.0;
   return BrainClampUnit(1.0 - recentAvg / priorAvg);
}

double BrainExpandEvidence(const double recentAvg, const double priorAvg)
{
   if(priorAvg <= 0.0) return 0.0;
   return BrainClampUnit(recentAvg / priorAvg - 1.0);
}

void ResetH1BrainInvalid(H1BrainResult &brain)
{
   brain.direction.state = DIRECTION_NEUTRAL;
   brain.direction.score = 0.0;
   brain.direction.valid = false;
   brain.direction.latestClosedH1 = 0;
   
   brain.momentum.state = MOMENTUM_NORMAL;
   brain.momentum.strengthScore = 0.0;
   brain.momentum.strengthDelta = 0.0;
   brain.momentum.strengthSlope = 0.0;
   brain.momentum.directionalAlignment = 0.0;
   brain.momentum.valid = false;
   brain.momentum.helperDegraded = false;
   brain.momentum.latestClosedH1 = 0;
   
   brain.volatility.level = VOL_NORMAL;
   brain.volatility.quality = VOLQ_HEALTHY;
   brain.volatility.levelScore = 0.0;
   brain.volatility.qualityConfidence = 0.0;
   brain.volatility.compressionScore = 0.0;
   brain.volatility.expansionScore = 0.0;
   brain.volatility.chaosScore = 0.0;
   brain.volatility.shockScore = 0.0;
   brain.volatility.healthyScore = 0.0;
   brain.volatility.valid = false;
   brain.volatility.latestClosedH1 = 0;
}

// ---------------------------------------------------------------------------
// BUILD 05 canonical behavior/persistence state
// ---------------------------------------------------------------------------

void Build05BehaviorStateInit(Build05BehaviorState &s)
{
   s.directionState = DIRECTION_NEUTRAL;
   s.directionDwell = 0;
   s.directionChallenger = DIRECTION_NEUTRAL;
   s.directionChallengerDwell = 0;

   s.momentumState = MOMENTUM_NORMAL;
   s.momentumPersist = 0;
   s.prevMomentumStrength = 0.0;
   s.momentumStrengthPrimed = false;

   s.volLevel = VOL_NORMAL;
   s.volLevelDwell = 0;
   s.volLevelChallenger = VOL_NORMAL;
   s.volLevelChallengerDwell = 0;

   s.volQuality = VOLQ_HEALTHY;
   s.volQualityConfidence = 0.0;
   s.volQualityPrimed = false;
   s.volQualityChallenger = VOLQ_HEALTHY;
   s.volQualityChallengerDwell = 0;
   s.volQualityReady = false;
}

// Canonical per-prefix B05 update. Used by BOTH live and cold-replay.
// Returns true if the result is valid (ATR available).
bool ProcessBuild05ClosedHistoryPrefix(
   const MqlRates &rates[],
   const double &atr[],
   const double &emaFast[],
   const double &emaSlow[],
   const double &adx[],
   const int count,
   const bool atrBufferReady,
   const bool emaBufferReady,
   const bool adxBufferReady,
   Build05BehaviorState &state,
   H1BrainResult &result,
   Build05RawTrace &trace,
   int &copyBufferFailures)
{
     ResetH1BrainInvalid(result);
     ZeroMemory(trace);
     copyBufferFailures = 0;
    if(!atrBufferReady) copyBufferFailures++;
    if(!emaBufferReady) copyBufferFailures++;
    if(!adxBufferReady) copyBufferFailures++;

    if(count < 3)
   {
      const datetime closed = (count > 0 ? rates[count - 1].time : 0);
      result.direction.latestClosedH1 = closed;
      result.momentum.latestClosedH1 = closed;
      result.volatility.latestClosedH1 = closed;
      return false;
   }

   // Direction (requires ATR + both EMA)
   if(atrBufferReady && emaBufferReady)
   {
       DirectionEngine(rates, emaFast, emaSlow, atr, count, result.direction, trace);
      if(result.direction.valid)
      {
         DirectionClassify(result.direction.score, state.directionState, state.directionDwell,
                           state.directionState, state.directionDwell,
                           state.directionChallenger, state.directionChallengerDwell);
         result.direction.state = state.directionState;
      }
   }

    // Momentum (requires ATR; ADX is helper-only)
    if(atrBufferReady)
    {
        MomentumEngine(rates, atr, adx, count, adxBufferReady, result.momentum, trace);
      if(result.momentum.valid)
      {
         if(state.momentumStrengthPrimed)
            result.momentum.strengthDelta = result.momentum.strengthScore - state.prevMomentumStrength;
         else
            result.momentum.strengthDelta = 0.0;
         result.momentum.strengthSlope = BrainClampSigned(result.momentum.strengthDelta);
         MomentumClassify(result.momentum.strengthScore, result.momentum.strengthSlope,
                          state.momentumState, state.momentumPersist, state.momentumState);
         result.momentum.state = state.momentumState;
         state.prevMomentumStrength = result.momentum.strengthScore;
         state.momentumStrengthPrimed = true;
      }
   }

    // Volatility Level + Quality (requires ATR)
    if(atrBufferReady)
    {
       VolatilityEngine(rates, atr, count, VolatilityBaselineBars, result.volatility, trace);
      if(result.volatility.valid)
      {
         VolatilityLevelClassify(result.volatility.levelScore, state.volLevel, state.volLevelDwell,
                                 state.volLevel, state.volLevelDwell,
                                 state.volLevelChallenger, state.volLevelChallengerDwell);
         result.volatility.level = state.volLevel;
         if(BrainVolQualityReady(count))
         {
             VolatilityQualityEngine(rates, atr, count, result.volatility, trace);
            double evidence[5];
            evidence[0] = result.volatility.healthyScore;
            evidence[1] = result.volatility.compressionScore;
            evidence[2] = result.volatility.expansionScore;
            evidence[3] = result.volatility.chaosScore;
            evidence[4] = result.volatility.shockScore;
            VolatilityQualitySelect(evidence, state.volQuality, state.volQualityPrimed,
                                    state.volQualityChallenger, state.volQualityChallengerDwell,
                                    state.volQuality, state.volQualityConfidence,
                                    state.volQualityPrimed,
                                    state.volQualityChallenger, state.volQualityChallengerDwell);
            result.volatility.quality = state.volQuality;
            result.volatility.qualityConfidence = state.volQualityConfidence;
         }
      }
    }

     state.volQualityReady = BrainVolQualityReady(count);
     trace.qualityReady = state.volQualityReady;
     return result.direction.valid || result.momentum.valid || result.volatility.valid;
}

double BrainTanh(const double v)
{
   // bounded sigmoid for ATR-normalized slopes/displacements -> [-1, 1]
   const double e = MathExp(-2.0 * v);
   if(!MathIsValidNumber(e)) return v >= 0.0 ? 1.0 : -1.0;
   return (1.0 - e) / (1.0 + e);
}

bool BrainValidAt(const double v) { return MathIsValidNumber(v) && v > 0.0; }

// Net displacement over N bars / ATR (chronological, index 0 = oldest).
double BrainDisplacement(const MqlRates &rates[], const double &atr[], const int count, const int bars)
{
   if(bars <= 0 || count < bars + 1) return 0.0;
   const double a = atr[count - 1];
   if(!BrainValidAt(a)) return 0.0;
   return (rates[count - 1].close - rates[count - 1 - bars].close) / a;
}

// Signed directional efficiency for Direction domain: netDirectional / totalPath (signed, [-1, +1]).
double BrainEfficiencySigned(const MqlRates &rates[], const int count, const int bars)
{
   if(bars <= 0 || count < bars + 1) return 0.0;
   double netDirectional = rates[count - 1].close - rates[count - 1 - bars].close;
   double path = 0.0;
   for(int i = count - bars; i < count; i++)
      path += MathAbs(rates[i].close - rates[i - 1].close);
   if(path <= 0.0) return 0.0;
   return netDirectional / path;
}

// Path efficiency magnitude for Momentum domain: |netDirectional| / totalPath (unsigned, [0, 1]).
double BrainEfficiencyMagnitude(const MqlRates &rates[], const int count, const int bars)
{
   if(bars <= 0 || count < bars + 1) return 0.0;
   double netDirectional = rates[count - 1].close - rates[count - 1 - bars].close;
   double path = 0.0;
   for(int i = count - bars; i < count; i++)
      path += MathAbs(rates[i].close - rates[i - 1].close);
   if(path <= 0.0) return 0.0;
   return MathAbs(netDirectional) / path;
}

// ---------------------------------------------------------------------------
// Direction
// ---------------------------------------------------------------------------

// Per-bar classification using ordinal hysteresis against a prior state + dwell.
// Challenger dwell tracks consecutive escalation evidence, not incumbent age.
void DirectionClassify(const double score, const ENUM_DIRECTION_STATE prevState, const int dwell,
                       ENUM_DIRECTION_STATE &state, int &outDwell,
                       ENUM_DIRECTION_STATE &challenger, int &challengerDwell)
{
   const double s = BrainClampSigned(score);
   ENUM_DIRECTION_STATE cand;
   if(s >= DIR_STRONG_COMMIT) cand = DIRECTION_STRONG_BULL;
   else if(s >= DIR_COMMIT)   cand = DIRECTION_BULL;
   else if(s <= -DIR_STRONG_COMMIT) cand = DIRECTION_STRONG_BEAR;
   else if(s <= -DIR_COMMIT)  cand = DIRECTION_BEAR;
   else                       cand = DIRECTION_NEUTRAL;

   if(cand == DIRECTION_NEUTRAL) { state = cand; outDwell = 0; challenger = DIRECTION_NEUTRAL; challengerDwell = 0; return; }
   if(prevState == DIRECTION_NEUTRAL) { state = cand; outDwell = 0; challenger = DIRECTION_NEUTRAL; challengerDwell = 0; return; }
   if(cand == prevState) { state = cand; outDwell = MathMin(dwell + 1, DIR_DWELL); challenger = DIRECTION_NEUTRAL; challengerDwell = 0; return; }

   const int candMag = (cand == DIRECTION_STRONG_BULL) ? 2 :
                       (cand == DIRECTION_BULL) ? 1 :
                       (cand == DIRECTION_BEAR) ? -1 : -2;
   const int prevMag = (prevState == DIRECTION_STRONG_BULL) ? 2 :
                       (prevState == DIRECTION_BULL) ? 1 :
                       (prevState == DIRECTION_BEAR) ? -1 : -2;

   const bool challengerTrigger =
       (candMag * prevMag > 0 && MathAbs(candMag) > MathAbs(prevMag))   // same-sign stronger
       || (candMag * prevMag < 0);                                       // opposite-sign reversal

   if(challengerTrigger)
   {
      if(cand == challenger)
         challengerDwell++;
      else
      {
         challenger = cand;
         challengerDwell = 1;
      }
      if(challengerDwell >= DIR_DWELL) { state = cand; outDwell = 0; challenger = DIRECTION_NEUTRAL; challengerDwell = 0; return; }
      state = prevState; outDwell = dwell; return;
   }

   challenger = DIRECTION_NEUTRAL;
   challengerDwell = 0;
   state = cand; outDwell = 0;
}

// Direction evidence from native EMA fast/slow buffers (chronological) + ATR.
void DirectionEngine(const MqlRates &rates[], const double &emaFast[], const double &emaSlow[],
                      const double &atr[], const int count, DirectionResult &out, Build05RawTrace &trace)
{
   H1BrainResult temp;
   ResetH1BrainInvalid(temp);
   out = temp.direction;
   if(count < 3) { out.latestClosedH1 = (count > 0 ? rates[count - 1].time : 0); return; }

   const int n = count - 1;
   if(!BrainValidAt(atr[n]) || !BrainValidAt(emaFast[n]) || !BrainValidAt(emaSlow[n]))
   {
      out.latestClosedH1 = rates[n].time;
      return;
   }

   const double a = atr[n];
   const double slopeFast = (emaFast[n] - emaFast[count - 3]) / a;
   const double slopeSlow = (emaSlow[n] - emaSlow[count - 3]) / a;
   const double displacement = BrainDisplacement(rates, atr, count, BRAIN_DISPLACEMENT_BARS);
   const double efficiency = BrainEfficiencySigned(rates, count, BRAIN_DISPLACEMENT_BARS);
   const double positioning = (rates[n].close > emaFast[n] ? 1.0 : -1.0) * 0.5
                            + (rates[n].close > emaSlow[n] ? 1.0 : -1.0) * 0.5;

   // fixed internal weights (small parameter surface)
   const double raw = 0.30 * BrainTanh(slopeFast)
                     + 0.25 * BrainTanh(slopeSlow)
                     + 0.15 * BrainClampSigned(positioning)
                     + 0.15 * BrainTanh(displacement)
                     + 0.15 * BrainClampSigned(efficiency);
   trace.fastSlopeAtr = slopeFast;
   trace.slowSlopeAtr = slopeSlow;
   trace.positioning = positioning;
   trace.signedDisplacement = displacement;
   trace.signedEfficiency = efficiency;
   trace.directionRawScore = raw;

    out.score = BrainClampSigned(raw);
   out.valid = true;
   out.latestClosedH1 = rates[n].time;
}

// ---------------------------------------------------------------------------
// Momentum
// ---------------------------------------------------------------------------

// Per-bar classification with state-specific persistence.
void MomentumClassify(const double strength, const double slope, const ENUM_MOMENTUM_STATE prevState,
                      int &persist, ENUM_MOMENTUM_STATE &state)
{
   const double st = BrainClampUnit(strength);
   const double sl = BrainClampSigned(slope);

   ENUM_MOMENTUM_STATE cand;
   if(st >= MOM_STRONG) cand = (sl >= MOM_SLOPE_UP) ? MOMENTUM_EXPANDING : MOMENTUM_STRONG;
   else if(st >= MOM_WEAK) cand = MOMENTUM_NORMAL;
   else cand = (sl <= MOM_SLOPE_DOWN) ? MOMENTUM_DECAYING : MOMENTUM_WEAK;

   const bool prevHigh = (prevState == MOMENTUM_EXPANDING || prevState == MOMENTUM_STRONG);
   const bool candHigh = (cand == MOMENTUM_EXPANDING || cand == MOMENTUM_STRONG);
   if(prevHigh && !candHigh)
   {
      if(persist + 1 < MOM_PERSISTENCE)
      {
         persist++;
         state = prevState;
         return;
      }
      persist = 0;
      state = cand;
      return;
   }
   if(prevHigh)
      persist = 0;
   state = cand;
}

// Momentum evidence from rates + ATR (+ ADX helper, supporting only).
void MomentumEngine(const MqlRates &rates[], const double &atr[], const double &adx[],
                     const int count, const bool adxValid, MomentumResult &out, Build05RawTrace &trace)
{
   H1BrainResult temp;
   ResetH1BrainInvalid(temp);
   out = temp.momentum;
   if(count < BRAIN_MOM_PROGRESSION_BARS + 1)
   {
      out.latestClosedH1 = (count > 0 ? rates[count - 1].time : 0);
      return;
   }

   const int n = count - 1;
   if(!BrainValidAt(atr[n]) || !MathIsValidNumber(rates[n].open) || !MathIsValidNumber(rates[n].close))
   {
      out.latestClosedH1 = rates[n].time;
      return;
   }

    const double range = rates[n].high - rates[n].low;
    const double a = atr[n];
    const double body = MathAbs(rates[n].close - rates[n].open);
    const double bodyAt = (a > 0.0) ? body / a : 0.0;
    const double bodyRange = (range > 0.0) ? body / range : 0.0;
    
    // Direction-agnostic close-location strength:
    // Bullish close near high -> (close - low) / range (large)
    // Bearish close near low -> (high - close) / range (large)
    double closeLocStrength = 0.5;
    if(range > 0.0)
    {
       if(rates[n].close >= rates[n].open)
          closeLocStrength = (rates[n].close - rates[n].low) / range;
       else
          closeLocStrength = (rates[n].high - rates[n].close) / range;
    }
    
    const double efficiencyMagnitude = BrainEfficiencyMagnitude(rates, count, BRAIN_MOM_PROGRESSION_BARS);

    // Signed progression for directionalAlignment diagnostic, magnitude for strength
    double signedProgression = 0.0;
    for(int i = count - BRAIN_MOM_PROGRESSION_BARS; i <= n; i++)
       signedProgression += (rates[i].close - rates[i].open) / MathMax(a, DBL_MIN);
    signedProgression /= (double)BRAIN_MOM_PROGRESSION_BARS;
    const double progressionStrength = MathAbs(BrainTanh(signedProgression));

    // Direction-agnostic momentum strength formula
     const double raw = 0.25 * BrainClampUnit(bodyAt)
                      + 0.25 * BrainClampUnit(bodyRange)
                      + 0.20 * BrainClampUnit(closeLocStrength)
                      + 0.15 * BrainClampUnit(progressionStrength)
                      + 0.15 * BrainClampUnit(efficiencyMagnitude);

     out.strengthScore = BrainClampUnit(raw);

     // directionalAlignment diagnostic: signed progression + signed efficiency
     const double efficiencySigned = BrainEfficiencySigned(rates, count, BRAIN_MOM_PROGRESSION_BARS);
     trace.bodyAtr = bodyAt;
     trace.bodyRange = bodyRange;
     trace.closeLocation = closeLocStrength;
     trace.signedProgression = signedProgression;
     trace.progressionStrength = progressionStrength;
     trace.efficiencyMagnitude = efficiencyMagnitude;
     trace.momentumSignedEfficiency = efficiencySigned;
     trace.momentumRawScore = raw;
     if(adxValid && count >= 2)
     {
        trace.adxCurrent = adx[n];
        trace.adxPrevious = adx[n - 1];
        trace.adxSlope = adx[n] - adx[n - 1];
     }
    out.directionalAlignment = BrainClampSigned(0.5 * BrainTanh(signedProgression) + 0.5 * efficiencySigned);
   out.valid = true;
   out.helperDegraded = !adxValid;
   out.latestClosedH1 = rates[n].time;

   // NOTE: strengthDelta and strengthSlope are computed by the caller across
   // consecutive closed-H1 updates (temporal), then fed back into
   // MomentumClassify via the `slope` argument. ADX level/slope are helper-only.
}

// ---------------------------------------------------------------------------
// Volatility Level
// ---------------------------------------------------------------------------

void VolatilityLevelClassify(const double ratio, const ENUM_VOLATILITY_LEVEL prevLevel,
                             const int dwell, ENUM_VOLATILITY_LEVEL &level, int &outDwell,
                             ENUM_VOLATILITY_LEVEL &challenger, int &challengerDwell)
{
   ENUM_VOLATILITY_LEVEL cand;
   if(ratio >= VOL_EXTREME_RATIO) cand = VOL_EXTREME;
   else if(ratio >= VOL_HIGH_RATIO) cand = VOL_HIGH;
   else if(ratio <= VOL_LOW_RATIO) cand = VOL_LOW;
   else cand = VOL_NORMAL;

   if(cand == prevLevel) { level = cand; outDwell = MathMin(dwell + 1, VOL_LEVEL_DWELL); challenger = cand; challengerDwell = 0; return; }

   const bool escalating = (prevLevel == VOL_NORMAL && (cand == VOL_HIGH || cand == VOL_EXTREME))
                         || (prevLevel == VOL_HIGH && cand == VOL_EXTREME);
   if(escalating)
   {
      if(cand == challenger)
      {
         challengerDwell++;
      }
      else
      {
         challenger = cand;
         challengerDwell = 1;
      }
      if(challengerDwell >= VOL_LEVEL_DWELL) { level = cand; outDwell = 0; challenger = cand; challengerDwell = 0; return; }
      level = prevLevel; outDwell = dwell; return;
   }

   challenger = cand;
   challengerDwell = 0;
   level = cand; outDwell = 0;
}

// Volatility level from ATR ratio = current ATR / baseline rolling mean.
void VolatilityEngine(const MqlRates &rates[], const double &atr[], const int count, const int baselineBars, VolatilityResult &out, Build05RawTrace &trace)
{
   H1BrainResult temp;
   ResetH1BrainInvalid(temp);
   out = temp.volatility;
   if(count < 1 || baselineBars <= 0)
   {
      return;
   }
   const int n = count - 1;
   if(!BrainValidAt(atr[n])) { return; }
   
   const int base = MathMin(baselineBars, count);
   double sum = 0.0;
   int validCount = 0;
   for(int i = count - base; i <= n; i++)
   {
      if(BrainValidAt(atr[i])) { sum += atr[i]; validCount++; }
   }
   if(validCount == 0) { return; }
   const double baseline = sum / (double)validCount;
   if(!(baseline > 0.0)) { return; }

   const double ratio = atr[n] / baseline;
   trace.atrCurrent = atr[n];
   trace.atrBaseline = baseline;
   trace.atrRatio = ratio;
   // levelScore: monotonic mapping of ratio into [0,1] for audit only
   out.levelScore = BrainClampUnit(ratio / VOL_EXTREME_RATIO);
   out.valid = true;
   out.latestClosedH1 = rates[n].time;
}

// ---------------------------------------------------------------------------
// Volatility Quality (non-ordinal) — challenger-dwell persistence
// ---------------------------------------------------------------------------

bool BrainVolQualityReady(const int count)
{
   return count >= 2 * BRAIN_DISPLACEMENT_BARS + 1;
}

// Evidence-max with challenger-dwell persistence and explicit primed state.
// Uses current-bar evidence for gap (not stale confidence).
void VolatilityQualitySelect(const double &evidence[],
                             const ENUM_VOLATILITY_QUALITY incState,
                             const bool primed,
                             const ENUM_VOLATILITY_QUALITY challenger,
                             const int challengerDwell,
                             ENUM_VOLATILITY_QUALITY &outState,
                             double &outConf,
                             bool &outPrimed,
                             ENUM_VOLATILITY_QUALITY &outChallenger,
                             int &outChallengerDwell)
{
   int best = 0;
   for(int i = 1; i < 5; i++)
      if(evidence[i] > evidence[best]) best = i;
   const ENUM_VOLATILITY_QUALITY bestState = (ENUM_VOLATILITY_QUALITY)best;

   // Not yet primed → pure evidence-max, commit immediately
   if(!primed)
   {
      outState = bestState;
      outConf = evidence[best];
      outPrimed = true;
      outChallenger = bestState;
      outChallengerDwell = 0;
      return;
   }

   // best == incumbent
   if(bestState == incState)
   {
      outState = bestState;
      outConf = evidence[best];
      outPrimed = true;
      outChallenger = bestState;
      outChallengerDwell = 0;
      return;
   }

   // best != incumbent — gap uses CURRENT BAR evidence for both states
   const double currentIncEvidence = evidence[(int)incState];
   const double currentBestEvidence = evidence[best];
   const double gap = currentBestEvidence - currentIncEvidence;
   if(gap < VOLQ_GAP)
   {
      // Insufficient advantage — retain incumbent
      outState = incState;
      outConf = currentIncEvidence;
      outPrimed = true;
      outChallenger = incState;
      outChallengerDwell = 0;
      return;
   }

   // Sufficient gap — challenger dwell logic
   int newDwell;
   if(bestState == challenger)
      newDwell = challengerDwell + 1;
   else
      newDwell = 1;

   if(newDwell >= VOLQ_DWELL)
   {
      // Commit challenger
      outState = bestState;
      outConf = currentBestEvidence;
      outPrimed = true;
      outChallenger = bestState;
      outChallengerDwell = 0;
      return;
   }

   // Hold incumbent, challenger pending
   outState = incState;
   outConf = currentIncEvidence;
   outPrimed = true;
   outChallenger = (ENUM_VOLATILITY_QUALITY)best;
   outChallengerDwell = newDwell;
}

// Volatility quality from efficiency + wick noise + compression/expansion evidence.
void VolatilityQualityEngine(const MqlRates &rates[], const double &atr[], const int count,
                              VolatilityResult &out, Build05RawTrace &trace)
{
   if(!BrainVolQualityReady(count))
   {
      out.quality = VOLQ_HEALTHY;
      out.qualityConfidence = 0.0;
      out.compressionScore = 0.0;
      out.expansionScore = 0.0;
      out.chaosScore = 0.0;
      out.shockScore = 0.0;
      out.healthyScore = 0.0;
      return;
   }
   const int n = count - 1;
   const double range = rates[n].high - rates[n].low;
   if(!(range > 0.0) || !BrainValidAt(atr[n]))
   {
      out.quality = VOLQ_HEALTHY; out.qualityConfidence = 0.0;
      return;
   }

   const double efficiency = BrainEfficiencyMagnitude(rates, count, BRAIN_DISPLACEMENT_BARS);
   const double wick = range > 0.0 ? (range - MathAbs(rates[n].close - rates[n].open)) / range : 0.0;

    // --- Compression evidence: mean(atrDecline, rangeShrink, bodyShrink) ---
    // Uses W-bar windows (BRAIN_DISPLACEMENT_BARS = 20) for all components.
    const int half = BRAIN_DISPLACEMENT_BARS;
    double recentAtrSum = 0.0, priorAtrSum = 0.0;
    double recentRangeSum = 0.0, priorRangeSum = 0.0;
    double recentBodySum = 0.0, priorBodySum = 0.0;
    int recentN = 0, priorN = 0;

    for(int i = count - half; i <= n; i++)
    {
       if(!BrainValidAt(atr[i])) continue;
       recentAtrSum += atr[i];
       recentRangeSum += (rates[i].high - rates[i].low);
       recentBodySum += MathAbs(rates[i].close - rates[i].open);
       recentN++;
    }
    for(int i = count - half * 2; i < count - half; i++)
    {
       if(i < 0 || !BrainValidAt(atr[i])) continue;
       priorAtrSum += atr[i];
       priorRangeSum += (rates[i].high - rates[i].low);
       priorBodySum += MathAbs(rates[i].close - rates[i].open);
       priorN++;
    }

   const double recentAtrAvg = recentN > 0 ? recentAtrSum / recentN : 0.0;
   const double priorAtrAvg  = priorN > 0 ? priorAtrSum / priorN : 0.0;
   const double recentRangeAvg = recentN > 0 ? recentRangeSum / recentN : 0.0;
   const double priorRangeAvg  = priorN > 0 ? priorRangeSum / priorN : 0.0;
   const double recentBodyAvg = recentN > 0 ? recentBodySum / recentN : 0.0;
   const double priorBodyAvg  = priorN > 0 ? priorBodySum / priorN : 0.0;

   const double atrDecline = (priorAtrAvg > 0.0) ? BrainClampUnit((priorAtrAvg - recentAtrAvg) / priorAtrAvg) : 0.0;
   const double rangeShrink = BrainShrinkEvidence(recentRangeAvg, priorRangeAvg);
   const double bodyShrink  = BrainShrinkEvidence(recentBodyAvg, priorBodyAvg);
   const double compressionScore = BrainClampUnit(BrainMean3(atrDecline, rangeShrink, bodyShrink));

   // --- Expansion evidence: mean(atrRise, rangeExpand, bodyExpand, effRise, dispRise) ---
   const double atrRise = (priorAtrAvg > 0.0) ? BrainClampUnit((recentAtrAvg - priorAtrAvg) / priorAtrAvg) : 0.0;
   const double rangeExpand = BrainExpandEvidence(recentRangeAvg, priorRangeAvg);
   const double bodyExpand  = BrainExpandEvidence(recentBodyAvg, priorBodyAvg);

   // --- Efficiency magnitude (recent vs prior) ---
   double effRecent = 0.0, effPrior = 0.0;
   if(count >= BRAIN_DISPLACEMENT_BARS + 1)
   {
      // Recent window efficiency: |netMove| / totalPath
      const double netRecent = rates[n].close - rates[n - BRAIN_DISPLACEMENT_BARS].close;
      double pathRecent = 0.0;
      for(int i = count - BRAIN_DISPLACEMENT_BARS; i <= n; i++)
         pathRecent += MathAbs(rates[i].close - rates[i - 1].close);
      effRecent = pathRecent > 0.0 ? MathAbs(netRecent) / pathRecent : 0.0;

       // Prior window efficiency
       const int pEnd = count - BRAIN_DISPLACEMENT_BARS - 1;
       if(pEnd >= BRAIN_DISPLACEMENT_BARS)
       {
          const double netPrior = rates[pEnd].close - rates[pEnd - BRAIN_DISPLACEMENT_BARS].close;
          double pathPrior = 0.0;
          for(int i = pEnd - BRAIN_DISPLACEMENT_BARS + 1; i <= pEnd; i++)
             pathPrior += MathAbs(rates[i].close - rates[i - 1].close);
          effPrior = pathPrior > 0.0 ? MathAbs(netPrior) / pathPrior : 0.0;
       }
   }
   const double effRise = BrainExpandEvidence(effRecent, effPrior);

    // --- Displacement magnitude (recent vs prior): |netMove| / endpoint ATR ---
    double dispRecent = 0.0, dispPrior = 0.0;
    if(count >= BRAIN_DISPLACEMENT_BARS + 1)
    {
       // Recent displacement: |close[n] - close[n-W]| / ATR[n]
       const double netR = rates[n].close - rates[n - BRAIN_DISPLACEMENT_BARS].close;
       dispRecent = BrainValidAt(atr[n]) ? MathAbs(netR) / atr[n] : 0.0;

       // Prior displacement: |close[n-W] - close[n-2W]| / ATR[n-W]
       const int pEnd = count - BRAIN_DISPLACEMENT_BARS - 1;
       if(pEnd >= BRAIN_DISPLACEMENT_BARS)
       {
          const double netP = rates[pEnd].close - rates[pEnd - BRAIN_DISPLACEMENT_BARS].close;
          dispPrior = BrainValidAt(atr[pEnd]) ? MathAbs(netP) / atr[pEnd] : 0.0;
       }
    }
   const double dispRise = BrainExpandEvidence(dispRecent, dispPrior);

   const double expansionScore = BrainClampUnit(BrainMean5(atrRise, rangeExpand, bodyExpand,
                                                            effRise, dispRise));

   // --- Per-category evidence scores ---
   double evidence[5];
   evidence[0] = BrainClampUnit(efficiency);                                   // HEALTHY
   evidence[1] = compressionScore;                                             // COMPRESSED
   evidence[2] = expansionScore;                                               // EXPANDING
   evidence[3] = BrainClampUnit(wick) * (1.0 - efficiency);                   // CHAOTIC
   evidence[4] = BrainClampUnit(atrRise) * BrainClampUnit(MathAbs(atrRise));   // SHOCK

   out.compressionScore = evidence[1];
   out.expansionScore = evidence[2];
   out.chaosScore = evidence[3];
   out.shockScore = evidence[4];
   out.healthyScore = evidence[0];
   trace.recentAtr = recentAtrAvg;
   trace.priorAtr = priorAtrAvg;
   trace.atrDecline = atrDecline;
   trace.atrRise = atrRise;
   trace.recentRange = recentRangeAvg;
   trace.priorRange = priorRangeAvg;
   trace.rangeShrink = rangeShrink;
   trace.rangeExpand = rangeExpand;
   trace.recentBody = recentBodyAvg;
   trace.priorBody = priorBodyAvg;
   trace.bodyShrink = bodyShrink;
   trace.bodyExpand = bodyExpand;
   trace.recentEfficiency = effRecent;
   trace.priorEfficiency = effPrior;
   trace.efficiencyRise = effRise;
   trace.recentDisplacement = dispRecent;
   trace.priorDisplacement = dispPrior;
   trace.displacementRise = dispRise;
   trace.wickNoise = wick;
   trace.healthyScore = evidence[0];
   trace.compressionScore = evidence[1];
   trace.expansionScore = evidence[2];
   trace.chaosScore = evidence[3];
   trace.shockScore = evidence[4];

   int best = 0;
   for(int i = 1; i < 5; i++) if(evidence[i] > evidence[best]) best = i;
   out.quality = (ENUM_VOLATILITY_QUALITY)best;
   out.qualityConfidence = evidence[best];
}

#endif
