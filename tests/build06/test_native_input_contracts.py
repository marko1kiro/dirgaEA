from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
TYPES = (ROOT / "Types.mqh").read_text(encoding="utf-8")
FUSION = (ROOT / "RegimeFusion.mqh").read_text(encoding="utf-8")
EA = (ROOT / "AdaptiveSurvivalEA.mq5").read_text(encoding="utf-8")


def test_native_observation_envelope_has_explicit_core_validity_and_nullable_break_ages():
    assert re.search(r"struct\s+RegimeObservation\b", TYPES)
    assert re.search(r"bool\s+criticalCoreValid\s*;", TYPES)
    assert len(re.findall(r"bool\s+break(?:Bull|Bear)AgePresent\s*;", TYPES)) == 2
    assert len(re.findall(r"int\s+break(?:Bull|Bear)AgeBars\s*;", TYPES)) == 2


def test_native_invalid_domain_gates_are_direct_and_normalizer_is_absent():
    assert "RegimeNormalizeObservation" not in FUSION
    for domain in ("structure", "direction", "momentum", "volatility"):
        assert f"{domain}Valid" in FUSION


def test_live_fusion_requires_all_closed_h1_timestamps_to_match():
    for field in ("direction.latestClosedH1", "momentum.latestClosedH1", "volatility.latestClosedH1"):
        assert re.search(rf"{re.escape(field)}\s*!=\s*b04Time", EA)
    assert "REGIME_ALIGN_SKIP" in EA


def test_live_core_provenance_comes_from_b04_b05_cycle_inputs_not_fresh_retry():
    assert "CurrentH1CriticalCoreReady" not in EA
    assert "b06_cycle_b04_rates_ready" in EA
    assert "b06_cycle_b04_atr_ready" in EA
    assert "b06_cycle_b05_rates_ready" in EA
    assert "b06_cycle_b05_atr_ready" in EA
    assert "ResetB06CycleProvenance" in EA
    assert re.search(r"b06_cycle_b04_atr_ready\s*=\s*copiedAtr\s*==\s*copiedRates", EA)
    assert re.search(r"b06_cycle_b05_atr_ready\s*=\s*atrBufferReady", EA)
