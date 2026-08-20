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
    fn = function(DIAG.read_text(encoding="utf-8"), "Build05DiagnosticCollect")
    for token in ("closed_h1=", "direction_state=", "momentum_state=", "vol_level=", "vol_quality=", "dir_dwell=", "mom_persist=", "vlev_dwell=", "vq_chd=", "signature=", "fast_slope_atr=", "momentum_raw_score=", "atr_ratio=", "wick_noise="):
        assert token in fn, token
    assert fn.count('LogDebug("BRAIN_UPDATE"') == 1
    assert fn.count('LogDebug("B05_SAFETY"') == 1


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


def test_restart_fixture_full_state_result_and_b05d2_determinism():
    data = fixture(48)
    n = 47
    continuous_state, result_n = _run_prefixes(data, n)
    sig_n = signature(result_n, continuous_state)
    live_state = copy.deepcopy(continuous_state)
    result_n1 = process_prefix(*(x[: n + 1] for x in data), live_state)
    sig_n1 = signature(result_n1, live_state)

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

    assert continuous_state.volLevelDwell != 0
    omitted = copy.deepcopy(replay_state)
    omitted.volLevelDwell = 0
    assert omitted != continuous_state
