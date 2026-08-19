"""Volatility Quality evidence + persistence tests.

Tests cover:
- Compression evidence (ATR decline, range shrink, body shrink)
- Expansion evidence (ATR rise, range/body/efficiency/displacement)
- Direction-agnostic quality (bull/bear mirrors)
- Score bounding [0,1] for all edge cases
- Quality persistence with challenger dwell
- Replay invalid quality gate
"""
import math
import pytest
from reference_volatility import (
    quality_enum, VOL_QUALITY, QUALITY_GAP, QUALITY_DWELL,
    compute_compression_score, compute_expansion_score,
)


# ---------------------------------------------------------------------------
# Helper: build fixture OHLC bars
# ---------------------------------------------------------------------------
def _bar(o, h, l, c):
    return {"open": o, "high": h, "low": l, "close": c}


def _mirror_bull_bear(bull_bars):
    """Return bear-mirrored bars: OHLC reflected around mid = (H+L)/2."""
    bear = []
    for b in bull_bars:
        mid = (b["high"] + b["low"]) / 2.0
        bear.append({
            "open": 2 * mid - b["open"],
            "high": 2 * mid - b["high"],
            "low": 2 * mid - b["low"],
            "close": 2 * mid - b["close"],
        })
    return bear


# ===========================================================================
# COMPRESSION EVIDENCE — isolated component tests
# ===========================================================================

class TestCompressionEvidence:
    """Compression = mean(atrDecline, rangeShrink, bodyShrink)."""

    def test_atr_decline_only(self):
        """ATR declining with constant range/body → compressionScore > 0."""
        # Simulate: recent ATR lower than prior ATR, range/body constant
        atr_recent = [1.0, 0.9, 0.8, 0.7, 0.6]
        atr_prior = [1.5, 1.4, 1.3, 1.2, 1.1]
        range_recent = [10.0] * 5
        range_prior = [10.0] * 5
        body_recent = [5.0] * 5
        body_prior = [5.0] * 5

        score = compute_compression_score(atr_recent, atr_prior,
                                          range_recent, range_prior,
                                          body_recent, body_prior)
        assert score > 0.0, "ATR declining should produce positive compression"
        assert score <= 1.0

    def test_range_shrink_only(self):
        """Range shrinking with constant ATR/body → compressionScore > 0."""
        atr_recent = [1.0] * 5
        atr_prior = [1.0] * 5
        range_recent = [5.0, 4.0, 3.0, 2.5, 2.0]
        range_prior = [10.0, 10.0, 10.0, 10.0, 10.0]
        body_recent = [5.0] * 5
        body_prior = [5.0] * 5

        score = compute_compression_score(atr_recent, atr_prior,
                                          range_recent, range_prior,
                                          body_recent, body_prior)
        assert score > 0.0, "Range shrinking should produce positive compression"
        assert score <= 1.0

    def test_body_shrink_only(self):
        """Body shrinking with constant ATR/range → compressionScore > 0."""
        atr_recent = [1.0] * 5
        atr_prior = [1.0] * 5
        range_recent = [10.0] * 5
        range_prior = [10.0] * 5
        body_recent = [2.0, 1.5, 1.0, 0.8, 0.5]
        body_prior = [5.0] * 5

        score = compute_compression_score(atr_recent, atr_prior,
                                          range_recent, range_prior,
                                          body_recent, body_prior)
        assert score > 0.0, "Body shrinking should produce positive compression"
        assert score <= 1.0

    def test_all_three_compression(self):
        """ATR decline + range shrink + body shrink → high compressionScore."""
        atr_recent = [0.5, 0.4, 0.3, 0.2, 0.1]
        atr_prior = [2.0, 2.0, 2.0, 2.0, 2.0]
        range_recent = [3.0, 2.5, 2.0, 1.5, 1.0]
        range_prior = [15.0, 15.0, 15.0, 15.0, 15.0]
        body_recent = [1.0, 0.8, 0.6, 0.4, 0.2]
        body_prior = [8.0, 8.0, 8.0, 8.0, 8.0]

        score = compute_compression_score(atr_recent, atr_prior,
                                          range_recent, range_prior,
                                          body_recent, body_prior)
        assert score > 0.5, f"All three declining should give high compression, got {score}"
        assert score <= 1.0

    def test_no_compression(self):
        """No compression signals → compressionScore ≈ 0."""
        atr_recent = [1.0] * 5
        atr_prior = [1.0] * 5
        range_recent = [10.0] * 5
        range_prior = [10.0] * 5
        body_recent = [5.0] * 5
        body_prior = [5.0] * 5

        score = compute_compression_score(atr_recent, atr_prior,
                                          range_recent, range_prior,
                                          body_recent, body_prior)
        assert score == 0.0, f"No compression should give 0, got {score}"


