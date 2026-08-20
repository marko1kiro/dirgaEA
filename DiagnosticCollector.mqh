#ifndef ADAPTIVE_SURVIVAL_EA_DIAGNOSTIC_COLLECTOR_MQH
#define ADAPTIVE_SURVIVAL_EA_DIAGNOSTIC_COLLECTOR_MQH

#include "Config.mqh"
#include "Types.mqh"
#include "Logger.mqh"
#include "RegimeFusion.mqh"

#define BUILD04_DIAGNOSTIC_SIGNATURE_VERSION "B04D3"
#define BUILD04_DIAGNOSTIC_REPRESENTATIVE_LIMIT 4

struct Build04DiagnosticSnapshot
{
   bool initialized;
   SwingStructureResult structure;
   datetime sweepTimes[SWING_STRUCTURE_MAX_HISTORY];
   datetime sweepSourceTimes[SWING_STRUCTURE_MAX_HISTORY];
   int sweepCount;
};

void Build04DiagnosticAppend(string &out,const string key,const string value) { out+=key+"="+value+";"; }
string Build04DiagnosticBool(const bool value) { return value ? "1" : "0"; }
string Build04DiagnosticDecimal(const double value) { string text=DoubleToString(value,_Digits); while(StringLen(text)>1 && StringGetCharacter(text,StringLen(text)-1)=='0') text=StringSubstr(text,0,StringLen(text)-1); if(StringGetCharacter(text,StringLen(text)-1)=='.') text=StringSubstr(text,0,StringLen(text)-1); return text=="-0" ? "0" : text; }
bool Build04DiagnosticAscii(const string text) { for(int i=0;i<StringLen(text);i++) if(StringGetCharacter(text,i)>127) return false; return true; }
void Build04DiagnosticAppendSwing(string &out,const SwingPoint &x) { Build04DiagnosticAppend(out,"st",IntegerToString((long)x.time)); Build04DiagnosticAppend(out,"sp",Build04DiagnosticDecimal(x.price)); Build04DiagnosticAppend(out,"sa",Build04DiagnosticDecimal(x.atr)); Build04DiagnosticAppend(out,"sk",IntegerToString(x.kind)); Build04DiagnosticAppend(out,"sg",IntegerToString(x.significance)); Build04DiagnosticAppend(out,"sl",IntegerToString(x.label)); Build04DiagnosticAppend(out,"sc",Build04DiagnosticBool(x.consumed)); }
void Build04DiagnosticAppendBreak(string &out,const StructureBreak &x) { Build04DiagnosticAppend(out,"bt",IntegerToString((long)x.time)); Build04DiagnosticAppend(out,"bu",Build04DiagnosticBool(x.bullish)); Build04DiagnosticAppend(out,"bl",Build04DiagnosticDecimal(x.level)); Build04DiagnosticAppend(out,"bp",Build04DiagnosticDecimal(x.penetrationAtr)); Build04DiagnosticAppend(out,"bs",Build04DiagnosticBool(x.strong)); Build04DiagnosticAppend(out,"bf",IntegerToString(x.followThrough)); Build04DiagnosticAppend(out,"bz",Build04DiagnosticBool(x.followThroughFinalized)); }
string Build04DiagnosticSignature(const SwingStructureResult &x) { string out="v="+BUILD04_DIAGNOSTIC_SIGNATURE_VERSION+";"; Build04DiagnosticAppend(out,"state",IntegerToString(x.state)); Build04DiagnosticAppend(out,"sweep",Build04DiagnosticBool(x.sweep)); Build04DiagnosticAppend(out,"valid",Build04DiagnosticBool(x.valid)); Build04DiagnosticAppend(out,"latest",IntegerToString((long)x.latestTime)); Build04DiagnosticAppend(out,"sn",IntegerToString(x.swingCount)); for(int i=0;i<x.swingCount;i++) Build04DiagnosticAppendSwing(out,x.swings[i]); Build04DiagnosticAppend(out,"bn",IntegerToString(x.breakCount)); for(int i=0;i<x.breakCount;i++) Build04DiagnosticAppendBreak(out,x.breaks[i]); if(!Build04DiagnosticAscii(out)) return BUILD04_DIAGNOSTIC_SIGNATURE_VERSION+":ASCII_REJECTED"; ulong hash=14695981039346656037; for(int i=0;i<StringLen(out);i++) { const ushort byteValue=(ushort)StringGetCharacter(out,i); hash^=(ulong)byteValue; hash*=1099511628211; } return BUILD04_DIAGNOSTIC_SIGNATURE_VERSION+":"+StringFormat("%I64X",hash); }
bool Build04DiagnosticSameSwingIdentity(const SwingPoint &a,const SwingPoint &b) { return a.time==b.time && a.kind==b.kind && a.significance==b.significance && a.price==b.price && a.atr==b.atr && a.label==b.label; }
int Build04DiagnosticFindSwing(const SwingStructureResult &x,const SwingPoint &target) { for(int i=0;i<x.swingCount;i++) if(Build04DiagnosticSameSwingIdentity(x.swings[i],target)) return i; return -1; }
int Build04DiagnosticFindBreak(const SwingStructureResult &x,const StructureBreak &target) { for(int i=0;i<x.breakCount;i++) if(x.breaks[i].time==target.time && x.breaks[i].bullish==target.bullish && x.breaks[i].level==target.level) return i; return -1; }
bool Build04DiagnosticHasSweep(const Build04DiagnosticSnapshot &s,const datetime time,const datetime source) { for(int i=0;i<s.sweepCount;i++) if(s.sweepTimes[i]==time && s.sweepSourceTimes[i]==source) return true; return false; }
void Build04DiagnosticLogSwing(const SwingPoint &x,const datetime confirm=0,const double excursion=0.0) { LogDebug("SWING_CONFIRMED",StringFormat("pivot_time=%I64d confirm_time=%I64d kind=%d significance=%d label=%d price=%s atr=%s excursion_atr=%s consumed=%s",(long)x.time,(long)confirm,x.kind,x.significance,x.label,Build04DiagnosticDecimal(x.price),Build04DiagnosticDecimal(x.atr),Build04DiagnosticDecimal(excursion),Build04DiagnosticBool(x.consumed))); }
void Build04DiagnosticLogBreak(const string eventName,const StructureBreak &x,const datetime source=0,const double body=0.0,const double range=0.0,const double close=0.0) { LogDebug(eventName,StringFormat("time=%I64d source_time=%I64d bullish=%s level=%s penetration_atr=%s body=%s range=%s directional_close=%s strong=%s followthrough=%d finalized=%s",(long)x.time,(long)source,Build04DiagnosticBool(x.bullish),Build04DiagnosticDecimal(x.level),Build04DiagnosticDecimal(x.penetrationAtr),Build04DiagnosticDecimal(body),Build04DiagnosticDecimal(range),Build04DiagnosticDecimal(close),Build04DiagnosticBool(x.strong),x.followThrough,Build04DiagnosticBool(x.followThroughFinalized))); }
void Build04DiagnosticSafety(const Build04DiagnosticTrace &t,const string phase) { LogDebug("DIAGNOSTIC_SAFETY",StringFormat("phase=%s duplicate_h1_attempts=%d duplicate_events_rejected=%d forming_bar_attempts=%d invalid_atr=%d copybuffer_failures=%d zero_range=%d abnormal_skips=%d",phase,t.counters.duplicateH1Attempts,t.counters.duplicateEventsRejected,t.counters.formingBarAttempts,t.counters.invalidAtr,t.counters.copyBufferFailures,t.counters.zeroRange,t.counters.abnormalSkips)); }
void Build04DiagnosticBootstrap(const SwingStructureResult &x,const Build04DiagnosticTrace &t) { int minor=0,major=0,bos=0,follow=0; for(int i=t.pivotCount-1;i>=0 && minor+major<BUILD04_DIAGNOSTIC_REPRESENTATIVE_LIMIT;i--) { if(t.pivots[i].significance==SWING_MINOR && minor==0) { Build04DiagnosticLogSwing(t.pivots[i],t.pivotConfirmationTimes[i],t.pivotExcursionAtr[i]); minor++; } else if(t.pivots[i].significance==SWING_MAJOR && major<BUILD04_DIAGNOSTIC_REPRESENTATIVE_LIMIT-1) { Build04DiagnosticLogSwing(t.pivots[i],t.pivotConfirmationTimes[i],t.pivotExcursionAtr[i]); major++; } } for(int i=t.bosCount-1;i>=0 && bos<BUILD04_DIAGNOSTIC_REPRESENTATIVE_LIMIT;i--) { Build04DiagnosticLogBreak("BOS_EVENT",t.bos[i],t.bosSourceTimes[i],t.bosBodies[i],t.bosRanges[i],t.bosDirectionalCloses[i]); bos++; } for(int i=t.followThroughCount-1;i>=0 && follow<BUILD04_DIAGNOSTIC_REPRESENTATIVE_LIMIT;i--) { Build04DiagnosticLogBreak("FOLLOWTHROUGH_FINAL",t.followThrough[i]); LogDebug("FOLLOWTHROUGH_WINDOW",StringFormat("parent_time=%I64d window_end=%I64d",(long)t.followThrough[i].time,(long)t.followThroughWindowEnds[i])); follow++; } LogDebug("BOOTSTRAP",StringFormat("symbol=%s requested_bars=%d copied_rates=%d copied_atr=%d atr_error=%d start=%I64d end=%I64d latest_closed=%I64d width=%d bar0_excluded=%s immutable_input=%s swings=%d breaks=%d minor=%d major=%d bos=%d followthrough=%d signature=%s",t.symbol,t.requestedBars,t.copiedRates,t.copiedAtr,t.atrError,(long)t.startTime,(long)t.endTime,(long)t.latestClosedTime,t.width,Build04DiagnosticBool(t.bar0Excluded),Build04DiagnosticBool(t.immutableInput),x.swingCount,x.breakCount,minor,major,bos,follow,Build04DiagnosticSignature(x))); Build04DiagnosticSafety(t,"bootstrap"); }
void Build04DiagnosticCollect(Build04DiagnosticSnapshot &s,const SwingStructureResult &x,Build04DiagnosticTrace &t) { if(!Build04DiagnosticMode || !x.valid) return; if(!s.initialized) { Build04DiagnosticBootstrap(x,t); s.structure=x; s.initialized=true; return; } for(int i=0;i<t.pivotCount;i++) if(Build04DiagnosticFindSwing(s.structure,t.pivots[i])<0) Build04DiagnosticLogSwing(t.pivots[i],t.pivotConfirmationTimes[i],t.pivotExcursionAtr[i]); else t.counters.duplicateEventsRejected++; for(int i=0;i<t.bosCount;i++) if(Build04DiagnosticFindBreak(s.structure,t.bos[i])<0) Build04DiagnosticLogBreak("BOS_EVENT",t.bos[i],t.bosSourceTimes[i],t.bosBodies[i],t.bosRanges[i],t.bosDirectionalCloses[i]); else t.counters.duplicateEventsRejected++; for(int i=0;i<t.sweepCount;i++) { if(Build04DiagnosticHasSweep(s,t.sweepTimes[i],t.sweeps[i].time)) { t.counters.duplicateEventsRejected++; continue; } LogDebug("SWEEP_EVENT",StringFormat("time=%I64d source_time=%I64d level=%s wick=%s close=%s",(long)t.sweepTimes[i],(long)t.sweeps[i].time,Build04DiagnosticDecimal(t.sweeps[i].price),Build04DiagnosticDecimal(t.sweepWicks[i]),Build04DiagnosticDecimal(t.sweepCloses[i]))); if(s.sweepCount<SWING_STRUCTURE_MAX_HISTORY) { s.sweepTimes[s.sweepCount]=t.sweepTimes[i]; s.sweepSourceTimes[s.sweepCount++]=t.sweeps[i].time; } } for(int i=0;i<t.followThroughCount;i++) { int prior=Build04DiagnosticFindBreak(s.structure,t.followThrough[i]); if(prior>=0 && s.structure.breaks[prior].followThroughFinalized) { t.counters.duplicateEventsRejected++; continue; } Build04DiagnosticLogBreak("FOLLOWTHROUGH_FINAL",t.followThrough[i]); LogDebug("FOLLOWTHROUGH_WINDOW",StringFormat("parent_time=%I64d window_end=%I64d",(long)t.followThrough[i].time,(long)t.followThroughWindowEnds[i])); } if(s.structure.state!=x.state) LogDebug("STRUCTURE_STATE_CHANGE",StringFormat("from=%d to=%d high_label=%d low_label=%d sequence_time=%I64d bos_required=%s",s.structure.state,x.state,t.stateHighLabel,t.stateLowLabel,(long)t.stateSequenceTime,Build04DiagnosticBool(t.stateBosRequired))); Build04DiagnosticSafety(t,"runtime"); s.structure=x; }

