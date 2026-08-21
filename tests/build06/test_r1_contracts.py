import copy

import pytest
import reference_fusion

from reference_fusion import (
    CompressionMemory,
    DEGRADED_DIRECTION,
    DEGRADED_MOMENTUM,
    DEGRADED_STRUCTURE,
    DEGRADED_VOLATILITY,
    DIRECTION,
    DomainInput,
    MOMENTUM,
    Params,
    PersistentState,
    REGIME,
    REGIME_QUALITY,
    STRUCTURE,
    TRANSITION,
    VOL_LEVEL,
    VOL_QUALITY,
    b06_signature,
    break_recency_score,
    cold_replay,
    compute_candidate_scores,
    live_update,
    update_fusion,
)


def dom(**overrides):
    values = dict(
        structure_state=STRUCTURE.BULLISH_STRONG,
        direction_state=DIRECTION.STRONG_BULL,
        direction_score=0.8,
        momentum_state=MOMENTUM.STRONG,
        vol_level=VOL_LEVEL.NORMAL,
        vol_quality=VOL_QUALITY.HEALTHY,
        structure_valid=True,
        direction_valid=True,
        momentum_valid=True,
        volatility_valid=True,
        critical_core_valid=True,
    )
    values.update(overrides)
    return DomainInput(**values)


@pytest.mark.parametrize(
    "flag,bit,changed",
    [
        ("structure_valid", DEGRADED_STRUCTURE, {"structure_state": STRUCTURE.BULLISH_STRONG, "break_bull_score": 1.0}),
        ("direction_valid", DEGRADED_DIRECTION, {"direction_state": DIRECTION.STRONG_BULL, "direction_score": 1.0}),
        ("momentum_valid", DEGRADED_MOMENTUM, {"momentum_state": MOMENTUM.EXPANDING}),
        ("volatility_valid", DEGRADED_VOLATILITY, {"vol_level": VOL_LEVEL.NORMAL, "vol_quality": VOL_QUALITY.HEALTHY, "compression_score": 1.0, "expansion_score": 1.0}),
    ],
)
def test_invalid_domain_is_zeroed_and_degraded(flag, bit, changed):
    invalid = dom(**changed, **{flag: False})
    stale_other = dom(**{flag: False})
    assert compute_candidate_scores(invalid) == compute_candidate_scores(stale_other)
    result = update_fusion(invalid, PersistentState(), Params())
    assert result["valid"] is True
    assert result["degraded_domains"] == bit
    assert result["evidence_completeness"] == 0.75


def test_adx_helper_degraded_does_not_invalidate_momentum():
    result = update_fusion(dom(adx_helper_degraded=True), PersistentState(), Params())
    assert result["valid"] is True
    assert result["degraded_domains"] == 0
    assert result["evidence_completeness"] == 1.0


def test_explicit_critical_core_is_independent_and_resets():
    result = update_fusion(dom(critical_core_valid=False), PersistentState(), Params())
    assert result["valid"] is False
    assert result["regime"] == REGIME.UNCERTAIN
    assert result["evidence_completeness"] == 0.0
    assert result["quality"] == REGIME_QUALITY.WEAK
    assert result["confidence"] == 0.0
    assert result["transition_reason"] == TRANSITION.RESET


def test_invalid_stale_values_do_not_trigger_hard_vetoes():
    stale_conflict = dom(structure_valid=False, structure_state=STRUCTURE.BULLISH_STRONG,
                         direction_state=DIRECTION.STRONG_BEAR, direction_score=-0.8)
    assert update_fusion(stale_conflict, PersistentState(), Params())["transition_reason"] != TRANSITION.OVERRIDE
    stale_chaos = dom(volatility_valid=False, vol_quality=VOL_QUALITY.CHAOTIC,
                      direction_valid=False, direction_state=DIRECTION.NEUTRAL, direction_score=0.0)
    assert update_fusion(stale_chaos, PersistentState(), Params())["transition_reason"] != TRANSITION.OVERRIDE