# ===========================================================================
# EXPANSION EVIDENCE — isolated component tests
# ===========================================================================

class TestExpansionEvidence:
    """Expansion = mean(atrRise, rangeExpand, bodyExpand, efficiencyRise, displacementRise)."""

    def test_atr_rise_only(self):
        """ATR rising → expansionScore > 0."""
        atr_recent = [1.5, 1.6, 1.7, 1.8, 2.0]
        atr_prior = [1.0, 1.0, 1.0, 1.0, 1.0]
        range_recent = [10.0] * 5
        range_prior = [10.0] * 5
        body_recent = [5.0] * 5
        body_prior = [5.0] * 5
        eff_recent = [0.5] * 5
        eff_prior = [0.5] * 5
        disp_recent = [0.3] * 5
        disp_prior = [0.3] * 5

        score = compute_expansion_score(atr_recent, atr_prior,
                                        range_recent, range_prior,
                                        body_recent, body_prior,
                                        eff_recent, eff_prior,
                                        disp_recent, disp_prior)
        assert score > 0.0, "ATR rising should produce positive expansion"
        assert score <= 1.0

    def test_range_expand_only(self):
        """Range expanding → expansionScore > 0."""
        atr_recent = [1.0] * 5
        atr_prior = [1.0] * 5
        range_recent = [15.0, 16.0, 17.0, 18.0, 20.0]
        range_prior = [10.0] * 5
        body_recent = [5.0] * 5
        body_prior = [5.0] * 5
        eff_recent = [0.5] * 5
        eff_prior = [0.5] * 5
        disp_recent = [0.3] * 5
        disp_prior = [0.3] * 5

        score = compute_expansion_score(atr_recent, atr_prior,
                                        range_recent, range_prior,
                                        body_recent, body_prior,
                                        eff_recent, eff_prior,
                                        disp_recent, disp_prior)
        assert score > 0.0, "Range expanding should produce positive expansion"
        assert score <= 1.0

    def test_body_expand_only(self):
        """Body expanding → expansionScore > 0."""
        atr_recent = [1.0] * 5
        atr_prior = [1.0] * 5
        range_recent = [10.0] * 5
        range_prior = [10.0] * 5
        body_recent = [6.0, 7.0, 8.0, 9.0, 10.0]
        body_prior = [4.0] * 5
        eff_recent = [0.5] * 5
        eff_prior = [0.5] * 5
        disp_recent = [0.3] * 5
        disp_prior = [0.3] * 5

        score = compute_expansion_score(atr_recent, atr_prior,
                                        range_recent, range_prior,
                                        body_recent, body_prior,
                                        eff_recent, eff_prior,
                                        disp_recent, disp_prior)
        assert score > 0.0, "Body expanding should produce positive expansion"
        assert score <= 1.0

    def test_efficiency_rise_only(self):
        """Efficiency magnitude rising → expansionScore > 0."""
        atr_recent = [1.0] * 5
        atr_prior = [1.0] * 5
        range_recent = [10.0] * 5
        range_prior = [10.0] * 5
        body_recent = [5.0] * 5
        body_prior = [5.0] * 5
        eff_recent = [0.7, 0.75, 0.8, 0.85, 0.9]
        eff_prior = [0.4] * 5
        disp_recent = [0.3] * 5
        disp_prior = [0.3] * 5

        score = compute_expansion_score(atr_recent, atr_prior,
                                        range_recent, range_prior,
                                        body_recent, body_prior,
                                        eff_recent, eff_prior,
                                        disp_recent, disp_prior)
        assert score > 0.0, "Efficiency rising should produce positive expansion"
        assert score <= 1.0

    def test_displacement_rise_only(self):
        """Absolute displacement rising → expansionScore > 0."""
        atr_recent = [1.0] * 5
        atr_prior = [1.0] * 5
        range_recent = [10.0] * 5
        range_prior = [10.0] * 5
        body_recent = [5.0] * 5
        body_prior = [5.0] * 5
        eff_recent = [0.5] * 5
        eff_prior = [0.5] * 5
        disp_recent = [0.5, 0.6, 0.7, 0.8, 0.9]
        disp_prior = [0.2] * 5

        score = compute_expansion_score(atr_recent, atr_prior,
                                        range_recent, range_prior,
                                        body_recent, body_prior,
                                        eff_recent, eff_prior,
                                        disp_recent, disp_prior)
        assert score > 0.0, "Displacement rising should produce positive expansion"
        assert score <= 1.0

    def test_all_five_expansion(self):
        """All five components rising → high expansionScore."""
        atr_recent = [1.5, 1.6, 1.7, 1.8, 2.0]
        atr_prior = [1.0] * 5
        range_recent = [15.0, 16.0, 17.0, 18.0, 20.0]
        range_prior = [10.0] * 5
        body_recent = [6.0, 7.0, 8.0, 9.0, 10.0]
        body_prior = [4.0] * 5
        eff_recent = [0.7, 0.75, 0.8, 0.85, 0.9]
        eff_prior = [0.4] * 5
        disp_recent = [0.5, 0.6, 0.7, 0.8, 0.9]
        disp_prior = [0.2] * 5

        score = compute_expansion_score(atr_recent, atr_prior,
                                        range_recent, range_prior,
                                        body_recent, body_prior,
                                        eff_recent, eff_prior,
                                        disp_recent, disp_prior)
        assert score > 0.5, f"All five rising should give high expansion, got {score}"
        assert score <= 1.0


