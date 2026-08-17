"""Task 4b — compression rolling memory (spec section 7)."""

from reference_fusion import CompressionMemory


def test_S1_old_max_evicted_recomputed():
    cm = CompressionMemory(lookback=3)
    cm.append(0.9)   # max
    cm.append(0.3)
    cm.append(0.5)
    assert abs(cm.max() - 0.9) < 1e-12
    # evict the 0.9 (oldest) by appending a 4th observation
    cm.append(0.2)
    assert cm.contents() == [0.3, 0.5, 0.2]
    # max must be recomputed to 0.5, NOT stale 0.9
    assert abs(cm.max() - 0.5) < 1e-12


def test_S2_current_bar_excluded_from_own_breakout():
    # Prior-only: reading max() BEFORE appending the current bar excludes the current bar.
    cm = CompressionMemory(lookback=3)
    cm.append(0.2)
    cm.append(0.3)
    prior_max = cm.max()          # reads prior observations only
    assert abs(prior_max - 0.3) < 1e-12
    # now finalize the current bar (append) — its own compression must not have
    # influenced the prior_max used for scoring this bar.
    cm.append(1.0)
    assert abs(prior_max - 0.3) < 1e-12  # unchanged (the 1.0 was appended AFTER the read)
    assert abs(cm.max() - 1.0) < 1e-12   # now the new max is visible for the NEXT bar


def test_S3_window_overflow_fifo_evict():
    cm = CompressionMemory(lookback=2)
    cm.append(0.1)
    cm.append(0.2)
    cm.append(0.3)
    cm.append(0.4)
    assert cm.contents() == [0.3, 0.4]   # exactly lookback observations, oldest evicted
    assert cm.count() == 2


def test_S4_empty_window_max_zero():
    cm = CompressionMemory(lookback=4)
    assert cm.max() == 0.0
    assert cm.count() == 0