def test_range_eligibility_masks_selection_but_preserves_raw_score():
    d = dom(structure_state=STRUCTURE.RANGE, direction_state=DIRECTION.NEUTRAL,
            direction_score=0.0, momentum_state=MOMENTUM.NORMAL,
            vol_quality=VOL_QUALITY.SHOCK)
    raw = compute_candidate_scores(d)
    result = update_fusion(d, PersistentState(), Params(uncertain_veto=1.1))
    assert raw["range"] == result["scores"]["range"]
    assert result["regime"] != REGIME.RANGE


@pytest.mark.parametrize(
    "incumbent,break_key,break_state,direction_state,direction_score",
    [
        (REGIME.TREND_BULL, "break_bull_score", STRUCTURE.BULLISH_WEAK, DIRECTION.BULL, 0.7),
        (REGIME.TREND_BEAR, "break_bear_score", STRUCTURE.BEARISH_WEAK, DIRECTION.BEAR, -0.7),
    ],
)
def test_stable_trend_makes_same_side_breakout_ineligible(incumbent, break_key, break_state, direction_state, direction_score):
    state = PersistentState()
    state.initialized = True
    state.regime = incumbent
    state.regime_age_bars = 4
    d = dom(structure_state=break_state, direction_state=direction_state,
            direction_score=direction_score, momentum_state=MOMENTUM.EXPANDING,
            vol_quality=VOL_QUALITY.COMPRESSED, compression_score=1.0,
            expansion_score=1.0, **{break_key: 1.0})
    result = update_fusion(d, state, Params(regime_dwell=1, challenger_gap=0.0, uncertain_veto=1.1))
    assert max(result["scores"], key=result["scores"].get).startswith("breakout")
    assert result["regime"] == incumbent


@pytest.mark.parametrize("lookback", [2, 5])
def test_break_recency_uses_parameter_boundaries(lookback):
    assert break_recency_score(0, lookback) == 1.0
    assert break_recency_score(1, lookback) == (0.4 if lookback > 1 else 0.0)
    assert break_recency_score(lookback - 1, lookback) == 0.4
    assert break_recency_score(lookback, lookback) == 0.0


def test_maturation_uses_direction_enum_not_direction_score():
    state = PersistentState()
    state.initialized = True
    state.regime = REGIME.BREAKOUT_BULL
    state.regime_age_bars = 1
    d = dom(direction_state=DIRECTION.NEUTRAL, direction_score=0.9)
    result = update_fusion(d, state, Params(breakout_maturation_min_bars=2, breakout_max_age_bars=9))
    assert result["regime"] == REGIME.BREAKOUT_BULL


def test_opposing_breakout_failure_remains_score_threshold_based():
    state = PersistentState()
    state.initialized = True
    state.regime = REGIME.BREAKOUT_BULL
    state.regime_age_bars = 1
    d = dom(structure_state=STRUCTURE.MIXED, direction_state=DIRECTION.STRONG_BEAR,
            direction_score=-0.2, momentum_state=MOMENTUM.NORMAL)
    result = update_fusion(d, state, Params(breakout_maturation_min_bars=99, breakout_max_age_bars=9))
    assert result["regime"] == REGIME.BREAKOUT_BULL


def test_invalid_stale_domains_cannot_fail_breakout_or_enter_compression_memory():
    state = PersistentState()
    state.initialized = True
    state.regime = REGIME.BREAKOUT_BULL
    state.regime_age_bars = 1
    memory = CompressionMemory()
    d = dom(structure_valid=False, structure_state=STRUCTURE.BEARISH_STRONG,
            direction_valid=False, direction_score=-1.0,
            volatility_valid=False, compression_score=1.0)
    result = update_fusion(d, state, Params(breakout_maturation_min_bars=99,
                           breakout_max_age_bars=9), compression_memory=memory)
    assert result["regime"] == REGIME.BREAKOUT_BULL
    assert memory.contents() == []


def test_uncertain_incumbent_effective_tie_has_no_fake_challenge():
    state = PersistentState()
    state.initialized = True
    state.regime = REGIME.UNCERTAIN
    state.regime_age_bars = 7
    state.pending_candidate = REGIME.TREND_BULL
    state.candidate_age_bars = 2
    d = dom(structure_state=STRUCTURE.UNKNOWN, direction_state=DIRECTION.NEUTRAL,
            direction_score=0.0, momentum_state=MOMENTUM.DECAYING,
            vol_level=VOL_LEVEL.EXTREME, vol_quality=VOL_QUALITY.HEALTHY,
            structure_valid=False, direction_valid=False, momentum_valid=False,
            volatility_valid=False)
    result = update_fusion(d, state, Params(tie_epsilon=1.0, uncertain_veto=1.1))
    assert result["regime"] == REGIME.UNCERTAIN
    assert result["transition_reason"] == TRANSITION.NONE
    assert result["pending_candidate"] is None
    assert result["candidate_age_bars"] == 0
    assert result["regime_age_bars"] == 8


