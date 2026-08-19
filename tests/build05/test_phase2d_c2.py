import re
import pathlib

BASE = pathlib.Path(r"C:\Users\dirga\Documents\EA\AdaptiveSurvivalEA")
MQH_PATH = BASE / "MarketBrain.mqh"
MQ5_PATH = BASE / "AdaptiveSurvivalEA.mq5"

def _read(path):
    return path.read_text(encoding="utf-8", errors="ignore")

def _find_func_body(source, pattern):
    m = re.search(pattern, source)
    if not m:
        return ""
    start = m.start()
    # find opening brace
    brace = source.find("{", m.end()-1)
    if brace == -1:
        return ""
    depth = 0
    for i in range(brace, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[brace:i+1]
    return ""

class TestBufferSafety:
    def test_atr_not_indexed_when_not_ready(self):
        """ATR array must not be indexed if atrBufferReady=false."""
        source = _read(MQH_PATH)
        body = _find_func_body(source, r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(")
        assert "BrainValidAt(atr[count - 1])" not in body and \
               "BrainValidAt(atr[count-1])" not in body, \
            "Canonical function still computes atrOk internally"

    def test_ema_not_indexed_when_not_ready(self):
        """EMA arrays must not be indexed if emaBufferReady=false."""
        source = _read(MQH_PATH)
        body = _find_func_body(source, r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(")
        assert "BrainValidAt(emaFast[count - 1])" not in body and \
               "BrainValidAt(emaFast[count-1])" not in body, \
            "Canonical function still computes emaOk internally"

    def test_signature_accepts_three_buffer_flags(self):
        """Canonical function must accept atrBufferReady, emaBufferReady, adxBufferReady."""
        source = _read(MQH_PATH)
        match = re.search(r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(([^)]*)\)", source, re.DOTALL)
        assert match, "ProcessBuild05ClosedHistoryPrefix not found"
        params = match.group(1)
        assert "atrBufferReady" in params, "Missing atrBufferReady parameter"
        assert "emaBufferReady" in params, "Missing emaBufferReady parameter"
        assert "adxBufferReady" in params, "Missing adxBufferReady parameter"

    def test_direction_gated_by_atr_and_ema(self):
        """Direction access must be gated by atrBufferReady && emaBufferReady."""
        source = _read(MQH_PATH)
        body = _find_func_body(source, r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(")
        assert "atrBufferReady && emaBufferReady" in body or \
               "atrBufferReady&&emaBufferReady" in body, \
            "Direction not gated by atrBufferReady && emaBufferReady"

    def test_momentum_gated_by_atr_only(self):
        """Momentum access must be gated by atrBufferReady only."""
        source = _read(MQH_PATH)
        body = _find_func_body(source, r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(")
        assert "if(atrBufferReady)" in body or "if (atrBufferReady)" in body, \
            "Momentum not gated by atrBufferReady"

    def test_volatility_gated_by_atr_only(self):
        """Volatility access must be gated by atrBufferReady only."""
        source = _read(MQH_PATH)
        body = _find_func_body(source, r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(")
        count = body.count("if(atrBufferReady)") + body.count("if (atrBufferReady)")
        assert count >= 2, \
            f"Expected at least 2 atrBufferReady gates (momentum + volatility), found {count}"

    def test_live_caller_passes_three_flags(self):
        """Live caller must pass atrBufferReady, emaBufferReady, adxBufferReady."""
        source = _read(MQ5_PATH)
        assert "atrBufferReady" in source, "Live caller missing atrBufferReady"
        assert "emaBufferReady" in source, "Live caller missing emaBufferReady"
        assert "adxBufferReady" in source, "Live caller missing adxBufferReady"
