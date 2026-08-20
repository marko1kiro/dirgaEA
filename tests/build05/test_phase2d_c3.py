import copy
import dataclasses
import pathlib
import re

import reference_build05
from reference_build05 import BehaviorState, fixture, process_prefix, signature

BASE = pathlib.Path(__file__).resolve().parents[2]
BRAIN = BASE / "MarketBrain.mqh"
EA = BASE / "AdaptiveSurvivalEA.mq5"
DIAG = BASE / "DiagnosticCollector.mqh"


def masked(source):
    source = re.sub(r"//[^\n]*|/\*.*?\*/|\"(?:\\.|[^\"])*\"", lambda m: "\n" * m.group().count("\n") + " " * (len(m.group()) - m.group().count("\n")), source, flags=re.S)
    return source


def scope(source, pattern, opening="{"):
    clean = masked(source)
    match = re.search(pattern, clean, re.S)
    assert match, pattern
    start = clean.find(opening, match.end())
    pairs = {"{": "}", "(": ")"}
    depth = 0
    for i in range(start, len(clean)):
        if clean[i] == opening:
            depth += 1
        elif clean[i] == pairs[opening]:
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
    raise AssertionError("unbalanced")


def function(source, name):
    return scope(source, rf"\b(?:bool|void|string|double|int)\s+{name}\s*\(")


def calls(source, name):
    clean = masked(source)
    return [scope(source[m.start():], rf"\b{name}\s*", "(") for m in re.finditer(rf"\b{name}\s*\(", clean)]


def argument_count(call):
    clean = masked(call)[1:-1]
    depth = commas = 0
    for char in clean:
        if char in "([{": depth += 1
        elif char in ")]}": depth -= 1
        elif char == "," and depth == 0: commas += 1
    return commas + 1


def test_canonical_owns_trace_without_diagnostics_or_globals():
    source = BRAIN.read_text(encoding="utf-8")
    params = scope(source, r"bool\s+ProcessBuild05ClosedHistoryPrefix", "(")
    body = masked(function(source, "ProcessBuild05ClosedHistoryPrefix"))
    assert re.search(r"Build05RawTrace\s*&\s*trace", params)
    assert "Build05DiagnosticCollect" not in body
    assert "LogDebug" not in body
    assert "build05_diagnostic_counters" not in body


def test_raw_trace_declares_complete_required_fields():
    body = masked(scope(DIAG.read_text(encoding="utf-8"), r"struct\s+Build05RawTrace"))
    fields = "fastSlopeAtr slowSlopeAtr positioning signedDisplacement signedEfficiency directionRawScore bodyAtr bodyRange closeLocation signedProgression progressionStrength efficiencyMagnitude momentumSignedEfficiency momentumRawScore adxCurrent adxPrevious adxSlope atrCurrent atrBaseline atrRatio recentAtr priorAtr atrDecline atrRise recentRange priorRange rangeShrink rangeExpand recentBody priorBody bodyShrink bodyExpand recentEfficiency priorEfficiency efficiencyRise recentDisplacement priorDisplacement displacementRise wickNoise qualityReady healthyScore compressionScore expansionScore chaosScore shockScore"
    for field in fields.split():
        assert re.search(rf"\b{field}\s*;", body), field


