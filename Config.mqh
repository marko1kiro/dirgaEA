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
input double RiskDiagnosticPercent = 0.50;
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
input double UncertainVeto = 0.55;
input double UncertainExitThreshold = 0.45;
input int UncertainExitDwell = 1;
input double UncertainWeakWinnerThreshold = 0.30;
input int BreakoutMaturationMinBars = 2;
input int BreakoutMaxAgeBars = 6;
input int BreakoutLookbackBars = 4;
input double TieEpsilon = 1e-6;

#endif
