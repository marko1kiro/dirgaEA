#ifndef ADAPTIVE_SURVIVAL_EA_SWING_STRUCTURE_MQH
#define ADAPTIVE_SURVIVAL_EA_SWING_STRUCTURE_MQH

#include "Types.mqh"

bool SwingValid(const double value) { return MathIsValidNumber(value) && value > 0.0; }

void SwingReset(SwingStructureResult &result)
{
   ZeroMemory(result);
   result.state = STRUCTURE_UNKNOWN;
}

bool SwingIsPivot(const MqlRates &rates[], const int index, const int count, const int width, const bool high)
{
   const double value = high ? rates[index].high : rates[index].low;
   for(int offset = 1; offset <= width; offset++)
   {
      const double left = high ? rates[index - offset].high : rates[index - offset].low;
      const double right = high ? rates[index + offset].high : rates[index + offset].low;
      if((high && (value <= left || value <= right)) || (!high && (value >= left || value >= right)))
         return false;
   }
   return true;
}

ENUM_SWING_LABEL SwingLabel(const SwingStructureResult &result, const ENUM_SWING_KIND kind,
                            const double price, const double atr, const double tolerance)
{
   for(int i = result.swingCount - 1; i >= 0; i--)
   {
      const SwingPoint prior = result.swings[i];
      if(prior.kind != kind || prior.significance != SWING_MAJOR)
         continue;
      if(MathAbs(price - prior.price) <= tolerance * atr)
         return kind == SWING_HIGH ? SWING_EH : SWING_EL;
      if(kind == SWING_HIGH)
         return price > prior.price ? SWING_HH : SWING_LH;
      return price > prior.price ? SWING_HL : SWING_LL;
   }
   return SWING_LABEL_NONE;
}

void SwingAdd(SwingStructureResult &result, const MqlRates &bar, const double atr,
              const ENUM_SWING_KIND kind, const ENUM_SWING_SIGNIFICANCE significance,
              const double tolerance, const int history)
{
   if(result.swingCount >= history)
   {
      for(int i = 1; i < history; i++) result.swings[i - 1] = result.swings[i];
      result.swingCount = history - 1;
   }
   const double price = kind == SWING_HIGH ? bar.high : bar.low;
   const ENUM_SWING_LABEL label = significance == SWING_MAJOR ? SwingLabel(result, kind, price, atr, tolerance) : SWING_LABEL_NONE;
   const int index = result.swingCount++;
   result.swings[index].time = bar.time;
   result.swings[index].price = price;
   result.swings[index].atr = atr;
   result.swings[index].kind = kind;
   result.swings[index].significance = significance;
   result.swings[index].label = label;
   result.swings[index].consumed = false;
}

void SwingAddBreak(SwingStructureResult &result, const MqlRates &bar, const bool bullish,
                   const double level, const double atr, const int history)
{
   if(result.breakCount >= history)
   {
      for(int i = 1; i < history; i++) result.breaks[i - 1] = result.breaks[i];
      result.breakCount = history - 1;
   }
   const double range = bar.high - bar.low;
   const double penetration = MathAbs(bar.close - level) / atr;
   const double body = MathAbs(bar.close - bar.open) / range;
   const double directionalClose = bullish ? (bar.close - bar.low) / range : (bar.high - bar.close) / range;
   const int index = result.breakCount++;
   result.breaks[index].time = bar.time;
   result.breaks[index].bullish = bullish;
   result.breaks[index].level = level;
   result.breaks[index].penetrationAtr = penetration;
   result.breaks[index].strong = penetration >= 0.35 && body >= 0.60 && directionalClose >= 0.75;
   result.breaks[index].followThrough = FOLLOW_THROUGH_NONE;
   result.breaks[index].followThroughFinalized = false;
}

