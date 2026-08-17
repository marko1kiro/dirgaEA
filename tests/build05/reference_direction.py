from enum import Enum


class DIRECTION(Enum):
    STRONG_BEAR = -2
    BEAR = -1
    NEUTRAL = 0
    BULL = 1
    STRONG_BULL = 2


BULL_COMMIT = 0.45          # score to enter BULL
STRONG_BULL_COMMIT = 0.75   # score to enter STRONG_BULL
NEUTRAL_DROP = 0.20         # |score| below this returns to NEUTRAL
DWELL = 2                   # consecutive bars at a candidate level before committing


def direction_enum(score, prev=DIRECTION.NEUTRAL, dwell=0):
    """Return (state, dwell_count) for a single closed-H1 score observation.

    score: signed continuous direction evidence in [-1, +1].
    prev:  previous committed state.
    dwell: consecutive bars already spent at the current candidate.

    Ordinal hysteresis: a stronger-magnitude candidate commits only after DWELL
    consecutive bars; a return toward NEUTRAL happens immediately when |score|
    drops below NEUTRAL_DROP. The score is always clamped to [-1, +1].
    """
    s = max(-1.0, min(1.0, score))

    if s >= STRONG_BULL_COMMIT:
        cand = DIRECTION.STRONG_BULL
    elif s >= BULL_COMMIT:
        cand = DIRECTION.BULL
    elif s <= -STRONG_BULL_COMMIT:
        cand = DIRECTION.STRONG_BEAR
    elif s <= -BULL_COMMIT:
        cand = DIRECTION.BEAR
    else:
        cand = DIRECTION.NEUTRAL

    if cand == DIRECTION.NEUTRAL:
        return (cand, 0)

    # Commit from NEUTRAL immediately (first directional observation).
    if prev == DIRECTION.NEUTRAL:
        return (cand, 0)

    if cand == prev:
        return (cand, min(dwell + 1, DWELL))

    if abs(cand.value) > abs(prev.value):
        # stronger magnitude candidate requires dwell before commit
        if dwell + 1 >= DWELL:
            return (cand, 0)
        return (prev, dwell + 1)

    # weaker candidate: immediate step down
    return (cand, 0)