def test_signature_includes_initialized_hidden_state():
    d = dom()
    state = PersistentState()
    memory = CompressionMemory()
    result = update_fusion(d, state, Params(), compression_memory=memory)
    other = copy.copy(state)
    other.initialized = not state.initialized
    assert b06_signature(result, state, memory) != b06_signature(result, other, memory)


def test_live_and_cold_replay_are_distinct_paths_and_reconstruct_all_state():
    history = [
        dom(compression_score=0.9),
        dom(structure_state=STRUCTURE.MIXED, direction_state=DIRECTION.BULL,
            direction_score=0.7, momentum_state=MOMENTUM.EXPANDING,
            vol_quality=VOL_QUALITY.EXPANDING, expansion_score=1.0,
            break_bull_score=1.0),
        dom(structure_valid=False, structure_state=STRUCTURE.BEARISH_STRONG),
    ]
    params = Params()
    live_state, live_memory, live_result = PersistentState(), CompressionMemory(), None
    for observation in history:
        live_result = live_update(observation, live_state, params, live_memory)
    replay_state, replay_memory, replay_result = cold_replay(history, params)
    replay2_state, replay2_memory, replay2_result = cold_replay(history, params)
    assert live_result == replay_result
    assert vars(live_state) == vars(replay_state)
    assert live_memory.contents() == replay_memory.contents()
    live_sig = b06_signature(live_result, live_state, live_memory)
    assert live_sig == b06_signature(replay_result, replay_state, replay_memory)
    assert live_sig == b06_signature(replay2_result, replay2_state, replay2_memory)
    assert replay_result["degraded_domains"] == DEGRADED_STRUCTURE


def test_breakout_invalid_volatility_stale_chaos_does_not_change_result():
    def run(vol_level, vol_quality):
        state = PersistentState()
        state.initialized = True
        state.regime = REGIME.BREAKOUT_BULL
        state.regime_age_bars = 1
        return update_fusion(
            dom(volatility_valid=False, vol_level=vol_level, vol_quality=vol_quality),
            state,
            Params(breakout_maturation_min_bars=99, breakout_max_age_bars=9),
        )
    stale = run(VOL_LEVEL.EXTREME, VOL_QUALITY.CHAOTIC)
    neutral = run(VOL_LEVEL.LOW, VOL_QUALITY.HEALTHY)
    assert stale == neutral


@pytest.mark.parametrize(
    "field,value",
    [
        ("structure_valid", None),
        ("direction_valid", 1),
        ("momentum_valid", "true"),
        ("volatility_valid", 0),
        ("critical_core_valid", None),
    ],
)
def test_validity_contract_rejects_malformed_bool(field, value):
    with pytest.raises(TypeError):
        dom(**{field: value})


def test_validity_and_direction_contract_fields_are_required():
    values = dict(
        structure_state=STRUCTURE.BULLISH_STRONG,
        direction_score=0.8,
        momentum_state=MOMENTUM.STRONG,
        vol_level=VOL_LEVEL.NORMAL,
        vol_quality=VOL_QUALITY.HEALTHY,
    )
    with pytest.raises(TypeError):
        DomainInput(**values)


def test_ineligible_range_cannot_create_soft_uncertainty_challenger():
    state = PersistentState()
    state.initialized = True
    state.regime = REGIME.TREND_BULL
    state.regime_age_bars = 3
    result = update_fusion(
        dom(structure_state=STRUCTURE.RANGE, direction_state=DIRECTION.NEUTRAL,
            direction_score=0.0, momentum_state=MOMENTUM.NORMAL,
            vol_quality=VOL_QUALITY.SHOCK),
        state,
        Params(regime_dwell=1, uncertain_veto=0.55),
    )
    assert result["pending_candidate"] != REGIME.RANGE
    assert result["challenger_confidence"] != result["scores"]["range"]


