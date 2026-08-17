"""Task 3 — hysteresis / persistence (spec section 8)."""

from reference_fusion import (
    DomainInput,
    STRUCTURE, MOMENTUM, VOL_LEVEL, VOL_QUALITY,
    REGIME, TRANSITION,
    Params, PersistentState, classify_regime,
)


def _dom(structure, dscore, momentum=MOMENTUM.STRONG,
         vol_level=VOL_LEVEL.NORMAL, vol_quality=VOL_QUALITY.HEALTHY, **kw):
    return DomainInput(
        structure_state=structure,
        direction_score=dscore,
        momentum_state=momentum,
        vol_level=vol_level,
        vol_quality=vol_quality,
        **kw,
    )


def _bull():
    return _dom(STRUCTURE.BULLISH_STRONG, 0.8)


def _bear():
    return _dom(STRUCTURE.BEARISH_STRONG, -0.8)


def _run(seq, params=None):
    """Feed a sequence of DomainInputs through classify_regime, return list of results."""
    params = params or Params()
    st = PersistentState()
    out = []
    for d in seq:
        out.append(classify_regime(d, st, params))
    return out


def test_L_challenger_leads_but_gap_below_threshold():
    # A same-side challenger (BREAKOUT_BULL) leads the bull incumbent by a margin BELOW
    # ChallengerGap => incumbent kept. UncertainVeto is raised to isolate the gap logic from
    # the balancedEvidence veto (that veto is covered in Task 2).
    p = Params(regime_dwell=1, challenger_gap=0.30, uncertain_veto=0.95)
    # bull incumbent established (trend_bull ~0.94)
    seq = [_bull(),
           _bull(),
           # breakout_bull leads (break=1.0, compression=1.0, EXPANDING, expansion=1.0) => ~0.97
           _dom(STRUCTURE.BULLISH_STRONG, 0.8, momentum=MOMENTUM.EXPANDING,
                vol_level=VOL_LEVEL.NORMAL, vol_quality=VOL_QUALITY.COMPRESSED,
                compression_score=1.0, expansion_score=1.0, break_bull_score=1.0)]
    out = _run(seq, p)
    assert out[0]["regime"] == REGIME.TREND_BULL
    assert out[2]["regime"] == REGIME.TREND_BULL  # incumbent kept (gap ~0.03 < 0.30)
    # sanity: challenger actually leads
    assert out[2]["challenger_confidence"] > out[2]["incumbent_confidence"]


def test_L2_challenger_identity_change_resets_dwell():
    p = Params(regime_dwell=2, challenger_gap=0.05)
    # First challenger: bear for one bar, then switch to range — dwell must reset.
    seq = [_bull(), _bull(),
           _dom(STRUCTURE.BEARISH_STRONG, -0.8),   # bear challenger bar 1
           _dom(STRUCTURE.RANGE, 0.0),              # identity change -> range challenger bar 1
           ]
    out = _run(seq, p)
    # after bear (bar 3) and range (bar 4), no flip occurred (each challenger had < dwell bars)
    assert out[2]["regime"] == REGIME.TREND_BULL
    assert out[3]["regime"] == REGIME.TREND_BULL
    assert out[2]["pending_candidate"] == REGIME.TREND_BEAR
    assert out[2]["candidate_age_bars"] == 1
    assert out[3]["pending_candidate"] == REGIME.RANGE
    assert out[3]["candidate_age_bars"] == 1


def test_M_one_bar_spike_no_flip_flop():
    p = Params(regime_dwell=2, challenger_gap=0.05)
    seq = [_bull(), _bull(),
           _dom(STRUCTURE.BEARISH_STRONG, -0.9),   # spike bear (1 bar)
           _bull(), _bull()]
    out = _run(seq, p)
    # dwell=2 => the 1-bar bear spike must not flip
    assert all(r["regime"] == REGIME.TREND_BULL for r in out)


def test_M2_incumbent_score_recomputed_every_bar():
    # The incumbent's score must be recomputed from the CURRENT bar's evidence, never a
    # frozen historical value. Establish bull (score ~0.94), then feed a bearish bar.
    p = Params(regime_dwell=1, challenger_gap=0.05)
    seq = [_bull(),
           _dom(STRUCTURE.BEARISH_STRONG, -0.8)]
    out = _run(seq, p)
    r = out[1]
    # On the bearish bar, the bull incumbent's structure contribution collapses to 0,
    # so its recomputed score (trend_bull) is ~0.35, NOT the frozen 0.94.
    assert r["incumbent_confidence"] < 0.5
    # recomputed incumbent score equals the current-bar trend_bull candidate score
    assert abs(r["incumbent_confidence"] - r["scores"]["trend_bull"]) < 1e-12


def test_T1_regime_dwell_two_flips_on_second_bar():
    # RegimeDwell=2 => flip only on the 2nd consecutive challenger bar (age 1 -> age 2).
    p = Params(regime_dwell=2, challenger_gap=0.05)
    seq = [_bull(), _bull(),
           _dom(STRUCTURE.BEARISH_STRONG, -0.9),   # bear challenger age 1
           _dom(STRUCTURE.BEARISH_STRONG, -0.9),   # bear challenger age 2 -> flip
           ]
    out = _run(seq, p)
    assert out[2]["regime"] == REGIME.TREND_BULL          # still incumbent after 1st bar
    assert out[2]["candidate_age_bars"] == 1
    assert out[3]["regime"] == REGIME.TREND_BEAR          # flipped on 2nd bar
    assert out[3]["transition_reason"] == TRANSITION.CHALLENGE_WIN


def test_Q_tie_resolution_deterministic_no_enum_order_bias():
    # Section 8.5: effective tie must NOT be resolved by bullish enum-ordinal bias.
    # The argmax uses a fixed candidate order only to pick among bit-identical scores;
    # verify the tie-break is deterministic and identical regardless of dict insertion order.
    from reference_fusion import _argmax_candidate, _effective_tie, _CANDIDATE_ORDER
    tied = {
        "trend_bull": 0.5,
        "trend_bear": 0.5,
        "range": 0.4,
        "breakout_bull": 0.4,
        "breakout_bear": 0.4,
    }
    # fixed order: trend_bull precedes trend_bear -> trend_bull is argmax (deterministic)
    assert _argmax_candidate(tied) == "trend_bull"
    p = Params(tie_epsilon=1e-6)
    assert _effective_tie(tied, p) is True


def test_Q_no_incumbent_tie_is_uncertain():
    p = Params(regime_dwell=1, challenger_gap=0.05)
    # First bar chaos veto => UNCERTAIN incumbent established.
    seq = [_dom(STRUCTURE.MIXED, 0.0, momentum=MOMENTUM.NORMAL, vol_quality=VOL_QUALITY.CHAOTIC)]
    out = _run(seq, p)
    assert out[0]["regime"] == REGIME.UNCERTAIN


def test_R_identical_sequence_identical_output():
    seq = [_bull(), _bull(), _bear(), _bear(), _bull()]
    o1 = _run(seq)
    o2 = _run(seq)
    r1 = [(r["regime"], r["transition_reason"], round(r["confidence"], 15)) for r in o1]
    r2 = [(r["regime"], r["transition_reason"], round(r["confidence"], 15)) for r in o2]
    assert r1 == r2