void SwingClassifyState(SwingStructureResult &result, const bool diagnostics, Build04DiagnosticTrace &trace)
{
   ENUM_SWING_LABEL high = SWING_LABEL_NONE, low = SWING_LABEL_NONE;
   for(int i = result.swingCount - 1; i >= 0 && (high == SWING_LABEL_NONE || low == SWING_LABEL_NONE); i--)
   {
      if(result.swings[i].significance != SWING_MAJOR) continue;
      if(result.swings[i].kind == SWING_HIGH && high == SWING_LABEL_NONE) high = result.swings[i].label;
      if(result.swings[i].kind == SWING_LOW && low == SWING_LABEL_NONE) low = result.swings[i].label;
   }
   if(high == SWING_EH && low == SWING_EL) result.state = STRUCTURE_RANGE;
   else if(high == SWING_HH && low == SWING_HL) result.state = STRUCTURE_BULLISH_STRONG;
   else if(high == SWING_LH && low == SWING_LL) result.state = STRUCTURE_BEARISH_STRONG;
   else if((high == SWING_HH && (low == SWING_LABEL_NONE || low == SWING_HL)) ||
           (low == SWING_HL && (high == SWING_LABEL_NONE || high == SWING_HH))) result.state = STRUCTURE_BULLISH_WEAK;
   else if((high == SWING_LH && (low == SWING_LABEL_NONE || low == SWING_LL)) ||
           (low == SWING_LL && (high == SWING_LABEL_NONE || high == SWING_LH))) result.state = STRUCTURE_BEARISH_WEAK;
   else if(high != SWING_LABEL_NONE || low != SWING_LABEL_NONE) result.state = STRUCTURE_MIXED;
   else result.state = STRUCTURE_UNKNOWN;
   datetime sequenceTime = 0;
   for(int i = result.swingCount - 1; i >= 0; i--)
      if(result.swings[i].significance == SWING_MAJOR &&
         (result.swings[i].label == high || result.swings[i].label == low))
      {
         sequenceTime = result.swings[i].time;
         break;
      }
   for(int i = result.breakCount - 1; i >= 0; i--)
      if(result.breaks[i].time >= sequenceTime &&
         ((result.state == STRUCTURE_BULLISH_STRONG && !result.breaks[i].bullish) ||
          (result.state == STRUCTURE_BEARISH_STRONG && result.breaks[i].bullish)))
       {
          result.state = result.state == STRUCTURE_BULLISH_STRONG ? STRUCTURE_BULLISH_WEAK : STRUCTURE_BEARISH_WEAK;
          break;
       }
    if(diagnostics)
    {
       trace.stateHighLabel = high;
       trace.stateLowLabel = low;
       trace.stateSequenceTime = sequenceTime;
       trace.stateBosRequired = false;
    }

}