def test_cold_replay_uses_distinct_ingestion_and_validates_chronology(monkeypatch):
    calls = []
    original = reference_fusion.replay_ingest

    def traced(observation, state, params, memory):
        calls.append(observation.closed_h1)
        return original(observation, state, params, memory)

    monkeypatch.setattr(reference_fusion, "replay_ingest", traced)
    history = [dom(), dom()]
    history[0].closed_h1 = 1
    history[1].closed_h1 = 2
    cold_replay(history, Params())
    assert calls == [1, 2]
    with pytest.raises(ValueError):
        cold_replay(list(reversed(history)), Params())


def test_signature_fixed_canonical_vector_and_hidden_field_mutations():
    state = PersistentState()
    memory = CompressionMemory(4)
    result = update_fusion(dom(), state, Params(), compression_memory=memory)
    assert reference_fusion.b06_canonical(result, state, memory) == (
        "v=B06D1;regime=0;quality=2;confidence=0.940000000000000;valid=1;"
        "initialized=1;age=1;prev=5;candAge=0;pend=NONE;tx=1;"
        "su=0.000000000000000;sTB=0.940000000000000;sTBe=0.350000000000000;"
        "sR=0.235000000000000;sBB=0.260000000000000;sBBe=0.140000000000000;"
        "mda=0.000000000000000;cm_count=1;cm_obs=0.000000000000000;"
    )
    mutations = {
        "regime": REGIME.TREND_BEAR,
        "previous_regime": REGIME.RANGE,
        "regime_age_bars": 8,
        "pending_candidate": REGIME.RANGE,
        "candidate_age_bars": 2,
        "initialized": False,
    }
    baseline = b06_signature(result, state, memory)
    for field, value in mutations.items():
        changed = copy.copy(state)
        setattr(changed, field, value)
        assert b06_signature(result, changed, memory) != baseline


def test_critical_invalid_bar_is_observational_reset_without_state_or_memory_contamination():
    params = Params()
    state = PersistentState()
    state.initialized = True
    state.regime = REGIME.TREND_BULL
    state.previous_regime = REGIME.RANGE
    state.regime_age_bars = 6
    state.pending_candidate = REGIME.TREND_BEAR
    state.candidate_age_bars = 1
    memory = CompressionMemory(4)
    memory.append(0.2)
    before_state = vars(state).copy()
    before_fifo = memory.contents()
    before_result = update_fusion(dom(), copy.copy(state), params,
                                  compression_memory=copy.deepcopy(memory))
    before_signature = b06_signature(before_result, state, memory)

    invalid = dom(critical_core_valid=False, volatility_valid=True,
                  compression_score=1.0)
    reset = update_fusion(invalid, state, params, compression_memory=memory)

    assert reset["valid"] is False
    assert reset["transition_reason"] == TRANSITION.RESET
    assert vars(state) == before_state
    assert memory.contents() == before_fifo
    assert b06_signature(before_result, state, memory) == before_signature

    breakout = dom(structure_state=STRUCTURE.MIXED, direction_state=DIRECTION.BULL,
                   direction_score=0.7, momentum_state=MOMENTUM.EXPANDING,
                   vol_quality=VOL_QUALITY.EXPANDING, expansion_score=1.0,
                   break_bull_score=1.0)
    contaminated_score = update_fusion(breakout, copy.copy(state), params,
                                       compression_memory=copy.deepcopy(memory))["scores"]["breakout_bull"]
    clean_memory = CompressionMemory(4)
    clean_memory.append(0.2)
    clean_score = update_fusion(breakout, copy.copy(state), params,
                                compression_memory=clean_memory)["scores"]["breakout_bull"]
    assert contaminated_score == clean_score

    replay_state, replay_memory, _ = cold_replay([invalid], params)
    assert vars(replay_state) == vars(PersistentState())
    assert replay_memory.contents() == []


def test_valid_override_cannot_bypass_false_critical_core():
    result = update_fusion(dom(critical_core_valid=False), PersistentState(),
                           Params(), valid=True)
    assert result["valid"] is False
    assert result["transition_reason"] == TRANSITION.RESET
