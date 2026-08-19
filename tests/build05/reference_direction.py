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


def direction_enum(score, prev=DIRECTION.NEUTRAL, dwell=0, challenger=None, challenger_dwell=0):
    """Return (state, dwell_count, challenger, challenger_dwell) for a single observation.

    challenger tracks the escalation/reversal candidate identity.
    challenger_dwell counts consecutive challenger bars for the same candidate.
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
        return (cand, 0, DIRECTION.NEUTRAL, 0)
    if prev == DIRECTION.NEUTRAL:
        return (cand, 0, DIRECTION.NEUTRAL, 0)
    if cand == prev:
        return (cand, min(dwell + 1, DWELL), DIRECTION.NEUTRAL, 0)

    cand_mag = cand.value
    prev_mag = prev.value

    challenger_trigger = (
        (cand_mag * prev_mag > 0 and abs(cand_mag) > abs(prev_mag))
        or (cand_mag * prev_mag < 0)
    )

    if challenger_trigger:
        if cand == challenger:
            challenger_dwell += 1
        else:
            challenger = cand
            challenger_dwell = 1
        if challenger_dwell >= DWELL:
            return (cand, 0, DIRECTION.NEUTRAL, 0)
        return (prev, dwell, challenger, challenger_dwell)

    return (cand, 0, DIRECTION.NEUTRAL, 0)