// ---------------------------------------------------------------------------
// BUILD 05 diagnostics
// ---------------------------------------------------------------------------
#define BUILD05_DIAGNOSTIC_SIGNATURE_VERSION "B05D2"

string Build05DiagnosticDecimal(const double value) { string text=DoubleToString(value,15); while(StringLen(text)>1 && StringGetCharacter(text,StringLen(text)-1)=='0') text=StringSubstr(text,0,StringLen(text)-1); if(StringGetCharacter(text,StringLen(text)-1)=='.') text=StringSubstr(text,0,StringLen(text)-1); return text=="-0" ? "0" : text; }

// High-precision serializer for native-indicator parity (observability only).
// Emits ~15 significant decimal digits; NOT truncated by _Digits.
string Build05NativeDecimal(const double value)
{
   string text = DoubleToString(value, 15);
   // strip trailing zeros and dangling decimal point
   while(StringLen(text) > 1 && StringGetCharacter(text, StringLen(text) - 1) == '0')
      text = StringSubstr(text, 0, StringLen(text) - 1);
   if(StringLen(text) > 0 && StringGetCharacter(text, StringLen(text) - 1) == '.')
      text = StringSubstr(text, 0, StringLen(text) - 1);
   return (text == "-0") ? "0" : text;
}

// B05D2: hashes H1BrainResult + Build05BehaviorState (hidden persistence).
string Build05DiagnosticSignature(const H1BrainResult &b, const Build05BehaviorState &s)
{
   // BrainVolQualityReady(count) used in MarketBrain to set s.volQualityReady
   string out = "v=" + BUILD05_DIAGNOSTIC_SIGNATURE_VERSION + ";";
   // Direction visible
   Build04DiagnosticAppend(out, "dstate", IntegerToString(b.direction.state));
   Build04DiagnosticAppend(out, "dscore", Build05DiagnosticDecimal(b.direction.score));
   Build04DiagnosticAppend(out, "dvalid", Build04DiagnosticBool(b.direction.valid));
   Build04DiagnosticAppend(out, "dtime", IntegerToString((long)b.direction.latestClosedH1));
   // Direction hidden
   Build04DiagnosticAppend(out, "ddwell", IntegerToString(s.directionDwell));
   Build04DiagnosticAppend(out, "dch", IntegerToString(s.directionChallenger));
   Build04DiagnosticAppend(out, "dchd", IntegerToString(s.directionChallengerDwell));
   // Momentum visible
   Build04DiagnosticAppend(out, "mstate", IntegerToString(b.momentum.state));
   Build04DiagnosticAppend(out, "mstrength", Build05DiagnosticDecimal(b.momentum.strengthScore));
   Build04DiagnosticAppend(out, "mdelta", Build05DiagnosticDecimal(b.momentum.strengthDelta));
   Build04DiagnosticAppend(out, "mslope", Build05DiagnosticDecimal(b.momentum.strengthSlope));
   Build04DiagnosticAppend(out, "malign", Build05DiagnosticDecimal(b.momentum.directionalAlignment));
   Build04DiagnosticAppend(out, "mvalid", Build04DiagnosticBool(b.momentum.valid));
   Build04DiagnosticAppend(out, "mdegraded", Build04DiagnosticBool(b.momentum.helperDegraded));
   Build04DiagnosticAppend(out, "mtime", IntegerToString((long)b.momentum.latestClosedH1));
   // Momentum hidden
   Build04DiagnosticAppend(out, "mpersist", IntegerToString(s.momentumPersist));
   Build04DiagnosticAppend(out, "mpstr", Build05DiagnosticDecimal(s.prevMomentumStrength));
   Build04DiagnosticAppend(out, "mprmd", Build04DiagnosticBool(s.momentumStrengthPrimed));
   // VolLevel visible
   Build04DiagnosticAppend(out, "vlevel", IntegerToString(b.volatility.level));
   Build04DiagnosticAppend(out, "vlscore", Build05DiagnosticDecimal(b.volatility.levelScore));
   Build04DiagnosticAppend(out, "vvalid", Build04DiagnosticBool(b.volatility.valid));
   Build04DiagnosticAppend(out, "vtime", IntegerToString((long)b.volatility.latestClosedH1));
   // VolLevel hidden
   Build04DiagnosticAppend(out, "vldwell", IntegerToString(s.volLevelDwell));
   Build04DiagnosticAppend(out, "vlch", IntegerToString(s.volLevelChallenger));
   Build04DiagnosticAppend(out, "vlchd", IntegerToString(s.volLevelChallengerDwell));
   // VolQuality visible
   Build04DiagnosticAppend(out, "vquality", IntegerToString(b.volatility.quality));
   Build04DiagnosticAppend(out, "vqconf", Build05DiagnosticDecimal(b.volatility.qualityConfidence));
   Build04DiagnosticAppend(out, "vqcomp", Build05DiagnosticDecimal(b.volatility.compressionScore));
   Build04DiagnosticAppend(out, "vqexp", Build05DiagnosticDecimal(b.volatility.expansionScore));
   Build04DiagnosticAppend(out, "vqchaos", Build05DiagnosticDecimal(b.volatility.chaosScore));
   Build04DiagnosticAppend(out, "vqshock", Build05DiagnosticDecimal(b.volatility.shockScore));
   Build04DiagnosticAppend(out, "vqhealth", Build05DiagnosticDecimal(b.volatility.healthyScore));
    // VolQuality hidden
    Build04DiagnosticAppend(out, "vqprmd", Build04DiagnosticBool(s.volQualityPrimed));
    Build04DiagnosticAppend(out, "vqch", IntegerToString(s.volQualityChallenger));
    Build04DiagnosticAppend(out, "vqchd", IntegerToString(s.volQualityChallengerDwell));
    // Direction hidden committed state
    Build04DiagnosticAppend(out, "dstate_h", IntegerToString(s.directionState));
    // Momentum hidden committed state
    Build04DiagnosticAppend(out, "mstate_h", IntegerToString(s.momentumState));
    // VolLevel hidden committed state
    Build04DiagnosticAppend(out, "vlstate_h", IntegerToString(s.volLevel));
    // VolQuality hidden committed state
    Build04DiagnosticAppend(out, "vqstate_h", IntegerToString(s.volQuality));
    // Quality readiness
    Build04DiagnosticAppend(out, "vqready", Build04DiagnosticBool(s.volQualityReady));
    if(!Build04DiagnosticAscii(out)) return BUILD05_DIAGNOSTIC_SIGNATURE_VERSION + ":ASCII_REJECTED";
   ulong hash = 14695981039346656037;
   for(int i = 0; i < StringLen(out); i++)
   {
      const ushort byteValue = (ushort)StringGetCharacter(out, i);
      hash ^= (ulong)byteValue;
      hash *= 1099511628211;
   }
   return BUILD05_DIAGNOSTIC_SIGNATURE_VERSION + ":" + StringFormat("%I64X", hash);
}

