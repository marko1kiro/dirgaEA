from reference_volatility import (
    volatility_level_enum,
    VOL_LEVEL,
    quality_enum,
    VOL_QUALITY,
)


def test_level_band_hysteresis_dwell():
    seq = [1.0, 1.0, 1.6, 1.6, 2.2, 2.2]
    out = []
    ch = None
    ch_dwell = 0
    for r in seq:
        prev_state = out[-1][0] if out else VOL_LEVEL.NORMAL
        prev_dwell = out[-1][1] if out else 0
        state, dwell, ch, ch_dwell = volatility_level_enum(
            r, prev=prev_state, dwell=prev_dwell,
            challenger=ch, challenger_dwell=ch_dwell)
        out.append((state, dwell))
    states = [s for s, _ in out]
    assert states == [VOL_LEVEL.NORMAL, VOL_LEVEL.NORMAL, VOL_LEVEL.NORMAL,
                      VOL_LEVEL.HIGH, VOL_LEVEL.HIGH, VOL_LEVEL.EXTREME]


def test_quality_evidence_max():
    ev = dict(compression=0.9, expansion=0.1, chaos=0.1, shock=0.1, healthy=0.2)
    state, conf, ch, cd = quality_enum(ev)
    assert state == VOL_QUALITY.COMPRESSED


def test_quality_candidate_confidence_gap_and_dwell():
    # incumbent HEALTHY (0.8) not displaced by COMPRESSED (0.85): gap < threshold
    ev = dict(compression=0.85, expansion=0.1, chaos=0.1, shock=0.1, healthy=0.8)
    state, conf, ch, cd = quality_enum(
        ev, incumbent_state=VOL_QUALITY.HEALTHY, incumbent_conf=0.8, incumbent_dwell=0)
    assert state == VOL_QUALITY.HEALTHY


def test_quality_all_five_candidates_participate():
    ev = dict(healthy=0.95, compression=0.3, expansion=0.3, chaos=0.2, shock=0.1)
    state, conf, ch, cd = quality_enum(ev)
    assert state == VOL_QUALITY.HEALTHY
    ev2 = dict(healthy=0.1, compression=0.2, expansion=0.9, chaos=0.3, shock=0.4)
    state, conf, ch, cd = quality_enum(ev2)
    assert state == VOL_QUALITY.EXPANDING
    ev3 = dict(healthy=0.1, compression=0.2, expansion=0.2, chaos=0.85, shock=0.4)
    state, conf, ch, cd = quality_enum(ev3)
    assert state == VOL_QUALITY.CHAOTIC
    ev4 = dict(healthy=0.1, compression=0.2, expansion=0.2, chaos=0.3, shock=0.95)
    state, conf, ch, cd = quality_enum(ev4)
    assert state == VOL_QUALITY.SHOCK
