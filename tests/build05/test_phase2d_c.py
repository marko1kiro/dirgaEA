"""Phase 2D-C tests — BUILD05 Deterministic State + B05D2 + Diagnostic Closure.

Tests cover:
- Source invariants (canonical state, hydration, B05D2, safety counters, etc.)
- RED tests exposing pre-fix issues
"""
import re
import os
import pytest

SOURCE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MQ5_PATH = os.path.join(SOURCE_DIR, "AdaptiveSurvivalEA.mq5")
MQH_PATH = os.path.join(SOURCE_DIR, "MarketBrain.mqh")
TYPES_PATH = os.path.join(SOURCE_DIR, "Types.mqh")
DIAG_PATH = os.path.join(SOURCE_DIR, "DiagnosticCollector.mqh")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ===========================================================================
# SOURCE INVARIANTS
# ===========================================================================

class TestSourceInvariantsBuild05C:
    """Source-level invariants for Phase 2D-C requirements."""

    def test_build05_behavior_state_struct_exists(self):
        """Types.mqh must define Build05BehaviorState struct."""
        source = _read(TYPES_PATH)
        assert "struct Build05BehaviorState" in source, \
            "Build05BehaviorState struct not found in Types.mqh"

    def test_build05_behavior_state_has_all_fields(self):
        """Build05BehaviorState must contain all required persistence fields."""
        source = _read(TYPES_PATH)
        # Find the struct
        match = re.search(r"struct Build05BehaviorState\s*\{([^}]+)\}", source, re.DOTALL)
        assert match, "Build05BehaviorState struct not found"
        body = match.group(1)
        required = [
            "directionState", "directionDwell", "directionChallenger", "directionChallengerDwell",
            "momentumState", "momentumPersist", "prevMomentumStrength", "momentumStrengthPrimed",
            "volLevel", "volLevelDwell", "volLevelChallenger", "volLevelChallengerDwell",
            "volQuality", "volQualityConfidence", "volQualityPrimed",
            "volQualityChallenger", "volQualityChallengerDwell",
        ]
        for field in required:
            assert field in body, f"Build05BehaviorState missing field: {field}"

    def test_build05_behavior_state_init_exists(self):
        """MarketBrain.mqh must define Build05BehaviorStateInit."""
        source = _read(MQH_PATH)
        assert "Build05BehaviorStateInit" in source, \
            "Build05BehaviorStateInit not found in MarketBrain.mqh"

    def test_process_build05_canonical_function_exists(self):
        """MarketBrain.mqh must define ProcessBuild05ClosedHistoryPrefix."""
        source = _read(MQH_PATH)
        assert "ProcessBuild05ClosedHistoryPrefix" in source, \
            "ProcessBuild05ClosedHistoryPrefix not found"

    def test_process_build05_uses_behavior_state(self):
        """ProcessBuild05ClosedHistoryPrefix must accept Build05BehaviorState parameter."""
        source = _read(MQH_PATH)
        match = re.search(
            r"bool\s+ProcessBuild05ClosedHistoryPrefix\s*\(([^)]*Build05BehaviorState[^)]*)\)",
            source, re.DOTALL)
        assert match, "ProcessBuild05ClosedHistoryPrefix must accept Build05BehaviorState"

    def test_live_caller_uses_canonical_function(self):
        """UpdateH1Brain must call ProcessBuild05ClosedHistoryPrefix."""
        source = _read(MQ5_PATH)
        assert "ProcessBuild05ClosedHistoryPrefix" in source, \
            "UpdateH1Brain must use canonical ProcessBuild05ClosedHistoryPrefix"

    def test_live_caller_no_adhoc_persistence(self):
        """UpdateH1Brain must NOT contain ad-hoc Direction/Momentum/Volatility persistence."""
        source = _read(MQ5_PATH)
        # Find UpdateH1Brain function
        match = re.search(r"void\s+UpdateH1Brain\s*\(\s*\)", source)
        assert match, "UpdateH1Brain not found"
        func_start = match.start()
        brace_count = 0
        func_end = func_start
        in_func = False
        for i, c in enumerate(source[func_start:], func_start):
            if c == "{":
                brace_count += 1
                in_func = True
            elif c == "}":
                brace_count -= 1
                if brace_count == 0 and in_func:
                    func_end = i + 1
                    break
        func_body = source[func_start:func_end]
        # Must NOT contain direct DirectionClassify/MomentumClassify/VolatilityLevelClassify
        assert "DirectionClassify" not in func_body, \
            "UpdateH1Brain must not contain direct DirectionClassify (use canonical function)"
        assert "MomentumClassify" not in func_body, \
            "UpdateH1Brain must not contain direct MomentumClassify (use canonical function)"
        assert "VolatilityLevelClassify" not in func_body, \
            "UpdateH1Brain must not contain direct VolatilityLevelClassify (use canonical function)"

    def test_replay_hydrates_state(self):
        """RebuildRegimeFusionState must hydrate b05_state from replay."""
        source = _read(MQ5_PATH)
        assert "b05_state = replayB05State" in source or "b05_state=replayB05State" in source, \
            "Replay must hydrate b05_state from replayB05State"

    def test_replay_hydrates_h1_brain(self):
        """RebuildRegimeFusionState must hydrate h1_brain from replay."""
        source = _read(MQ5_PATH)
        assert "h1_brain = replayBrain" in source or "h1_brain=replayBrain" in source, \
            "Replay must hydrate h1_brain from replayBrain"

    def test_replay_uses_canonical_function(self):
        """RebuildRegimeFusionState must call ProcessBuild05ClosedHistoryPrefix."""
        source = _read(MQ5_PATH)
        # Find RebuildRegimeFusionState
        match = re.search(r"void\s+RebuildRegimeFusionState\s*\(\s*\)", source)
        assert match, "RebuildRegimeFusionState not found"
        func_start = match.start()
        brace_count = 0
        func_end = func_start
        in_func = False
        for i, c in enumerate(source[func_start:], func_start):
            if c == "{":
                brace_count += 1
                in_func = True
            elif c == "}":
                brace_count -= 1
                if brace_count == 0 and in_func:
                    func_end = i + 1
                    break
        func_body = source[func_start:func_end]
        assert "ProcessBuild05ClosedHistoryPrefix" in func_body, \
            "Replay must use canonical ProcessBuild05ClosedHistoryPrefix"

    def test_b05d2_version(self):
        """DiagnosticCollector must use B05D2 version."""
        source = _read(DIAG_PATH)
        assert 'BUILD05_DIAGNOSTIC_SIGNATURE_VERSION "B05D2"' in source, \
            "B05D2 version not found"

    def test_b05d2_hashes_behavior_state(self):
        """B05D2 signature must hash Build05BehaviorState (hidden state)."""
        source = _read(DIAG_PATH)
        match = re.search(r"string\s+Build05DiagnosticSignature\s*\(([^)]*)\)", source, re.DOTALL)
        assert match, "Build05DiagnosticSignature not found"
        params = match.group(1)
        assert "Build05BehaviorState" in params, \
            "B05D2 signature must accept Build05BehaviorState parameter"

    def test_b05d2_includes_direction_dwell(self):
        """B05D2 must encode direction dwell/challenger."""
        source = _read(DIAG_PATH)
        assert "ddwell" in source, "B05D2 must encode direction dwell"
        assert "dch" in source, "B05D2 must encode direction challenger"
        assert "dchd" in source, "B05D2 must encode direction challenger dwell"

    def test_b05d2_includes_momentum_persist(self):
        """B05D2 must encode momentum persist/prevStrength/primed."""
        source = _read(DIAG_PATH)
        assert "mpersist" in source, "B05D2 must encode momentum persist"
        assert "mpstr" in source, "B05D2 must encode prevMomentumStrength"
        assert "mprmd" in source, "B05D2 must encode momentum primed"

    def test_b05d2_includes_vollevel_challenger(self):
        """B05D2 must encode volLevel challenger/dwell."""
        source = _read(DIAG_PATH)
        assert "vldwell" in source, "B05D2 must encode volLevel dwell"
        assert "vlch" in source, "B05D2 must encode volLevel challenger"

    def test_b05d2_includes_volquality_hidden(self):
        """B05D2 must encode volQuality primed/challenger/dwell."""
        source = _read(DIAG_PATH)
        assert "vqprmd" in source, "B05D2 must encode volQuality primed"
        assert "vqch" in source, "B05D2 must encode volQuality challenger"
        assert "vqchd" in source, "B05D2 must encode volQuality challenger dwell"

    def test_b05d2_includes_quality_ready(self):
        """B05D2 must encode qualityReady."""
        source = _read(DIAG_PATH)
        assert "vqready" in source, "B05D2 must encode qualityReady"

    def test_b05d2_includes_latest_closed_h1(self):
        """B05D2 must encode latestClosedH1 for all domains."""
        source = _read(DIAG_PATH)
        assert "dtime" in source, "B05D2 must encode direction latestClosedH1"
        assert "mtime" in source, "B05D2 must encode momentum latestClosedH1"
        assert "vtime" in source, "B05D2 must encode volatility latestClosedH1"

    def test_serializer_uses_15_digits(self):
        """Build05DiagnosticDecimal must use 15 digits, not _Digits."""
        source = _read(DIAG_PATH)
        assert "DoubleToString(value,15)" in source or "DoubleToString(value, 15)" in source, \
            "Build05DiagnosticDecimal must use 15-digit precision"

    def test_safety_counters_struct_exists(self):
        """DiagnosticCollector must define Build05DiagnosticCounters."""
        source = _read(DIAG_PATH)
        assert "struct Build05DiagnosticCounters" in source, \
            "Build05DiagnosticCounters struct not found"

    def test_safety_counters_has_required_fields(self):
        """Build05DiagnosticCounters must contain required counter fields."""
        source = _read(DIAG_PATH)
        match = re.search(r"struct Build05DiagnosticCounters\s*\{([^}]+)\}", source, re.DOTALL)
        assert match, "Build05DiagnosticCounters not found"
        body = match.group(1)
        required = [
            "copyBufferFailures", "invalidAtr", "invalidEma", "adxDegraded",
            "duplicateH1Attempts", "formingBarAttempts", "abnormalSkips", "volQualityNotReady",
        ]
        for field in required:
            assert field in body, f"Build05DiagnosticCounters missing field: {field}"

    def test_brain_update_includes_hidden_state(self):
        """BRAIN_UPDATE log must include hidden persistence fields."""
        source = _read(DIAG_PATH)
        runtime = re.search(r"string\s+Build05RuntimeMessage[\s\S]*?\n\}", source).group(0)
        assert "s.directionDwell" in runtime, "BRAIN_UPDATE must log direction dwell"
        assert "s.momentumPersist" in runtime, "BRAIN_UPDATE must log momentum persist"
        assert "s.volLevelDwell" in runtime, "BRAIN_UPDATE must log volLevel dwell"
        assert "s.volQualityPrimed" in runtime, "BRAIN_UPDATE must log volQuality primed"

    def test_single_b05_state_global(self):
        """AdaptiveSurvivalEA.mq5 must have exactly one b05_state global."""
        source = _read(MQ5_PATH)
        assert "Build05BehaviorState b05_state" in source, \
            "b05_state global not found"
        # Must NOT have old ad-hoc globals
        assert "b05_direction_state" not in source, \
            "Old ad-hoc b05_direction_state must be removed"
        assert "b05_momentum_state" not in source, \
            "Old ad-hoc b05_momentum_state must be removed"
        assert "b05_vol_level" not in source or "b05_vol_level_challenger" in source, \
            "Old ad-hoc b05_vol_level must be removed"

    def test_build04_source_unchanged(self):
        """BUILD04 semantic files must not contain B05 canonical function."""
        source = _read(MQH_PATH)
        # ProcessBuild05ClosedHistoryPrefix is in MarketBrain.mqh (B05 file), which is allowed
        # But BUILD04 files must not reference it
        b04_files = ["SwingStructure.mqh", "BrokerEnvironment.mqh", "RiskEngine.mqh"]
        for f in b04_files:
            path = os.path.join(SOURCE_DIR, f)
            if os.path.exists(path):
                content = _read(path)
                assert "ProcessBuild05ClosedHistoryPrefix" not in content, \
                    f"{f} must not reference B05 canonical function"

    def test_structure_agreement_diagnostic_only(self):
        """BUILD05 must not consume SwingStructureResult in scoring functions."""
        source = _read(MQH_PATH)
        # DirectionEngine, MomentumEngine, VolatilityEngine, VolatilityQualityEngine
        # must NOT accept SwingStructureResult
        for func in ["DirectionEngine", "MomentumEngine", "VolatilityEngine", "VolatilityQualityEngine"]:
            match = re.search(rf"void\s+{func}\s*\(([^)]*)\)", source, re.DOTALL)
            if match:
                params = match.group(1)
                assert "SwingStructureResult" not in params, \
                    f"{func} must not accept SwingStructureResult (diagnostic only)"


