import re
import pathlib

BASE = pathlib.Path(r"C:\Users\dirga\Documents\EA\AdaptiveSurvivalEA")
MQH_PATH = BASE / "MarketBrain.mqh"
MQ5_PATH = BASE / "AdaptiveSurvivalEA.mq5"
DCOLL_PATH = BASE / "DiagnosticCollector.mqh"

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

def find_fn_body(source, name):
    pattern = r'\b' + re.escape(name) + r'\s*\('
    m = re.search(pattern, source)
    if not m:
        return ""
    start = m.start()
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

    def test_b05_state_explicit_init_before_first_update(self):
        """b05_state must be explicitly initialized before first UpdateH1Brain in OnInit."""
        source = _read(MQ5_PATH)
        on_init = _find_func_body(source, r"int\s+OnInit\s*\(")
        assert "Build05BehaviorStateInit(b05_state)" in on_init or \
               "Build05BehaviorStateInit( b05_state )" in on_init, \
            "b05_state not initialized in OnInit"
        assert "ResetH1BrainInvalid(h1_brain)" in on_init or \
               "ResetH1BrainInvalid( h1_brain )" in on_init, \
            "h1_brain not reset in OnInit"
        idx_init = on_init.find("Build05BehaviorStateInit")
        idx_reset = on_init.find("ResetH1BrainInvalid")
        idx_update = on_init.find("UpdateH1Brain")
        assert         idx_update == -1 or idx_init < idx_update, \
            "b05_state init must come before first UpdateH1Brain"
        assert idx_update == -1 or idx_reset < idx_update, \
            "h1_brain reset must come before first UpdateH1Brain"


class TestB05D2CompleteHash:
    def test_direction_state_in_b05d2_hash(self):
        """B05D2 must encode s.directionState."""
        source = _read(DCOLL_PATH)
        sig = _find_func_body(source, r"string\s+Build05DiagnosticSignature\s*\(")
        assert "s.directionState" in sig, "B05D2 missing s.directionState"

    def test_momentum_state_in_b05d2_hash(self):
        """B05D2 must encode s.momentumState."""
        source = _read(DCOLL_PATH)
        sig = _find_func_body(source, r"string\s+Build05DiagnosticSignature\s*\(")
        assert "s.momentumState" in sig, "B05D2 missing s.momentumState"

    def test_volatility_state_in_b05d2_hash(self):
        """B05D2 must encode s.volatilityState."""
        source = _read(DCOLL_PATH)
        sig = _find_func_body(source, r"string\s+Build05DiagnosticSignature\s*\(")
        assert "s.volLevel" in sig or "s.volatilityState" in sig, "B05D2 missing s.volatilityState"

    def test_vol_quality_ready_in_b05d2_hash(self):
        """B05D2 must encode volQualityReady."""
        source = _read(DCOLL_PATH)
        sig = _find_func_body(source, r"string\s+Build05DiagnosticSignature\s*\(")
        assert "volQualityReady" in sig, "B05D2 missing volQualityReady"

    def test_vol_quality_bucket_in_b05d2_hash(self):
        """B05D2 must encode volQualityBucket."""
        source = _read(DCOLL_PATH)
        sig = _find_func_body(source, r"string\s+Build05DiagnosticSignature\s*\(")
        assert "volQuality" in sig, "B05D2 missing volQualityBucket"

    def test_signature_takes_behavior_state(self):
        """Build05DiagnosticSignature must accept Build05BehaviorState."""
        source = _read(DCOLL_PATH)
        match = re.search(r"string\s+Build05DiagnosticSignature\s*\(([^)]*)\)", source, re.DOTALL)
        assert match, "Build05DiagnosticSignature not found"
        assert "Build05BehaviorState" in match.group(1), "Missing Build05BehaviorState param"

    def test_collect_takes_behavior_state(self):
        """Build05DiagnosticCollect must accept Build05BehaviorState."""
        source = _read(DCOLL_PATH)
        match = re.search(r"void\s+Build05DiagnosticCollect\s*\(([^)]*)\)", source, re.DOTALL)
        assert match, "Build05DiagnosticCollect not found"
        assert "Build05BehaviorState" in match.group(1), "Missing Build05BehaviorState param"


class TestTransitionLogging:
    def test_transitions_emitted_only_from_live_orchestration(self):
        canonical = _read(MQH_PATH)
        live = _find_func_body(_read(MQ5_PATH), r"void\s+UpdateH1Brain\s*\(")
        diagnostics = _read(DCOLL_PATH)
        for event in ("B05_DIRECTION_TRANSITION", "B05_MOMENTUM_TRANSITION",
                      "B05_VOLLEVEL_TRANSITION", "B05_VOLQUALITY_TRANSITION"):
            assert event not in canonical
            assert event in diagnostics
        assert "Build05DiagnosticTransitions" in live
        assert "Build05DiagnosticMode" in live

    def test_transition_struct_exists(self):
        """Build05TransitionState struct must exist."""
        source = _read(DCOLL_PATH)
        assert "struct Build05TransitionState" in source, "Build05TransitionState struct not found"


class TestNativeIndicatorDiagnostics:
    def test_adx_prev_in_native_log(self):
        source = _read(DCOLL_PATH)
        assert "trace.adxPrevious" in source, "adxPrevious not found in BRAIN_UPDATE trace"

    def test_adx_slope_in_native_log(self):
        source = _read(DCOLL_PATH)
        assert "trace.adxSlope" in source, "adxSlope not found in BRAIN_UPDATE trace"


class TestDeterminism:
    def test_b05_state_init_is_deterministic(self):
        """Build05BehaviorStateInit always initializes real persistent fields."""
        source = _read(MQH_PATH)
        for field in ("directionState", "momentumState", "volLevel", "volQuality",
                      "directionDwell", "momentumPersist", "volLevelDwell",
                      "directionChallenger", "directionChallengerDwell", "volQualityReady"):
            assert field in source, f"{field} not in behavior state"

    def test_b05d2_hash_deterministic(self):
        """Build05DiagnosticSignature uses locked ASCII FNV-1a."""
        body = _find_func_body(_read(DCOLL_PATH), r"string\s+Build05DiagnosticSignature\s*\(")
        assert "Build04DiagnosticAscii(out)" in body
        assert "14695981039346656037" in body
        assert "hash ^= (ulong)byteValue" in body
        assert "hash *= 1099511628211" in body

    def test_canonical_function_pure(self):
        """Canonical function must have no side effects beyond state mutation."""
        source = _read(MQH_PATH)
        body = find_fn_body(source, "ProcessBuild05ClosedHistoryPrefix")
        assert "g_" not in body, "Canonical function accesses global variables"

    def test_replay_hydration_restores_state(self):
        """Replay must hydrate b05_state from replay state."""
        source = _read(MQ5_PATH)
        assert "replayB05State" in source, "replayB05State not found"
        assert "b05_state" in source, "b05_state not found in hydration"
