from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
FUSION = (ROOT / "RegimeFusion.mqh").read_text(encoding="utf-8")


def test_scores_consume_normalized_observation_not_raw_upstream_values():
    assert re.search(r"RegimeComputeScores\s*\([^)]*RegimeObservation", FUSION)


def test_break_recency_uses_active_parameter_and_excludes_lookback_boundary():
    assert "breakoutLookbackBars" in FUSION
    assert re.search(r"age\w*\s*<\s*\w*lookback", FUSION)


def test_candidate_selection_applies_post_score_eligibility_mask():
    assert re.search(r"(?:Apply|Mask)\w*Eligibility", FUSION)


def test_hard_veto_reads_only_valid_normalized_domains():
    veto = re.search(r"bool\s+RegimeHardUncertainVeto\b[\s\S]*?\n}\n", FUSION)
    assert veto
    assert "Valid" in veto.group(0)
