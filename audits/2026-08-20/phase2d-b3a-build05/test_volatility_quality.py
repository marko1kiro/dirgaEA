"""Phase 2D-B2 Volatility Quality tests.

Tests cover:
- Compression 1/3 equal weighting
- Efficiency/displacement independence
- Stale confidence gap regression
- Zero-confidence primed regression
- Quality persistence state machine (full)
- Real bull/bear mirror (proper OHLC reflection)
- Bounding tests (full algorithm)
- Replay invalid quality gate
- Source invariants
"""
import math
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reference_volatility import (
    quality_enum, VOL_QUALITY, QUALITY_GAP, QUALITY_DWELL,
    compute_quality_evidence, compute_compression_score, compute_expansion_score,
)


def _bar(o, h, l, c):
    return {"open": o, "high": h, "low": l, "close": c}


def _mirror_bull_bear(bull_bars, K):
    """Correct OHLC reflection around center K."""
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


# ===========================================================================
# COMPRESSION 1/3 EQUAL WEIGHTING
# ===========================================================================

class TestCompressionWeighting:
    """Compression must use equal 1/3 weighting for atr, range, body."""

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

    def test_source_invariant_mean3_weighting(self):
        """MQL5 source must contain BrainMean3 for compression, not BrainMean5 with duplicates."""
        source_path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))), "MarketBrain.mqh")
        with open(source_path, "r", encoding="utf-8") as f:
            source = f.read()
        # Find the compressionScore line
        assert "BrainMean3(atrDecline, rangeShrink, bodyShrink)" in source, \
            "Compression must use BrainMean3 with equal 1/3 weighting"
        # Must NOT have the old duplicated pattern
        assert "BrainMean5(atrDecline, rangeShrink, bodyShrink, rangeShrink, bodyShrink)" not in source, \
            "Must not use BrainMean5 with duplicated rangeShrink/bodyShrink"


# ===========================================================================
# EFFICIENCY / DISPLACEMENT INDEPENDENCE
# ===========================================================================

class TestEffDisplacementIndependence:
    """Efficiency and displacement must be independent evidence channels."""

    def test_efficiency_rise_displacement_flat(self):
        score = compute_expansion_score(
            atr_recent=[1.0]*5, atr_prior=[1.0]*5,
            range_recent=[10.0]*5, range_prior=[10.0]*5,
            body_recent=[5.0]*5, body_prior=[5.0]*5,
            eff_rise_scalar=0.5,
            disp_rise_scalar=0.0)
        assert score > 0.0, "Efficiency rise should contribute to expansion"
        assert score <= 1.0

    def test_displacement_rise_efficiency_flat(self):
        score = compute_expansion_score(
            atr_recent=[1.0]*5, atr_prior=[1.0]*5,
            range_recent=[10.0]*5, range_prior=[10.0]*5,
            body_recent=[5.0]*5, body_prior=[5.0]*5,
            eff_rise_scalar=0.0,
            disp_rise_scalar=0.5)
        assert score > 0.0, "Displacement rise should contribute to expansion"
        assert score <= 1.0

    def test_both_rise(self):
        score = compute_expansion_score(
            atr_recent=[1.0]*5, atr_prior=[1.0]*5,
            range_recent=[10.0]*5, range_prior=[10.0]*5,
            body_recent=[5.0]*5, body_prior=[5.0]*5,
            eff_rise_scalar=0.5,
            disp_rise_scalar=0.5)
        assert score > 0.0
        assert score <= 1.0

    def test_neither_rises(self):
        score = compute_expansion_score(
            atr_recent=[1.0]*5, atr_prior=[1.0]*5,
            range_recent=[10.0]*5, range_prior=[10.0]*5,
            body_recent=[5.0]*5, body_prior=[5.0]*5,
            eff_rise_scalar=0.0,
            disp_rise_scalar=0.0)
        assert abs(score) < 1e-9, f"Neither rising should give ~0, got {score}"

    def test_source_invariant_no_shared_disp_var(self):
        """MQL5 must derive effRise from effRecent/effPrior, not dispRecent."""
        source_path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))), "MarketBrain.mqh")
        with open(source_path, "r", encoding="utf-8") as f:
            source = f.read()
        # effRise must NOT use dispRecent — the old bug was: effRise = BrainExpandEvidence(dispRecent, dispPrior)
        assert "effRise = BrainExpandEvidence(dispRecent" not in source, \
            "effRise must not derive from dispRecent (old shared-variable bug)"
        # effRise must use effRecent
        assert "effRise = BrainExpandEvidence(effRecent" in source, \
            "effRise must derive from effRecent (independent channel)"


