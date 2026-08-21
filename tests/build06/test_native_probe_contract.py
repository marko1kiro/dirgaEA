from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "tests" / "build06" / "native" / "Build06ParityProbe.mq5"
EXPECTED_SIGNATURE = "B06D1:D80BE01B4A71B434"
REQUIRED_CASES = {"baseline_signature", "invalid_stale", "lookback_boundary", "uncertain_tie", "replay_hydration",
                  "retained_break_age", "rejected_then_accepted_age", "weekend_adjacent_age"}


def parse_probe_output(raw):
    records = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        fields = dict(part.split("=", 1) for part in line.split("|") if "=" in part)
        records.append(fields)
    return records


def test_probe_parser_preserves_raw_canonical_and_expected_signature():
    records = parse_probe_output(
        "case=baseline_signature|canonical=v=B06D1;regime=0;|signature=B06D1:D80BE01B4A71B434"
    )
    assert records == [{"case": "baseline_signature", "canonical": "v=B06D1;regime=0;", "signature": EXPECTED_SIGNATURE}]


def test_executable_mql5_probe_exists_with_case_manifest_and_raw_output_contract():
    assert PROBE.is_file(), "missing native executable probe: tests/build06/native/Build06ParityProbe.mq5"
    source = PROBE.read_text(encoding="utf-8")
    for case in REQUIRED_CASES:
        assert case in source
    assert EXPECTED_SIGNATURE in source
    assert '"|signature="' in source
    assert '"|canonical="' in source


def test_probe_is_tester_compatible_expert_that_finishes_from_oninit():
    source = PROBE.read_text(encoding="utf-8")
    assert "int OnInit()" in source
    assert "Print(\"fail_count=\", failures);" in source
    assert "return INIT_SUCCEEDED;" in source


def test_probe_exercises_production_fusion_paths_not_result_mutation_only():
    source = PROBE.read_text(encoding="utf-8")
    assert "IngestRegimeObservation(" in source
    assert "UpdateRegimeFusion(" in source
    assert "RegimeApplyEligibility(" in source
    assert "RegimeBreakRecency(" in source
    assert "B06ChronologicalBreakAge(" in source
    assert "AssertNear(" in source
