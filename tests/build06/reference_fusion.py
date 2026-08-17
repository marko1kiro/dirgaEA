"""BUILD 06 reference fusion math — independently derived from the locked spec.

This module mirrors the pure, collapsed-domain scoring of
docs/specs/2026-08-15-build-06-regime-fusion-design.md. It consumes ONLY the
final B04/B05 collapsed outputs (never raw evidence) and produces candidate
scores plus the derived uncertainty mass.

Enum integer values intentionally mirror Types.mqh so reference and native
signatures stay comparable. No MQL5 import is used.
"""

from enum import Enum


# ---------------------------------------------------------------------------
# Upstream enum mirrors (values match Types.mqh)
# ---------------------------------------------------------------------------

class STRUCTURE(Enum):
    UNKNOWN = 0
    BULLISH_STRONG = 1
    BEARISH_STRONG = 2
    RANGE = 3
    MIXED = 4
    BULLISH_WEAK = 5
    BEARISH_WEAK = 6


class DIRECTION(Enum):
    STRONG_BEAR = 0
    BEAR = 1
    NEUTRAL = 2
    BULL = 3
    STRONG_BULL = 4


class MOMENTUM(Enum):
    EXPANDING = 0
    STRONG = 1
    NORMAL = 2
    WEAK = 3
    DECAYING = 4