# ===========================================================================
# DIRECTION-AGNOSTIC QUALITY
# ===========================================================================

class TestDirectionAgnosticQuality:
    """Bull/bear mirrored OHLC must produce identical quality evidence."""

    def test_bull_bear_mirror_equal(self):
        """Bull and bear bars produce identical compressionScore."""
        bull_bars = [
            _bar(100, 105, 98, 103),
            _bar(103, 108, 101, 106),
            _bar(106, 110, 104, 108),
            _bar(108, 112, 106, 110),
            _bar(110, 115, 108, 113),
            _bar(113, 118, 111, 116),
            _bar(116, 120, 114, 118),
            _bar(118, 122, 116, 120),
            _bar(120, 125, 118, 123),
            _bar(123, 128, 121, 126),
        ]
        bear_bars = _mirror_bull_bear(bull_bars)

        bull_comp = compute_compression_score(
            [1.0] * 5, [1.0] * 5, [10.0] * 5, [10.0] * 5, [5.0] * 5, [5.0] * 5)
        bear_comp = compute_compression_score(
            [1.0] * 5, [1.0] * 5, [10.0] * 5, [10.0] * 5, [5.0] * 5, [5.0] * 5)
        assert bull_comp == bear_comp, "Compression must be direction-agnostic"

    def test_quality_bull_bear_identical_scores(self):
        """quality_enum with identical evidence dicts → same result regardless of direction context."""
        ev = dict(healthy=0.2, compression=0.8, expansion=0.1, chaos=0.1, shock=0.1)
        # Same evidence = same result, direction doesn't matter
        r1 = quality_enum(ev)
        r2 = quality_enum(ev)
        assert r1 == r2


# ===========================================================================
# SCORE BOUNDING — adversarial edge cases
# ===========================================================================

