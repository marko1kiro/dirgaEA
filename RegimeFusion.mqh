#ifndef ADAPTIVE_SURVIVAL_EA_REGIME_FUSION_MQH
#define ADAPTIVE_SURVIVAL_EA_REGIME_FUSION_MQH

#include "Types.mqh"

// ---------------------------------------------------------------------------
// BUILD 06 — H1 Regime Fusion (classification-only)
//
// Pure functions over the FINAL B04 (SwingStructureResult) + B05 (H1BrainResult)
// outputs. No raw evidence, no trade side effects. This is a 1:1 translation of
// the locked Python reference harness (tests/build06/reference_fusion.py).
//
// Momentum is direction-agnostic: momentumDirectionalAlignment is NEVER read by
// scoring/quality/mass. Bull/bear side comes only from Structure + Direction.
// ---------------------------------------------------------------------------

// Fixed v1 weights (section 16, NOT exposed inputs)
#define REGIME_W_TREND_S 0.35
#define REGIME_W_TREND_D 0.30
#define REGIME_W_TREND_M 0.15
#define REGIME_W_TREND_V 0.10
#define REGIME_W_TREND_Q 0.10

#define REGIME_W_RANGE_S 0.40
#define REGIME_W_RANGE_D 0.25
#define REGIME_W_RANGE_M 0.15
#define REGIME_W_RANGE_V 0.10
#define REGIME_W_RANGE_Q 0.10

#define REGIME_W_BREAK_S 0.30
#define REGIME_W_BREAK_Q 0.25
#define REGIME_W_BREAK_M 0.20
#define REGIME_W_BREAK_D 0.15
#define REGIME_W_BREAK_V 0.10

// Fixed v1 constants (section 16, NOT exposed inputs)
#define REGIME_DIR_COMMIT 0.45
#define REGIME_BALANCED_SPAN 0.20
#define REGIME_CONFIDENCE_SPAN 0.20

double RegimeClamp01(const double v) { return MathMax(0.0, MathMin(1.0, v)); }

// ---------------------------------------------------------------------------
// Domain contribution mappings (sections 4.3 - 4.6)
// ---------------------------------------------------------------------------

double RegimeSBullishTrend(const ENUM_STRUCTURE_STATE s)
{
   switch(s)
   {
      case STRUCTURE_BULLISH_STRONG: return 1.0;
      case STRUCTURE_BULLISH_WEAK:   return 0.6;
      case STRUCTURE_MIXED:          return 0.25;
      default:                       return 0.0;
   }
}

double RegimeSBearishTrend(const ENUM_STRUCTURE_STATE s)
{
   switch(s)
   {
      case STRUCTURE_BEARISH_STRONG: return 1.0;
      case STRUCTURE_BEARISH_WEAK:   return 0.6;
      case STRUCTURE_MIXED:          return 0.25;
      default:                       return 0.0;
   }
}

double RegimeSRange(const ENUM_STRUCTURE_STATE s)
{
   switch(s)
   {
      case STRUCTURE_RANGE: return 1.0;
      case STRUCTURE_MIXED: return 0.5;
      default:              return 0.0;
   }
}

double RegimeDBullish(const double score)  { return RegimeClamp01(score); }
double RegimeDBearish(const double score)  { return RegimeClamp01(-score); }
double RegimeDNeutral(const double score)  { return RegimeClamp01(1.0 - MathAbs(score)); }

double RegimeMSupportive(const ENUM_MOMENTUM_STATE m)
{
   switch(m)
   {
      case MOMENTUM_EXPANDING: return 1.0;
      case MOMENTUM_STRONG:    return 1.0;
      case MOMENTUM_NORMAL:    return 0.6;
      case MOMENTUM_WEAK:      return 0.3;
      case MOMENTUM_DECAYING:  return 0.0;
      default:                 return 0.0;
   }
}

double RegimeMNonExpansion(const ENUM_MOMENTUM_STATE m)
{
   switch(m)
   {
      case MOMENTUM_NORMAL:    return 1.0;
      case MOMENTUM_WEAK:      return 0.8;
      case MOMENTUM_DECAYING:  return 0.5;
      case MOMENTUM_STRONG:    return 0.3;
      case MOMENTUM_EXPANDING: return 0.1;
      default:                 return 0.0;
   }
}

double RegimeMExpanding(const ENUM_MOMENTUM_STATE m)
{
   switch(m)
   {
      case MOMENTUM_EXPANDING: return 1.0;
      case MOMENTUM_STRONG:    return 0.7;
      case MOMENTUM_NORMAL:    return 0.3;
      case MOMENTUM_WEAK:      return 0.1;
      case MOMENTUM_DECAYING:  return 0.0;
      default:                 return 0.0;
   }
}