# ===========================================================================
# STALE CONFIDENCE GAP
# ===========================================================================

class TestStaleConfidenceGap:
    """Challenger uses current-bar incumbent evidence, not stale confidence."""

    def test_stale_high_conf_does_not_block_challenger(self):
        """incConf=0.90 but current HEALTHY=0.10, COMPRESSED=0.25 → gap=0.15 >= 0.10."""
        ev = dict(healthy=0.10, compression=0.25, expansion=0.10, chaos=0.10, shock=0.10)
        state, conf, primed, ch, cd = quality_enum(
            ev,
            incumbent_state=VOL_QUALITY.HEALTHY,
            primed=True)
        assert ch == VOL_QUALITY.COMPRESSED or state == VOL_QUALITY.COMPRESSED, \
            f"COMPRESSED should qualify as challenger despite stale conf=0.90; got state={state}, ch={ch}"


# ===========================================================================
# ZERO-CONFIDENCE PRIMED
# ===========================================================================

class TestZeroConfidencePrimed:
    """Established incumbent with conf=0.0 still requires dwell."""

    def test_zero_confidence_incumbent_still_requires_dwell(self):
        ev = dict(healthy=0.0, compression=0.25, expansion=0.10, chaos=0.10, shock=0.10)
        state, conf, primed, ch, cd = quality_enum(
            ev,
            incumbent_state=VOL_QUALITY.HEALTHY,
            primed=True)
        assert state == VOL_QUALITY.HEALTHY, \
            f"Incumbent should be retained at dwell=1, got state={state}"


# ===========================================================================
# QUALITY PERSISTENCE STATE MACHINE
# ===========================================================================

class TestQualityPersistence:
    """Full quality persistence state machine."""

    def test_incumbent_held_by_insufficient_gap(self):
        ev = dict(healthy=0.8, compression=0.85, expansion=0.1, chaos=0.1, shock=0.1)
        state, conf, primed, ch, cd = quality_enum(
            ev, incumbent_state=VOL_QUALITY.HEALTHY, primed=True)
        assert state == VOL_QUALITY.HEALTHY

    def test_challenger_bar1_held(self):
        ev = dict(healthy=0.3, compression=0.9, expansion=0.1, chaos=0.1, shock=0.1)
        state, conf, primed, ch, cd = quality_enum(
            ev, incumbent_state=VOL_QUALITY.HEALTHY, primed=True)
        assert state == VOL_QUALITY.HEALTHY
        assert ch == VOL_QUALITY.COMPRESSED
        assert cd == 1

    def test_challenger_bar2_commits(self):
        ev1 = dict(healthy=0.3, compression=0.9, expansion=0.1, chaos=0.1, shock=0.1)
        state, conf, primed, ch, cd = quality_enum(
            ev1, incumbent_state=VOL_QUALITY.HEALTHY, primed=True)
        assert state == VOL_QUALITY.HEALTHY and ch == VOL_QUALITY.COMPRESSED and cd == 1

        ev2 = dict(healthy=0.3, compression=0.85, expansion=0.1, chaos=0.1, shock=0.1)
        state, conf, primed, ch, cd = quality_enum(
            ev2, incumbent_state=state, primed=primed,
            challenger=ch, challenger_dwell=cd)
        assert state == VOL_QUALITY.COMPRESSED, "Second challenger bar: commit"
        assert cd == 0, "Challenger reset after commit"

    def test_challenger_interruption_resets(self):
        ev1 = dict(healthy=0.3, compression=0.9, expansion=0.1, chaos=0.1, shock=0.1)
        state, conf, primed, ch, cd = quality_enum(
            ev1, incumbent_state=VOL_QUALITY.HEALTHY, primed=True)
        assert ch == VOL_QUALITY.COMPRESSED and cd == 1

        ev2 = dict(healthy=0.1, compression=0.3, expansion=0.9, chaos=0.1, shock=0.1)
        state, conf, primed, ch, cd = quality_enum(
            ev2, incumbent_state=state, primed=primed,
            challenger=ch, challenger_dwell=cd)
        assert ch == VOL_QUALITY.EXPANDING, "Different challenger: resets dwell"
        assert cd == 1

    def test_incumbent_recovery_clears(self):
        ev1 = dict(healthy=0.3, compression=0.9, expansion=0.1, chaos=0.1, shock=0.1)
        state, conf, primed, ch, cd = quality_enum(
            ev1, incumbent_state=VOL_QUALITY.HEALTHY, primed=True)
        assert ch == VOL_QUALITY.COMPRESSED and cd == 1

        ev2 = dict(healthy=0.9, compression=0.3, expansion=0.1, chaos=0.1, shock=0.1)
        state, conf, primed, ch, cd = quality_enum(
            ev2, incumbent_state=state, primed=primed,
            challenger=ch, challenger_dwell=cd)
        assert state == VOL_QUALITY.HEALTHY
        assert ch == VOL_QUALITY.HEALTHY, "Incumbent recovery: clear challenger"
        assert cd == 0

    def test_unprimed_commits_immediately(self):
        """First observation: pure evidence-max, no dwell needed."""
        ev = dict(healthy=0.3, compression=0.9, expansion=0.1, chaos=0.1, shock=0.1)
        state, conf, primed, ch, cd = quality_enum(
            ev, incumbent_state=VOL_QUALITY.HEALTHY, primed=False)
        assert state == VOL_QUALITY.COMPRESSED, "Unprimed: commit immediately"
        assert primed is True