class VOL_LEVEL(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    EXTREME = 3


class VOL_QUALITY(Enum):
    HEALTHY = 0
    COMPRESSED = 1
    EXPANDING = 2
    CHAOTIC = 3
    SHOCK = 4


# BUILD 06 official enums (mirror the spec sections 2.1–2.3)
class REGIME(Enum):
    TREND_BULL = 0
    TREND_BEAR = 1
    RANGE = 2
    BREAKOUT_BULL = 3
    BREAKOUT_BEAR = 4
    UNCERTAIN = 5


class REGIME_QUALITY(Enum):
    WEAK = 0
    NORMAL = 1
    STRONG = 2


class TRANSITION(Enum):
    NONE = 0
    INIT = 1
    OVERRIDE = 2
    CHALLENGE_WIN = 3
    MATURATION = 4
    FAILED_BREAKOUT = 5
    DECAY = 6
    DEGRADED = 7
    RESET = 8


# ---------------------------------------------------------------------------
# Collapsed-domain input struct
# ---------------------------------------------------------------------------

class DomainInput:
    """Final B04/B05 collapsed outputs consumed by candidate scoring.

    structure_state : STRUCTURE
    direction_score : signed [-1, +1] (DirectionResult.score)
    momentum_state  : MOMENTUM (direction-agnostic; directionalAlignment NEVER used)
    vol_level       : VOL_LEVEL
    vol_quality     : VOL_QUALITY
    compression_score : [0,1] (final B05 compressionScore)
    expansion_score   : [0,1] (final B05 expansionScore)
    break_bull_score  : [0,1] collapsed break recency for bull (S_breakBull)
    break_bear_score  : [0,1] collapsed break recency for bear (S_breakBear)
    """
    def __init__(self, structure_state, direction_score, momentum_state,
                 vol_level, vol_quality, compression_score=0.0,
                 expansion_score=0.0, break_bull_score=0.0, break_bear_score=0.0,
                 directional_alignment=0.0):
        self.structure_state = structure_state
        self.direction_score = direction_score
        self.momentum_state = momentum_state
        self.vol_level = vol_level
        self.vol_quality = vol_quality
        self.compression_score = compression_score
        self.expansion_score = expansion_score
        self.break_bull_score = break_bull_score
        self.break_bear_score = break_bear_score
        # DIAGNOSTIC-ONLY mirror (section 4.8 / 14): never enters scoring/quality/mass.
        self.directional_alignment = directional_alignment


# ---------------------------------------------------------------------------
# Fixed v1 weights (section 16)
# ---------------------------------------------------------------------------

# TREND: S/D/M/V/Q
W_TREND = (0.35, 0.30, 0.15, 0.10, 0.10)
# RANGE: S/D/M/V/Q
W_RANGE = (0.40, 0.25, 0.15, 0.10, 0.10)
# BREAKOUT: S/Q/M/D/V
W_BREAKOUT = (0.30, 0.25, 0.20, 0.15, 0.10)

DIR_COMMIT = 0.45


def _clamp01(x):
    return max(0.0, min(1.0, x))


# ---------------------------------------------------------------------------
# Structure contributions (section 4.3 / 4.4 / 4.5 / 4.6)
# ---------------------------------------------------------------------------

_S_BULLISH_TREND = {
    STRUCTURE.BULLISH_STRONG: 1.0,
    STRUCTURE.BULLISH_WEAK: 0.6,
    STRUCTURE.MIXED: 0.25,
}

_S_BEARISH_TREND = {
    STRUCTURE.BEARISH_STRONG: 1.0,
    STRUCTURE.BEARISH_WEAK: 0.6,
    STRUCTURE.MIXED: 0.25,
}

_S_RANGE = {
    STRUCTURE.RANGE: 1.0,
    STRUCTURE.MIXED: 0.5,
}


def _s_bullish_trend(state):
    return _S_BULLISH_TREND.get(state, 0.0)


def _s_bearish_trend(state):
    return _S_BEARISH_TREND.get(state, 0.0)


def _s_range(state):
    return _S_RANGE.get(state, 0.0)


# ---------------------------------------------------------------------------
# Direction contributions (section 4.3 / 4.4 / 4.5)
# ---------------------------------------------------------------------------

def _d_bullish(score):
    return _clamp01(score)


def _d_bearish(score):
    return _clamp01(-score)


def _d_neutral(score):
    return _clamp01(1.0 - abs(score))


# ---------------------------------------------------------------------------
# Momentum contributions (direction-agnostic — section 4.8)
# ---------------------------------------------------------------------------

# M_supportive (TREND) and M_nonExpansion (RANGE) and M_expanding (BREAKOUT)
_M_SUPPORTIVE = {
    MOMENTUM.EXPANDING: 1.0,
    MOMENTUM.STRONG: 1.0,
    MOMENTUM.NORMAL: 0.6,
    MOMENTUM.WEAK: 0.3,
    MOMENTUM.DECAYING: 0.0,
}

_M_NON_EXPANSION = {
    MOMENTUM.NORMAL: 1.0,
    MOMENTUM.WEAK: 0.8,
    MOMENTUM.DECAYING: 0.5,
    MOMENTUM.STRONG: 0.3,
    MOMENTUM.EXPANDING: 0.1,
}

_M_EXPANDING = {
    MOMENTUM.EXPANDING: 1.0,
    MOMENTUM.STRONG: 0.7,
    MOMENTUM.NORMAL: 0.3,
    MOMENTUM.WEAK: 0.1,
    MOMENTUM.DECAYING: 0.0,
}


def _m_supportive(state):
    return _M_SUPPORTIVE.get(state, 0.0)


def _m_non_expansion(state):
    return _M_NON_EXPANSION.get(state, 0.0)


def _m_expanding(state):
    return _M_EXPANDING.get(state, 0.0)


# ---------------------------------------------------------------------------
# Volatility Level contributions (section 4.3 / 4.5)
# ---------------------------------------------------------------------------

_V_TREND_SUITABLE = {
    VOL_LEVEL.NORMAL: 1.0,
    VOL_LEVEL.HIGH: 1.0,
    VOL_LEVEL.LOW: 0.5,
    VOL_LEVEL.EXTREME: 0.3,
}

_V_RANGE_SUITABLE = {
    VOL_LEVEL.LOW: 1.0,
    VOL_LEVEL.NORMAL: 0.7,
    VOL_LEVEL.HIGH: 0.4,
    VOL_LEVEL.EXTREME: 0.1,
}


def _v_trend_suitable(level):
    return _V_TREND_SUITABLE.get(level, 0.0)


def _v_range_suitable(level):
    return _V_RANGE_SUITABLE.get(level, 0.0)


# ---------------------------------------------------------------------------
# Volatility Quality contributions (section 4.3 / 4.5 / 4.6)
# ---------------------------------------------------------------------------

_Q_CLEAN = {
    VOL_QUALITY.HEALTHY: 1.0,
    VOL_QUALITY.EXPANDING: 0.7,
    VOL_QUALITY.COMPRESSED: 0.4,
    VOL_QUALITY.SHOCK: 0.2,
    VOL_QUALITY.CHAOTIC: 0.15,
}

_Q_TWO_SIDED = {
    VOL_QUALITY.COMPRESSED: 1.0,
    VOL_QUALITY.HEALTHY: 0.7,
    VOL_QUALITY.EXPANDING: 0.3,
    VOL_QUALITY.CHAOTIC: 0.0,
    VOL_QUALITY.SHOCK: 0.0,
}


def _q_clean(q):
    return _Q_CLEAN.get(q, 0.0)


def _q_two_sided(q):
    return _Q_TWO_SIDED.get(q, 0.0)


# ---------------------------------------------------------------------------
# Candidate scoring (sections 4.3 – 4.6)
# ---------------------------------------------------------------------------

def compute_candidate_scores(d, compression_context=None):
    """Return a dict of the five real candidate scores for DomainInput d.

    `compression_context` is the PRIOR compression context (Q_compressionContext from
    the rolling memory, section 7); when None it falls back to `d.compression_score`
    (used by simple unit tests that pass the prior context directly).
    """
    ctx = d.compression_score if compression_context is None else compression_context
    d_bull = _d_bullish(d.direction_score)
    d_bear = _d_bearish(d.direction_score)
    d_neutral = _d_neutral(d.direction_score)

    s_bull = _s_bullish_trend(d.structure_state)
    s_bear = _s_bearish_trend(d.structure_state)
    s_range = _s_range(d.structure_state)

    m_supportive = _m_supportive(d.momentum_state)
    m_non_expansion = _m_non_expansion(d.momentum_state)
    m_expanding = _m_expanding(d.momentum_state)

    v_trend = _v_trend_suitable(d.vol_level)
    v_range = _v_range_suitable(d.vol_level)

    q_clean = _q_clean(d.vol_quality)
    q_two_sided = _q_two_sided(d.vol_quality)

    # TREND_BULL (4.3)
    score_trend_bull = (
        W_TREND[0] * s_bull
        + W_TREND[1] * d_bull
        + W_TREND[2] * m_supportive
        + W_TREND[3] * v_trend
        + W_TREND[4] * q_clean
    )

    # TREND_BEAR (4.4)
    score_trend_bear = (
        W_TREND[0] * s_bear
        + W_TREND[1] * d_bear
        + W_TREND[2] * m_supportive
        + W_TREND[3] * v_trend
        + W_TREND[4] * q_clean
    )

    # RANGE (4.5)
    score_range = (
        W_RANGE[0] * s_range
        + W_RANGE[1] * d_neutral
        + W_RANGE[2] * m_non_expansion
        + W_RANGE[3] * v_range
        + W_RANGE[4] * q_two_sided
    )

    # BREAKOUT_BULL (4.6)
    score_breakout_bull = (
        W_BREAKOUT[0] * d.break_bull_score
        + W_BREAKOUT[1] * ctx              # Q_compressionContext = prior compression
        + W_BREAKOUT[2] * m_expanding
        + W_BREAKOUT[3] * d_bull
        + W_BREAKOUT[4] * d.expansion_score     # V_expanding = expansionScore, NOT level==HIGH
    )

    # BREAKOUT_BEAR (4.6)
    score_breakout_bear = (
        W_BREAKOUT[0] * d.break_bear_score
        + W_BREAKOUT[1] * ctx
        + W_BREAKOUT[2] * m_expanding
        + W_BREAKOUT[3] * d_bear
        + W_BREAKOUT[4] * d.expansion_score
    )

    return {
        "trend_bull": score_trend_bull,
        "trend_bear": score_trend_bear,
        "range": score_range,
        "breakout_bull": score_breakout_bull,
        "breakout_bear": score_breakout_bear,
    }


# ---------------------------------------------------------------------------
# UNCERTAIN mass (section 4.7) + confidence (6.1) + quality (6.2)
# ---------------------------------------------------------------------------

BALANCED_EVIDENCE_SPAN = 0.20
CONFIDENCE_MARGIN_SPAN = 0.20
UNCERTAIN_WEAK_WINNER_THRESHOLD = 0.30

# Canonical candidate order for tie resolution in top1/top2 (section 4.7.3)
_CANDIDATE_ORDER = ["trend_bull", "trend_bear", "range", "breakout_bull", "breakout_bear"]


def _structural_direction_conflict(structure_state, direction_score):
    bull_struct = structure_state in (STRUCTURE.BULLISH_STRONG, STRUCTURE.BULLISH_WEAK)
    bear_struct = structure_state in (STRUCTURE.BEARISH_STRONG, STRUCTURE.BEARISH_WEAK)
    bull_dir = direction_score > +DIR_COMMIT
    bear_dir = direction_score < -DIR_COMMIT
    return 1.0 if (bull_struct and bear_dir) or (bear_struct and bull_dir) else 0.0


def _chaos_mass(vol_quality, direction_score):
    committed = abs(direction_score) >= DIR_COMMIT
    if vol_quality == VOL_QUALITY.CHAOTIC and not committed:
        return 1.00
    if vol_quality == VOL_QUALITY.CHAOTIC and committed:
        return 0.45
    if vol_quality == VOL_QUALITY.SHOCK:
        return 0.50
    return 0.00


def _top1_top2(scores):
    """Return (top1, top2) over the five real candidates, ties broken by fixed order."""
    ordered = [_clamp01(scores[k]) for k in _CANDIDATE_ORDER]
    top1 = max(ordered)
    # second-highest distinct value; among equals the fixed order resolves top1 vs top2
    remaining = [v for v in ordered]
    remaining.remove(top1)
    top2 = max(remaining) if remaining else top1
    return top1, top2


def _balanced_evidence(scores):
    top1, top2 = _top1_top2(scores)
    margin = top1 - top2
    return _clamp01(1.0 - margin / BALANCED_EVIDENCE_SPAN)


def _weak_winner_mass(scores, threshold=UNCERTAIN_WEAK_WINNER_THRESHOLD):
    top1, _ = _top1_top2(scores)
    return _clamp01(1.0 - top1 / threshold)


def _degradation_mass(evidence_completeness):
    return _clamp01(1.0 - evidence_completeness)


def compute_uncertain_mass(scores, structure_state, vol_quality, direction_score,
                           evidence_completeness=1.0):
    """Return scoreUncertain (derived mass) per section 4.7."""
    return _clamp01(max(
        _structural_direction_conflict(structure_state, direction_score),
        _chaos_mass(vol_quality, direction_score),
        _balanced_evidence(scores),
        _weak_winner_mass(scores),
        _degradation_mass(evidence_completeness),
    ))


def compute_confidence(scores, reported_regime, score_uncertain, evidence_completeness=1.0):
    """Return confidence for the final reported regime per section 6.1."""
    if reported_regime == REGIME.UNCERTAIN:
        return _clamp01(score_uncertain)

    key = {
        REGIME.TREND_BULL: "trend_bull",
        REGIME.TREND_BEAR: "trend_bear",
        REGIME.RANGE: "range",
        REGIME.BREAKOUT_BULL: "breakout_bull",
        REGIME.BREAKOUT_BEAR: "breakout_bear",
    }[reported_regime]

    score_r = _clamp01(scores[key])
    # best alternative = max of the OTHER four real candidates
    best_alt = max(_clamp01(scores[k]) for k in _CANDIDATE_ORDER if k != key)
    margin = score_r - best_alt
    margin_factor = _clamp01(margin / CONFIDENCE_MARGIN_SPAN)
    return _clamp01(score_r * (0.70 + 0.30 * margin_factor) * evidence_completeness)


# Quality mappings not already defined for scoring
_Q_BREAKOUT_CLEAN = {
    VOL_QUALITY.HEALTHY: 1.0,
    VOL_QUALITY.EXPANDING: 1.0,
    VOL_QUALITY.COMPRESSED: 0.60,
    VOL_QUALITY.CHAOTIC: 0.10,
    VOL_QUALITY.SHOCK: 0.10,
}

_Q_GENERAL = {
    VOL_QUALITY.HEALTHY: 1.0,
    VOL_QUALITY.EXPANDING: 0.80,
    VOL_QUALITY.COMPRESSED: 0.70,
    VOL_QUALITY.CHAOTIC: 0.10,
    VOL_QUALITY.SHOCK: 0.00,
}

_V_GENERAL = {
    VOL_LEVEL.NORMAL: 1.0,
    VOL_LEVEL.LOW: 0.70,
    VOL_LEVEL.HIGH: 0.70,
    VOL_LEVEL.EXTREME: 0.20,
}


def compute_quality_evidence(reported_regime, d, evidence_completeness=1.0):
    """Return qualityEvidence for the final reported regime (section 6.2)."""
    if reported_regime == REGIME.UNCERTAIN:
        q_general = _Q_GENERAL.get(d.vol_quality, 0.0)
        v_general = _V_GENERAL.get(d.vol_level, 0.0)
        return _clamp01(0.55 * q_general + 0.25 * v_general + 0.20 * evidence_completeness)

    if reported_regime in (REGIME.TREND_BULL, REGIME.TREND_BEAR):
        q_clean = _q_clean(d.vol_quality)
        v_trend = _v_trend_suitable(d.vol_level)
        m_supportive = _m_supportive(d.momentum_state)
        return _clamp01(
            0.35 * q_clean + 0.25 * v_trend + 0.25 * m_supportive + 0.15 * evidence_completeness
        )

    if reported_regime == REGIME.RANGE:
        q_two = _q_two_sided(d.vol_quality)
        v_range = _v_range_suitable(d.vol_level)
        m_non_exp = _m_non_expansion(d.momentum_state)
        return _clamp01(
            0.35 * q_two + 0.25 * v_range + 0.25 * m_non_exp + 0.15 * evidence_completeness
        )

    # BREAKOUT_BULL / BREAKOUT_BEAR
    q_breakout = _Q_BREAKOUT_CLEAN.get(d.vol_quality, 0.0)
    m_expanding = _m_expanding(d.momentum_state)
    expansion_evidence = _clamp01(d.expansion_score)
    return _clamp01(
        0.30 * q_breakout + 0.30 * expansion_evidence + 0.25 * m_expanding
        + 0.15 * evidence_completeness
    )


def classify_quality(quality_evidence):
    """Map qualityEvidence -> REGIME_QUALITY (section 6.2.5, inclusive bounds)."""
    if quality_evidence >= 0.75:
        return REGIME_QUALITY.STRONG
    if quality_evidence >= 0.45:
        return REGIME_QUALITY.NORMAL
    return REGIME_QUALITY.WEAK


def compute_quality(reported_regime, d, evidence_completeness=1.0):
    """Return (qualityEvidence, REGIME_QUALITY) for the final reported regime.

    Critical-invalid convention (6.2.6) is applied by the caller when valid=False:
    caller should force qualityEvidence=0.0, quality=WEAK.
    """
    qe = compute_quality_evidence(reported_regime, d, evidence_completeness)
    return qe, classify_quality(qe)


# ---------------------------------------------------------------------------
# Temporal compression memory (section 7) — bounded rolling window
# ---------------------------------------------------------------------------

class CompressionMemory:
    """Bounded rolling FIFO of the last `lookback` finalized compression observations.

    Observable behavior (section 7): max is recomputed on demand (never cached), FIFO
    eviction keeps exactly `lookback` observations, empty -> 0.0. The MQL5 counterpart
    uses a dynamically-sized ring array; this reference uses a chronological list with
    identical observable semantics.
    """

    def __init__(self, lookback=4):
        self.lookback = lookback
        self.obs = []          # chronological, oldest -> newest

    def append(self, value):
        self.obs.append(value)
        if len(self.obs) > self.lookback:
            self.obs.pop(0)    # FIFO evict oldest

    def max(self):
        return max(self.obs) if self.obs else 0.0

    def contents(self):
        return list(self.obs)

    def count(self):
        return len(self.obs)


# ---------------------------------------------------------------------------
# Hysteresis / persistence (section 8)
# ---------------------------------------------------------------------------

class Params:
    def __init__(self, regime_dwell=2, challenger_gap=0.10, uncertain_veto=0.55,
                 uncertain_exit_threshold=0.45, uncertain_exit_dwell=1,
                 tie_epsilon=1e-6, weak_winner_threshold=0.30,
                 breakout_maturation_min_bars=2, breakout_max_age_bars=6,
                 breakout_lookback_bars=4):
        self.regime_dwell = regime_dwell
        self.challenger_gap = challenger_gap
        self.uncertain_veto = uncertain_veto
        self.uncertain_exit_threshold = uncertain_exit_threshold
        self.uncertain_exit_dwell = uncertain_exit_dwell
        self.tie_epsilon = tie_epsilon
        self.weak_winner_threshold = weak_winner_threshold
        self.breakout_maturation_min_bars = breakout_maturation_min_bars
        self.breakout_max_age_bars = breakout_max_age_bars
        self.breakout_lookback_bars = breakout_lookback_bars


class PersistentState:
    def __init__(self):
        self.regime = REGIME.UNCERTAIN            # official incumbent
        self.previous_regime = REGIME.UNCERTAIN
        self.regime_age_bars = 0
        self.pending_candidate = None             # REGIME or None (explicit challenger identity)
        self.candidate_age_bars = 0
        self.initialized = False                  # first valid fusion => INIT


def _argmax_candidate(scores):
    """Return the winning candidate key among the five real candidates (fixed-order tie-break)."""
    return max(_CANDIDATE_ORDER, key=lambda k: scores[k])


def _effective_tie(scores, params):
    top1, top2 = _top1_top2(scores)
    return (top1 - top2) <= params.tie_epsilon


def _regime_key(regime):
    return {
        REGIME.TREND_BULL: "trend_bull",
        REGIME.TREND_BEAR: "trend_bear",
        REGIME.RANGE: "range",
        REGIME.BREAKOUT_BULL: "breakout_bull",
        REGIME.BREAKOUT_BEAR: "breakout_bear",
    }.get(regime)


def classify_regime(d, state, params, evidence_completeness=1.0, valid=True,
                    compression_context=None):
    """Advance the persistent state by one closed-H1 fusion and return a result dict.

    Hysteresis core (section 8) with HARD vs SOFT uncertainty split:
      - HARD veto (structural-direction conflict, uncommitted CHAOTIC) bypasses dwell.
      - SOFT uncertainty (scoreUncertain >= UncertainVeto from balancedEvidence /
        weakWinnerMass / chaosMass(SHOCK, committed CHAOTIC) / degradationMass) becomes
        a special derived UNCERTAIN challenger subject to gap + dwell, never a sixth
        symmetric candidate.

    Breakout maturation/aging (sections 9-10) is handled by `update_fusion`, not here.
    Mutates `state` in place; returns a RegimeResult-like dict.
    """
    scores = compute_candidate_scores(d, compression_context)
    su = compute_uncertain_mass(scores, d.structure_state, d.vol_quality,
                                d.direction_score, evidence_completeness)

    prev = state.regime
    state.previous_regime = prev

    # --- critical-invalid short-circuit (section 11.2 / 6.2.6): hard, reason RESET ---
    if not valid:
        state.regime = REGIME.UNCERTAIN
        state.regime_age_bars = 1
        state.pending_candidate = None
        state.candidate_age_bars = 0
        return _result(state, d, scores, su, TRANSITION.RESET, 0.0,
                       evidence_completeness=0.0, valid=False)

    # --- HARD uncertainty veto (section 5 rules 1 & 2): immediate UNCERTAIN, no dwell ---
    if _hard_uncertain_veto(d):
        state.regime = REGIME.UNCERTAIN
        state.regime_age_bars = 1
        state.pending_candidate = None
        state.candidate_age_bars = 0
        return _result(state, d, scores, su, TRANSITION.OVERRIDE, su,
                       evidence_completeness=evidence_completeness, valid=True,
                       challenger_score=su, incumbent_score=scores.get(_regime_key(prev), 0.0))

    winner_key = _argmax_candidate(scores)
    winner_regime = {
        "trend_bull": REGIME.TREND_BULL,
        "trend_bear": REGIME.TREND_BEAR,
        "range": REGIME.RANGE,
        "breakout_bull": REGIME.BREAKOUT_BULL,
        "breakout_bear": REGIME.BREAKOUT_BEAR,
    }[winner_key]
    winner_score = scores[winner_key]

    # --- tie handling (section 8.5) ---
    tie = _effective_tie(scores, params)
    if tie:
        if state.regime not in (None, REGIME.UNCERTAIN):
            # retain valid incumbent
            winner_regime = state.regime
            winner_score = scores[_regime_key(state.regime)]
        else:
            # no valid incumbent => UNCERTAIN
            winner_regime = REGIME.UNCERTAIN

    incumbent = state.regime

    # --- bootstrap: first valid fusion (section 8.3 / spec patch) ---
    if not state.initialized:
        state.initialized = True
        state.regime_age_bars = 1
        state.pending_candidate = None
        state.candidate_age_bars = 0
        if winner_regime == REGIME.UNCERTAIN:
            # effective real-candidate tie with no incumbent => UNCERTAIN
            state.regime = REGIME.UNCERTAIN
            return _result(state, d, scores, su, TRANSITION.INIT, winner_score,
                           evidence_completeness=evidence_completeness, valid=True,
                           challenger_score=su, incumbent_score=0.0)
        if su >= params.uncertain_veto:
            # soft uncertainty at bootstrap (no incumbent to protect) => UNCERTAIN
            state.regime = REGIME.UNCERTAIN
            return _result(state, d, scores, su, TRANSITION.INIT, winner_score,
                           evidence_completeness=evidence_completeness, valid=True,
                           challenger_score=su, incumbent_score=0.0)
        state.regime = winner_regime
        return _result(state, d, scores, su, TRANSITION.INIT, winner_score,
                       evidence_completeness=evidence_completeness, valid=True,
                       challenger_score=winner_score, incumbent_score=winner_score)

    # --- incumbent == UNCERTAIN: exit via UncertainExitThreshold + UncertainExitDwell ---
    if incumbent == REGIME.UNCERTAIN:
        # track challenger identity (1-based entry)
        if state.pending_candidate == winner_regime:
            state.candidate_age_bars += 1
        else:
            state.pending_candidate = winner_regime
            state.candidate_age_bars = 1

        if winner_score >= params.uncertain_exit_threshold and \
           state.candidate_age_bars >= params.uncertain_exit_dwell:
            state.regime = winner_regime
            state.regime_age_bars = 1
            state.pending_candidate = None
            state.candidate_age_bars = 0
            return _result(state, d, scores, su, TRANSITION.CHALLENGE_WIN, winner_score,
                           evidence_completeness=evidence_completeness, valid=True,
                           challenger_score=winner_score, incumbent_score=0.0)
        # keep UNCERTAIN
        state.regime = REGIME.UNCERTAIN
        return _result(state, d, scores, su, TRANSITION.NONE, winner_score,
                       evidence_completeness=evidence_completeness, valid=True,
                       challenger_score=winner_score, incumbent_score=0.0)

    # --- established non-BREAKOUT incumbent ---
    # Determine the challenger for this bar. SOFT uncertainty evidence makes UNCERTAIN
    # a special derived challenger (NOT a sixth symmetric candidate).
    soft_uncertain = su >= params.uncertain_veto
    if soft_uncertain:
        challenger_regime = REGIME.UNCERTAIN
        challenger_score = su
    else:
        challenger_regime = winner_regime
        challenger_score = winner_score

    incumbent_score = scores[_regime_key(incumbent)]   # recomputed this bar

    if challenger_regime == incumbent:
        # winner == incumbent and no soft uncertainty: incumbent survives, ages.
        state.pending_candidate = None
        state.candidate_age_bars = 0
        state.regime_age_bars += 1
        state.regime = incumbent
        return _result(state, d, scores, su, TRANSITION.NONE, winner_score,
                       evidence_completeness=evidence_completeness, valid=True,
                       challenger_score=challenger_score,
                       incumbent_score=incumbent_score)

    # challenger (real candidate or derived UNCERTAIN) identity tracking (1-based entry)
    if state.pending_candidate == challenger_regime:
        state.candidate_age_bars += 1
    else:
        state.pending_candidate = challenger_regime
        state.candidate_age_bars = 1

    gap = challenger_score - incumbent_score
    if gap >= params.challenger_gap and state.candidate_age_bars >= params.regime_dwell:
        state.regime = challenger_regime
        state.regime_age_bars = 1
        state.pending_candidate = None
        state.candidate_age_bars = 0
        return _result(state, d, scores, su, TRANSITION.CHALLENGE_WIN, winner_score,
                       evidence_completeness=evidence_completeness, valid=True,
                       challenger_score=challenger_score, incumbent_score=incumbent_score)

    # keep incumbent: it survives another bar, so it ages.
    state.regime = incumbent
    state.regime_age_bars += 1
    return _result(state, d, scores, su, TRANSITION.NONE, winner_score,
                   evidence_completeness=evidence_completeness, valid=True,
                   challenger_score=challenger_score, incumbent_score=incumbent_score)


# ---------------------------------------------------------------------------
# Degradation / completeness (section 11) + signature (section 14)
# ---------------------------------------------------------------------------

DEGRADED_NONE = 0
DEGRADED_STRUCTURE = 1
DEGRADED_DIRECTION = 2
DEGRADED_MOMENTUM = 4
DEGRADED_VOLATILITY = 8

_DOMAIN_BITS = (DEGRADED_STRUCTURE, DEGRADED_DIRECTION,
                DEGRADED_MOMENTUM, DEGRADED_VOLATILITY)


def evidence_completeness(degraded_domains=0):
    """Return evidenceCompleteness = 0.25 per valid B06 domain (section 11.1).

    ADX helper degradation is NOT a domain bit and does NOT reduce completeness.
    """
    return 0.25 * sum(1 for bit in _DOMAIN_BITS if not (degraded_domains & bit))


def fnv1a_64(s):
    """FNV-1a 64-bit, matching the MQL5 implementation (offset 14695981039346656037,
    prime 1099511628211) used by B04D3/B05D1."""
    h = 14695981039346656037
    for ch in s:
        h ^= ord(ch)
        h = (h * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h


def b06_signature(result, state, compression_memory, directional_alignment=0.0):
    """Return 'B06D1:<hex>' FNV-1a 64-bit over a canonical string of finalized fusion
    state INCLUDING all behavior-affecting persistent state (section 14).

    Hashes: regime/quality/confidence/valid/ages, pending candidate + dwell, the
    chronological compression FIFO contents+count, and the momentumDirectionalAlignment
    diagnostic mirror — so two runs with identical visible results but different hidden
    state produce different signatures.
    """
    scores = result["scores"]
    cm = compression_memory.contents()
    parts = [
        "v=B06D1",
        "regime=%d" % result["regime"].value,
        "quality=%d" % result["quality"].value,
        "confidence=%s" % _dec(result["confidence"]),
        "valid=%d" % (1 if result["valid"] else 0),
        "age=%d" % result["regime_age_bars"],
        "prev=%d" % result["previous_regime"].value,
        "candAge=%d" % result["candidate_age_bars"],
        "pend=%s" % ("NONE" if result["pending_candidate"] is None
                     else str(result["pending_candidate"].value)),
        "tx=%d" % result["transition_reason"].value,
        "su=%s" % _dec(result["score_uncertain"]),
        "sTB=%s" % _dec(scores["trend_bull"]),
        "sTBe=%s" % _dec(scores["trend_bear"]),
        "sR=%s" % _dec(scores["range"]),
        "sBB=%s" % _dec(scores["breakout_bull"]),
        "sBBe=%s" % _dec(scores["breakout_bear"]),
        "mda=%s" % _dec(directional_alignment),
        "cm_count=%d" % len(cm),
        "cm_obs=%s" % ",".join(_dec(v) for v in cm),
    ]
    canonical = ";".join(parts) + ";"
    return "B06D1:%016X" % fnv1a_64(canonical)


def _dec(x):
    """Serialize a float deterministically (mirrors DoubleToString(...,15))."""
    return "%.15f" % x


# ---------------------------------------------------------------------------
# Breakout maturation / aging / handoff (sections 9-10)
# ---------------------------------------------------------------------------

def _sustained_bull(d):
    return (d.structure_state in (STRUCTURE.BULLISH_STRONG, STRUCTURE.BULLISH_WEAK)
            and d.direction_score >= DIR_COMMIT
            and d.momentum_state != MOMENTUM.DECAYING)


def _sustained_bear(d):
    return (d.structure_state in (STRUCTURE.BEARISH_STRONG, STRUCTURE.BEARISH_WEAK)
            and d.direction_score <= -DIR_COMMIT
            and d.momentum_state != MOMENTUM.DECAYING)


def _opposing_structure(regime, d):
    if regime == REGIME.BREAKOUT_BULL:
        return d.structure_state in (STRUCTURE.BEARISH_STRONG, STRUCTURE.BEARISH_WEAK)
    if regime == REGIME.BREAKOUT_BEAR:
        return d.structure_state in (STRUCTURE.BULLISH_STRONG, STRUCTURE.BULLISH_WEAK)
    return False


def _opposing_direction(regime, d):
    """Explicit breakout failure on clearly opposing committed direction (section 10)."""
    if regime == REGIME.BREAKOUT_BULL:
        return d.direction_score <= -DIR_COMMIT
    if regime == REGIME.BREAKOUT_BEAR:
        return d.direction_score >= +DIR_COMMIT
    return False


def _hard_uncertain_veto(d):
    """HARD uncertainty veto (immediate UNCERTAIN, no dwell).

    Only three sources bypass hysteresis (section 5 rules 1 & 2 + critical-invalid,
    where critical-invalid is handled separately as RESET):
      1. structuralDirectionConflict >= 1.0
      2. volatilityQuality == CHAOTIC AND |directionScore| < DIR_COMMIT

    SHOCK, committed-direction CHAOTIC (chaosMass=0.45), balancedEvidence,
    weakWinnerMass, and non-critical degradation are SOFT and do NOT hard-veto.
    """
    if _structural_direction_conflict(d.structure_state, d.direction_score) >= 1.0:
        return True
    if d.vol_quality == VOL_QUALITY.CHAOTIC and abs(d.direction_score) < DIR_COMMIT:
        return True
    return False


def _breakout_step(d, state, params, scores, su, evidence_completeness):
    """Handle one bar for a BREAKOUT_BULL/BEAR incumbent (sections 9-10).

    Breakout incumbents follow a dedicated mature/fail/stay lifecycle and are NOT
    subject to the generic challenger CHALLENGE_WIN flip (a breakout cannot be flipped
    directly to an unrelated regime; it must mature to TREND or fail to UNCERTAIN).

    Returns a result dict. Mutates state in place.
    """
    entering = state.regime
    bull = entering == REGIME.BREAKOUT_BULL

    def build(new_regime, reason):
        state.regime = new_regime
        state.previous_regime = entering
        qe, quality = compute_quality(new_regime, d, evidence_completeness)
        confidence = compute_confidence(scores, new_regime, su, evidence_completeness)
        return {
            "regime": new_regime,
            "quality": quality,
            "quality_evidence": qe,
            "confidence": confidence,
            "valid": True,
            "previous_regime": entering,
            "regime_age_bars": state.regime_age_bars,
            "transition_reason": reason,
            "pending_candidate": state.pending_candidate,
            "candidate_age_bars": state.candidate_age_bars,
            "challenger_confidence": None,
            "incumbent_confidence": None,
            "score_uncertain": su,
            "scores": dict(scores),
        }

    # Trigger 1: immediate failure (section 10.1), checked BEFORE the bar is "spent".
    # Hard opposing evidence: opposing structure, opposing committed direction, or a
    # HARD uncertainty veto (structural-direction conflict / uncommitted CHAOTIC).
    if (_opposing_structure(entering, d)
            or _opposing_direction(entering, d)
            or _hard_uncertain_veto(d)):
        state.regime_age_bars = 1
        state.pending_candidate = None
        state.candidate_age_bars = 0
        return build(REGIME.UNCERTAIN, TRANSITION.FAILED_BREAKOUT)

    # Spend this bar: age counts completed bars including the entry bar (section 8.0).
    state.regime_age_bars += 1

    # Maturation (section 9): eligible at age >= min with sustained evidence.
    sustained = _sustained_bull(d) if bull else _sustained_bear(d)
    if state.regime_age_bars >= params.breakout_maturation_min_bars and sustained:
        state.regime_age_bars = 1
        state.pending_candidate = None
        state.candidate_age_bars = 0
        return build(REGIME.TREND_BULL if bull else REGIME.TREND_BEAR, TRANSITION.MATURATION)

    # Trigger 2: age cap (section 10.2), checked at age >= max.
    if state.regime_age_bars >= params.breakout_max_age_bars:
        state.regime_age_bars = 1
        state.pending_candidate = None
        state.candidate_age_bars = 0
        return build(REGIME.UNCERTAIN, TRANSITION.FAILED_BREAKOUT)

    # still a breakout: incumbent unchanged (age already incremented)
    return build(entering, TRANSITION.NONE)


def update_fusion(d, state, params, evidence_completeness=1.0, valid=True,
                  compression_memory=None):
    """Full per-bar fusion (sections 8-10).

    Canonical entry point for a closed-H1 update and for cold-start replay.
    Mutates `state` in place and returns the result dict.

    If `compression_memory` is provided (a CompressionMemory), the breakout scoring reads
    the PRIOR compression max from it, and `d.compression_score` (the current bar's raw
    B05 compression) is appended to the memory AFTER this bar's fusion finalizes
    (section 7.1 prior-only rule).
    """
    ctx = compression_memory.max() if compression_memory is not None else None

    scores = compute_candidate_scores(d, ctx)
    su = compute_uncertain_mass(scores, d.structure_state, d.vol_quality,
                                d.direction_score, evidence_completeness)

    entering = state.regime

    # Breakout incumbents take a dedicated lifecycle path (no generic challenger flip).
    if entering in (REGIME.BREAKOUT_BULL, REGIME.BREAKOUT_BEAR) and valid:
        result = _breakout_step(d, state, params, scores, su, evidence_completeness)
    else:
        # Otherwise, delegate to the generic hysteresis core.
        result = classify_regime(d, state, params, evidence_completeness, valid, ctx)

    # Append the current bar's compression AFTER fusion finalizes (prior-only).
    if compression_memory is not None:
        compression_memory.append(d.compression_score)

    return result


def _result(state, d, scores, su, reason, winner_score, evidence_completeness, valid,
            challenger_score=None, incumbent_score=None):
    """Build the RegimeResult-like dict."""
    regime = state.regime
    qe, quality = compute_quality(regime, d, evidence_completeness)
    if not valid:
        qe = 0.0
        quality = REGIME_QUALITY.WEAK
    confidence = compute_confidence(scores, regime, su, evidence_completeness)
    if not valid:
        confidence = 0.0
    return {
        "regime": regime,
        "quality": quality,
        "quality_evidence": qe,
        "confidence": confidence,
        "valid": valid,
        "previous_regime": state.previous_regime,
        "regime_age_bars": state.regime_age_bars,
        "transition_reason": reason,
        "pending_candidate": state.pending_candidate,
        "candidate_age_bars": state.candidate_age_bars,
        "challenger_confidence": challenger_score,
        "incumbent_confidence": incumbent_score,
        "score_uncertain": su,
        "scores": dict(scores),
    }