double RegimeVTrendSuitable(const ENUM_VOLATILITY_LEVEL v)
{
   switch(v)
   {
      case VOL_NORMAL:  return 1.0;
      case VOL_HIGH:    return 1.0;
      case VOL_LOW:     return 0.5;
      case VOL_EXTREME: return 0.3;
      default:          return 0.0;
   }
}

double RegimeVRangeSuitable(const ENUM_VOLATILITY_LEVEL v)
{
   switch(v)
   {
      case VOL_LOW:     return 1.0;
      case VOL_NORMAL:  return 0.7;
      case VOL_HIGH:    return 0.4;
      case VOL_EXTREME: return 0.1;
      default:          return 0.0;
   }
}

double RegimeQClean(const ENUM_VOLATILITY_QUALITY q)
{
   switch(q)
   {
      case VOLQ_HEALTHY:    return 1.0;
      case VOLQ_EXPANDING:  return 0.7;
      case VOLQ_COMPRESSED: return 0.4;
      case VOLQ_SHOCK:      return 0.2;
      case VOLQ_CHAOTIC:    return 0.15;
      default:              return 0.0;
   }
}

double RegimeQTwoSided(const ENUM_VOLATILITY_QUALITY q)
{
   switch(q)
   {
      case VOLQ_COMPRESSED: return 1.0;
      case VOLQ_HEALTHY:    return 0.7;
      case VOLQ_EXPANDING:  return 0.3;
      case VOLQ_CHAOTIC:    return 0.0;
      case VOLQ_SHOCK:      return 0.0;
      default:              return 0.0;
   }
}

double RegimeQBreakoutClean(const ENUM_VOLATILITY_QUALITY q)
{
   switch(q)
   {
      case VOLQ_HEALTHY:    return 1.0;
      case VOLQ_EXPANDING:  return 1.0;
      case VOLQ_COMPRESSED: return 0.60;
      case VOLQ_CHAOTIC:    return 0.10;
      case VOLQ_SHOCK:      return 0.10;
      default:              return 0.0;
   }
}

double RegimeQGeneral(const ENUM_VOLATILITY_QUALITY q)
{
   switch(q)
   {
      case VOLQ_HEALTHY:    return 1.0;
      case VOLQ_EXPANDING:  return 0.80;
      case VOLQ_COMPRESSED: return 0.70;
      case VOLQ_CHAOTIC:    return 0.10;
      case VOLQ_SHOCK:      return 0.00;
      default:              return 0.0;
   }
}

double RegimeVGeneral(const ENUM_VOLATILITY_LEVEL v)
{
   switch(v)
   {
      case VOL_NORMAL:  return 1.0;
      case VOL_LOW:     return 0.70;
      case VOL_HIGH:    return 0.70;
      case VOL_EXTREME: return 0.20;
      default:          return 0.0;
   }
}

// ---------------------------------------------------------------------------
// Break recency for BREAKOUT structure contribution (section 4.6)
//
// ponytail: "fresh" vs "older within window" boundary is not numerically fixed in
// the locked spec (it says "fresh -> 1.0; older within window -> 0.4"). We define
// fresh = break on the latest completed H1 bar (age 0), older-within-window =
// 1..lookback bars (age in completed H1 bars). Upgrade path: if a more precise
// age split is required, expose it as an input and re-validate scenarios F/G.
// ---------------------------------------------------------------------------
double RegimeBreakRecency(const SwingStructureResult &s, const bool bullish,
                          const datetime latest, const int lookback)
{
   if(s.breakCount <= 0 || lookback <= 0) return 0.0;
   const double barSeconds = (double)PeriodSeconds(PERIOD_H1);
   if(!(barSeconds > 0.0)) return 0.0;

   datetime newest = 0;
   for(int i = 0; i < s.breakCount; i++)
   {
      const StructureBreak b = s.breaks[i];
      if(b.bullish != bullish) continue;
      if(b.time > latest) continue;
      if(b.time > newest) newest = b.time;
   }
   if(newest == 0) return 0.0;

   const int ageBars = (int)MathFloor((double)(latest - newest) / barSeconds);
   if(ageBars <= 0) return 1.0;              // fresh (latest completed bar)
   if(ageBars <= lookback) return 0.4;       // older within window
   return 0.0;
}

// ---------------------------------------------------------------------------
// Candidate scores (sections 4.3 - 4.6)
// ---------------------------------------------------------------------------

struct RegimeCandidateScores
{
   double trendBull;
   double trendBear;
   double range;
   double breakoutBull;
   double breakoutBear;
};

