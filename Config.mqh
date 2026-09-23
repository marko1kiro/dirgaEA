#ifndef ADAPTIVE_SURVIVAL_EA_CONFIG_MQH
#define ADAPTIVE_SURVIVAL_EA_CONFIG_MQH

input ulong MagicNumber = 26081301;
input bool DebugMode = true;
input int TimerSeconds = 5;
input bool RiskDiagnosticMode = false;
input bool Build04DiagnosticMode = false;
input ENUM_ORDER_TYPE RiskDiagnosticOrderType = ORDER_TYPE_BUY;
input double RiskDiagnosticEntryPrice = 0.0;
input double RiskDiagnosticStopLossPrice = 0.0;
// M-5: live risk per trade (% of equity). Renamed from RiskDiagnosticPercent —
// the old name suggested a diagnostics-only knob, but this value drives LIVE
// position sizing. The old input is kept below as a deprecated alias so
// existing .set files keep working.
input double RiskPercent = 0.50;
// DEPRECATED alias for .set-file compat (M-5). -1.0 = unset (use RiskPercent).
input double RiskDiagnosticPercent = -1.0;
input double HardRiskCapPercent = 0.80;
input double MinVolumeTolerancePercent = 0.05;
input double MarginReservePercent = 5.0;
input int SwingPivotWidth = 3;
input int SwingHistoryBars = 64;
input int SwingLookbackBars = 512;
input double SwingEqualToleranceAtr = 0.15;

// BUILD 05 — H1 Direction / Momentum / Volatility
input bool Build05DiagnosticMode = false;
input int DirectionFastPeriod = 20;
input int DirectionSlowPeriod = 50;
input int MomentumAdxPeriod = 14;
input int VolatilityBaselineBars = 100;

// BUILD 06 — H1 Regime Fusion (classification-only; weights are fixed v1 constants)
input bool Build06DiagnosticMode = false;
input int RegimeDwell = 2;
input double ChallengerGap = 0.10;
// B06 recalibration (Fase 2b evidence: UNCERTAIN 64%, BREAKOUT 30/10,731 bars).
// UncertainVeto 0.55->0.70: benign close-race mass (balanced margin 0.06-0.09,
// weak-winner top1 0.09-0.135) now flows to challenger gap+dwell instead of an
// instant veto, while hard-conflict (1.0) and single-domain degradation (0.75)
// mass still vetoes — precision preserved via ChallengerGap/RegimeDwell.
// UncertainExitThreshold 0.45->0.35: breakout winner mass is structurally capped
// (~0.35 typical per section 4.6 weights: 0.30*recency + small context terms),
// so veto relief alone can never let BREAKOUT exit UNCERTAIN — this companion
// is REQUIRED, not optional. UncertainExitDwell stays 1: threshold does the work.
// ChallengerGap/RegimeDwell unchanged: with veto lifted, benign close-races flow
// to the existing gap+dwell machinery which already protects precision.
input double UncertainVeto = 0.70;
input double UncertainExitThreshold = 0.35;
input int UncertainExitDwell = 1;
input double UncertainWeakWinnerThreshold = 0.30;
input int BreakoutMaturationMinBars = 2;
input int BreakoutMaxAgeBars = 6;
input int BreakoutLookbackBars = 4;
input double TieEpsilon = 1e-6;

// Safety & Risk Guards (F-07)
input double MaxDailyLossPercent = 2.0;
input int MaxConsecutiveLosses = 3;
input double AbsoluteMaxSpreadPoints = 35.0;
input bool NewsGuardRequired = true;

// Position Management (F-01)
input double InitialRiskATRMultiple = 2.0;

// Execution (F-08)
input ulong DeviationPoints = 10;

#endif
