from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
EA = (ROOT / "AdaptiveSurvivalEA.mq5").read_text(encoding="utf-8")


def test_live_and_replay_use_one_shared_regime_observation_ingestion_path():
    assert len(re.findall(r"(?:Ingest|Process)Regime\w*Observation\s*\(", EA)) >= 3


def test_replay_acquires_complete_available_history_and_fails_closed_when_unavailable():
    assert "WHOLE_ARRAY" in EA
    assert re.search(r"if\s*\([^)]*copiedRates[^)]*<\s*0[^)]*\)\s*return", EA)
    assert "REPLAY_HISTORY_UNAVAILABLE" in EA


def test_replay_locked_void_wrapper_reports_success_only_after_atomic_hydration():
    assert "bool b06_rebuild_success = false;" in EA
    assert re.search(r"void\s+RebuildRegimeFusionState\s*\(\s*\)", EA)
    start = EA.index("void RebuildRegimeFusionState()")
    end = EA.index("int OnInit()", start)
    replay = EA[start:end]
    assert "b06_rebuild_success = false;" in replay
    assert "return false" not in replay
    assert "return true" not in replay
    assert not re.search(r"\bLog(?:Debug|Warning|Error)\s*\(", replay)
    assert replay.index("b06_rebuild_success = true;") > replay.index("b06_result = replayResult")
    on_init = EA[end:EA.index("void OnTick()", end)]
    assert "RebuildRegimeFusionState();" in on_init
    assert "if(!b06_rebuild_success)" in on_init


def test_replay_keeps_locked_complete_history_loop_and_advances_b05_before_b04_gate():
    start = EA.index("void RebuildRegimeFusionState()")
    end = EA.index("int OnInit()", start)
    replay = EA[start:end]
    assert "const int warmup = 0;" in replay
    assert "for(int t = warmup; t < copiedRates; t++)" in replay
    b05 = replay.index("ProcessBuild05ClosedHistoryPrefix")
    b04_gate = replay.index("if(!structOk)", b05)
    assert b05 < b04_gate
    assert "if(!replayPublished) continue;" in replay


def test_break_tracker_seeds_retained_break_from_replay_index_and_mutates_only_after_ingest():
    assert re.search(r"struct\s+B06BreakTracker\b", EA)
    assert "B06ChronologicalBreakAge" in EA
    assert "B06AdvanceBreakTracker" in EA
    assert "replayBreakTracker, rates, t" in EA
    process = EA[EA.index("bool ProcessRegimeObservation"):EA.index("void UpdateH1RegimeFusion()")]
    assert process.index("IngestRegimeObservation") < process.index("tracker = nextTracker")


def test_break_age_is_recomputed_from_chronological_rates_with_lookback_ceiling():
    assert "B06ChronologicalBreakAge" in EA
    assert "CopyRates(_Symbol, PERIOD_H1, 1, BreakoutLookbackBars + 1" in EA


def test_replay_hydrates_b04_b05_and_b06_atomically_after_strict_alignment():
    assert "REGIME_ALIGN_SKIP" in EA
    assert "replayAligned" in EA
    assert "replayStructure" in EA
    assert "replayB05State" in EA
    assert "b06_compression" in EA


def test_live_rejection_unprimes_without_mutating_published_b06_result():
    assert re.search(r"void\s+RejectB06Observation\s*\([^)]*\)\s*\{[^}]*b06_primed\s*=\s*false", EA, re.S)
    assert "RejectB06Observation(" in EA
    update = EA[EA.index("void UpdateH1RegimeFusion()"):EA.index("void RebuildRegimeFusionState()")]
    assert "else\n      RejectB06Observation" in update


def test_replay_failure_returns_before_all_global_hydration_writes():
    failure = EA.index("if(!replayAligned || !replayPublished || replayLastAccepted == 0)")
    hydrate = EA.index("swing_structure = replayStructure")
    assert failure < hydrate
    prefix = EA[:hydrate]
    assert "b06_state = replayB06State" not in prefix
    assert "b06_result = replayResult" not in prefix