void RegimeComputeScores(const SwingStructureResult &structure,
                         const H1BrainResult &brain,
                         const double compressionContext,
                         RegimeCandidateScores &out)
{
   const double dBull = RegimeDBullish(brain.direction.score);
   const double dBear = RegimeDBearish(brain.direction.score);
   const double dNeutral = RegimeDNeutral(brain.direction.score);

   const double sBull = RegimeSBullishTrend(structure.state);
   const double sBear = RegimeSBearishTrend(structure.state);
   const double sRange = RegimeSRange(structure.state);

   const double mSupportive = RegimeMSupportive(brain.momentum.state);
   const double mNonExp = RegimeMNonExpansion(brain.momentum.state);
   const double mExpanding = RegimeMExpanding(brain.momentum.state);

   const double vTrend = RegimeVTrendSuitable(brain.volatility.level);
   const double vRange = RegimeVRangeSuitable(brain.volatility.level);

   const double qClean = RegimeQClean(brain.volatility.quality);
   const double qTwoSided = RegimeQTwoSided(brain.volatility.quality);

   const double breakBull = RegimeBreakRecency(structure, true, structure.latestTime, 4);
   const double breakBear = RegimeBreakRecency(structure, false, structure.latestTime, 4);
   const double expansionEvidence = RegimeClamp01(brain.volatility.expansionScore);

   out.trendBull = REGIME_W_TREND_S * sBull + REGIME_W_TREND_D * dBull
                 + REGIME_W_TREND_M * mSupportive + REGIME_W_TREND_V * vTrend
                 + REGIME_W_TREND_Q * qClean;

   out.trendBear = REGIME_W_TREND_S * sBear + REGIME_W_TREND_D * dBear
                 + REGIME_W_TREND_M * mSupportive + REGIME_W_TREND_V * vTrend
                 + REGIME_W_TREND_Q * qClean;

   out.range = REGIME_W_RANGE_S * sRange + REGIME_W_RANGE_D * dNeutral
             + REGIME_W_RANGE_M * mNonExp + REGIME_W_RANGE_V * vRange
             + REGIME_W_RANGE_Q * qTwoSided;

   out.breakoutBull = REGIME_W_BREAK_S * breakBull + REGIME_W_BREAK_Q * compressionContext
                    + REGIME_W_BREAK_M * mExpanding + REGIME_W_BREAK_D * dBull
                    + REGIME_W_BREAK_V * expansionEvidence;

   out.breakoutBear = REGIME_W_BREAK_S * breakBear + REGIME_W_BREAK_Q * compressionContext
                    + REGIME_W_BREAK_M * mExpanding + REGIME_W_BREAK_D * dBear
                    + REGIME_W_BREAK_V * expansionEvidence;
}

// ---------------------------------------------------------------------------
// UNCERTAIN mass (section 4.7) — HARD vs SOFT split
// ---------------------------------------------------------------------------

double RegimeStructuralConflict(const ENUM_STRUCTURE_STATE s, const double dscore)
{
   const bool bullStruct = (s == STRUCTURE_BULLISH_STRONG || s == STRUCTURE_BULLISH_WEAK);
   const bool bearStruct = (s == STRUCTURE_BEARISH_STRONG || s == STRUCTURE_BEARISH_WEAK);
   const bool bullDir = dscore > +REGIME_DIR_COMMIT;
   const bool bearDir = dscore < -REGIME_DIR_COMMIT;
   return ((bullStruct && bearDir) || (bearStruct && bullDir)) ? 1.0 : 0.0;
}

double RegimeChaosMass(const ENUM_VOLATILITY_QUALITY q, const double dscore)
{
   const bool committed = MathAbs(dscore) >= REGIME_DIR_COMMIT;
   if(q == VOLQ_CHAOTIC && !committed) return 1.00;
   if(q == VOLQ_CHAOTIC && committed)  return 0.45;
   if(q == VOLQ_SHOCK)                 return 0.50;
   return 0.00;
}

// top1/top2 over the five real candidates (fixed order: TB, TBe, R, BB, BBe)
void RegimeTopTwo(const RegimeCandidateScores &s, double &top1, double &top2)
{
   const double c[5] = { s.trendBull, s.trendBear, s.range, s.breakoutBull, s.breakoutBear };
   int bestIdx = 0;
   for(int i = 1; i < 5; i++) if(c[i] > c[bestIdx]) bestIdx = i;
   top1 = c[bestIdx];
   double second = -1.0;
   for(int i = 0; i < 5; i++)
   {
      if(i == bestIdx) continue;
      if(c[i] > second) second = c[i];
   }
   if(second < 0.0) second = top1;
   top2 = second;
}

