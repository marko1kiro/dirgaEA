#ifndef ADAPTIVE_SURVIVAL_EA_MARKET_BRAIN_MQH
#define ADAPTIVE_SURVIVAL_EA_MARKET_BRAIN_MQH

#include "Types.mqh"

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
// `prevState` and `dwell` are caller-tracked across closed-H1 updates.
void DirectionClassify(const double score, const ENUM_DIRECTION_STATE prevState, const int dwell,
                       ENUM_DIRECTION_STATE &state, int &outDwell)
{
   const double s = BrainClampSigned(score);
   ENUM_DIRECTION_STATE cand;
   if(s >= DIR_STRONG_COMMIT) cand = DIRECTION_STRONG_BULL;
   else if(s >= DIR_COMMIT)   cand = DIRECTION_BULL;
   else if(s <= -DIR_STRONG_COMMIT) cand = DIRECTION_STRONG_BEAR;
   else if(s <= -DIR_COMMIT)  cand = DIRECTION_BEAR;
   else                       cand = DIRECTION_NEUTRAL;

   if(cand == DIRECTION_NEUTRAL) { state = cand; outDwell = 0; return; }
   if(prevState == DIRECTION_NEUTRAL) { state = cand; outDwell = 0; return; }
   if(cand == prevState) { state = cand; outDwell = MathMin(dwell + 1, DIR_DWELL); return; }

   // magnitude helper (signed): +1 bull/+2 strong bull, -1 bear/-2 strong bear
   const int candMag = (cand == DIRECTION_STRONG_BULL) ? 2 :
                       (cand == DIRECTION_BULL) ? 1 :
                       (cand == DIRECTION_BEAR) ? -1 : -2;
   const int prevMag = (prevState == DIRECTION_STRONG_BULL) ? 2 :
                       (prevState == DIRECTION_BULL) ? 1 :
                       (prevState == DIRECTION_BEAR) ? -1 : -2;

   // stronger magnitude (same sign, larger |mag|) requires dwell before commit
   if(candMag * prevMag > 0 && MathAbs(candMag) > MathAbs(prevMag))
   {
      if(dwell + 1 >= DIR_DWELL) { state = cand; outDwell = 0; return; }
      state = prevState; outDwell = dwell + 1; return;
   }
   // weaker: immediate step
   state = cand; outDwell = 0;
}

// Direction evidence from native EMA fast/slow buffers (chronological) + ATR.
void DirectionEngine(const MqlRates &rates[], const double &emaFast[], const double &emaSlow[],
                     const double &atr[], const int count, DirectionResult &out)
{
   ZeroMemory(out);
   out.state = DIRECTION_NEUTRAL;
   out.valid = false;
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

   out.score = BrainClampSigned(raw);
   out.valid = true;
   out.latestClosedH1 = rates[n].time;
}

// ---------------------------------------------------------------------------
// Momentum
// ---------------------------------------------------------------------------

// Per-bar classification with state-specific persistence.
void MomentumClassify(const double strength, const double slope, const ENUM_MOMENTUM_STATE prevState,
                      const int persist, ENUM_MOMENTUM_STATE &state)
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
      state = (persist + 1 < MOM_PERSISTENCE) ? prevState : cand;
      return;
   }
   state = cand;
}

// Momentum evidence from rates + ATR (+ ADX helper, supporting only).
void MomentumEngine(const MqlRates &rates[], const double &atr[], const double &adx[],
                    const int count, const bool adxValid, MomentumResult &out)
{
   ZeroMemory(out);
   out.state = MOMENTUM_NORMAL;
   out.valid = false;
   out.helperDegraded = false;
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
                             const int dwell, ENUM_VOLATILITY_LEVEL &level, int &outDwell)
{
   ENUM_VOLATILITY_LEVEL cand;
   if(ratio >= VOL_EXTREME_RATIO) cand = VOL_EXTREME;
   else if(ratio >= VOL_HIGH_RATIO) cand = VOL_HIGH;
   else if(ratio <= VOL_LOW_RATIO) cand = VOL_LOW;
   else cand = VOL_NORMAL;

   if(cand == prevLevel) { level = cand; outDwell = MathMin(dwell + 1, VOL_LEVEL_DWELL); return; }

   // escalate further from NORMAL toward an extreme requires dwell
   const bool escalating = (prevLevel == VOL_NORMAL && (cand == VOL_HIGH || cand == VOL_EXTREME))
                         || (prevLevel == VOL_HIGH && cand == VOL_EXTREME);
   if(escalating)
   {
      if(dwell + 1 >= VOL_LEVEL_DWELL) { level = cand; outDwell = 0; return; }
      level = prevLevel; outDwell = dwell + 1; return;
   }
   // step down immediate
   level = cand; outDwell = 0;
}

