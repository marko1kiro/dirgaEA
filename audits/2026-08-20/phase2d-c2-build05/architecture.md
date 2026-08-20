Phase 2D-C2 BUILD05 architecture

- AdaptiveSurvivalEA.mq5 owns lifecycle and closed-H1 update orchestration.
- MarketBrain.mqh owns canonical BUILD05 direction, momentum, volatility, persistence, replay, readiness, and safety-counter logic.
- DiagnosticCollector.mqh owns deterministic signatures, raw traces, transitions, and native indicator diagnostics.
- Config.mqh and Types.mqh define fixed policy and data contracts; Logger.mqh emits records.
- BUILD04 swing behavior remains covered by its regression suite.