// BUILD05 safety counters (observability only, never alter B05 outputs)
struct Build05DiagnosticCounters
{
   int copyBufferFailures;
   int invalidAtr;
   int invalidEma;
   int adxDegraded;
   int duplicateH1Attempts;
   int formingBarAttempts;
   int abnormalSkips;
   int volQualityNotReady;
};

struct Build05RawTrace
{
   double fastSlopeAtr;
   double slowSlopeAtr;
   double positioning;
   double signedDisplacement;
   double signedEfficiency;
   double directionRawScore;
   double bodyAtr;
   double bodyRange;
   double closeLocation;
   double signedProgression;
   double progressionStrength;
   double efficiencyMagnitude;
   double momentumSignedEfficiency;
   double momentumRawScore;
   double adxCurrent;
   double adxPrevious;
   double adxSlope;
   double atrCurrent;
   double atrBaseline;
   double atrRatio;
   double recentAtr;
   double priorAtr;
   double atrDecline;
   double atrRise;
   double recentRange;
   double priorRange;
   double rangeShrink;
   double rangeExpand;
   double recentBody;
   double priorBody;
   double bodyShrink;
   double bodyExpand;
   double recentEfficiency;
   double priorEfficiency;
   double efficiencyRise;
   double recentDisplacement;
   double priorDisplacement;
   double displacementRise;
   double wickNoise;
   bool qualityReady;
   double healthyScore;
   double compressionScore;
   double expansionScore;
   double chaosScore;
   double shockScore;
};

