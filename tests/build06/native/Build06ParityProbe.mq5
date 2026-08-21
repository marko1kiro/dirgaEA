#property strict

#include "../../../DiagnosticCollector.mqh"

int failures = 0;

void AssertTrue(bool &ok, const bool value) { if(!value) ok = false; }
void AssertNear(bool &ok, const double actual, const double expected)
{
   if(MathAbs(actual - expected) > 1e-12) ok = false;
}

void Emit(const string name, const RegimeResult &r, const RegimeFusionState &s,
          const RegimeCompressionMemory &cm, const bool ok, const string expected = "")
{
   const string canonical = Build06DiagnosticCanonical(r, s, cm);
   const string signature = Build06DiagnosticSignature(r, s, cm);
   const bool pass = ok && (expected == "" || signature == expected);
   if(!pass) failures++;
   Print("case=", name, "|signature=", signature, "|pass=", pass ? "1" : "0");
   Print("case=", name, "|canonical=", canonical);
}

void Params(RegimeFusionParams &p)
{
   p.regimeDwell = 2; p.challengerGap = 0.10; p.uncertainVeto = 0.55;
   p.uncertainExitThreshold = 0.45; p.uncertainExitDwell = 1;
   p.uncertainWeakWinnerThreshold = 0.30; p.tieEpsilon = 1e-6;
   p.breakoutMaturationMinBars = 2; p.breakoutMaxAgeBars = 6; p.breakoutLookbackBars = 4;
}

void Observation(RegimeObservation &o, const datetime timestamp = 1700000000)
{
   ZeroMemory(o);
   o.latestClosedH1 = timestamp; o.criticalCoreValid = true;
   o.structureValid = true; o.directionValid = true; o.momentumValid = true; o.volatilityValid = true;
   o.structureState = STRUCTURE_BULLISH_STRONG; o.directionState = DIRECTION_STRONG_BULL; o.directionScore = 0.8;
   o.momentumState = MOMENTUM_NORMAL; o.momentumStrength = 0.0;
   o.volatilityLevel = VOL_NORMAL; o.volatilityQuality = VOLQ_HEALTHY;
}

void Baseline(RegimeResult &r, RegimeFusionState &s, RegimeCompressionMemory &cm)
{
   RegimeFusionStateInit(s); s.initialized = true; s.regime = REGIME_UNCERTAIN;
   s.previousRegime = REGIME_BREAKOUT_BEAR; s.regimeAgeBars = 1;
   RegimeCompressionInit(cm, 4); cm.obs[0] = 0.0; cm.count = 1;
   ZeroMemory(r);
   // Locked cross-language vector uses explicit canonical enum IDs.
   r.regime = (ENUM_REGIME_STATE)0; r.quality = (ENUM_REGIME_QUALITY)2; r.confidence = 0.94; r.valid = true;
   r.latestClosedH1 = 1700000000; r.regimeAgeBars = 1; r.previousRegime = (ENUM_REGIME_STATE)5;
   r.structureState = (ENUM_STRUCTURE_STATE)1; r.directionState = (ENUM_DIRECTION_STATE)4; r.directionScore = 0.8;
   r.momentumState = (ENUM_MOMENTUM_STATE)1; r.volatilityLevel = (ENUM_VOLATILITY_LEVEL)1; r.volatilityQuality = (ENUM_VOLATILITY_QUALITY)0;
   r.scoreTrendBull = 0.94; r.scoreTrendBear = 0.35; r.scoreRange = 0.235; r.scoreBreakoutBull = 0.26; r.scoreBreakoutBear = 0.14;
   r.transitionReason = REGIME_TRANSITION_INIT; r.evidenceCompleteness = 1.0;
}

bool Ingest(RegimeFusionState &s, RegimeCompressionMemory &cm, datetime &last,
            const RegimeObservation &o, const RegimeFusionParams &p, RegimeResult &r)
{
   return IngestRegimeObservation(s, cm, last, o, p, r);
}

