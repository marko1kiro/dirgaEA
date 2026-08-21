from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
FUSION = (ROOT / "RegimeFusion.mqh").read_text(encoding="utf-8")
EA = (ROOT / "AdaptiveSurvivalEA.mq5").read_text(encoding="utf-8")


def test_uncertain_tie_clears_pending_challenger_without_creating_one():
    assert re.search(r"EffectiveTie[\s\S]{0,800}UNCERTAIN[\s\S]{0,800}ClearPending", FUSION)


def test_breakout_maturation_and_failure_are_validity_gated():
    assert re.search(r"SustainedBull\b[\s\S]{0,500}Valid", FUSION)
    assert re.search(r"OpposingStructure\b[\s\S]{0,500}Valid", FUSION)


def test_invalid_volatility_does_not_append_compression_fifo():
    append = re.search(r"void\s+RegimeCompressionAppend\w*\b[\s\S]*?\n}\n", FUSION)
    assert append
    assert "volatilityValid" in append.group(0)


def test_native_build06_source_has_no_trade_or_execution_side_effect_api():
    source = FUSION + EA
    for api in ("CTrade", "OrderSend", "OrderCheck", "PositionModify", "PositionClose"):
        assert api not in source
