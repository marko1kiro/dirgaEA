import re
import pathlib

BASE = pathlib.Path(r"C:\Users\dirga\Documents\EA\AdaptiveSurvivalEA")
MARKET_BRAIN = BASE / "MarketBrain.mqh"
EA = BASE / "AdaptiveSurvivalEA.mq5"
DIAG = BASE / "DiagnosticCollector.mqh"

def read(p): return p.read_text(encoding="utf-8", errors="ignore")

def find_fn_body(text, name):
    m = re.search(r'\b' + re.escape(name) + r'\s*\([^)]*\)\s*\{', text)
    if not m: return ""
    start = m.end()-1
    depth=0
    for i in range(start, len(text)):
        if text[i]=='{': depth+=1
        elif text[i]=='}':
            depth-=1
            if depth==0: return text[start:i+1]
    return ""

def test_01_atr_partial_copybuffer_unsafe():
    src = read(MARKET_BRAIN)
    body = find_fn_body(src, "ProcessBuild05ClosedHistoryPrefix")
    assert "bool ProcessBuild05ClosedHistoryPrefix" in src
    has_atr_ready_param = re.search(r'ProcessBuild05ClosedHistoryPrefix\s*\([^)]*atrBufferReady', src)
    assert has_atr_ready_param is not None, "atrBufferReady param missing – ATR partial CopyBuffer unsafe"
    # Ensure internal unsafe indexing is gone
    assert "const bool atrOk = BrainValidAt(atr[count - 1]);" not in body

def test_02_ema_partial_copybuffer_unsafe():
    src = read(MARKET_BRAIN)
    body = find_fn_body(src, "ProcessBuild05ClosedHistoryPrefix")
    has_ema_ready_param = re.search(r'ProcessBuild05ClosedHistoryPrefix\s*\([^)]*emaBufferReady', src)
    assert has_ema_ready_param is not None, "emaBufferReady param missing – EMA partial CopyBuffer unsafe"
    assert "const bool emaOk = BrainValidAt(emaFast[count - 1]) && BrainValidAt(emaSlow[count - 1]);" not in body

def test_03_b05_state_not_explicitly_initialized():
    src = read(EA)
    init_pos = src.find("int OnInit()")
    oninit = src[init_pos: init_pos+4000]
    first_update = oninit.find("UpdateH1Brain()")
    first_init = oninit.find("Build05BehaviorStateInit(b05_state)")
    assert first_init != -1 and first_init < first_update, "b05_state not explicitly initialized before first UpdateH1Brain"

def test_04_b05d2_hidden_committed_state_collision():
    src = read(DIAG)
    sig = find_fn_body(src, "Build05DiagnosticSignature")
    assert "s.directionState" in sig, "B05D2 does not encode hidden s.directionState"

def test_05_qualityReady_timestamp_inference():
    src = read(DIAG)
    sig = find_fn_body(src, "Build05DiagnosticSignature")
    collect = find_fn_body(src, "Build05DiagnosticCollect")
    # Should use BrainVolQualityReady with actual count, not timestamp inference
    # Check no timestamp inference pattern
    assert "latestClosedH1 != 0" not in sig, "qualityReady derived from timestamp"
    assert "BrainVolQualityReady(count)" in sig or "BrainVolQualityReady(" in collect

def test_06_missing_raw_diagnostic_trace():
    src = read(DIAG)
    assert "struct Build05RawTrace" in src, "Missing Build05RawTrace struct"

def test_07_missing_transition_emission():
    live = find_fn_body(read(EA), "UpdateH1Brain")
    diagnostics = read(DIAG)
    assert "Build05DiagnosticMode" in live
    assert "Build05DiagnosticTransitions" in live
    assert "B05_DIRECTION_TRANSITION" in diagnostics, "Missing live B05_DIRECTION_TRANSITION emission"

def test_08_safety_counters_not_wired():
    src = read(MARKET_BRAIN)
    body = find_fn_body(src, "ProcessBuild05ClosedHistoryPrefix")
    assert "copyBufferFailures" in body, "Safety counters not wired to ProcessBuild05ClosedHistoryPrefix"
