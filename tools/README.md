# Build & Deploy

Official build flow (repo must be a git checkout):

```
.\tools\write_build_info.ps1      # regenerates mql5/include/BuildInfo.mqh (BUILD_SHA macro)
compile_mql5(...)                  # compile AdaptiveSurvivalEA.mq5
```

Deploy flow — copy the vendored includes into the terminal Include dir before compiling:

```
Copy-Item mql5/include/*.mqh -> <Terminal>\MQL5\Include\
```

Why BuildInfo is generated: `BUILD_SHA` is derived from `git rev-parse --short HEAD`
so each build is reproducible from its exact commit. The file is machine-generated,
so it is gitignored (`mql5/include/BuildInfo.mqh`) and never committed. The two
`.mqh` includes (`EA_StatusReporter.mqh`, `EA_CalendarWriter.mqh`) ARE committed —
they are the canonical repo sources, byte-identical to what the coordinator ships.