// Volatility level from ATR ratio = current ATR / baseline rolling mean.
void VolatilityEngine(const MqlRates &rates[], const double &atr[], const int count, const int baselineBars, VolatilityResult &out)
{
   // fills level/levelScore/valid/latestClosedH1; quality filled separately
   ZeroMemory(out);
   out.level = VOL_NORMAL;
   out.valid = false;
   if(count < 1 || baselineBars <= 0)
   {
      out.latestClosedH1 = 0;
      return;
   }
   const int n = count - 1;
   if(!BrainValidAt(atr[n])) { out.latestClosedH1 = 0; return; }

   const int base = MathMin(baselineBars, count);
   double sum = 0.0;
   int validCount = 0;
   for(int i = count - base; i <= n; i++)
   {
      if(BrainValidAt(atr[i])) { sum += atr[i]; validCount++; }
   }
   if(validCount == 0) { out.latestClosedH1 = 0; return; }
   const double baseline = sum / (double)validCount;
   if(!(baseline > 0.0)) { out.latestClosedH1 = 0; return; }

   const double ratio = atr[n] / baseline;
   // levelScore: monotonic mapping of ratio into [0,1] for audit only
   out.levelScore = BrainClampUnit(ratio / VOL_EXTREME_RATIO);
   out.valid = true;
   out.latestClosedH1 = rates[n].time;
}

// ---------------------------------------------------------------------------
// Volatility Quality (non-ordinal)
// ---------------------------------------------------------------------------

// Evidence-max over five candidates; candidate-confidence persistence handled
// by caller via incumbent (state, confidence, dwell). Returns selected state.
void VolatilityQualitySelect(const double &evidence[], const ENUM_VOLATILITY_QUALITY incumbent,
                             const double incumbentConf, const int incumbentDwell,
                             ENUM_VOLATILITY_QUALITY &quality)
{
   // evidence order: HEALTHY, COMPRESSED, EXPANDING, CHAOTIC, SHOCK
   int best = 0;
   for(int i = 1; i < 5; i++)
      if(evidence[i] > evidence[best]) best = i;
   const ENUM_VOLATILITY_QUALITY bestState = (ENUM_VOLATILITY_QUALITY)best;

   if(incumbentConf <= 0.0 && incumbentDwell == 0) { quality = bestState; return; }

   if(bestState != incumbent)
   {
      if(evidence[best] - incumbentConf < VOLQ_GAP) { quality = incumbent; return; }
      if(incumbentDwell + 1 < VOLQ_DWELL) { quality = incumbent; return; }
   }
   quality = bestState;
}

// Volatility quality from efficiency + wick noise + compression/expansion.
void VolatilityQualityEngine(const MqlRates &rates[], const double &atr[], const int count,
                             VolatilityResult &out)
{
   if(count < 3) { out.quality = VOLQ_HEALTHY; out.qualityConfidence = 0.0; return; }
   const int n = count - 1;
   const double range = rates[n].high - rates[n].low;
   if(!(range > 0.0) || !BrainValidAt(atr[n]))
   {
      out.quality = VOLQ_HEALTHY; out.qualityConfidence = 0.0;
      return;
   }

   const double efficiency = BrainEfficiencyMagnitude(rates, count, BRAIN_DISPLACEMENT_BARS);
   const double wick = range > 0.0 ? (range - MathAbs(rates[n].close - rates[n].open)) / range : 0.0;

   // compression/expansion: ATR short trend vs longer lookback
   double recentSum = 0.0, priorSum = 0.0;
   int recentN = 0, priorN = 0;
   const int half = 5;
   for(int i = count - half; i <= n; i++) { if(BrainValidAt(atr[i])) { recentSum += atr[i]; recentN++; } }
   for(int i = count - half * 2; i < count - half; i++) { if(i >= 0 && BrainValidAt(atr[i])) { priorSum += atr[i]; priorN++; } }
   const double recentAvg = recentN > 0 ? recentSum / recentN : 0.0;
   const double priorAvg = priorN > 0 ? priorSum / priorN : 0.0;
   const double atrTrend = (priorAvg > 0.0) ? (recentAvg - priorAvg) / priorAvg : 0.0;

   // per-category evidence scores (all [0,1])
   double evidence[5];
   evidence[0] = BrainClampUnit(efficiency);                                   // HEALTHY
   evidence[1] = BrainClampUnit(-atrTrend);                                     // COMPRESSED (ATR falling)
   evidence[2] = BrainClampUnit(atrTrend);                                      // EXPANDING (ATR rising)
   evidence[3] = BrainClampUnit(wick) * (1.0 - efficiency);                     // CHAOTIC (wicky + noisy)
   evidence[4] = BrainClampUnit(atrTrend) * BrainClampUnit(MathAbs(atrTrend));  // SHOCK (abrupt expansion)

   out.compressionScore = evidence[1];
   out.expansionScore = evidence[2];
   out.chaosScore = evidence[3];
   out.shockScore = evidence[4];
   out.healthyScore = evidence[0];

   int best = 0;
   for(int i = 1; i < 5; i++) if(evidence[i] > evidence[best]) best = i;
   out.quality = (ENUM_VOLATILITY_QUALITY)best;
   out.qualityConfidence = evidence[best];
}

#endif