void Build05DiagnosticCountersInit(Build05DiagnosticCounters &c)
{
   c.copyBufferFailures = 0;
   c.invalidAtr = 0;
   c.invalidEma = 0;
   c.adxDegraded = 0;
   c.duplicateH1Attempts = 0;
   c.formingBarAttempts = 0;
   c.abnormalSkips = 0;
   c.volQualityNotReady = 0;
}

// Transition-only state for detecting committed enum changes
struct Build05TransitionState
{
   ENUM_DIRECTION_STATE prevDirection;
   ENUM_MOMENTUM_STATE prevMomentum;
   ENUM_VOLATILITY_LEVEL prevVolLevel;
   ENUM_VOLATILITY_QUALITY prevVolQuality;
};

void Build05TransitionStateInit(Build05TransitionState &t)
{
   t.prevDirection = DIRECTION_NEUTRAL;
   t.prevMomentum = MOMENTUM_NORMAL;
   t.prevVolLevel = VOL_NORMAL;
   t.prevVolQuality = VOLQ_HEALTHY;
}

void Build05DiagnosticTransitions(const H1BrainResult &b, const Build05BehaviorState &s,
                                  const ENUM_DIRECTION_STATE prevDirection,
                                  const ENUM_MOMENTUM_STATE prevMomentum,
                                  const ENUM_VOLATILITY_LEVEL prevVolLevel,
                                  const ENUM_VOLATILITY_QUALITY prevVolQuality)
{
   const datetime closedH1 = b.direction.latestClosedH1 != 0 ? b.direction.latestClosedH1 :
                             (b.momentum.latestClosedH1 != 0 ? b.momentum.latestClosedH1 : b.volatility.latestClosedH1);
   if(b.direction.valid && prevDirection != s.directionState)
      LogDebug("B05_DIRECTION_TRANSITION", StringFormat("closed_h1=%I64d from=%d to=%d dwell=%d challenger=%d challenger_dwell=%d", (long)closedH1, prevDirection, s.directionState, s.directionDwell, s.directionChallenger, s.directionChallengerDwell));
   if(b.momentum.valid && prevMomentum != s.momentumState)
      LogDebug("B05_MOMENTUM_TRANSITION", StringFormat("closed_h1=%I64d from=%d to=%d persist=%d", (long)closedH1, prevMomentum, s.momentumState, s.momentumPersist));
   if(b.volatility.valid && prevVolLevel != s.volLevel)
      LogDebug("B05_VOLLEVEL_TRANSITION", StringFormat("closed_h1=%I64d from=%d to=%d dwell=%d challenger=%d challenger_dwell=%d", (long)closedH1, prevVolLevel, s.volLevel, s.volLevelDwell, s.volLevelChallenger, s.volLevelChallengerDwell));
   if(b.volatility.valid && s.volQualityReady && prevVolQuality != s.volQuality)
      LogDebug("B05_VOLQUALITY_TRANSITION", StringFormat("closed_h1=%I64d from=%d to=%d challenger=%d challenger_dwell=%d", (long)closedH1, prevVolQuality, s.volQuality, s.volQualityChallenger, s.volQualityChallengerDwell));
}