class TestScoreBounding:
    """All quality scores strictly [0,1], no NaN/INF."""

    def test_high_wick_extreme(self):
        """High wick (range >> body) doesn't break bounds."""
        from reference_volatility import compute_quality_evidence
        bars = [_bar(100, 200, 90, 101)] * 10  # huge wick
        atr = [50.0] * 10
        ev = compute_quality_evidence(bars, atr)
        for k, v in ev.items():
            assert 0.0 <= v <= 1.0, f"{k}={v} out of [0,1]"
            assert math.isfinite(v), f"{k}={v} is not finite"

    def test_extreme_atr(self):
        """Extreme ATR ratio doesn't break bounds."""
        from reference_volatility import compute_quality_evidence
        bars = [_bar(100, 102, 98, 101)] * 10
        atr = [1000.0] * 10  # extreme
        ev = compute_quality_evidence(bars, atr)
        for k, v in ev.items():
            assert 0.0 <= v <= 1.0, f"{k}={v} out of [0,1]"
            assert math.isfinite(v), f"{k}={v} is not finite"

    def test_zero_efficiency(self):
        """Zero efficiency (close == open) doesn't break bounds."""
        from reference_volatility import compute_quality_evidence
        bars = [_bar(100, 102, 98, 100)] * 10  # close == open
        atr = [2.0] * 10
        ev = compute_quality_evidence(bars, atr)
        for k, v in ev.items():
            assert 0.0 <= v <= 1.0, f"{k}={v} out of [0,1]"
            assert math.isfinite(v), f"{k}={v} is not finite"

    def test_near_zero_range(self):
        """Near-zero range doesn't break bounds."""
        from reference_volatility import compute_quality_evidence
        bars = [_bar(100, 100.001, 99.999, 100)] * 10
        atr = [0.001] * 10
        ev = compute_quality_evidence(bars, atr)
        for k, v in ev.items():
            assert 0.0 <= v <= 1.0, f"{k}={v} out of [0,1]"
            assert math.isfinite(v), f"{k}={v} is not finite"

    def test_zero_atr(self):
        """Zero ATR doesn't produce NaN/INF."""
        from reference_volatility import compute_quality_evidence
        bars = [_bar(100, 102, 98, 101)] * 10
        atr = [0.0] * 10
        ev = compute_quality_evidence(bars, atr)
        for k, v in ev.items():
            assert math.isfinite(v), f"{k}={v} is not finite"


# ===========================================================================
# QUALITY PERSISTENCE — challenger dwell
# ===========================================================================

