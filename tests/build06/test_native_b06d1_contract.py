from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
TYPES = (ROOT / "Types.mqh").read_text(encoding="utf-8")
FUSION = (ROOT / "RegimeFusion.mqh").read_text(encoding="utf-8")
DIAGNOSTICS = (ROOT / "DiagnosticCollector.mqh").read_text(encoding="utf-8")

CANONICAL_KEYS = (
    "v regime quality confidence valid initialized latest age prev structure direction "
    "dscore momentum mstrength mda vlevel vquality comp exp sTB sTBe sR sBB sBBe "
    "sU tx candAge pend complete degraded cm_count cm_obs"
).split()


def test_b06d1_signature_covers_initialized_state_and_none_pending_identity():
    assert re.search(r'"initialized"', DIAGNOSTICS)
    assert '"NONE"' in DIAGNOSTICS


def test_b06d1_uses_exact_fifteen_decimal_places_and_fixed_width_hash():
    assert "DoubleToString(value, 15)" in DIAGNOSTICS
    assert 'StringFormat("%016I64X", hash)' in DIAGNOSTICS


def test_b06d1_source_declares_canonical_field_order_and_chronological_fifo():
    source = DIAGNOSTICS[DIAGNOSTICS.index("string Build06DiagnosticCanonical"):DIAGNOSTICS.index("string Build06DiagnosticSignature")]
    positions = [source.find(f'"{key}"') for key in CANONICAL_KEYS]
    assert all(position >= 0 for position in positions)
    assert positions == sorted(positions)
    assert re.search(r"for\s*\(int\s+\w+\s*=\s*0\s*;\s*\w+\s*<\s*\w+\.count", DIAGNOSTICS)
    assert "RegimeFusionStateInit" in FUSION