bool ProcessSwingStructure(const MqlRates &rates[], const double &atr[], const int count,
                           const int width, const double equalTolerance, const int history,
                           SwingStructureResult &result, const bool diagnostics, Build04DiagnosticTrace &trace)
{
   SwingReset(result);
   if(diagnostics)
   {
      ZeroMemory(trace);
      trace.width = width;
      trace.copiedRates = count;
      trace.copiedAtr = count;
      trace.startTime = count > 0 ? rates[0].time : 0;
      trace.endTime = count > 0 ? rates[count - 1].time : 0;
      trace.latestClosedTime = trace.endTime;
      trace.bar0Excluded = true;
      trace.immutableInput = true;
   }
    if(count < width * 2 + 3 || width < 1 || history < 1 || history > SWING_STRUCTURE_MAX_HISTORY || !MathIsValidNumber(equalTolerance) || equalTolerance < 0.0)
    {
       if(diagnostics) trace.counters.abnormalSkips++;
       return false;
    }

   for(int i = 0; i < count; i++)
      if(rates[i].time <= 0 || !SwingValid(atr[i]) ||
         !MathIsValidNumber(rates[i].open) || !MathIsValidNumber(rates[i].high) ||
         !MathIsValidNumber(rates[i].low) || !MathIsValidNumber(rates[i].close) ||
         rates[i].open <= 0.0 || rates[i].high <= 0.0 || rates[i].low <= 0.0 || rates[i].close <= 0.0 ||
         rates[i].high < rates[i].low || rates[i].open < rates[i].low || rates[i].open > rates[i].high ||
         rates[i].close < rates[i].low || rates[i].close > rates[i].high ||
          (i > 0 && rates[i].time <= rates[i - 1].time))
       {
          if(diagnostics)
          {
             trace.counters.abnormalSkips++;
             if(!SwingValid(atr[i])) trace.counters.invalidAtr++;
          }
          return false;
       }

   for(int i = width; i < count - width; i++)
   {
if(SwingIsPivot(rates, i, count, width, true))
       {
          double opposite = 0.0;
          for(int j = result.swingCount - 1; j >= 0; j--) if(result.swings[j].kind == SWING_LOW) { opposite = result.swings[j].price; break; }
          const double distance = opposite > 0.0 ? MathAbs(rates[i].high - opposite) / atr[i] : 0.0;
          ENUM_SWING_SIGNIFICANCE significance;
          if(opposite <= 0.0)
             significance = SWING_MINOR;  // B04-R1: no opposite → never MAJOR, MINOR bootstrap
          else if(distance < 0.5)
             significance = SWING_REJECTED;
          else
             significance = distance >= 1.25 ? SWING_MAJOR : SWING_MINOR;
           if(significance != SWING_REJECTED)
           {
              SwingAdd(result, rates[i], atr[i], SWING_HIGH, significance, equalTolerance, history);
               if(diagnostics && trace.pivotCount < SWING_STRUCTURE_MAX_HISTORY)
              {
                 const int diagnosticIndex = trace.pivotCount++;
                 trace.pivots[diagnosticIndex] = result.swings[result.swingCount - 1];
                 trace.pivotConfirmationTimes[diagnosticIndex] = rates[i + width].time;
                 trace.pivotExcursionAtr[diagnosticIndex] = distance;
              }
           }

       }
       if(SwingIsPivot(rates, i, count, width, false))
       {
          double opposite = 0.0;
          for(int j = result.swingCount - 1; j >= 0; j--) if(result.swings[j].kind == SWING_HIGH) { opposite = result.swings[j].price; break; }
          const double distance = opposite > 0.0 ? MathAbs(rates[i].low - opposite) / atr[i] : 0.0;
          ENUM_SWING_SIGNIFICANCE significance;
          if(opposite <= 0.0)
             significance = SWING_MINOR;  // B04-R1: no opposite → never MAJOR, MINOR bootstrap
          else if(distance < 0.5)
             significance = SWING_REJECTED;
          else
             significance = distance >= 1.25 ? SWING_MAJOR : SWING_MINOR;
           if(significance != SWING_REJECTED)
           {
              SwingAdd(result, rates[i], atr[i], SWING_LOW, significance, equalTolerance, history);
               if(diagnostics && trace.pivotCount < SWING_STRUCTURE_MAX_HISTORY)
              {
                 const int diagnosticIndex = trace.pivotCount++;
                 trace.pivots[diagnosticIndex] = result.swings[result.swingCount - 1];
                 trace.pivotConfirmationTimes[diagnosticIndex] = rates[i + width].time;
                 trace.pivotExcursionAtr[diagnosticIndex] = distance;
              }
           }

       }
       const double range = rates[i].high - rates[i].low;
       if(range <= 0.0)
       {
           if(diagnostics) trace.counters.zeroRange++;

          continue;
       }

// B04-R2: only the LATEST active (unconsumed) MAJOR level per kind may break.
       for(int kind = 0; kind <= 1; kind++)
       {
          int active = -1;
          for(int j = result.swingCount - 1; j >= 0; j--)
             if(result.swings[j].kind == kind && result.swings[j].significance == SWING_MAJOR &&
                !result.swings[j].consumed && result.swings[j].time < rates[i].time)
             {
                active = j;
                break;
             }
          if(active < 0) continue;
          const bool bullish = result.swings[active].kind == SWING_HIGH;
          const bool broken = bullish ? rates[i].close >= result.swings[active].price + 0.10 * atr[i] : rates[i].close <= result.swings[active].price - 0.10 * atr[i];
          if(broken)
          {
              SwingAddBreak(result, rates[i], bullish, result.swings[active].price, atr[i], history);
               if(diagnostics && trace.bosCount < SWING_STRUCTURE_MAX_HISTORY)
              {
                 const int diagnosticIndex = trace.bosCount++;
                 trace.bos[diagnosticIndex] = result.breaks[result.breakCount - 1];
                 trace.bosSourceTimes[diagnosticIndex] = result.swings[active].time;
                 trace.bosBodies[diagnosticIndex] = MathAbs(rates[i].close - rates[i].open) / range;
                 trace.bosRanges[diagnosticIndex] = range;
                 trace.bosDirectionalCloses[diagnosticIndex] = bullish ? (rates[i].close - rates[i].low) / range : (rates[i].high - rates[i].close) / range;
              }
              result.swings[active].consumed = true;

             continue;
          }
          const bool sweptWick = bullish ? rates[i].high > result.swings[active].price : rates[i].low < result.swings[active].price;
          const bool inside = bullish ? rates[i].close <= result.swings[active].price : rates[i].close >= result.swings[active].price;
          const bool sweep = sweptWick && inside && MathAbs(rates[i].close - result.swings[active].price) <= equalTolerance * atr[i];
            if(diagnostics && sweep && trace.sweepCount < SWING_STRUCTURE_MAX_HISTORY)
           {
              const int diagnosticIndex = trace.sweepCount++;
              trace.sweeps[diagnosticIndex] = result.swings[active];
              trace.sweepTimes[diagnosticIndex] = rates[i].time;
              trace.sweepWicks[diagnosticIndex] = bullish ? rates[i].high : rates[i].low;
              trace.sweepCloses[diagnosticIndex] = rates[i].close;
           }
           result.sweep = result.sweep || sweep;

       }
   }
   for(int b = 0; b < result.breakCount; b++)
   {
      int index = -1;
      for(int i = 0; i < count; i++) if(rates[i].time == result.breaks[b].time) { index = i; break; }
       if(result.breaks[b].followThroughFinalized || index < 0 || index + 2 >= count) continue;
       const double close = rates[index + 2].close;
       if((result.breaks[b].bullish && close < result.breaks[b].level) || (!result.breaks[b].bullish && close > result.breaks[b].level)) result.breaks[b].followThrough = FOLLOW_THROUGH_FAILED;
       else if((result.breaks[b].bullish && close > result.breaks[b].level + 0.35 * atr[index + 2]) || (!result.breaks[b].bullish && close < result.breaks[b].level - 0.35 * atr[index + 2])) result.breaks[b].followThrough = FOLLOW_THROUGH_STRONG;
       else result.breaks[b].followThrough = FOLLOW_THROUGH_VALID;
        result.breaks[b].followThroughFinalized = true;
        if(diagnostics && trace.followThroughCount < SWING_STRUCTURE_MAX_HISTORY)
        {
           const int diagnosticIndex = trace.followThroughCount++;
           trace.followThrough[diagnosticIndex] = result.breaks[b];
           trace.followThroughWindowEnds[diagnosticIndex] = rates[index + 2].time;
        }
 

   }
   result.latestTime = rates[count - 1].time;
    SwingClassifyState(result, diagnostics, trace);

    result.valid = true;
    return true;

}

void PreserveSwingStructureFollowThrough(const SwingStructureResult &previous, SwingStructureResult &current)
{
   for(int i = 0; i < current.breakCount; i++)
      for(int j = 0; j < previous.breakCount; j++)
         if(previous.breaks[j].time == current.breaks[i].time &&
            previous.breaks[j].bullish == current.breaks[i].bullish &&
            previous.breaks[j].level == current.breaks[i].level &&
            previous.breaks[j].followThroughFinalized)
         {
            current.breaks[i].followThrough = previous.breaks[j].followThrough;
            current.breaks[i].followThroughFinalized = true;
            break;
         }
}

#endif