class TestQualityPersistence:
    """Quality persistence with challenger identity + dwell."""

    def test_incumbent_held_by_insufficient_gap(self):
        """best != incumbent but gap < QUALITY_GAP → retain incumbent."""
        inc = (VOL_QUALITY.HEALTHY, 0.8, 0)
        ev = dict(healthy=0.8, compression=0.85, expansion=0.1, chaos=0.1, shock=0.1)
        # gap = 0.85 - 0.8 = 0.05 < 0.10
        state, conf, ch, cd = quality_enum(
            ev, incumbent_state=inc[0], incumbent_conf=inc[1],
            incumbent_dwell=inc[2])
        assert state == VOL_QUALITY.HEALTHY, "Insufficient gap: retain incumbent"

    def test_challenger_bar1_held(self):
        """Challenger with sufficient gap → dwell=1, not committed."""
        ev = dict(healthy=0.3, compression=0.9, expansion=0.1, chaos=0.1, shock=0.1)
        state, conf, ch, cd = quality_enum(
            ev, incumbent_state=VOL_QUALITY.HEALTHY, incumbent_conf=0.3,
            incumbent_dwell=0)
        # gap = 0.9 - 0.3 = 0.6 >= 0.10, but dwell starts at 0 → challenger
        assert state == VOL_QUALITY.HEALTHY, "First challenger bar: hold incumbent"
        assert ch == VOL_QUALITY.COMPRESSED
        assert cd == 1

    def test_challenger_bar2_commits(self):
        """Same challenger bar #2 → dwell=2 >= VOLQ_DWELL → commit."""
        ev1 = dict(healthy=0.3, compression=0.9, expansion=0.1, chaos=0.1, shock=0.1)
        state, conf, ch, cd = quality_enum(
            ev1, incumbent_state=VOL_QUALITY.HEALTHY, incumbent_conf=0.3,
            incumbent_dwell=0)
        assert state == VOL_QUALITY.HEALTHY and ch == VOL_QUALITY.COMPRESSED and cd == 1

        ev2 = dict(healthy=0.3, compression=0.85, expansion=0.1, chaos=0.1, shock=0.1)
        state, conf, ch, cd = quality_enum(
            ev2, incumbent_state=state, incumbent_conf=conf,
            incumbent_dwell=0, challenger=ch, challenger_dwell=cd)
        assert state == VOL_QUALITY.COMPRESSED, "Second challenger bar: commit"
        assert cd == 0, "Challenger reset after commit"

    def test_challenger_interruption_resets(self):
        """Different challenger resets dwell."""
        ev1 = dict(healthy=0.3, compression=0.9, expansion=0.1, chaos=0.1, shock=0.1)
        state, conf, ch, cd = quality_enum(
            ev1, incumbent_state=VOL_QUALITY.HEALTHY, incumbent_conf=0.3,
            incumbent_dwell=0)
        assert ch == VOL_QUALITY.COMPRESSED and cd == 1

        # Different challenger (EXPANDING)
        ev2 = dict(healthy=0.1, compression=0.3, expansion=0.9, chaos=0.1, shock=0.1)
        state, conf, ch, cd = quality_enum(
            ev2, incumbent_state=state, incumbent_conf=conf,
            incumbent_dwell=0, challenger=ch, challenger_dwell=cd)
        assert ch == VOL_QUALITY.EXPANDING, "Different challenger: resets dwell"
        assert cd == 1

    def test_incumbent_recovery_clears(self):
        """best == incumbent → clear pending challenger."""
        ev1 = dict(healthy=0.3, compression=0.9, expansion=0.1, chaos=0.1, shock=0.1)
        state, conf, ch, cd = quality_enum(
            ev1, incumbent_state=VOL_QUALITY.HEALTHY, incumbent_conf=0.3,
            incumbent_dwell=0)
        assert ch == VOL_QUALITY.COMPRESSED and cd == 1

        # Incumbent recovers
        ev2 = dict(healthy=0.9, compression=0.3, expansion=0.1, chaos=0.1, shock=0.1)
        state, conf, ch, cd = quality_enum(
            ev2, incumbent_state=state, incumbent_conf=conf,
            incumbent_dwell=0, challenger=ch, challenger_dwell=cd)
        assert state == VOL_QUALITY.HEALTHY
        assert ch == VOL_QUALITY.HEALTHY, "Incumbent recovery: clear challenger"
        assert cd == 0

    def test_invalid_freezes_challenger(self):
        """Caller skipping quality classify freezes all persistence."""
        ev1 = dict(healthy=0.3, compression=0.9, expansion=0.1, chaos=0.1, shock=0.1)
        state, conf, ch, cd = quality_enum(
            ev1, incumbent_state=VOL_QUALITY.HEALTHY, incumbent_conf=0.3,
            incumbent_dwell=0)
        assert ch == VOL_QUALITY.COMPRESSED and cd == 1

        # Caller skips: dwell stays 1 (frozen)
        assert cd == 1, "Challenger dwell frozen during skip"

        # Resume: same challenger bar #2 → commit
        ev2 = dict(healthy=0.3, compression=0.85, expansion=0.1, chaos=0.1, shock=0.1)
        state, conf, ch, cd = quality_enum(
            ev2, incumbent_state=state, incumbent_conf=conf,
            incumbent_dwell=0, challenger=ch, challenger_dwell=cd)
        assert state == VOL_QUALITY.COMPRESSED, "Resume: commits"


# ===========================================================================
# REPLAY INVALID QUALITY GATE
# ===========================================================================

class TestReplayInvalidGate:
    """Replay must gate quality computation inside .valid."""

    def test_replay_invalid_freezes_quality(self):
        """valid challenger bar #1, invalid bar, valid same challenger bar #2 → frozen."""
        ev1 = dict(healthy=0.3, compression=0.9, expansion=0.1, chaos=0.1, shock=0.1)
        state, conf, ch, cd = quality_enum(
            ev1, incumbent_state=VOL_QUALITY.HEALTHY, incumbent_conf=0.3,
            incumbent_dwell=0)
        assert state == VOL_QUALITY.HEALTHY
        assert ch == VOL_QUALITY.COMPRESSED and cd == 1

        # Invalid bar: caller must NOT call quality_enum → state frozen
        # (In production, this means VolatilityQualityEngine is skipped)

        # Resume with same challenger
        ev2 = dict(healthy=0.3, compression=0.85, expansion=0.1, chaos=0.1, shock=0.1)
        state, conf, ch, cd = quality_enum(
            ev2, incumbent_state=state, incumbent_conf=conf,
            incumbent_dwell=0, challenger=ch, challenger_dwell=cd)
        assert state == VOL_QUALITY.COMPRESSED, "Resume after invalid: commits"
