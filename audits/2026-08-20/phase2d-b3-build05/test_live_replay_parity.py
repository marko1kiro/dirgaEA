import pytest
from reference_momentum import momentum_enum, MOMENTUM


def test_live_replay_momentum_persistence_identical():
    """Live model and replay model must produce identical state sequences.

    Sequence: STRONG → NORMAL candidate → NORMAL candidate
    Expected: bar1 STRONG persist=1, bar2 NORMAL persist=0
    """
    live_persist = [0]
    live_state = MOMENTUM.STRONG
    replay_persist = [0]
    replay_state = MOMENTUM.STRONG
    live_seq = []
    replay_seq = []

    inputs = [
        (0.65, 0.0),   # STRONG bar
        (0.50, 0.0),   # NORMAL candidate #1
        (0.50, 0.0),   # NORMAL candidate #2
    ]

    for strength, slope in inputs:
        live_state = momentum_enum(strength, slope, prev=live_state, persist=live_persist)
        live_seq.append((live_state, live_persist[0]))

        replay_state = momentum_enum(strength, slope, prev=replay_state, persist=replay_persist)
        replay_seq.append((replay_state, replay_persist[0]))

    assert live_seq == replay_seq, f"Live/replay diverged: {live_seq} vs {replay_seq}"
    assert live_seq[0] == (MOMENTUM.STRONG, 0), "Bar1: STRONG, persist=0 (high band resets)"
    assert live_seq[1] == (MOMENTUM.STRONG, 1), "Bar2: still STRONG, persist=1 (first low bar)"
    assert live_seq[2] == (MOMENTUM.NORMAL, 0), "Bar3: exit STRONG → NORMAL"


def test_live_replay_challenger_parity():
    """Live and replay challenger tracking must be identical."""
    from reference_direction import direction_enum, DIRECTION

    live = (DIRECTION.NEUTRAL, 0, DIRECTION.NEUTRAL, 0)
    replay = (DIRECTION.NEUTRAL, 0, DIRECTION.NEUTRAL, 0)
    live_seq = []
    replay_seq = []

    inputs = [0.6, 0.85, 0.85, -0.6, -0.85, -0.85]

    for s in inputs:
        live = direction_enum(s, prev=live[0], dwell=live[1],
                              challenger=live[2], challenger_dwell=live[3])
        replay = direction_enum(s, prev=replay[0], dwell=replay[1],
                                challenger=replay[2], challenger_dwell=replay[3])
        live_seq.append(live[:2])
        replay_seq.append(replay[:2])

    assert live_seq == replay_seq, f"Live/replay diverged: {live_seq} vs {replay_seq}"
