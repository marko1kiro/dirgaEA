# Phase 2D-A3 BUILD05 — Persistence State-Machine Repair

**Date**: 2026-08-20
**Commit**: pending (Commit A = source + tests)
**EX5 SHA256**: `2DDDDADC77668F0CF4D9F505098F4BA6040118A50C8707970294681CA5E58A52`

## Scope
- Momentum persistence: internal counter in `MomentumClassify`, `int &persist` by reference
- Direction challenger dwell: escalation candidate identity + `challengerDwell` counter
- Volatility Level challenger dwell: same pattern as direction
- Invalid domain freeze: invalid domains do not advance persistence state

## Test Results
```
BUILD05: 55 passed in 0.12s
BUILD04: 13 passed in 0.04s
```

## Compile
```
Result: 0 errors, 0 warnings, 1717 ms elapsed
```

## Files Changed
### MQL5 Source
- `MarketBrain.mqh`: `MomentumClassify` (persist by ref), `DirectionClassify` (+challenger), `VolatilityLevelClassify` (+challenger)
- `AdaptiveSurvivalEA.mq5`: Caller with validity guards + replay section updated for 7-param calls

### Python References
- `reference_momentum.py`: `momentum_enum` with list-based `persist`
- `reference_direction.py`: `direction_enum` returns 4-tuple `(state, dwell, challenger, challenger_dwell)`
- `reference_volatility.py`: `volatility_level_enum` returns 4-tuple `(state, dwell, challenger, challenger_dwell)`

### Test Files
- `test_persistence_state_machine.py`: 5 momentum persistence state-machine tests
- `test_direction_challenger.py`: 3 direction challenger dwell tests
- `test_vollevel_challenger.py`: 3 volatility level challenger dwell tests
- `test_invalid_persistence_freeze.py`: 3 invalid persistence freeze tests

### Existing Tests Updated
- `test_direction.py`: adapted to 4-tuple return format
- `test_volatility.py`: adapted to 4-tuple return format + corrected expectations