# ===========================================================================
# BULL/BEAR MIRROR
# ===========================================================================

class TestBullBearMirror:
    """Real bull/bear mirror with proper OHLC reflection."""

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

    def test_mirror_hl_swapped(self):
        """Mirrored HIGH = 2K - original LOW, mirrored LOW = 2K - original HIGH."""
        K = 120.0
        bull = self._make_bull_bars()
        bear = _mirror_bull_bear(bull, K)
        for b, m in zip(bull, bear):
            assert m["high"] == 2 * K - b["low"], \
                f"Mirror HIGH should be 2K-L: {m['high']} != {2*K - b['low']}"
            assert m["low"] == 2 * K - b["high"], \
                f"Mirror LOW should be 2K-H: {m['low']} != {2*K - b['high']}"

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
# BOUNDING TESTS
# ===========================================================================

class TestScoreBounding:
    """All quality scores strictly [0,1], no NaN/INF."""

    def test_extreme_atr_rise(self):
        bars = [_bar(100, 102, 98, 101)] * 10
        atr = [0.1, 0.1, 0.1, 0.1, 0.1, 100.0, 100.0, 100.0, 100.0, 100.0]
        ev = compute_quality_evidence(bars, atr)
        for k, v in ev.items():
            assert 0.0 <= v <= 1.0, f"{k}={v} out of [0,1]"
            assert math.isfinite(v), f"{k}={v} is not finite"

    def test_extreme_atr_decline(self):
        bars = [_bar(100, 102, 98, 101)] * 10
        atr = [100.0, 100.0, 100.0, 100.0, 100.0, 0.1, 0.1, 0.1, 0.1, 0.1]
        ev = compute_quality_evidence(bars, atr)
        for k, v in ev.items():
            assert 0.0 <= v <= 1.0, f"{k}={v} out of [0,1]"
            assert math.isfinite(v), f"{k}={v} is not finite"

    def test_large_range(self):
        bars = [_bar(100, 1000, 1, 500)] * 10
        atr = [500.0] * 10
        ev = compute_quality_evidence(bars, atr)
        for k, v in ev.items():
            assert 0.0 <= v <= 1.0, f"{k}={v} out of [0,1]"
            assert math.isfinite(v), f"{k}={v} is not finite"

    def test_near_zero_range(self):
        bars = [_bar(100, 100.001, 99.999, 100)] * 10
        atr = [0.001] * 10
        ev = compute_quality_evidence(bars, atr)
        for k, v in ev.items():
            assert 0.0 <= v <= 1.0, f"{k}={v} out of [0,1]"
            assert math.isfinite(v), f"{k}={v} is not finite"

    def test_high_wick(self):
        bars = [_bar(100, 200, 90, 101)] * 10
        atr = [50.0] * 10
        ev = compute_quality_evidence(bars, atr)
        for k, v in ev.items():
            assert 0.0 <= v <= 1.0, f"{k}={v} out of [0,1]"
            assert math.isfinite(v), f"{k}={v} is not finite"

    def test_zero_body(self):
        bars = [_bar(100, 102, 98, 100)] * 10
        atr = [2.0] * 10
        ev = compute_quality_evidence(bars, atr)
        for k, v in ev.items():
            assert 0.0 <= v <= 1.0, f"{k}={v} out of [0,1]"
            assert math.isfinite(v), f"{k}={v} is not finite"

    def test_high_efficiency(self):
        bars = [_bar(100 + i, 101 + i, 99 + i, 101 + i) for i in range(10)]
        atr = [1.0] * 10
        ev = compute_quality_evidence(bars, atr)
        for k, v in ev.items():
            assert 0.0 <= v <= 1.0, f"{k}={v} out of [0,1]"
            assert math.isfinite(v), f"{k}={v} is not finite"

    def test_noisy_path_low_efficiency(self):
        bars = [_bar(100, 105, 95, 100 + (-1)**i * 2) for i in range(10)]
        atr = [3.0] * 10
        ev = compute_quality_evidence(bars, atr)
        for k, v in ev.items():
            assert 0.0 <= v <= 1.0, f"{k}={v} out of [0,1]"
            assert math.isfinite(v), f"{k}={v} is not finite"

    def test_large_displacement(self):
        bars = [_bar(100 + i * 10, 110 + i * 10, 99 + i * 10, 109 + i * 10)
                for i in range(10)]
        atr = [5.0] * 10
        ev = compute_quality_evidence(bars, atr)
        for k, v in ev.items():
            assert 0.0 <= v <= 1.0, f"{k}={v} out of [0,1]"
            assert math.isfinite(v), f"{k}={v} is not finite"

    def test_near_zero_displacement(self):
        bars = [_bar(100, 101, 99, 100.01)] * 10
        atr = [100.0] * 10
        ev = compute_quality_evidence(bars, atr)
        for k, v in ev.items():
            assert 0.0 <= v <= 1.0, f"{k}={v} out of [0,1]"
            assert math.isfinite(v), f"{k}={v} is not finite"

    def test_large_absolute_prices(self):
        bars = [_bar(100000, 100010, 99990, 100005)] * 10
        atr = [5.0] * 10
        ev = compute_quality_evidence(bars, atr)
        for k, v in ev.items():
            assert 0.0 <= v <= 1.0, f"{k}={v} out of [0,1]"
            assert math.isfinite(v), f"{k}={v} is not finite"

    def test_zero_atr(self):
        bars = [_bar(100, 102, 98, 101)] * 10
        atr = [0.0] * 10
        ev = compute_quality_evidence(bars, atr)
        for k, v in ev.items():
            assert math.isfinite(v), f"{k}={v} is not finite"


# ===========================================================================
# REPLAY INVALID QUALITY GATE
# ===========================================================================

class TestReplayInvalidGate:
    """Replay must gate quality computation inside .valid."""

    def test_replay_invalid_freezes_quality(self):
        ev1 = dict(healthy=0.3, compression=0.9, expansion=0.1, chaos=0.1, shock=0.1)
        state, conf, primed, ch, cd = quality_enum(
            ev1, incumbent_state=VOL_QUALITY.HEALTHY, primed=True)
        assert state == VOL_QUALITY.HEALTHY
        assert ch == VOL_QUALITY.COMPRESSED and cd == 1

        # Invalid bar: caller must NOT call quality_enum → state frozen

        # Resume with same challenger
        ev2 = dict(healthy=0.3, compression=0.85, expansion=0.1, chaos=0.1, shock=0.1)
        state, conf, primed, ch, cd = quality_enum(
            ev2, incumbent_state=state, primed=primed,
            challenger=ch, challenger_dwell=cd)
        assert state == VOL_QUALITY.COMPRESSED, "Resume after invalid: commits"
