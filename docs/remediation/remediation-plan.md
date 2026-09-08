# dirgaEA remediation plan

Target: marko1kiro/dirgaEA main @ 844987eea6601379fcb534fd9aac8fe98a71c241
Working branch: fix/forensic-audit-remediation

## Scope
Fix all 12 primary findings in Laporan-Audit-dirgaEA.md plus directly related dormant defects needed for safe wiring:
1. lock bootstrap/lease/heartbeat and pending timeout fail-closed;
2. daily risk baseline and lifecycle ledger across restart/rollover;
3. news UNKNOWN/cache/event horizon;
4. directional SELL SL modify validation;
5. volatility raw-ratio classification;
6. normalize final stops before risk sizing and send identical checked values;
7. wire trend/range/breakout with one-candidate arbitration and directional validation;
8. correct break-retest signal bar and recalculate candidate metrics at live entry;
9. historical-only spread baseline and consistent sampling;
10. swing FIFO;
11. persistent initial SL identity/full-close cleanup/protective recovery;
12. update management ordering/provenance/docs/tests where required by the fixes.

## Quality gates
- Add regression tests that fail against old behavior.
- Run full Python suite and focused audit counterexamples.
- Static source integrity and compile-oriented contract checks.
- Native MetaEditor/Strategy Tester cannot be claimed unless GitHub or available environment actually runs them.
- Create draft PR; inspect checks. Do not merge without explicit user request.
