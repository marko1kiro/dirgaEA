"""BUILD 13 reference dashboard telemetry implementation."""

from __future__ import annotations


def format_hud_telemetry(
    symbol: str,
    ea_ready: bool,
    trade_ready: bool,
    regime_name: str,
    regime_quality: str,
    regime_confidence: float,
    active_strategy: str,
    last_score: float,
    open_positions: int
) -> str:
    lines = [
        "========================================",
        f" ADAPTIVE SURVIVAL EA — [{symbol}]",
        "========================================",
        f"EA Ready: {'YES' if ea_ready else 'NO'} | Trade Ready: {'YES' if trade_ready else 'NO'}",
        f"H1 Regime: {regime_name} | Quality: {regime_quality}",
        f"Confidence: {regime_confidence * 100:.1f}%",
        "----------------------------------------",
        f"Active Strategy: {active_strategy}",
        f"Quality Score: {last_score:.1f}/100",
        f"Open Positions: {open_positions}",
        "========================================"
    ]
    return "\n".join(lines)