string Build05RuntimeDecimal(const double value)
{
   string text=DoubleToString(value, 8);
   while(StringLen(text)>1 && StringGetCharacter(text,StringLen(text)-1)=='0') text=StringSubstr(text,0,StringLen(text)-1);
   if(StringGetCharacter(text,StringLen(text)-1)=='.') text=StringSubstr(text,0,StringLen(text)-1);
   return text=="-0" ? "0" : text;
}

// B05T1 positions:
// d=[state,score,valid,fastSlopeAtr,slowSlopeAtr,positioning,signedDisplacement,signedEfficiency,rawScore]
// m=[state,strength,delta,slope,alignment,valid,degraded,bodyAtr,bodyRange,closeLocation,signedProgression,progressionStrength,efficiencyMagnitude,signedEfficiency,rawScore,adxCurrent,adxPrevious,adxSlope]
// v=[level,levelScore,quality,qualityConfidence,valid,qualityReady,atrCurrent,atrBaseline,atrRatio,recentAtr,priorAtr,atrDecline,atrRise,recentRange,priorRange,rangeShrink,rangeExpand,recentBody,priorBody,bodyShrink,bodyExpand,recentEfficiency,priorEfficiency,efficiencyRise,recentDisplacement,priorDisplacement,displacementRise,wickNoise,healthy,compression,expansion,chaos,shock]
// p=[directionState,directionDwell,directionChallenger,directionChallengerDwell,momentumState,momentumPersist,prevMomentumStrength,momentumStrengthPrimed,volLevel,volLevelDwell,volLevelChallenger,volLevelChallengerDwell,volQuality,volQualityConfidence,volQualityPrimed,volQualityChallenger,volQualityChallengerDwell]
string Build05RuntimeMessage(const H1BrainResult &b, const Build05BehaviorState &s, const Build05RawTrace &t)
{
   const datetime h=b.direction.latestClosedH1!=0 ? b.direction.latestClosedH1 : (b.momentum.latestClosedH1!=0 ? b.momentum.latestClosedH1 : b.volatility.latestClosedH1);
   string d=StringFormat("%d,%s,%s,%s,%s,%s,%s,%s,%s",s.directionState,Build05RuntimeDecimal(b.direction.score),Build04DiagnosticBool(b.direction.valid),Build05RuntimeDecimal(t.fastSlopeAtr),Build05RuntimeDecimal(t.slowSlopeAtr),Build05RuntimeDecimal(t.positioning),Build05RuntimeDecimal(t.signedDisplacement),Build05RuntimeDecimal(t.signedEfficiency),Build05RuntimeDecimal(t.directionRawScore));
   string m=StringFormat("%d,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s",s.momentumState,Build05RuntimeDecimal(b.momentum.strengthScore),Build05RuntimeDecimal(b.momentum.strengthDelta),Build05RuntimeDecimal(b.momentum.strengthSlope),Build05RuntimeDecimal(b.momentum.directionalAlignment),Build04DiagnosticBool(b.momentum.valid),Build04DiagnosticBool(b.momentum.helperDegraded),Build05RuntimeDecimal(t.bodyAtr),Build05RuntimeDecimal(t.bodyRange),Build05RuntimeDecimal(t.closeLocation),Build05RuntimeDecimal(t.signedProgression),Build05RuntimeDecimal(t.progressionStrength),Build05RuntimeDecimal(t.efficiencyMagnitude),Build05RuntimeDecimal(t.momentumSignedEfficiency),Build05RuntimeDecimal(t.momentumRawScore),Build05RuntimeDecimal(t.adxCurrent),Build05RuntimeDecimal(t.adxPrevious),Build05RuntimeDecimal(t.adxSlope));
   string v=StringFormat("%d,%s,%d,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s",s.volLevel,Build05RuntimeDecimal(b.volatility.levelScore),s.volQuality,Build05RuntimeDecimal(s.volQualityConfidence),Build04DiagnosticBool(b.volatility.valid),Build04DiagnosticBool(s.volQualityReady),Build05RuntimeDecimal(t.atrCurrent),Build05RuntimeDecimal(t.atrBaseline),Build05RuntimeDecimal(t.atrRatio),Build05RuntimeDecimal(t.recentAtr),Build05RuntimeDecimal(t.priorAtr),Build05RuntimeDecimal(t.atrDecline),Build05RuntimeDecimal(t.atrRise),Build05RuntimeDecimal(t.recentRange),Build05RuntimeDecimal(t.priorRange),Build05RuntimeDecimal(t.rangeShrink),Build05RuntimeDecimal(t.rangeExpand),Build05RuntimeDecimal(t.recentBody),Build05RuntimeDecimal(t.priorBody),Build05RuntimeDecimal(t.bodyShrink),Build05RuntimeDecimal(t.bodyExpand),Build05RuntimeDecimal(t.recentEfficiency),Build05RuntimeDecimal(t.priorEfficiency),Build05RuntimeDecimal(t.efficiencyRise),Build05RuntimeDecimal(t.recentDisplacement),Build05RuntimeDecimal(t.priorDisplacement),Build05RuntimeDecimal(t.displacementRise),Build05RuntimeDecimal(t.wickNoise),Build05RuntimeDecimal(t.healthyScore),Build05RuntimeDecimal(t.compressionScore),Build05RuntimeDecimal(t.expansionScore),Build05RuntimeDecimal(t.chaosScore),Build05RuntimeDecimal(t.shockScore));
   string p=StringFormat("%d,%d,%d,%d,%d,%d,%s,%s,%d,%d,%d,%d,%d,%s,%s,%d,%d",s.directionState,s.directionDwell,s.directionChallenger,s.directionChallengerDwell,s.momentumState,s.momentumPersist,Build05RuntimeDecimal(s.prevMomentumStrength),Build04DiagnosticBool(s.momentumStrengthPrimed),s.volLevel,s.volLevelDwell,s.volLevelChallenger,s.volLevelChallengerDwell,s.volQuality,Build05RuntimeDecimal(s.volQualityConfidence),Build04DiagnosticBool(s.volQualityPrimed),s.volQualityChallenger,s.volQualityChallengerDwell);
   return StringFormat("schema=B05T1 h=%I64d d=[%s] m=[%s] v=[%s] p=[%s] sig=%s end=1",(long)h,d,m,v,p,Build05DiagnosticSignature(b,s));
}

