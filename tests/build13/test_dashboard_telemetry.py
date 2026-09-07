import pytest
from tests.build13.reference_dashboard import format_hud_telemetry


def test_format_hud_telemetry():
    hud_text = format_hud_telemetry(
        symbol="EURUSDm",
        ea_ready=True,
        trade_ready=True,
        regime_name="TREND_BULL",
        regime_quality="STRONG",
        regime_confidence=0.88,
        active_strategy="M15_TREND",
        last_score=85.0,
        open_positions=1
    )
    assert "ADAPTIVE SURVIVAL EA" in hud_text
    assert "Regime: TREND_BULL" in hud_text
    assert "Quality: STRONG" in hud_text
    assert "Strategy: M15_TREND" in hud_text
    assert "Score: 85.0" in hud_text