def test_engines_fill_trace_from_production_intermediates():
    source = BRAIN.read_text(encoding="utf-8")
    checks = {
        "DirectionEngine": {"fastSlopeAtr": "slopeFast", "slowSlopeAtr": "slopeSlow", "positioning": "positioning", "signedDisplacement": "displacement", "signedEfficiency": "efficiency", "directionRawScore": "raw"},
        "MomentumEngine": {"bodyAtr": "bodyAt", "bodyRange": "bodyRange", "closeLocation": "closeLocStrength", "signedProgression": "signedProgression", "progressionStrength": "progressionStrength", "efficiencyMagnitude": "efficiencyMagnitude", "momentumSignedEfficiency": "efficiencySigned", "momentumRawScore": "raw"},
        "VolatilityEngine": {"atrCurrent": "atr[n]", "atrBaseline": "baseline", "atrRatio": "ratio"},
        "VolatilityQualityEngine": {"recentAtr": "recentAtrAvg", "priorAtr": "priorAtrAvg", "atrDecline": "atrDecline", "atrRise": "atrRise", "recentRange": "recentRangeAvg", "priorRange": "priorRangeAvg", "rangeShrink": "rangeShrink", "rangeExpand": "rangeExpand", "recentBody": "recentBodyAvg", "priorBody": "priorBodyAvg", "bodyShrink": "bodyShrink", "bodyExpand": "bodyExpand", "recentEfficiency": "effRecent", "priorEfficiency": "effPrior", "efficiencyRise": "effRise", "recentDisplacement": "dispRecent", "priorDisplacement": "dispPrior", "displacementRise": "dispRise", "wickNoise": "wick"},
    }
    for name, assignments in checks.items():
        body = masked(function(source, name))
        for target, value in assignments.items():
            assert re.search(rf"trace\s*\.\s*{target}\s*=\s*{re.escape(value)}\s*;", body), f"{name}: {target}"


def test_live_and_replay_have_single_canonical_call_and_replay_no_diagnostics():
    source = EA.read_text(encoding="utf-8")
    live = masked(function(source, "UpdateH1Brain"))
    replay = masked(function(source, "RebuildRegimeFusionState"))
    assert len(re.findall(r"ProcessBuild05ClosedHistoryPrefix\s*\(", live)) == 1
    assert len(re.findall(r"ProcessBuild05ClosedHistoryPrefix\s*\(", replay)) == 1
    assert "Build05DiagnosticCollect" not in replay
    assert "build05_diagnostic_counters" not in replay
    assert len(re.findall(r"Build05DiagnosticCollect\s*\(", live)) == 1


def test_live_cumulative_counters_and_bounded_diagnostics():
    source = EA.read_text(encoding="utf-8")
    globals_ = masked(source[:source.find("void BuildRegimeFusionParams")])
    live = masked(function(source, "UpdateH1Brain"))
    assert re.search(r"Build05DiagnosticCounters\s+build05_diagnostic_counters\s*;", globals_)
    for field in "copyBufferFailures invalidAtr invalidEma adxDegraded duplicateH1Attempts formingBarAttempts abnormalSkips volQualityNotReady".split():
        assert re.search(rf"build05_diagnostic_counters\s*\.\s*{field}\s*\+\+|build05_diagnostic_counters\s*\.\s*{field}\s*\+=", live), field
    duplicate = re.search(r"if\s*\([^)]*b05_last_accepted_h1[^)]*\)\s*\{", live)
    canonical = live.find("ProcessBuild05ClosedHistoryPrefix")
    assert duplicate and duplicate.start() < canonical
    assert len(re.findall(r"Build05DiagnosticCollect\s*\(", live)) == 1


def test_committed_transition_names_gates_and_payloads():
    body = DIAG.read_text(encoding="utf-8")
    for event in ("B05_DIRECTION_TRANSITION", "B05_MOMENTUM_TRANSITION", "B05_VOLLEVEL_TRANSITION", "B05_VOLQUALITY_TRANSITION"):
        assert body.count(f'"{event}"') == 1
    fn = function(body, "Build05DiagnosticTransitions")
    for token in ("closed_h1=", "from=", "to=", "dwell=", "persist=", "challenger="):
        assert token in fn
    clean = masked(fn)
    assert "direction.valid" in clean and "momentum.valid" in clean and "volatility.valid" in clean


def test_brain_update_contains_identity_final_state_persistence_signature_and_trace():
    source = DIAG.read_text(encoding="utf-8")
    builder = function(source, "Build05DiagnosticMessage")
    collect = function(source, "Build05DiagnosticCollect")
    for token in ("closed_h1=", "direction_state=", "momentum_state=", "vol_level=", "vol_quality=", "dir_dwell=", "mom_persist=", "vlev_dwell=", "vq_chd=", "signature=", "fast_slope_atr=", "momentum_raw_score=", "atr_ratio=", "wick_noise="):
        assert token in builder, token
    assert collect.count('LogDebug("BRAIN_UPDATE"') == 1
    assert collect.count('LogDebug("B05_SAFETY"') == 1


