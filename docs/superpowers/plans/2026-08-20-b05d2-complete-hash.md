# B05D2 Complete Hash + volQualityReady Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete B05D2 diagnostic hash to include hidden committed state and volQualityReady, removing timestamp inference.

**Architecture:** Modify Types.mqh, MarketBrain.mqh, DiagnosticCollector.mqh, AdaptiveSurvivalEA.mq5 to propagate volQualityReady and include committed enums in B05D2 hash.

**Tech Stack:** MQL5, Python pytest

---

### Task 1: Read files

**Files:**
- Modify: `C:\Users\dirga\Documents\EA\AdaptiveSurvivalEA\Types.mqh`
- Modify: `C:\Users\dirga\Documents\EA\AdaptiveSurvivalEA\MarketBrain.mqh`
- Modify: `C:\Users\dirga\Documents\EA\AdaptiveSurvivalEA\DiagnosticCollector.mqh`
- Modify: `C:\Users\dirga\Documents\EA\AdaptiveSurvivalEA\AdaptiveSurvivalEA.mq5`

- [ ] **Step 1: Read all 4 files**
Run: already done via read tool.

- [ ] **Step 2: Confirm current signatures**
Verify Build05DiagnosticSignature takes 1 param, Build05DiagnosticCollect takes 1 param.

### Task 2: Add volQualityReady to Types.mqh

**Files:**
- Modify: `C:\Users\dirga\Documents\EA\AdaptiveSurvivalEA\Types.mqh:170-196`

- [ ] **Step 1: Add field**
Edit file to add `bool volQualityReady;` after `bool isValid`? Actually after barCount? Task says after bool isValid or after int barCount. Current struct Build05BehaviorState has no isValid/barCount. Wait task says after bool isValid (or after int barCount). Might be different struct. Let's inspect. Types.mqh Build05BehaviorState currently has directionState, directionDwell, directionChallenger, directionChallengerDwell, momentumState, momentumPersist, prevMomentumStrength, momentumStrengthPrimed, volLevel, volLevelDwell, volLevelChallenger, volLevelChallengerDwell, volQuality, volQualityConfidence, volQualityPrimed, volQualityChallenger, volQualityChallengerDwell. No isValid/barCount. Maybe task description generic. Add volQualityReady field to struct.

Add:
```
bool volQualityReady;
```

- [ ] **Step 2: Verify addition**
Grep for volQualityReady.

### Task 3: Init volQualityReady

**Files:**
- Modify: `C:\Users\dirga\Documents\EA\AdaptiveSurvivalEA\MarketBrain.mqh:98-120`

- [ ] **Step 1: Update Build05BehaviorStateInit**
Set `s.volQualityReady = false;`

- [ ] **Step 2: Update ProcessBuild05ClosedHistoryPrefix**
After direction/momentum/volatility blocks, before return, add:
```
state.volQualityReady = BrainVolQualityReady(count);
state.isValid = true;
```
Note: state.isValid may not exist. Check struct. Actually struct has no isValid. Maybe task expects different struct. Possibly Build05BehaviorState should have isValid and barCount? Hmm.

Let's inspect task description: Add volQualityReady field to Build05BehaviorState in Types.mqh after bool isValid (or after int barCount). Maybe current struct missing those fields? Could be outdated. Let's search for isValid in Types.mqh.