int OnInit()
{
   RegimeFusionParams p; Params(p);
   RegimeResult r; RegimeFusionState s; RegimeCompressionMemory cm; datetime last = 0;
   Baseline(r, s, cm); Emit("baseline_signature", r, s, cm, true, "B06D1:D80BE01B4A71B434");

   bool ok = true; RegimeObservation o; Observation(o); RegimeFusionStateInit(s); RegimeCompressionInit(cm, 4);
   AssertTrue(ok, Ingest(s, cm, last, o, p, r)); AssertNear(ok, r.scoreTrendBull, 0.88);
   AssertTrue(ok, r.regime == REGIME_TREND_BULL && r.transitionReason == REGIME_TRANSITION_INIT);
   Emit("bull_scoring_mirror", r, s, cm, ok);

   ok = true; Observation(o, 1700003600); o.structureState = STRUCTURE_BEARISH_STRONG;
   o.directionState = DIRECTION_STRONG_BEAR; o.directionScore = -0.8; RegimeFusionStateInit(s); RegimeCompressionInit(cm, 4); last = 0;
   AssertTrue(ok, Ingest(s, cm, last, o, p, r)); AssertNear(ok, r.scoreTrendBear, 0.88);
   AssertTrue(ok, r.regime == REGIME_TREND_BEAR); Emit("bear_scoring_mirror", r, s, cm, ok);

   ok = true; Observation(o, 1700007200); o.criticalCoreValid = false; o.volatilityValid = false;
   RegimeFusionStateInit(s); RegimeCompressionInit(cm, 4); last = 0;
   AssertTrue(ok, Ingest(s, cm, last, o, p, r)); AssertTrue(ok, !r.valid && r.regime == REGIME_UNCERTAIN);
   AssertTrue(ok, r.transitionReason == REGIME_TRANSITION_RESET && r.degradedDomains == REGIME_DEGRADED_VOLATILITY);
   AssertTrue(ok, cm.count == 0 && last == o.latestClosedH1); Emit("invalid_stale", r, s, cm, ok);

   ok = true; Observation(o, 1700010800); o.structureValid = false; o.directionValid = false; o.momentumValid = false; o.volatilityValid = false;
   RegimeFusionStateInit(s); RegimeCompressionInit(cm, 4); last = 0; AssertTrue(ok, Ingest(s, cm, last, o, p, r));
   AssertNear(ok, r.evidenceCompleteness, 0.0); AssertTrue(ok, r.degradedDomains == 15 && cm.count == 0);
   Emit("invalid_domain_permutations", r, s, cm, ok);

   ok = true; Observation(o); RegimeCandidateScores raw, eligible; RegimeComputeScores(o, p, 0.0, raw);
   o.volatilityQuality = VOLQ_CHAOTIC; RegimeApplyEligibility(o, REGIME_UNCERTAIN, raw, eligible);
   AssertTrue(ok, eligible.range == -1.0); Emit("eligibility", r, s, cm, ok);

   ok = true; RegimeCandidateScores tied; tied.trendBull = 0.5; tied.trendBear = 0.5; tied.range = 0.0; tied.breakoutBull = 0.0; tied.breakoutBear = 0.0;
   AssertTrue(ok, RegimeEffectiveTie(tied, p.tieEpsilon)); Emit("uncertain_tie", r, s, cm, ok);

   ok = true; AssertNear(ok, RegimeBreakRecency(true, 0, p.breakoutLookbackBars), 1.0);
   AssertNear(ok, RegimeBreakRecency(true, 3, p.breakoutLookbackBars), 0.4);
   AssertNear(ok, RegimeBreakRecency(true, 4, p.breakoutLookbackBars), 0.0); Emit("lookback_boundary", r, s, cm, ok);

   MqlRates chronology[]; ArrayResize(chronology, 4);
   chronology[0].time = 100; chronology[1].time = 200; chronology[2].time = 300; chronology[3].time = 400;
   ok = true; AssertTrue(ok, B06ChronologicalBreakAge(chronology, 3, 200, p.breakoutLookbackBars) == 2);
   Emit("retained_break_age", r, s, cm, ok);

   ok = true; const int beforeReject = B06ChronologicalBreakAge(chronology, 1, 100, p.breakoutLookbackBars);
   const int afterReject = B06ChronologicalBreakAge(chronology, 3, 100, p.breakoutLookbackBars);
   AssertTrue(ok, beforeReject == 1 && afterReject == 3); Emit("rejected_then_accepted_age", r, s, cm, ok);

   chronology[0].time = 100; chronology[1].time = 100000;
   ok = true; AssertTrue(ok, B06ChronologicalBreakAge(chronology, 1, 100, p.breakoutLookbackBars) == 1);
   Emit("weekend_adjacent_age", r, s, cm, ok);

   ok = true; Observation(o, 1700014400); o.compressionEvidence = 0.125; RegimeFusionStateInit(s); RegimeCompressionInit(cm, 4); last = 0;
   AssertTrue(ok, Ingest(s, cm, last, o, p, r)); o.latestClosedH1 += 3600; o.compressionEvidence = 0.5;
   AssertTrue(ok, Ingest(s, cm, last, o, p, r)); AssertTrue(ok, cm.count == 2); AssertNear(ok, cm.obs[0], 0.125); AssertNear(ok, cm.obs[1], 0.5);
   Emit("fifo_prior_only", r, s, cm, ok);

   ok = true; Observation(o, 1700018000); RegimeFusionStateInit(s); s.initialized = true; s.regime = REGIME_BREAKOUT_BULL; s.regimeAgeBars = 1; RegimeCompressionInit(cm, 4); last = 0;
   UpdateRegimeFusion(s, o, p, 0.0, r); AssertTrue(ok, s.regime == REGIME_TREND_BULL && r.transitionReason == REGIME_TRANSITION_MATURATION);
   Emit("breakout_maturation", r, s, cm, ok);

   ok = true; Observation(o, 1700021600); o.structureState = STRUCTURE_BEARISH_STRONG; RegimeFusionStateInit(s); s.initialized = true; s.regime = REGIME_BREAKOUT_BULL; s.regimeAgeBars = 1;
   UpdateRegimeFusion(s, o, p, 0.0, r); AssertTrue(ok, s.regime == REGIME_UNCERTAIN && r.transitionReason == REGIME_TRANSITION_FAILED_BREAKOUT);
   Emit("breakout_failure", r, s, cm, ok);

   ok = true; Observation(o, 1700194400); RegimeFusionStateInit(s); RegimeCompressionInit(cm, 4); last = 1700021600;
   AssertTrue(ok, Ingest(s, cm, last, o, p, r)); AssertTrue(ok, r.latestClosedH1 == 1700194400 && r.regimeAgeBars == 1);
   Emit("weekend_gap_age", r, s, cm, ok);

   ok = true; Observation(o, 1700198000); RegimeFusionStateInit(s); RegimeCompressionInit(cm, 4); last = 0;
   AssertTrue(ok, Ingest(s, cm, last, o, p, r)); const datetime accepted = last;
   AssertTrue(ok, !Ingest(s, cm, last, o, p, r) && last == accepted); Emit("replay_hydration", r, s, cm, ok);

   Print("fail_count=", failures); return INIT_SUCCEEDED;
}

void OnTick() {}
