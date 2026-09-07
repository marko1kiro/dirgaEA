# BUILD 09 — Quality Gate & Candidate Scoring Design Spec

**Status:** DESIGN (Approved by user).
**Scope:** Evaluates `TradeCandidate` instances emitted from BUILD 07, computes a deterministic 0–100 Quality Score, and decides whether a candidate is approved for execution.
**Threshold:** Quality Score `>= 70.0` required for approval.

---

## 1. Quality Gate Scoring Model (0–100 points)

1. **Reward-to-Risk Ratio (35 pts max):**
   - `RR >= 2.0`: 35 pts
   - `1.5 <= RR < 2.0`: 25 pts
   - `1.0 <= RR < 1.5`: 15 pts
   - `RR < 1.0`: 0 pts (Hard disqualification or low score)

2. **H1 Regime Quality & Confidence (30 pts max):**
   - `RegimeQuality == STRONG` & `Confidence >= 0.80`: 30 pts
   - `RegimeQuality == NORMAL` & `Confidence >= 0.60`: 20 pts
   - `RegimeQuality == WEAK` or low confidence: 5 pts

3. **Extension & Displacement Health (20 pts max):**
   - Pullback / Setup not over-extended (`extensionAtr <= 1.8`): 20 pts
   - Moderately extended (`1.8 < extensionAtr <= 2.2`): 10 pts
   - Near boundary (`extensionAtr > 2.2`): 0 pts

4. **Spread & Market Friction (15 pts max):**
   - Spread `<= 0.05 * StopDistance`: 15 pts
   - Spread `<= 0.10 * StopDistance`: 10 pts
   - Spread `> 0.10 * StopDistance`: 0 pts

---

## 2. Hard Veto Filters

A candidate is immediately rejected (Score = 0) if:
- `TradeCandidate.valid == false`
- `StopDistance <= 0` or invalid SL geometry
- Spread exceeds hard maximum tolerance (`> 0.25 * StopDistance`)
- H1 Regime is invalid or not trend.

---

## 3. Data Structures

```mql5
struct QualityGateResult
{
   bool   approved;
   double totalScore;         // 0 - 100
   double scoreRewardRisk;    // 0 - 35
   double scoreRegime;        // 0 - 30
   double scoreExtension;     // 0 - 20
   double scoreSpread;        // 0 - 15
   string rejectReason;
};
```