string Build05DiagnosticMessage(const H1BrainResult &b, const Build05BehaviorState &s, const Build05RawTrace &trace)
{
   return Build05RuntimeMessage(b,s,trace);
}

void Build05DiagnosticCollect(const H1BrainResult &b, const Build05BehaviorState &s, const Build05RawTrace &trace, const Build05DiagnosticCounters &c)
{
   if(!Build05DiagnosticMode)
      return;
   const string message = Build05DiagnosticMessage(b, s, trace);
   LogDebug("BRAIN_UPDATE", message);
   LogDebug("B05_SAFETY", StringFormat("copy_buffer_failures=%d invalid_atr=%d invalid_ema=%d adx_degraded=%d duplicate_h1_attempts=%d forming_bar_attempts=%d abnormal_skips=%d vol_quality_not_ready=%d", c.copyBufferFailures, c.invalidAtr, c.invalidEma, c.adxDegraded, c.duplicateH1Attempts, c.formingBarAttempts, c.abnormalSkips, c.volQualityNotReady));
}

// ---------------------------------------------------------------------------
// BUILD 06 diagnostics — H1 Regime Fusion
// ---------------------------------------------------------------------------
#define BUILD06_DIAGNOSTIC_SIGNATURE_VERSION "B06D1"

// Canonical string matches docs/specs section 14 exactly. Hashes ALL behavior-
// affecting persistent state (pending candidate + compression FIFO contents+count
// + momentumDirectionalAlignment mirror), so identical visible results with
// different hidden state produce different signatures.
string Build06DiagnosticSignature(const RegimeResult &r, const RegimeCompressionMemory &cm)
{
   string out = "v=" + BUILD06_DIAGNOSTIC_SIGNATURE_VERSION + ";";
   Build04DiagnosticAppend(out, "regime", IntegerToString((int)r.regime));
   Build04DiagnosticAppend(out, "quality", IntegerToString((int)r.quality));
   Build04DiagnosticAppend(out, "confidence", Build05NativeDecimal(r.confidence));
   Build04DiagnosticAppend(out, "valid", Build04DiagnosticBool(r.valid));
   Build04DiagnosticAppend(out, "latest", IntegerToString((long)r.latestClosedH1));
   Build04DiagnosticAppend(out, "age", IntegerToString(r.regimeAgeBars));
   Build04DiagnosticAppend(out, "prev", IntegerToString((int)r.previousRegime));
   Build04DiagnosticAppend(out, "structure", IntegerToString((int)r.structureState));
   Build04DiagnosticAppend(out, "direction", IntegerToString((int)r.directionState));
   Build04DiagnosticAppend(out, "dscore", Build05NativeDecimal(r.directionScore));
   Build04DiagnosticAppend(out, "momentum", IntegerToString((int)r.momentumState));
   Build04DiagnosticAppend(out, "mstrength", Build05NativeDecimal(r.momentumStrength));
   Build04DiagnosticAppend(out, "mda", Build05NativeDecimal(r.momentumDirectionalAlignment));
   Build04DiagnosticAppend(out, "vlevel", IntegerToString((int)r.volatilityLevel));
   Build04DiagnosticAppend(out, "vquality", IntegerToString((int)r.volatilityQuality));
   Build04DiagnosticAppend(out, "comp", Build05NativeDecimal(r.compressionEvidence));
   Build04DiagnosticAppend(out, "exp", Build05NativeDecimal(r.expansionEvidence));
   Build04DiagnosticAppend(out, "sTB", Build05NativeDecimal(r.scoreTrendBull));
   Build04DiagnosticAppend(out, "sTBe", Build05NativeDecimal(r.scoreTrendBear));
   Build04DiagnosticAppend(out, "sR", Build05NativeDecimal(r.scoreRange));
   Build04DiagnosticAppend(out, "sBB", Build05NativeDecimal(r.scoreBreakoutBull));
   Build04DiagnosticAppend(out, "sBBe", Build05NativeDecimal(r.scoreBreakoutBear));
   Build04DiagnosticAppend(out, "sU", Build05NativeDecimal(r.scoreUncertain));
   Build04DiagnosticAppend(out, "tx", IntegerToString((int)r.transitionReason));
   Build04DiagnosticAppend(out, "candAge", IntegerToString(r.candidateAgeBars));
   Build04DiagnosticAppend(out, "pend", r.pendingCandidateActive
                            ? IntegerToString((int)r.pendingCandidateRegime) : "NONE");
   Build04DiagnosticAppend(out, "complete", Build05NativeDecimal(r.evidenceCompleteness));
   Build04DiagnosticAppend(out, "degraded", IntegerToString(r.degradedDomains));
   Build04DiagnosticAppend(out, "cm_count", IntegerToString(cm.count));
   string obs = "";
   for(int i = 0; i < cm.count; i++)
   {
      if(i > 0) obs += ",";
      obs += Build05NativeDecimal(cm.obs[i]);
   }
   Build04DiagnosticAppend(out, "cm_obs", obs);

   if(!Build04DiagnosticAscii(out)) return BUILD06_DIAGNOSTIC_SIGNATURE_VERSION + ":ASCII_REJECTED";
   ulong hash = 14695981039346656037;
   for(int i = 0; i < StringLen(out); i++)
   {
      const ushort byteValue = (ushort)StringGetCharacter(out, i);
      hash ^= (ulong)byteValue;
      hash *= 1099511628211;
   }
   return BUILD06_DIAGNOSTIC_SIGNATURE_VERSION + ":" + StringFormat("%I64X", hash);
}