double RegimeBalancedEvidence(const RegimeCandidateScores &s)
{
   double top1, top2;
   RegimeTopTwo(s, top1, top2);
   const double margin = top1 - top2;
   return RegimeClamp01(1.0 - margin / REGIME_BALANCED_SPAN);
}

double RegimeWeakWinnerMass(const RegimeCandidateScores &s, const double threshold)
{
   double top1, top2;
   RegimeTopTwo(s, top1, top2);
   if(!(threshold > 0.0)) return 0.0;
   return RegimeClamp01(1.0 - top1 / threshold);
}

double RegimeDegradationMass(const double evidenceCompleteness)
{
   return RegimeClamp01(1.0 - evidenceCompleteness);
}

double RegimeComputeUncertainMass(const SwingStructureResult &structure,
                                  const H1BrainResult &brain,
                                  const RegimeCandidateScores &scores,
                                  const double evidenceCompleteness,
                                  const double weakWinnerThreshold)
{
   const double structuralConflict = RegimeStructuralConflict(structure.state, brain.direction.score);
   const double chaos = RegimeChaosMass(brain.volatility.quality, brain.direction.score);
   const double balanced = RegimeBalancedEvidence(scores);
   const double weakWinner = RegimeWeakWinnerMass(scores, weakWinnerThreshold);
   const double degradation = RegimeDegradationMass(evidenceCompleteness);

   double m = structuralConflict;
   if(chaos > m) m = chaos;
   if(balanced > m) m = balanced;
   if(weakWinner > m) m = weakWinner;
   if(degradation > m) m = degradation;
   return RegimeClamp01(m);
}

bool RegimeHardUncertainVeto(const SwingStructureResult &structure, const H1BrainResult &brain)
{
   if(RegimeStructuralConflict(structure.state, brain.direction.score) >= 1.0) return true;
   if(brain.volatility.quality == VOLQ_CHAOTIC && MathAbs(brain.direction.score) < REGIME_DIR_COMMIT) return true;
   return false;
}

// ---------------------------------------------------------------------------
// Confidence (section 6.1) — final reported regime vs best alternative
// ---------------------------------------------------------------------------

double RegimeScoreOf(const ENUM_REGIME_STATE regime, const RegimeCandidateScores &s)
{
   switch(regime)
   {
      case REGIME_TREND_BULL:   return s.trendBull;
      case REGIME_TREND_BEAR:   return s.trendBear;
      case REGIME_RANGE:        return s.range;
      case REGIME_BREAKOUT_BULL:return s.breakoutBull;
      case REGIME_BREAKOUT_BEAR:return s.breakoutBear;
      default:                  return 0.0;
   }
}

double RegimeBestAlternative(const ENUM_REGIME_STATE regime, const RegimeCandidateScores &s)
{
   double best = -1.0;
   const ENUM_REGIME_STATE all[5] = { REGIME_TREND_BULL, REGIME_TREND_BEAR, REGIME_RANGE,
                                      REGIME_BREAKOUT_BULL, REGIME_BREAKOUT_BEAR };
   for(int i = 0; i < 5; i++)
   {
      if(all[i] == regime) continue;
      const double v = RegimeScoreOf(all[i], s);
      if(v > best) best = v;
   }
   return (best < 0.0) ? RegimeScoreOf(regime, s) : best;
}

double RegimeConfidence(const ENUM_REGIME_STATE regime, const RegimeCandidateScores &s,
                        const double scoreUncertain, const double evidenceCompleteness)
{
   if(regime == REGIME_UNCERTAIN) return RegimeClamp01(scoreUncertain);
   const double scoreR = RegimeClamp01(RegimeScoreOf(regime, s));
   const double bestAlt = RegimeBestAlternative(regime, s);
   const double margin = scoreR - bestAlt;
   const double marginFactor = RegimeClamp01(margin / REGIME_CONFIDENCE_SPAN);
   return RegimeClamp01(scoreR * (0.70 + 0.30 * marginFactor) * evidenceCompleteness);
}

// ---------------------------------------------------------------------------
// RegimeQuality (section 6.2) — regime-specific market-state health
// ---------------------------------------------------------------------------