def _run_prefixes(data, end):
    state = BehaviorState()
    result = None
    for count in range(41, end + 1):
        result = process_prefix(*(x[:count] for x in data), state)
    return state, result


def test_live_invalid_atr_counter_never_indexes_unready_or_short_buffer():
    live = masked(function(EA.read_text(encoding="utf-8"), "UpdateH1Brain"))
    assert not re.search(r"!atrBufferReady\s*\|\|\s*!BrainValidAt\s*\(\s*atrB05\s*\[", live)
    guarded = re.search(r"if\s*\(\s*atrBufferReady\s*&&\s*copiedAtr\s*>=\s*copiedRates\s*\)\s*\{([^{}]*)\}", live, re.S)
    assert guarded and re.search(r"atrB05\s*\[\s*copiedRates\s*-\s*1\s*\]", guarded.group(1))


def test_short_copyrates_updates_safety_without_canonical_or_state_mutation():
    live = masked(function(EA.read_text(encoding="utf-8"), "UpdateH1Brain"))
    branch = re.search(r"if\s*\(\s*copiedRates\s*<\s*3\s*\)\s*\{([^{}]*)\}", live, re.S)
    assert branch
    body = branch.group(1)
    assert "abnormalSkips++" in body
    assert "copyBufferFailures++" in body
    assert "ProcessBuild05ClosedHistoryPrefix" not in body
    assert "b05_state" not in body
    assert "LogDebug" not in body


def test_b05d2_fnv1a_known_vectors_and_canonical_ascii():
    assert hasattr(reference_build05, "fnv1a64")
    assert hasattr(reference_build05, "canonical_ascii")
    assert reference_build05.fnv1a64(b"") == 0xCBF29CE484222325
    assert reference_build05.fnv1a64(b"a") == 0xAF63DC4C8601EC8C
    assert reference_build05.fnv1a64(b"foobar") == 0x85944171F73967E8
    state = BehaviorState()
    result = {"closed_h1": 0, "direction": (state.directionState, 0.0, False), "momentum": (state.momentumState, 0.0, 0.0, 0.0, 0.0, False, False), "volatility": (state.volLevel, state.volQuality, 0.0, 0.0, {"compression": 0.0, "expansion": 0.0, "chaos": 0.0, "shock": 0.0, "healthy": 0.0}, False)}
    expected = "v=B05D2;dstate=2;dscore=0;dvalid=0;dtime=0;ddwell=0;dch=2;dchd=0;mstate=2;mstrength=0;mdelta=0;mslope=0;malign=0;mvalid=0;mdegraded=0;mtime=0;mpersist=0;mpstr=0;mprmd=0;vlevel=1;vlscore=0;vvalid=0;vtime=0;vldwell=0;vlch=1;vlchd=0;vquality=0;vqconf=0;vqcomp=0;vqexp=0;vqchaos=0;vqshock=0;vqhealth=0;vqprmd=0;vqch=0;vqchd=0;dstate_h=2;mstate_h=2;vlstate_h=1;vqstate_h=0;vqready=0;"
    assert reference_build05.canonical_ascii(result, state) == expected
    assert signature(result, state) == "B05D2:ADE48AE15B59C9F7"


def test_all_stringformat_calls_fit_mql_limit_and_single_live_brain_update():
    production = "\n".join(path.read_text(encoding="utf-8") for path in (*BASE.glob("*.mq5"), *BASE.glob("*.mqh")))
    assert max(map(argument_count, calls(production, "StringFormat"))) <= 64
    collect = function(DIAG.read_text(encoding="utf-8"), "Build05DiagnosticCollect")
    assert collect.count('LogDebug("BRAIN_UPDATE"') == 1
    live = function(EA.read_text(encoding="utf-8"), "UpdateH1Brain")
    assert live.count("Build05DiagnosticCollect(") == 1


