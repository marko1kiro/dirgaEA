#ifndef ADAPTIVE_SURVIVAL_EA_TYPES_MQH
#define ADAPTIVE_SURVIVAL_EA_TYPES_MQH

enum ENUM_EXECUTION_STATE
{
   IDLE,
   ORDER_PENDING,
   POSITION_CONFIRMED
};

enum ENUM_RISK_REJECT_REASON
{
   RISK_APPROVED,
   REJECT_INVALID_REQUEST,
   REJECT_INVALID_SL,
   REJECT_ENVIRONMENT,
   REJECT_ACCOUNT_DATA,
   REJECT_RISK_HARD_CAP,
   REJECT_RISK_CALC,
   REJECT_MIN_VOLUME_RISK,
   REJECT_VOLUME_INVALID,
   REJECT_MARGIN_CALC,
   REJECT_MARGIN
};

#define SWING_STRUCTURE_MAX_HISTORY 512

enum ENUM_SWING_KIND { SWING_HIGH, SWING_LOW };
enum ENUM_SWING_SIGNIFICANCE { SWING_REJECTED, SWING_MINOR, SWING_MAJOR };
enum ENUM_SWING_LABEL { SWING_LABEL_NONE, SWING_HH, SWING_LH, SWING_EH, SWING_HL, SWING_LL, SWING_EL };
enum ENUM_STRUCTURE_FOLLOW_THROUGH { FOLLOW_THROUGH_NONE, FOLLOW_THROUGH_VALID, FOLLOW_THROUGH_STRONG, FOLLOW_THROUGH_FAILED };
enum ENUM_STRUCTURE_STATE { STRUCTURE_UNKNOWN, STRUCTURE_BULLISH_STRONG, STRUCTURE_BEARISH_STRONG, STRUCTURE_RANGE, STRUCTURE_MIXED, STRUCTURE_BULLISH_WEAK, STRUCTURE_BEARISH_WEAK };

struct SwingPoint
{
   datetime time;
   double price;
   double atr;
   ENUM_SWING_KIND kind;
   ENUM_SWING_SIGNIFICANCE significance;
   ENUM_SWING_LABEL label;
   bool consumed;
};

struct StructureBreak
{
   datetime time;
   bool bullish;
   double level;
   double penetrationAtr;
   bool strong;
   ENUM_STRUCTURE_FOLLOW_THROUGH followThrough;
   bool followThroughFinalized;
};

struct SwingStructureResult
{
   SwingPoint swings[SWING_STRUCTURE_MAX_HISTORY];
   int swingCount;
   StructureBreak breaks[SWING_STRUCTURE_MAX_HISTORY];
   int breakCount;
   ENUM_STRUCTURE_STATE state;
   bool sweep;
   bool valid;
   datetime latestTime;
};

struct Build04DiagnosticCounters
{
   int duplicateH1Attempts;
   int duplicateEventsRejected;
   int formingBarAttempts;
   int invalidAtr;
   int copyBufferFailures;
   int zeroRange;
   int abnormalSkips;
};

struct Build04DiagnosticTrace
{
   string symbol;
   int requestedBars;
   int copiedRates;
   int copiedAtr;
   int atrError;
   datetime startTime;
   datetime endTime;
   datetime latestClosedTime;
   int width;
   bool bar0Excluded;
   bool immutableInput;
   SwingPoint pivots[SWING_STRUCTURE_MAX_HISTORY];
   datetime pivotConfirmationTimes[SWING_STRUCTURE_MAX_HISTORY];
   double pivotExcursionAtr[SWING_STRUCTURE_MAX_HISTORY];
   int pivotCount;
   StructureBreak bos[SWING_STRUCTURE_MAX_HISTORY];
   datetime bosSourceTimes[SWING_STRUCTURE_MAX_HISTORY];
   double bosBodies[SWING_STRUCTURE_MAX_HISTORY];
   double bosRanges[SWING_STRUCTURE_MAX_HISTORY];
   double bosDirectionalCloses[SWING_STRUCTURE_MAX_HISTORY];
   int bosCount;
   SwingPoint sweeps[SWING_STRUCTURE_MAX_HISTORY];
   datetime sweepTimes[SWING_STRUCTURE_MAX_HISTORY];
   double sweepWicks[SWING_STRUCTURE_MAX_HISTORY];
   double sweepCloses[SWING_STRUCTURE_MAX_HISTORY];
   int sweepCount;
   StructureBreak followThrough[SWING_STRUCTURE_MAX_HISTORY];
   datetime followThroughWindowEnds[SWING_STRUCTURE_MAX_HISTORY];
   int followThroughCount;
   ENUM_SWING_LABEL stateHighLabel;
   ENUM_SWING_LABEL stateLowLabel;
   datetime stateSequenceTime;
   bool stateBosRequired;
   Build04DiagnosticCounters counters;
};

enum ENUM_DIRECTION_STATE { DIRECTION_STRONG_BEAR, DIRECTION_BEAR, DIRECTION_NEUTRAL, DIRECTION_BULL, DIRECTION_STRONG_BULL };
enum ENUM_MOMENTUM_STATE { MOMENTUM_EXPANDING, MOMENTUM_STRONG, MOMENTUM_NORMAL, MOMENTUM_WEAK, MOMENTUM_DECAYING };
enum ENUM_VOLATILITY_LEVEL { VOL_LOW, VOL_NORMAL, VOL_HIGH, VOL_EXTREME };
enum ENUM_VOLATILITY_QUALITY { VOLQ_HEALTHY, VOLQ_COMPRESSED, VOLQ_EXPANDING, VOLQ_CHAOTIC, VOLQ_SHOCK };