double RegimeQualityEvidence(const ENUM_REGIME_STATE regime, const H1BrainResult &brain,
                             const double evidenceCompleteness)
{
   if(regime == REGIME_UNCERTAIN)
   {
      const double qGeneral = RegimeQGeneral(brain.volatility.quality);
      const double vGeneral = RegimeVGeneral(brain.volatility.level);
      return RegimeClamp01(0.55 * qGeneral + 0.25 * vGeneral + 0.20 * evidenceCompleteness);
   }
   if(regime == REGIME_TREND_BULL || regime == REGIME_TREND_BEAR)
   {
      const double qClean = RegimeQClean(brain.volatility.quality);
      const double vTrend = RegimeVTrendSuitable(brain.volatility.level);
      const double mSupportive = RegimeMSupportive(brain.momentum.state);
      return RegimeClamp01(0.35 * qClean + 0.25 * vTrend + 0.25 * mSupportive + 0.15 * evidenceCompleteness);
   }
   if(regime == REGIME_RANGE)
   {
      const double qTwo = RegimeQTwoSided(brain.volatility.quality);
      const double vRange = RegimeVRangeSuitable(brain.volatility.level);
      const double mNonExp = RegimeMNonExpansion(brain.momentum.state);
      return RegimeClamp01(0.35 * qTwo + 0.25 * vRange + 0.25 * mNonExp + 0.15 * evidenceCompleteness);
   }
   // BREAKOUT_BULL / BREAKOUT_BEAR
   const double qBreakout = RegimeQBreakoutClean(brain.volatility.quality);
   const double mExpanding = RegimeMExpanding(brain.momentum.state);
   const double expansionEvidence = RegimeClamp01(brain.volatility.expansionScore);
   return RegimeClamp01(0.30 * qBreakout + 0.30 * expansionEvidence + 0.25 * mExpanding
                        + 0.15 * evidenceCompleteness);
}

ENUM_REGIME_QUALITY RegimeClassifyQuality(const double qualityEvidence)
{
   if(qualityEvidence >= 0.75) return REGIME_QUALITY_STRONG;
   if(qualityEvidence >= 0.45) return REGIME_QUALITY_NORMAL;
   return REGIME_QUALITY_WEAK;
}

// ---------------------------------------------------------------------------
// Compression memory (section 7) — bounded rolling window, dynamic array
// ---------------------------------------------------------------------------

struct RegimeCompressionMemory
{
   double obs[];     // dynamic, chronological (oldest -> newest)
   int    count;
};

void RegimeCompressionInit(RegimeCompressionMemory &m, const int lookback)
{
   ArrayResize(m.obs, lookback);
   m.count = 0;
}

void RegimeCompressionAppend(RegimeCompressionMemory &m, const double value, const int lookback)
{
   if(lookback <= 0) return;
   if(m.count < lookback)
   {
      m.obs[m.count] = value;
      m.count++;
      return;
   }
   // FIFO: shift left, append at end
   for(int i = 0; i < lookback - 1; i++)
      m.obs[i] = m.obs[i + 1];
   m.obs[lookback - 1] = value;
}

double RegimeCompressionMax(const RegimeCompressionMemory &m)
{
   if(m.count <= 0) return 0.0;
   double mx = m.obs[0];
   for(int i = 1; i < m.count; i++)
      if(m.obs[i] > mx) mx = m.obs[i];
   return mx;
}

// ---------------------------------------------------------------------------
// Persistent fusion state + full update (sections 8 - 10)
// ---------------------------------------------------------------------------

struct RegimeFusionState
{
   ENUM_REGIME_STATE   regime;
   ENUM_REGIME_STATE   previousRegime;
   int                 regimeAgeBars;
   ENUM_REGIME_STATE   pendingCandidateRegime;
   bool                pendingCandidateActive;   // false => no pending challenger
   int                 candidateAgeBars;
   bool                initialized;
};

void RegimeFusionStateInit(RegimeFusionState &st)
{
   st.regime = REGIME_UNCERTAIN;
   st.previousRegime = REGIME_UNCERTAIN;
   st.regimeAgeBars = 0;
   st.pendingCandidateRegime = REGIME_UNCERTAIN;
   st.pendingCandidateActive = false;
   st.candidateAgeBars = 0;
   st.initialized = false;
}

void RegimeFusionStateClearPending(RegimeFusionState &st)
{
   st.pendingCandidateRegime = REGIME_UNCERTAIN;
   st.pendingCandidateActive = false;
   st.candidateAgeBars = 0;
}

ENUM_REGIME_STATE RegimeArgmax(const RegimeCandidateScores &s)
{
   const double c[5] = { s.trendBull, s.trendBear, s.range, s.breakoutBull, s.breakoutBear };
   int best = 0;
   for(int i = 1; i < 5; i++) if(c[i] > c[best]) best = i;
   switch(best)
   {
      case 0: return REGIME_TREND_BULL;
      case 1: return REGIME_TREND_BEAR;
      case 2: return REGIME_RANGE;
      case 3: return REGIME_BREAKOUT_BULL;
      default:return REGIME_BREAKOUT_BEAR;
   }
}

