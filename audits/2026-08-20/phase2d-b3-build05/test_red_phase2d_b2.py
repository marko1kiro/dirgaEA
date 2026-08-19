"""Phase 2D-B2 RED tests — these MUST FAIL on the starting commit.

Capture raw pytest output as genuine RED evidence before any repair.
"""
import math
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reference_volatility import (
    quality_enum, VOL_QUALITY, QUALITY_GAP, QUALITY_DWELL,
    compute_quality_evidence,
)


def _bar(o, h, l, c):
    return {"open": o, "high": h, "low": l, "close": c}


def _mirror_bull_bear(bull_bars, K):
    bear = []
    for b in bull_bars:
        bear.append({
            "open": 2 * K - b["open"],
            "high": 2 * K - b["low"],
            "low": 2 * K - b["high"],
            "close": 2 * K - b["close"],
        })
    return bear


def _assert_bar_valid(bar):
    assert bar["low"] <= bar["open"] <= bar["high"], \
        f"Invalid OHLC: O={bar['open']} H={bar['high']} L={bar['low']}"
    assert bar["low"] <= bar["close"] <= bar["high"], \
        f"Invalid OHLC: C={bar['close']} H={bar['high']} L={bar['low']}"
    assert bar["low"] <= bar["high"], \
        f"L > H: L={bar['low']} H={bar['high']}"


# ===========================================================================
# RED TEST 1: Compression equal 1/3 weighting
# ===========================================================================

class TestRedCompressionWeighting:
    def test_atr_only_gives_one_third(self):
        from reference_volatility import compute_compression_score
        score = compute_compression_score(
            atr_recent=[0.4], atr_prior=[1.0],
            range_recent=[10.0], range_prior=[10.0],
            body_recent=[5.0], body_prior=[5.0])
        assert abs(score - 0.20) < 1e-9, \
            f"atr-only compression should be 0.20 (1/3 of 0.60), got {score}"

    def test_range_only_gives_one_third(self):
        from reference_volatility import compute_compression_score
        score = compute_compression_score(
            atr_recent=[1.0], atr_prior=[1.0],
            range_recent=[4.0], range_prior=[10.0],
            body_recent=[5.0], body_prior=[5.0])
        assert abs(score - 0.20) < 1e-9, \
            f"range-only compression should be 0.20, got {score}"

    def test_body_only_gives_one_third(self):
        from reference_volatility import compute_compression_score
        score = compute_compression_score(
            atr_recent=[1.0], atr_prior=[1.0],
            range_recent=[10.0], range_prior=[10.0],
            body_recent=[2.0], body_prior=[5.0])
        assert abs(score - 0.20) < 1e-9, \
            f"body-only compression should be 0.20, got {score}"

    def test_all_three_equal_gives_mean(self):
        from reference_volatility import compute_compression_score
        score = compute_compression_score(
            atr_recent=[0.4], atr_prior=[1.0],
            range_recent=[4.0], range_prior=[10.0],
            body_recent=[2.0], body_prior=[5.0])
        assert abs(score - 0.60) < 1e-9, \
            f"all-three compression should be 0.60, got {score}"


# ===========================================================================
# RED TEST 2: Efficiency/displacement independence
# ===========================================================================

class TestRedEffDisplacementIndependence:
    def test_efficiency_rise_displacement_flat(self):
        from reference_volatility import compute_expansion_score
        score = compute_expansion_score(
            atr_recent=[1.0]*5, atr_prior=[1.0]*5,
            range_recent=[10.0]*5, range_prior=[10.0]*5,
            body_recent=[5.0]*5, body_prior=[5.0]*5,
            eff_rise_scalar=0.5,
            disp_rise_scalar=0.0)
        assert score > 0.0, "Efficiency rise should contribute to expansion"
        assert score <= 1.0

    def test_displacement_rise_efficiency_flat(self):
        from reference_volatility import compute_expansion_score
        score = compute_expansion_score(
            atr_recent=[1.0]*5, atr_prior=[1.0]*5,
            range_recent=[10.0]*5, range_prior=[10.0]*5,
            body_recent=[5.0]*5, body_prior=[5.0]*5,
            eff_rise_scalar=0.0,
            disp_rise_scalar=0.5)
        assert score > 0.0, "Displacement rise should contribute to expansion"
        assert score <= 1.0

    def test_both_rise(self):
        from reference_volatility import compute_expansion_score
        score = compute_expansion_score(
            atr_recent=[1.0]*5, atr_prior=[1.0]*5,
            range_recent=[10.0]*5, range_prior=[10.0]*5,
            body_recent=[5.0]*5, body_prior=[5.0]*5,
            eff_rise_scalar=0.5,
            disp_rise_scalar=0.5)
        assert score > 0.0
        assert score <= 1.0

    def test_neither_rises(self):
        from reference_volatility import compute_expansion_score
        score = compute_expansion_score(
            atr_recent=[1.0]*5, atr_prior=[1.0]*5,
            range_recent=[10.0]*5, range_prior=[10.0]*5,
            body_recent=[5.0]*5, body_prior=[5.0]*5,
            eff_rise_scalar=0.0,
            disp_rise_scalar=0.0)
        assert abs(score) < 1e-9, f"Neither rising should give ~0, got {score}"


# ===========================================================================
# RED TEST 3: Stale confidence gap
# ===========================================================================

