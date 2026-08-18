#ifndef ADAPTIVE_SURVIVAL_EA_RISK_ENGINE_MQH
#define ADAPTIVE_SURVIVAL_EA_RISK_ENGINE_MQH

#include "Types.mqh"
#include "BrokerEnvironment.mqh"

string RiskRejectReasonToString(const ENUM_RISK_REJECT_REASON reason)
{
   switch(reason)
   {
      case RISK_APPROVED: return "RISK_APPROVED";
      case REJECT_INVALID_REQUEST: return "REJECT_INVALID_REQUEST";
      case REJECT_INVALID_SL: return "REJECT_INVALID_SL";
      case REJECT_ENVIRONMENT: return "REJECT_ENVIRONMENT";
      case REJECT_ACCOUNT_DATA: return "REJECT_ACCOUNT_DATA";
      case REJECT_RISK_HARD_CAP: return "REJECT_RISK_HARD_CAP";
      case REJECT_RISK_CALC: return "REJECT_RISK_CALC";
      case REJECT_MIN_VOLUME_RISK: return "REJECT_MIN_VOLUME_RISK";
      case REJECT_VOLUME_INVALID: return "REJECT_VOLUME_INVALID";
      case REJECT_MARGIN_CALC: return "REJECT_MARGIN_CALC";
      case REJECT_MARGIN: return "REJECT_MARGIN";
   }
   return "REJECT_UNKNOWN";
}

void InitializeRiskResult(RiskResult &result)
{
   ZeroMemory(result);
   result.rejectReason = REJECT_INVALID_REQUEST;
}

bool RejectRisk(RiskResult &result, const ENUM_RISK_REJECT_REASON reason)
{
   result.approved = false;
   result.rejectReason = reason;
   return false;
}

int VolumeDigits(const double volumeStep)
{
   int digits = 0;
   double scaled = volumeStep;
   while(digits < 8 && MathAbs(scaled - MathRound(scaled)) > 1e-9)
   {
      scaled *= 10.0;
      digits++;
   }
   return digits;
}

double NormalizeVolumeDown(const double rawVolume,
                           const double volumeMin,
                           const double volumeStep,
                           const double volumeMax)
{
   if(rawVolume < volumeMin || volumeMin <= 0.0 || volumeStep <= 0.0 || volumeMax < volumeMin)
      return 0.0;

   const double cappedVolume = MathMin(rawVolume, volumeMax);
   const double gridPosition = (cappedVolume - volumeMin) / volumeStep;
   const double epsilon = 1e-9 * MathMax(1.0, MathAbs(gridPosition));
   const double steps = MathFloor(gridPosition + epsilon);
   const double normalized = volumeMin + steps * volumeStep;
   return NormalizeDouble(MathMin(normalized, volumeMax), VolumeDigits(volumeStep));
}

bool CalculateLossMoney(const RiskRequest &request,
                        const double volume,
                        double &lossMoney)
{
   double profit = 0.0;
   ResetLastError();
   if(!OrderCalcProfit(request.orderType, request.symbol, volume,
                       request.entryPrice, request.stopLossPrice, profit))
      return false;

   lossMoney = -profit;
   return MathIsValidNumber(lossMoney) && lossMoney > 0.0;
}