bool RegimeEffectiveTie(const RegimeCandidateScores &s, const double tieEpsilon)
{
   double top1, top2;
   RegimeTopTwo(s, top1, top2);
   return (top1 - top2) <= tieEpsilon;
}

// Breakout maturation helpers (section 9)
bool RegimeSustainedBull(const SwingStructureResult &structure, const H1BrainResult &brain)
{
   return (structure.state == STRUCTURE_BULLISH_STRONG || structure.state == STRUCTURE_BULLISH_WEAK)
          && brain.direction.score >= REGIME_DIR_COMMIT
          && brain.momentum.state != MOMENTUM_DECAYING;
}

bool RegimeSustainedBear(const SwingStructureResult &structure, const H1BrainResult &brain)
{
   return (structure.state == STRUCTURE_BEARISH_STRONG || structure.state == STRUCTURE_BEARISH_WEAK)
          && brain.direction.score <= -REGIME_DIR_COMMIT
          && brain.momentum.state != MOMENTUM_DECAYING;
}

bool RegimeOpposingStructure(const ENUM_REGIME_STATE regime, const SwingStructureResult &structure)
{
   if(regime == REGIME_BREAKOUT_BULL)
      return (structure.state == STRUCTURE_BEARISH_STRONG || structure.state == STRUCTURE_BEARISH_WEAK);
   if(regime == REGIME_BREAKOUT_BEAR)
      return (structure.state == STRUCTURE_BULLISH_STRONG || structure.state == STRUCTURE_BULLISH_WEAK);
   return false;
}

bool RegimeOpposingDirection(const ENUM_REGIME_STATE regime, const H1BrainResult &brain)
{
   if(regime == REGIME_BREAKOUT_BULL)  return brain.direction.score <= -REGIME_DIR_COMMIT;
   if(regime == REGIME_BREAKOUT_BEAR)  return brain.direction.score >= +REGIME_DIR_COMMIT;
   return false;
}

// The B06 input parameters are read from the EA globals (Config.mqh inputs).
struct RegimeFusionParams
{
   int    regimeDwell;
   double challengerGap;
   double uncertainVeto;
   double uncertainExitThreshold;
   int    uncertainExitDwell;
   double uncertainWeakWinnerThreshold;
   double tieEpsilon;
   int    breakoutMaturationMinBars;
   int    breakoutMaxAgeBars;
   int    breakoutLookbackBars;
};

// Fill a RegimeResult from the current state + upstream snapshot + scores + mass.
void RegimeBuildResult(RegimeResult &out,
                       const RegimeFusionState &st,
                       const SwingStructureResult &structure,
                       const H1BrainResult &brain,
                       const RegimeCandidateScores &scores,
                       const double scoreUncertain,
                       const ENUM_REGIME_TRANSITION_REASON reason,
                       const double evidenceCompleteness,
                       const bool valid,
                       const double challengerScore,
                       const double incumbentScore)
{
   out.regime = st.regime;
   out.valid = valid;
   out.previousRegime = st.previousRegime;
   out.regimeAgeBars = st.regimeAgeBars;
   out.transitionReason = reason;
   out.pendingCandidateRegime = st.pendingCandidateRegime;
   out.pendingCandidateActive = st.pendingCandidateActive;
   out.candidateAgeBars = st.candidateAgeBars;
   out.challengerConfidence = challengerScore;
   out.incumbentConfidence = incumbentScore;
   out.scoreUncertain = scoreUncertain;
   out.evidenceCompleteness = (valid ? evidenceCompleteness : 0.0);
   out.degradedDomains = REGIME_DEGRADED_NONE;

   // upstream snapshot mirrors
   out.latestClosedH1 = brain.direction.latestClosedH1;
   if(out.latestClosedH1 == 0) out.latestClosedH1 = brain.momentum.latestClosedH1;
   if(out.latestClosedH1 == 0) out.latestClosedH1 = structure.latestTime;
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

   out.scoreTrendBull = scores.trendBull;
   out.scoreTrendBear = scores.trendBear;
   out.scoreRange = scores.range;
   out.scoreBreakoutBull = scores.breakoutBull;
   out.scoreBreakoutBear = scores.breakoutBear;

   if(valid)
   {
      out.quality = RegimeClassifyQuality(RegimeQualityEvidence(st.regime, brain, evidenceCompleteness));
      out.confidence = RegimeConfidence(st.regime, scores, scoreUncertain, evidenceCompleteness);
   }
   else
   {
      out.quality = REGIME_QUALITY_WEAK;
      out.confidence = 0.0;
   }
}