struct DirectionResult
{
   ENUM_DIRECTION_STATE state;
   double score;              // signed [-1, +1]
   bool valid;
   datetime latestClosedH1;
};

struct MomentumResult
{
   ENUM_MOMENTUM_STATE state;
   double strengthScore;      // [0, 1]
   double strengthDelta;      // change vs prior closed H1
   double strengthSlope;      // short-lookback slope
   double directionalAlignment;// [-1, +1] diagnostic-only
   bool valid;
   bool helperDegraded;       // true when ADX unavailable
   datetime latestClosedH1;
};

struct VolatilityResult
{
   ENUM_VOLATILITY_LEVEL level;
   ENUM_VOLATILITY_QUALITY quality;
   double levelScore;         // [0, 1]
   double qualityConfidence;  // [0, 1]
   double compressionScore;   // [0, 1]
   double expansionScore;     // [0, 1]
   double chaosScore;         // [0, 1]
   double shockScore;         // [0, 1]
   double healthyScore;       // [0, 1]
   bool valid;
   datetime latestClosedH1;
};

struct H1BrainResult
{
   DirectionResult direction;
   MomentumResult momentum;
   VolatilityResult volatility;
};

struct RiskRequest
{
   string symbol;
   ENUM_ORDER_TYPE orderType;
   double entryPrice;
   double stopLossPrice;
   double riskPercent;
   double hardRiskCapPercent;
   double minVolumeTolerancePercent;
   double marginReservePercent;
};

struct RiskResult
{
   bool approved;
   ENUM_RISK_REJECT_REASON rejectReason;
   double equity;
   double targetRiskMoney;
   double referenceVolume;
   double referenceLossMoney;
   double rawVolume;
   double normalizedVolume;
   bool minimumVolumeException;
   bool volumeCappedAtMax;
   double allowedRiskPercent;
   double actualRiskMoney;
   double actualRiskPercent;
   double estimatedMargin;
   double freeMargin;
   double requiredFreeMargin;
};

// ---------------------------------------------------------------------------
// BUILD 06 — H1 Regime Fusion (classification-only)
// ---------------------------------------------------------------------------

// Order matches the Python reference (reference_fusion.py) for signature parity.
enum ENUM_REGIME_STATE
{
   REGIME_TREND_BULL,
   REGIME_TREND_BEAR,
   REGIME_RANGE,
   REGIME_BREAKOUT_BULL,
   REGIME_BREAKOUT_BEAR,
   REGIME_UNCERTAIN
};

enum ENUM_REGIME_QUALITY
{
   REGIME_QUALITY_WEAK,
   REGIME_QUALITY_NORMAL,
   REGIME_QUALITY_STRONG
};

enum ENUM_REGIME_TRANSITION_REASON
{
   REGIME_TRANSITION_NONE,
   REGIME_TRANSITION_INIT,
   REGIME_TRANSITION_OVERRIDE,
   REGIME_TRANSITION_CHALLENGE_WIN,
   REGIME_TRANSITION_MATURATION,
   REGIME_TRANSITION_FAILED_BREAKOUT,
   REGIME_TRANSITION_DECAY,
   REGIME_TRANSITION_DEGRADED,
   REGIME_TRANSITION_RESET
};

#define REGIME_DEGRADED_NONE       0
#define REGIME_DEGRADED_STRUCTURE  (1<<0)
#define REGIME_DEGRADED_DIRECTION  (1<<1)
#define REGIME_DEGRADED_MOMENTUM   (1<<2)
#define REGIME_DEGRADED_VOLATILITY (1<<3)

struct RegimeResult
{
   // official downstream contract
   ENUM_REGIME_STATE      regime;
   ENUM_REGIME_QUALITY    quality;
   double                 confidence;             // [0,1]
   bool                   valid;                  // false => critical-input failure (regime UNCERTAIN)

   // temporal bookkeeping
   datetime               latestClosedH1;         // exact aligned timestamp
   int                    regimeAgeBars;          // bars since incumbent last changed (1-based)
   ENUM_REGIME_STATE      previousRegime;

   // upstream FINAL evidence snapshot (read-only mirrors)
   ENUM_STRUCTURE_STATE   structureState;
   ENUM_DIRECTION_STATE   directionState;
   double                 directionScore;         // signed [-1,+1]
   ENUM_MOMENTUM_STATE    momentumState;
   double                 momentumStrength;       // [0,1]
   double                 momentumDirectionalAlignment; // diagnostic-only mirror
   ENUM_VOLATILITY_LEVEL  volatilityLevel;
   ENUM_VOLATILITY_QUALITY volatilityQuality;
   double                 compressionEvidence;    // [0,1] final B05 compression evidence
   double                 expansionEvidence;      // [0,1] final B05 expansion evidence

   // fusion candidate scores (diagnostic-only, deterministic)
   double                 scoreTrendBull;
   double                 scoreTrendBear;
   double                 scoreRange;
   double                 scoreBreakoutBull;
   double                 scoreBreakoutBear;
   double                 scoreUncertain;         // derived conflict/uncertainty mass

   // hysteresis observables
   ENUM_REGIME_TRANSITION_REASON transitionReason;
   ENUM_REGIME_STATE      pendingCandidateRegime; // explicit challenger identity
   bool                   pendingCandidateActive; // false => no pending challenger (Python None)
   int                    candidateAgeBars;       // dwell of the current pending candidate (1-based)
   double                 challengerConfidence;   // challenger candidate score (this bar)
   double                 incumbentConfidence;    // incumbent candidate score RECOMPUTED this bar

   // completeness / degradation
   double                 evidenceCompleteness;   // [0,1]
   int                    degradedDomains;        // bitmask (REGIME_DEGRADED_*)
};

#endif