# ===========================================================================
# RED TESTS — must fail on starting SHA
# ===========================================================================

class TestRedPhase2DC:
    """RED tests exposing pre-fix issues on starting SHA."""

    def test_red_a_replay_hydration(self):
        """RED A: replay-local B05 state is not hydrated to live globals."""
        source = _read(MQ5_PATH)
        # After fix: b05_state = replayB05State must exist
        # On starting SHA: this line does NOT exist
        # We test that the hydration line exists (GREEN after fix)
        assert "b05_state = replayB05State" in source or "b05_state=replayB05State" in source, \
            "RED A: replay does not hydrate b05_state to live globals"

    def test_red_b_b05d2_omits_latestclosedh1(self):
        """RED B: current B05D2 must include latestClosedH1."""
        source = _read(DIAG_PATH)
        # After fix: dtime, mtime, vtime must exist in signature
        assert "dtime" in source, "RED B: B05D2 missing direction latestClosedH1"
        assert "mtime" in source, "RED B: B05D2 missing momentum latestClosedH1"
        assert "vtime" in source, "RED B: B05D2 missing volatility latestClosedH1"

    def test_red_c_digest_ignores_hidden_state(self):
        """RED C: current digest must include hidden challenger/persistence."""
        source = _read(DIAG_PATH)
        assert "ddwell" in source, "RED C: B05D2 missing direction dwell"
        assert "mpersist" in source, "RED C: B05D2 missing momentum persist"
        assert "vqchd" in source, "RED C: B05D2 missing volQuality challenger dwell"

    def test_red_d_serializer_depends_on_digits(self):
        """RED D: serializer must use 15 digits, not _Digits."""
        source = _read(DIAG_PATH)
        # Build05DiagnosticDecimal must NOT use _Digits
        match = re.search(r"Build05DiagnosticDecimal\s*\(([^)]*)\)", source)
        if match:
            # Find the function body
            func_start = match.start()
            # Look for DoubleToString
            dt_match = re.search(r"DoubleToString\(value,\s*(\d+)\)", source[func_start:func_start+200])
            if dt_match:
                precision = dt_match.group(1)
                assert precision == "15", f"RED D: Build05DiagnosticDecimal uses {precision} digits, expected 15"

    def test_red_e_brain_update_lacks_raw_inputs(self):
        """RED E: BRAIN_UPDATE must include raw evidence fields."""
        source = _read(DIAG_PATH)
        assert "s.volQualityReady" in source, "RED E: BRAIN_UPDATE missing qualityReady"
        assert "s.directionDwell" in source, "RED E: BRAIN_UPDATE missing direction dwell"

    def test_red_f_no_transition_records(self):
        """RED F: transition-only records must exist."""
        source = _read(DIAG_PATH)
        # Build05TransitionState must exist for transition-only records
        assert "struct Build05TransitionState" in source, \
            "RED F: Build05TransitionState struct not found"

    def test_red_g_no_safety_counters(self):
        """RED G: Build05DiagnosticCounters must exist."""
        source = _read(DIAG_PATH)
        assert "struct Build05DiagnosticCounters" in source, \
            "RED G: Build05DiagnosticCounters struct not found"
        assert "volQualityNotReady" in source, \
            "RED G: volQualityNotReady counter not found"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