// Breakout dedicated lifecycle (sections 9 - 10). Returns the new regime + reason.
void RegimeBreakoutStep(RegimeFusionState &st,
                        const SwingStructureResult &structure,
                        const H1BrainResult &brain,
                        const RegimeCandidateScores &scores,
                        const double scoreUncertain,
                        const RegimeFusionParams &p,
                        ENUM_REGIME_STATE &newRegime,
                        ENUM_REGIME_TRANSITION_REASON &reason)
{
   const ENUM_REGIME_STATE entering = st.regime;
   const bool bull = (entering == REGIME_BREAKOUT_BULL);

   // Trigger 1: immediate opposing evidence or hard conflict (section 10.1)
   if(RegimeOpposingStructure(entering, structure)
      || RegimeOpposingDirection(entering, brain)
      || RegimeHardUncertainVeto(structure, brain))
   {
      st.regimeAgeBars = 1;
      RegimeFusionStateClearPending(st);
      newRegime = REGIME_UNCERTAIN;
      reason = REGIME_TRANSITION_FAILED_BREAKOUT;
      return;
   }

   // Spend this bar (age counts completed bars including entry, section 8.0)
   st.regimeAgeBars += 1;

   // Maturation (section 9)
   const bool sustained = bull ? RegimeSustainedBull(structure, brain) : RegimeSustainedBear(structure, brain);
   if(st.regimeAgeBars >= p.breakoutMaturationMinBars && sustained)
   {
      st.regimeAgeBars = 1;
      RegimeFusionStateClearPending(st);
      newRegime = bull ? REGIME_TREND_BULL : REGIME_TREND_BEAR;
      reason = REGIME_TRANSITION_MATURATION;
      return;
   }

   // Trigger 2: age cap (section 10.2)
   if(st.regimeAgeBars >= p.breakoutMaxAgeBars)
   {
      st.regimeAgeBars = 1;
      RegimeFusionStateClearPending(st);
      newRegime = REGIME_UNCERTAIN;
      reason = REGIME_TRANSITION_FAILED_BREAKOUT;
      return;
   }

   // still a breakout
   newRegime = entering;
   reason = REGIME_TRANSITION_NONE;
}