def test_no_duplicate_native_indicator_emissions():
    production = EA.read_text(encoding="utf-8") + DIAG.read_text(encoding="utf-8")
    assert '"BRAIN_NATIVE_INDICATOR"' not in production
    assert '"B05_NATIVE_INDICATORS"' not in production
    live = function(EA.read_text(encoding="utf-8"), "UpdateH1Brain")
    assert "Build05NativeIndicatorLog(" not in live


def test_brain_message_builder_uses_committed_state_and_complete_persistence():
    source = DIAG.read_text(encoding="utf-8")
    builder = function(source, "Build05DiagnosticMessage")
    for field in ("s.directionState", "s.momentumState", "s.volLevel", "s.volQuality", "s.volQualityConfidence", "s.directionDwell", "s.directionChallenger", "s.directionChallengerDwell", "s.momentumPersist", "s.prevMomentumStrength", "s.momentumStrengthPrimed", "s.volLevelDwell", "s.volLevelChallenger", "s.volLevelChallengerDwell", "s.volQualityPrimed", "s.volQualityChallenger", "s.volQualityChallengerDwell", "s.volQualityReady", "Build05DiagnosticSignature(b, s)"):
        assert field in masked(builder), field
    assert "b.direction.state" not in masked(builder)
    assert "b.momentum.state" not in masked(builder)
    assert not re.search(r"b\.volatility\.level\b", masked(builder))
    assert not re.search(r"b\.volatility\.quality\b", masked(builder))
    for field in "fastSlopeAtr slowSlopeAtr positioning signedDisplacement signedEfficiency directionRawScore bodyAtr bodyRange closeLocation signedProgression progressionStrength efficiencyMagnitude momentumSignedEfficiency momentumRawScore adxCurrent adxPrevious adxSlope atrCurrent atrBaseline atrRatio recentAtr priorAtr atrDecline atrRise recentRange priorRange rangeShrink rangeExpand recentBody priorBody bodyShrink bodyExpand recentEfficiency priorEfficiency efficiencyRise recentDisplacement priorDisplacement displacementRise wickNoise healthyScore compressionScore expansionScore chaosScore shockScore".split():
        assert f"trace.{field}" in masked(builder), field


def test_primed_only_after_accepted_canonical_result():
    live = masked(function(EA.read_text(encoding="utf-8"), "UpdateH1Brain"))
    accepted = re.search(r"if\s*\(\s*b05_ok\s*\)\s*\{([^{}]*)\}", live, re.S)
    assert accepted and "b05_h1_brain_primed = true" in accepted.group(1)
    outside = live[:accepted.start()] + live[accepted.end():]
    assert "b05_h1_brain_primed = true" not in outside


def test_copybuffer_failures_count_each_actual_primary_call():
    live = masked(function(EA.read_text(encoding="utf-8"), "UpdateH1Brain"))
    assert live.count("CopyBrainBuffer(") == 4
    for copied in ("copiedAtr", "copiedFast", "copiedSlow", "copiedAdx"):
        assert re.search(rf"if\s*\(\s*{copied}\s*!=\s*copiedRates\s*\)\s*build05_diagnostic_counters\.copyBufferFailures\+\+", live)
    canonical = masked(function(BRAIN.read_text(encoding="utf-8"), "ProcessBuild05ClosedHistoryPrefix"))
    assert "copyBufferFailures" not in canonical
    assert reference_build05.count_copy_failures(100, 100, 100, 100, 100) == 0
    assert reference_build05.count_copy_failures(100, 99, 100, 100, 100) == 1
    assert reference_build05.count_copy_failures(100, 100, 99, 98, 100) == 2
    assert reference_build05.count_copy_failures(100, -1, -1, -1, -1) == 4