void Build06DiagnosticCollect(const RegimeResult &r, const RegimeCompressionMemory &cm)
{
   if(!Build06DiagnosticMode)
      return;

   LogDebug("REGIME_FUSION", StringFormat(
      "regime=%d quality=%d confidence=%s valid=%s latest=%I64d age=%d prev=%d "
      "structure=%d direction=%d dscore=%s momentum=%d mstrength=%s mda=%s "
      "vlevel=%d vquality=%d comp=%s exp=%s "
      "sTB=%s sTBe=%s sR=%s sBB=%s sBBe=%s sU=%s "
      "tx=%d candAge=%d pend=%s complete=%s degraded=%d signature=%s",
      (int)r.regime, (int)r.quality, Build05NativeDecimal(r.confidence), Build04DiagnosticBool(r.valid),
      (long)r.latestClosedH1, r.regimeAgeBars, (int)r.previousRegime,
      (int)r.structureState, (int)r.directionState, Build05NativeDecimal(r.directionScore),
      (int)r.momentumState, Build05NativeDecimal(r.momentumStrength),
      Build05NativeDecimal(r.momentumDirectionalAlignment),
      (int)r.volatilityLevel, (int)r.volatilityQuality,
      Build05NativeDecimal(r.compressionEvidence), Build05NativeDecimal(r.expansionEvidence),
      Build05NativeDecimal(r.scoreTrendBull), Build05NativeDecimal(r.scoreTrendBear),
      Build05NativeDecimal(r.scoreRange), Build05NativeDecimal(r.scoreBreakoutBull),
      Build05NativeDecimal(r.scoreBreakoutBear), Build05NativeDecimal(r.scoreUncertain),
      (int)r.transitionReason, r.candidateAgeBars,
      r.pendingCandidateActive ? IntegerToString((int)r.pendingCandidateRegime) : "NONE",
      Build05NativeDecimal(r.evidenceCompleteness), r.degradedDomains,
      Build06DiagnosticSignature(r, cm)));

   if(r.regime != r.previousRegime)
   {
      LogDebug("REGIME_TRANSITION", StringFormat(
         "prev=%d new=%d reason=%d timestamp=%I64d challenger=%s incumbent=%s age=%d",
         (int)r.previousRegime, (int)r.regime, (int)r.transitionReason,
         (long)r.latestClosedH1,
         Build05NativeDecimal(r.challengerConfidence),
         Build05NativeDecimal(r.incumbentConfidence),
         r.regimeAgeBars));
   }
}

#endif