// Full per-bar fusion (sections 8 - 10). Mutates st + returns a filled RegimeResult.
void UpdateRegimeFusion(RegimeFusionState &st,
                        const SwingStructureResult &structure,
                        const H1BrainResult &brain,
                        const RegimeFusionParams &p,
                        const double evidenceCompleteness,
                        const bool valid,
                        const double compressionContext,
                        RegimeResult &out)
{
   RegimeCandidateScores scores;
   RegimeComputeScores(structure, brain, compressionContext, scores);
   const double scoreUncertain = RegimeComputeUncertainMass(structure, brain, scores,
                                                            evidenceCompleteness,
                                                            p.uncertainWeakWinnerThreshold);

   const ENUM_REGIME_STATE entering = st.regime;
   st.previousRegime = entering;

   // Critical-invalid short-circuit (section 11.2 / 6.2.6)
   if(!valid)
   {
      st.regime = REGIME_UNCERTAIN;
      st.regimeAgeBars = 1;
      RegimeFusionStateClearPending(st);
      RegimeBuildResult(out, st, structure, brain, scores, scoreUncertain,
                        REGIME_TRANSITION_RESET, 0.0, false, 0.0, 0.0);
      return;
   }

   // Breakout incumbents: dedicated lifecycle, no generic challenger flip.
   if(entering == REGIME_BREAKOUT_BULL || entering == REGIME_BREAKOUT_BEAR)
   {
      ENUM_REGIME_STATE newRegime;
      ENUM_REGIME_TRANSITION_REASON reason;
      RegimeBreakoutStep(st, structure, brain, scores, scoreUncertain, p, newRegime, reason);
      st.regime = newRegime;
      RegimeBuildResult(out, st, structure, brain, scores, scoreUncertain, reason,
                        evidenceCompleteness, true, 0.0, 0.0);
      return;
   }

   // HARD uncertainty veto (section 5 rules 1 & 2): immediate UNCERTAIN, no dwell.
   if(RegimeHardUncertainVeto(structure, brain))
   {
      st.regime = REGIME_UNCERTAIN;
      st.regimeAgeBars = 1;
      RegimeFusionStateClearPending(st);
      RegimeBuildResult(out, st, structure, brain, scores, scoreUncertain,
                        REGIME_TRANSITION_OVERRIDE, evidenceCompleteness, true,
                        scoreUncertain, RegimeScoreOf(entering, scores));
      return;
   }

   ENUM_REGIME_STATE winnerRegime = RegimeArgmax(scores);
   double winnerScore = RegimeScoreOf(winnerRegime, scores);

   // Tie handling (section 8.5)
   if(RegimeEffectiveTie(scores, p.tieEpsilon))
   {
      if(st.regime != REGIME_UNCERTAIN)
      {
         winnerRegime = st.regime;
         winnerScore = RegimeScoreOf(st.regime, scores);
      }
      else
      {
         winnerRegime = REGIME_UNCERTAIN;
      }
   }

   const ENUM_REGIME_STATE incumbent = st.regime;

   // Bootstrap: first valid fusion
   if(!st.initialized)
   {
      st.initialized = true;
      st.regimeAgeBars = 1;
      RegimeFusionStateClearPending(st);
      if(winnerRegime == REGIME_UNCERTAIN || scoreUncertain >= p.uncertainVeto)
      {
         st.regime = REGIME_UNCERTAIN;
         RegimeBuildResult(out, st, structure, brain, scores, scoreUncertain,
                           REGIME_TRANSITION_INIT, evidenceCompleteness, true,
                           scoreUncertain, 0.0);
      }
      else
      {
         st.regime = winnerRegime;
         RegimeBuildResult(out, st, structure, brain, scores, scoreUncertain,
                           REGIME_TRANSITION_INIT, evidenceCompleteness, true,
                           winnerScore, winnerScore);
      }
      return;
   }

   // Incumbent == UNCERTAIN: exit via threshold + dwell
   if(incumbent == REGIME_UNCERTAIN)
   {
      if(st.pendingCandidateActive && st.pendingCandidateRegime == winnerRegime)
         st.candidateAgeBars += 1;
      else
      {
         st.pendingCandidateRegime = winnerRegime;
         st.pendingCandidateActive = true;
         st.candidateAgeBars = 1;
      }
      if(winnerScore >= p.uncertainExitThreshold && st.candidateAgeBars >= p.uncertainExitDwell)
      {
         st.regime = winnerRegime;
         st.regimeAgeBars = 1;
         RegimeFusionStateClearPending(st);
         RegimeBuildResult(out, st, structure, brain, scores, scoreUncertain,
                           REGIME_TRANSITION_CHALLENGE_WIN, evidenceCompleteness, true,
                           winnerScore, 0.0);
      }
      else
      {
         st.regime = REGIME_UNCERTAIN;
         RegimeBuildResult(out, st, structure, brain, scores, scoreUncertain,
                           REGIME_TRANSITION_NONE, evidenceCompleteness, true,
                           winnerScore, 0.0);
      }
      return;
   }

   // Established non-BREAKOUT incumbent.
   const bool softUncertain = scoreUncertain >= p.uncertainVeto;
   ENUM_REGIME_STATE challengerRegime = softUncertain ? REGIME_UNCERTAIN : winnerRegime;
   double challengerScore = softUncertain ? scoreUncertain : winnerScore;
   const double incumbentScore = RegimeScoreOf(incumbent, scores);   // recomputed this bar

   if(challengerRegime == incumbent)
   {
      RegimeFusionStateClearPending(st);
      st.regimeAgeBars += 1;
      st.regime = incumbent;
      RegimeBuildResult(out, st, structure, brain, scores, scoreUncertain,
                        REGIME_TRANSITION_NONE, evidenceCompleteness, true,
                        challengerScore, incumbentScore);
      return;
   }

   if(st.pendingCandidateActive && st.pendingCandidateRegime == challengerRegime)
      st.candidateAgeBars += 1;
   else
   {
      st.pendingCandidateRegime = challengerRegime;
      st.pendingCandidateActive = true;
      st.candidateAgeBars = 1;
   }

   const double gap = challengerScore - incumbentScore;
   if(gap >= p.challengerGap && st.candidateAgeBars >= p.regimeDwell)
   {
      st.regime = challengerRegime;
      st.regimeAgeBars = 1;
      RegimeFusionStateClearPending(st);
      RegimeBuildResult(out, st, structure, brain, scores, scoreUncertain,
                        REGIME_TRANSITION_CHALLENGE_WIN, evidenceCompleteness, true,
                        challengerScore, incumbentScore);
      return;
   }

   st.regime = incumbent;
   st.regimeAgeBars += 1;
   RegimeBuildResult(out, st, structure, brain, scores, scoreUncertain,
                     REGIME_TRANSITION_NONE, evidenceCompleteness, true,
                     challengerScore, incumbentScore);
}

#endif