bool CalculateBasicRisk(const RiskRequest &request,
                        BrokerEnvironment &environment,
                        RiskResult &result)
{
   InitializeRiskResult(result);

   if(request.symbol == "" || request.symbol != environment.symbol ||
      (request.orderType != ORDER_TYPE_BUY && request.orderType != ORDER_TYPE_SELL) ||
      !MathIsValidNumber(request.entryPrice) || !MathIsValidNumber(request.stopLossPrice) ||
      !MathIsValidNumber(request.riskPercent) || !MathIsValidNumber(request.hardRiskCapPercent) ||
      !MathIsValidNumber(request.minVolumeTolerancePercent) ||
      !MathIsValidNumber(request.marginReservePercent) ||
      request.entryPrice <= 0.0 || request.stopLossPrice <= 0.0 ||
      request.riskPercent <= 0.0 || request.hardRiskCapPercent <= 0.0 ||
      request.minVolumeTolerancePercent < 0.0 || request.marginReservePercent < 0.0 ||
      request.marginReservePercent >= 100.0)
      return RejectRisk(result, REJECT_INVALID_REQUEST);

   if(request.riskPercent > request.hardRiskCapPercent)
      return RejectRisk(result, REJECT_RISK_HARD_CAP);

   if((request.orderType == ORDER_TYPE_BUY && request.stopLossPrice >= request.entryPrice) ||
      (request.orderType == ORDER_TYPE_SELL && request.stopLossPrice <= request.entryPrice))
      return RejectRisk(result, REJECT_INVALID_SL);

   if(environment.point <= 0.0 || environment.tickSize <= 0.0 ||
      environment.volumeMin <= 0.0 || environment.volumeStep <= 0.0 ||
      environment.volumeMax < environment.volumeMin)
      return RejectRisk(result, REJECT_ENVIRONMENT);

   if(!RefreshAccountSnapshot(environment))
      return RejectRisk(result, REJECT_ACCOUNT_DATA);

   result.equity = environment.equity;
   result.freeMargin = environment.freeMargin;
   result.targetRiskMoney = result.equity * request.riskPercent / 100.0;
   result.referenceVolume = environment.volumeMin;

   if(!CalculateLossMoney(request, result.referenceVolume, result.referenceLossMoney))
      return RejectRisk(result, REJECT_RISK_CALC);

   result.rawVolume = result.targetRiskMoney * result.referenceVolume /
                      result.referenceLossMoney;
   if(!MathIsValidNumber(result.rawVolume) || result.rawVolume <= 0.0)
      return RejectRisk(result, REJECT_RISK_CALC);

   if(result.rawVolume < environment.volumeMin)
   {
      result.minimumVolumeException = true;
      result.normalizedVolume = environment.volumeMin;
      result.allowedRiskPercent = MathMin(request.riskPercent +
                                          request.minVolumeTolerancePercent,
                                          request.hardRiskCapPercent);
   }
   else
   {
      result.minimumVolumeException = false;
      result.volumeCappedAtMax = result.rawVolume > environment.volumeMax;
      result.normalizedVolume = NormalizeVolumeDown(result.rawVolume,
                                                     environment.volumeMin,
                                                     environment.volumeStep,
                                                     environment.volumeMax);
      result.allowedRiskPercent = request.riskPercent;
   }

   if(result.normalizedVolume < environment.volumeMin ||
      result.normalizedVolume > environment.volumeMax)
      return RejectRisk(result, REJECT_VOLUME_INVALID);

   if(!CalculateLossMoney(request, result.normalizedVolume, result.actualRiskMoney))
      return RejectRisk(result, REJECT_RISK_CALC);

   result.actualRiskPercent = result.actualRiskMoney / result.equity * 100.0;
   if(!MathIsValidNumber(result.actualRiskPercent))
      return RejectRisk(result, REJECT_RISK_CALC);

   const double riskEpsilon = 1e-9;
   if(result.actualRiskPercent > request.hardRiskCapPercent + riskEpsilon)
      return RejectRisk(result, REJECT_RISK_HARD_CAP);
   if(result.minimumVolumeException &&
      result.actualRiskPercent > result.allowedRiskPercent + riskEpsilon)
      return RejectRisk(result, REJECT_MIN_VOLUME_RISK);
   if(!result.minimumVolumeException &&
      result.actualRiskMoney > result.targetRiskMoney + 0.01)
      return RejectRisk(result, REJECT_VOLUME_INVALID);

   ResetLastError();
   if(!OrderCalcMargin(request.orderType, request.symbol, result.normalizedVolume,
                       request.entryPrice, result.estimatedMargin) ||
      !MathIsValidNumber(result.estimatedMargin) || result.estimatedMargin < 0.0)
      return RejectRisk(result, REJECT_MARGIN_CALC);

   result.requiredFreeMargin = result.estimatedMargin /
                               (1.0 - request.marginReservePercent / 100.0);
   if(result.requiredFreeMargin > result.freeMargin)
      return RejectRisk(result, REJECT_MARGIN);

   result.approved = true;
   result.rejectReason = RISK_APPROVED;
   return true;
}

void LogRiskDiagnostic(const RiskRequest &request, const RiskResult &result)
{
   LogDebug("RISK_DIAGNOSTIC",
            StringFormat("symbol=%s side=%s entry=%.8f sl=%.8f risk_pct=%.4f hard_cap_pct=%.4f approved=%s reason=%s equity=%.2f target_risk=%.2f reference_volume=%.8f reference_loss=%.2f raw_volume=%.8f normalized_volume=%.8f min_exception=%s max_capped=%s allowed_risk_pct=%.4f actual_risk=%.2f actual_risk_pct=%.6f estimated_margin=%.2f free_margin=%.2f required_free_margin=%.2f risk_definition=price_loss_to_sl_excludes_costs",
                         request.symbol,
                         request.orderType == ORDER_TYPE_BUY ? "BUY" : "SELL",
                         request.entryPrice, request.stopLossPrice,
                         request.riskPercent, request.hardRiskCapPercent,
                         result.approved ? "true" : "false",
                         RiskRejectReasonToString(result.rejectReason), result.equity,
                         result.targetRiskMoney, result.referenceVolume,
                         result.referenceLossMoney, result.rawVolume,
                         result.normalizedVolume,
                         result.minimumVolumeException ? "true" : "false",
                         result.volumeCappedAtMax ? "true" : "false",
                         result.allowedRiskPercent, result.actualRiskMoney,
                         result.actualRiskPercent, result.estimatedMargin,
                         result.freeMargin, result.requiredFreeMargin));
}

#endif