def test_volquality_transition_uses_only_challenger_dwell():
    fn = function(DIAG.read_text(encoding="utf-8"), "Build05DiagnosticTransitions")
    line = next(line for line in fn.splitlines() if '"B05_VOLQUALITY_TRANSITION"' in line)
    assert not re.search(r"(?<!challenger_)dwell=", line)
    assert line.count("challenger_dwell=") == 1


def test_canonical_forwards_engine_trace_without_recalculation():
    canonical = masked(function(BRAIN.read_text(encoding="utf-8"), "ProcessBuild05ClosedHistoryPrefix"))
    for engine in ("DirectionEngine", "MomentumEngine", "VolatilityEngine", "VolatilityQualityEngine"):
        call = next(call for call in calls(canonical, engine))
        assert re.search(r"\btrace\s*\)$", masked(call))
    assert not re.search(r"trace\s*\.\s*(?:fastSlopeAtr|bodyAtr|atrRatio|recentAtr)\s*=", canonical)


def test_restart_fixture_full_state_result_and_b05d2_determinism():
    data = fixture(48)
    n = 47
    continuous_state, result_n = _run_prefixes(data, n)
    sig_n = signature(result_n, continuous_state)
    live_state = copy.deepcopy(continuous_state)
    result_n1 = process_prefix(*(x[: n + 1] for x in data), live_state)
    sig_n1 = signature(result_n1, live_state)
    assert sig_n == "B05D2:CC3D1B363989DCF7"
    assert sig_n1 == "B05D2:43CC431608D2DD33"
    assert dataclasses.asdict(continuous_state) == {
        "directionState": reference_build05.DIRECTION.NEUTRAL, "directionDwell": 0, "directionChallenger": reference_build05.DIRECTION.NEUTRAL, "directionChallengerDwell": 0,
        "momentumState": reference_build05.MOMENTUM.WEAK, "momentumPersist": 0, "prevMomentumStrength": 0.39756615774938214, "momentumStrengthPrimed": True,
        "volLevel": reference_build05.VOL_LEVEL.HIGH, "volLevelDwell": 2, "volLevelChallenger": reference_build05.VOL_LEVEL.HIGH, "volLevelChallengerDwell": 0,
        "volQuality": reference_build05.VOL_QUALITY.SHOCK, "volQualityConfidence": 0.953131590870034, "volQualityPrimed": True, "volQualityChallenger": reference_build05.VOL_QUALITY.SHOCK, "volQualityChallengerDwell": 0, "volQualityReady": True,
    }

    replay_state, replay_n = _run_prefixes(data, n)
    hydrated = copy.deepcopy(replay_state)
    replay_n1 = process_prefix(*(x[: n + 1] for x in data), hydrated)
    assert replay_state == continuous_state
    assert replay_n == result_n
    assert signature(replay_n, replay_state) == sig_n
    assert hydrated == live_state
    assert replay_n1 == result_n1
    assert signature(replay_n1, hydrated) == sig_n1
    assert any((continuous_state.directionDwell, continuous_state.momentumPersist, continuous_state.directionChallengerDwell, continuous_state.volLevelDwell, continuous_state.volQualityChallengerDwell))

    replay2_state, replay2_n = _run_prefixes(data, n)
    assert (signature(replay2_n, replay2_state), dataclasses.asdict(replay2_state)) == (sig_n, dataclasses.asdict(replay_state))

    defaults = BehaviorState()
    for field in dataclasses.fields(BehaviorState):
        mutated = copy.deepcopy(replay_state)
        current = getattr(mutated, field.name)
        replacement = getattr(defaults, field.name)
        if replacement == current:
            replacement = (not current) if isinstance(current, bool) else (current + 1 if isinstance(current, (int, float)) else list(type(current))[0])
        setattr(mutated, field.name, replacement)
        assert mutated != replay_state
        changed_signature = signature(replay_n, mutated) != sig_n
        next_result = process_prefix(*(x[: n + 1] for x in data), mutated)
        changed_next = mutated != live_state or next_result != result_n1 or signature(next_result, mutated) != sig_n1
        assert changed_signature or changed_next or dataclasses.asdict(mutated) != dataclasses.asdict(replay_state)
