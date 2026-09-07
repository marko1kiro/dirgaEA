"""BUILD 14 reference session and news engine implementation."""

from __future__ import annotations
from enum import IntEnum
from typing import List


class SESSION_STATE(IntEnum):
    SESSION_CORE = 0
    SESSION_SECONDARY = 1
    SESSION_LOW_LIQUIDITY = 2
    SESSION_ROLLOVER = 3
    SESSION_CLOSED = 4


class NEWS_STATE(IntEnum):
    NEWS_CLEAR = 0
    NEWS_LOCK = 1
    NEWS_SHOCK = 2
    NEWS_RECOVERY = 3


def evaluate_session_state(hour: int, minute: int) -> SESSION_STATE:
    total_mins = hour * 60 + minute
    # Rollover: 23:45 (1425 mins) to 00:15 (15 mins)
    if total_mins >= 1425 or total_mins < 15:
        return SESSION_STATE.SESSION_ROLLOVER
    # Core Session: 08:00 (480 mins) to 21:00 (1260 mins)
    if 480 <= total_mins < 1260:
        return SESSION_STATE.SESSION_CORE
    # Secondary / Low Liquidity
    return SESSION_STATE.SESSION_SECONDARY


def evaluate_news_state(current_time: int, high_impact_events: List[int]) -> NEWS_STATE:
    for event_time in high_impact_events:
        diff_seconds = event_time - current_time
        # NEWS_LOCK: 30 mins before event (0 <= diff <= 1800)
        if 0 <= diff_seconds <= 1800:
            return NEWS_STATE.NEWS_LOCK
        # NEWS_SHOCK: 0 to 15 mins after event (-900 <= diff_seconds < 0)
        if -900 <= diff_seconds < 0:
            return NEWS_STATE.NEWS_SHOCK
        # NEWS_RECOVERY: 15 to 45 mins after event (-2700 <= diff_seconds < -900)
        if -2700 <= diff_seconds < -900:
            return NEWS_STATE.NEWS_RECOVERY
    return NEWS_STATE.NEWS_CLEAR