class TestRedStaleConfidenceGap:
    def test_stale_high_conf_does_not_block_challenger(self):
        ev = dict(healthy=0.10, compression=0.25, expansion=0.10, chaos=0.10, shock=0.10)
        state, conf, primed, ch, cd = quality_enum(
            ev,
            incumbent_state=VOL_QUALITY.HEALTHY,
            primed=True)
        assert ch == VOL_QUALITY.COMPRESSED or state == VOL_QUALITY.COMPRESSED, \
            f"COMPRESSED should qualify as challenger despite stale conf=0.90; got state={state}, ch={ch}"

    def test_zero_confidence_incumbent_still_requires_dwell(self):
        ev = dict(healthy=0.0, compression=0.25, expansion=0.10, chaos=0.10, shock=0.10)
        state, conf, primed, ch, cd = quality_enum(
            ev,
            incumbent_state=VOL_QUALITY.HEALTHY,
            primed=True)
        assert state == VOL_QUALITY.HEALTHY, \
            f"Incumbent should be retained at dwell=1, got state={state}"


# ===========================================================================
# RED TEST 4: Real bull/bear mirror
# ===========================================================================

class TestRedBullBearMirror:
    def _make_bull_bars(self):
        return [
            _bar(100, 108, 99, 106),
            _bar(106, 112, 104, 110),
            _bar(110, 115, 108, 113),
            _bar(113, 118, 111, 116),
            _bar(116, 122, 114, 120),
            _bar(120, 125, 118, 123),
            _bar(123, 128, 121, 126),
            _bar(126, 130, 124, 128),
            _bar(128, 132, 126, 130),
            _bar(130, 135, 128, 133),
        ]

    def test_mirror_physical_validity(self):
        K = 120.0
        bull = self._make_bull_bars()
        bear = _mirror_bull_bear(bull, K)
        for b in bull:
            _assert_bar_valid(b)
        for b in bear:
            _assert_bar_valid(b)

    def test_full_quality_mirror(self):
        K = 120.0
        bull = self._make_bull_bars()
        bear = _mirror_bull_bear(bull, K)
        atr = [5.0 + i * 0.5 for i in range(10)]

        bull_ev = compute_quality_evidence(bull, atr)
        bear_ev = compute_quality_evidence(bear, atr)

        for key in ["healthy", "compression", "expansion", "chaos", "shock"]:
            assert abs(bull_ev[key] - bear_ev[key]) < 1e-9, \
                f"{key}: bull={bull_ev[key]} != bear={bear_ev[key]}"

    def test_quality_persistence_mirror(self):
        K = 120.0
        bull = self._make_bull_bars()
        bear = _mirror_bull_bear(bull, K)
        atr = [5.0 + i * 0.5 for i in range(10)]

        bull_ev = compute_quality_evidence(bull, atr)
        bear_ev = compute_quality_evidence(bear, atr)

        bs, bc, bp, bch, bcd = quality_enum(
            bull_ev, incumbent_state=VOL_QUALITY.HEALTHY, primed=True)
        rs, rc, rp, rch, rcd = quality_enum(
            bear_ev, incumbent_state=VOL_QUALITY.HEALTHY, primed=True)

        assert bs == rs, f"quality state: bull={bs} != bear={rs}"
        assert abs(bc - rc) < 1e-9, f"quality conf: bull={bc} != bear={rc}"
        assert bch == rch, f"challenger: bull={bch} != bear={rch}"
        assert bcd == rcd, f"challenger_dwell: bull={bcd} != bear={rcd}"


# ===========================================================================
# RED TEST 5: Python reference uses full multi-component algorithm
# ===========================================================================

class TestRedPythonReferenceFull:
    def test_compression_not_just_atr_trend(self):
        from reference_volatility import compute_compression_score
        score = compute_compression_score(
            atr_recent=[0.1]*5, atr_prior=[1.0]*5,
            range_recent=[20.0]*5, range_prior=[20.0]*5,
            body_recent=[10.0]*5, body_prior=[10.0]*5)
        assert abs(score - 0.30) < 1e-9, \
            f"Compression with only ATR decline should be 0.30 (1/3 of 0.9), got {score}"

    def test_expansion_has_five_components(self):
        from reference_volatility import compute_expansion_score
        atr_rise = 0.5
        score = compute_expansion_score(
            atr_recent=[1.5]*5, atr_prior=[1.0]*5,
            range_recent=[10.0]*5, range_prior=[10.0]*5,
            body_recent=[5.0]*5, body_prior=[5.0]*5,
            eff_rise_scalar=0.0,
            disp_rise_scalar=0.0)
        assert abs(score - atr_rise / 5.0) < 1e-9, \
            f"Single component expansion should be 1/5 of value, got {score}"

    def test_quality_evidence_uses_new_compression(self):
        # Prior 5 bars: wide range/large body. Recent 5 bars: narrow range/small body.
        bars = [
            _bar(100, 120, 80, 110),
            _bar(110, 130, 90, 120),
            _bar(120, 140, 100, 130),
            _bar(130, 150, 110, 140),
            _bar(140, 160, 120, 150),
            _bar(150, 152, 148, 151),
            _bar(151, 153, 149, 152),
            _bar(152, 154, 150, 153),
            _bar(153, 155, 151, 154),
            _bar(154, 156, 152, 155),
        ]
        atr = [10.0] * 10
        ev = compute_quality_evidence(bars, atr)
        assert ev["compression"] > 0.0, \
            f"Shrinking range/body should give positive compression, got {ev['compression']}"
